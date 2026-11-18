"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb
import numpy as np
from scipy import stats as sps

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    # TODO M2
    confusion_matrix = dict(tp=0, fp=0, fn=0, tn=0)
    for h, j in zip(human, judge):
        if h == POS:
            if j == POS:
                confusion_matrix["tp"] += 1
            else:
                confusion_matrix["fn"] += 1
        else:
            if j == POS:
                confusion_matrix["fp"] += 1
            else:
                confusion_matrix["tn"] += 1
    return confusion_matrix


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    # TODO M2: precision = tp/(tp+fp), recall = tp/(tp+fn); return 0.0 when the denominator is 0
    cm = confusion(human, judge)
    tp = cm["tp"]
    fp = cm["fp"]
    fn = cm["fn"]
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    # TODO M2
    cm = confusion(human, judge)
    tp = cm["tp"]
    fp = cm["fp"]
    tn = cm["tn"]
    fn = cm["fn"]

    n = tp+tn+fp+fn
    if n == 0:
        raise ValueError("kappa is undefined for empty input")

    p_o = (tp + tn)/n
    p_e = ((tp+fp)/n) * ((tp+fn)/n) + ((fn+tn)/n) * ((fp+tn)/n)
    if p_e == 1:
        raise ValueError("kappa is undefined when expected agreement is 1")

    return (p_o-p_e)/(1-p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    # TODO M2: (p_obs + spec - 1) / (sens + spec - 1)
    if not all(0.0 <= x <= 1.0 for x in (observed_rate, sensitivity, specificity)):
        raise ValueError("observed_rate, sensitivity, and specificity must be in [0, 1]")

    denominator = sensitivity + specificity - 1.0
    if denominator == 0.0:
        raise ValueError("Rogan–Gladen correction is undefined when sens + spec == 1")

    corrected = (observed_rate + specificity - 1.0) / denominator
    return min(1.0, max(0.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    # TODO M4
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    if a_arr.shape != b_arr.shape:
        raise ValueError("a and b must have the same length (same items, same order)")

    # identical everywhere -> no difference and a degenerate interval
    if np.array_equal(a_arr, b_arr):
        return (0.0, 0.0, 0.0)

    def mean_diff(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    res = sps.bootstrap(
        (a_arr, b_arr),
        mean_diff,
        paired=True,
        vectorized=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    ci = res.confidence_interval
    return (float(a_arr.mean() - b_arr.mean()), float(ci.low), float(ci.high))

def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _validate_pass_k_args(n, c, k)
    return 1.0 - comb(n - c, k) / comb(n, k) if n - c >= k else 1.0


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _validate_pass_k_args(n, c, k)
    return comb(c, k) / comb(n, k) if c >= k else 0.0


def _validate_pass_k_args(n: int, c: int, k: int) -> None:
    """Validate counts shared by pass@k and pass^k estimators."""
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (n, c, k)):
        raise ValueError("n, c, and k must be integers")
    if n <= 0:
        raise ValueError("n must be positive")
    if c < 0 or c > n:
        raise ValueError("c must be between 0 and n")
    if k <= 0 or k > n:
        raise ValueError("k must be between 1 and n")
