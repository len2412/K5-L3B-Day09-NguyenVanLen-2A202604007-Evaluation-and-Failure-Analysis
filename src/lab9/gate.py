"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    def non_finite(value: object) -> bool:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return not math.isfinite(value)
        if isinstance(value, dict):
            return any(non_finite(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(non_finite(v) for v in value)
        return False

    def report_rows(report: dict, label: str) -> list[dict]:
        rows = report.get("rows")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            problems.append(f"{label} rows missing or malformed")
            return []
        return rows

    pr_rows = report_rows(pr, "PR")
    base_rows = report_rows(base, "baseline")
    metrics = pr.get("metrics")
    if not isinstance(metrics, dict):
        problems.append("PR metrics missing or malformed")
        metrics = {}
    for mid, value in metrics.items():
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"metric {mid} is missing or non-numeric")
        if non_finite(value):
            problems.append(f"metric {mid} is non-finite")

    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures is non-empty")

    manifest = pr.get("manifest")
    if not isinstance(manifest, dict):
        problems.append("PR manifest missing or malformed")
        manifest = {}
    item_count, seeds = manifest.get("items"), manifest.get("seeds")
    if not isinstance(item_count, int) or isinstance(item_count, bool) or item_count < 0:
        problems.append("PR manifest items missing or invalid")
    if not isinstance(seeds, list) or any(not isinstance(s, int) or isinstance(s, bool) for s in seeds):
        problems.append("PR manifest seeds missing or invalid")
        seeds = []
    if isinstance(item_count, int) and not isinstance(item_count, bool) and len(pr_rows) != item_count * len(seeds):
        problems.append(f"PR row count {len(pr_rows)} != manifest items x seeds ({item_count * len(seeds)})")

    def row_keys(rows: list[dict], label: str) -> set[tuple[object, object]]:
        keys: list[tuple[object, object]] = []
        for index, row in enumerate(rows):
            if "item_id" not in row or "seed" not in row:
                problems.append(f"{label} row {index} missing item_id or seed")
                continue
            keys.append((row["item_id"], row["seed"]))
        if len(keys) != len(set(keys)):
            problems.append(f"{label} has duplicate (item_id, seed) rows")
        return set(keys)

    pr_keys, base_keys = row_keys(pr_rows, "PR"), row_keys(base_rows, "baseline")
    if pr_keys != base_keys:
        problems.append("PR (item_id, seed) set differs from baseline")

    # A row-level graded metric may not silently disappear or become None.
    # Metrics produced only by the aggregate summarizer (for example pass_hat_5
    # and cost_per_success) do not have a corresponding value on each row.
    for metric in spec.get("metrics", []):
        mid = metric.get("id")
        if not mid or metric.get("grader") == "lab8.metrics.summarize":
            continue
        if not pr_rows or any(row.get(mid) is None for row in pr_rows):
            problems.append(f"graded metric {mid} is missing or None in a PR row")

    # Relabeling a claim out of a slice must not make its regression disappear.
    def tags_by_item(rows: list[dict]) -> dict[object, set[str]]:
        tags: dict[object, set[str]] = {}
        for row in rows:
            item_id = row.get("item_id")
            raw = row.get("slices") or []
            if not isinstance(raw, list):
                problems.append(f"item {item_id} has malformed slice tags")
                continue
            current = {str(tag) for tag in raw}
            if item_id in tags and tags[item_id] != current:
                problems.append(f"item {item_id} has inconsistent slice tags across rows")
            tags[item_id] = current
        return tags

    if pr_rows and base_rows:
        pr_tags, base_tags = tags_by_item(pr_rows), tags_by_item(base_rows)
        for item_id in sorted(set(pr_tags) & set(base_tags), key=str):
            if pr_tags[item_id] != base_tags[item_id]:
                problems.append(f"item {item_id} slice tags differ from baseline")

    # Ratchet thresholds only within the same eval-set version. Removing a
    # metric/slice or weakening any blocking condition must also be rejected.
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        def index_by(items: list[dict], key: str) -> dict[object, dict]:
            return {item.get(key): item for item in items if item.get(key) is not None}

        current_metrics = index_by(spec.get("metrics", []), "id")
        for mid, old in index_by(base_spec.get("metrics", []), "id").items():
            new = current_metrics.get(mid)
            if new is None:
                problems.append(f"metric {mid} removed from spec")
                continue
            old_th, new_th = old.get("threshold", {}), new.get("threshold", {})
            if "min" in old_th and ("min" not in new_th or new_th["min"] < old_th["min"]):
                problems.append(f"metric {mid} min threshold loosened")
            if "max" in old_th and ("max" not in new_th or new_th["max"] > old_th["max"]):
                problems.append(f"metric {mid} max threshold loosened")
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"metric {mid} changed from blocking to non-blocking")
            if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
                problems.append(f"metric {mid} dropped no_significant_drop")

        current_slices = index_by(spec.get("slices", []), "name")
        for name, old in index_by(base_spec.get("slices", []), "name").items():
            new = current_slices.get(name)
            if new is None:
                problems.append(f"slice {name} removed from spec")
                continue
            if old.get("metric") != new.get("metric"):
                problems.append(f"slice {name} metric changed")
            for bound in ("min", "max"):
                if bound == "min" and bound in old and (bound not in new or new[bound] < old[bound]):
                    problems.append(f"slice {name} min threshold loosened")
                if bound == "max" and bound in old and (bound not in new or new[bound] > old[bound]):
                    problems.append(f"slice {name} max threshold loosened")
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"slice {name} changed from blocking to non-blocking")
            if old.get("no_significant_drop") and not new.get("no_significant_drop"):
                problems.append(f"slice {name} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices", []):
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        threshold = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        values = per_item(pr, metric, slice_name=name)
        baseline = per_item(base, metric, slice_name=name)

        verdict = "ok"
        note = ""
        value = sum(values.values()) / len(values) if values else None
        if value is None:
            verdict = "missing"
            note = "no PR items in slice"
        elif "min" in sl and value < sl["min"]:
            verdict = "fail"

        if sl.get("no_significant_drop") and value is not None:
            keys = sorted(set(values) & set(baseline))
            if not keys:
                verdict = "missing"
                note = "no paired baseline items in slice"
            else:
                delta, lo, hi = stats.paired_bootstrap(
                    [values[k] for k in keys], [baseline[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                # M5 treats an upper CI that touches zero as a blocking
                # regression when the observed paired delta is negative.
                # Keep an exact A/A result (delta == 0) non-blocking.
                if delta < 0 and hi <= 0:
                    verdict = "fail"

        is_blocking = sl.get("blocking", False)
        if verdict in {"fail", "missing"} and is_blocking:
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("MISSING" if verdict == "missing" else ("BLOCK" if is_blocking else "warn"))
        lines.append(f"  {sid:<36} {value!s:<8} {json.dumps(threshold):<40} {note:<30} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    pr_manifest = pr.get("manifest") if isinstance(pr, dict) else None
    base_manifest = base.get("manifest") if isinstance(base, dict) else None
    if not isinstance(pr_manifest, dict) or not isinstance(base_manifest, dict) or \
            "eval_set_sha" not in pr_manifest or "eval_set_sha" not in base_manifest:
        return ["integrity"], ["  INTEGRITY report manifest or eval_set_sha missing"]
    if pr_manifest["eval_set_sha"] != base_manifest["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
