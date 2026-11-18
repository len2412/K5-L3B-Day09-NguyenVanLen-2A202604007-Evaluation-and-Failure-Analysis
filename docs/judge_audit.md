# Judge audit (M2)

Calibration command (replay; no API key):

```powershell
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```

The failure class is positive (`FAIL`). Calibration floors are κ ≥ 0.6, precision ≥ 0.8, and recall ≥ 0.7.

| Criterion | n | κ | Precision | Recall | Confusion (TP/FP/FN/TN) | Meets floors? | Decision |
|---|---:|---:|---:|---:|---|---|---|
| `judge_tone` | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | Yes | May be used as a tone screen, with human review for consequential decisions. |
| `judge_helpful` | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | No | Do not use as a gate. |

## Why `judge_helpful` must not gate

Its precision of 1.0 can look reassuring, but it comes from labeling only 9 replies as failures, all of which match the human label. It misses 21 of the 30 human-labeled failures: recall is only 0.3. Thus 70% of failures pass through the gate. The low κ (0.375) also shows weak agreement beyond chance. The observed failure rate is 0.09, while Rogan–Gladen correction estimates 0.30, consistent with the high false-negative rate. A gate must catch failures; this judge's conservative, surface-level notion of helpfulness lets polished but factually wrong replies pass.

## Audit of disagreements

For the five disagreements shown by `--audit 5` for `judge_helpful`, the human label is supported by the failure notes in the public CSV. In each case the judge says PASS despite a concrete content defect.

| # | Case | Judge | Human | Who is right? | Rubric correction |
|---:|---|---|---|---|---|
| 1 | HL-015: says refund was 55,000đ; ledger note says 40,000đ. | PASS | FAIL — wrong amount | Human | Verify every amount against the ledger/expected result. Any amount mismatch is FAIL regardless of tone or fluency. |
| 2 | HL-016: polished apology says 55,000đ; ledger note says 35,000đ. | PASS | FAIL — wrong amount | Human | Do not let apology, politeness, or verbosity compensate for a factual or financial mismatch. |
| 3 | HL-020: says refund was 90,000đ; ledger note says 120,000đ. | PASS | FAIL — wrong amount | Human | Compare the reply's amount and order with the authoritative ledger; mismatch is FAIL. |
| 4 | HL-028: reply is apologetic and polished; the audit CSV marks a wrong amount. | PASS | FAIL — wrong amount | Human | Score correctness before style. Require checking the stated refund against the ledger, not merely whether the response sounds helpful. |
| 5 | HL-035: reply contains reassuring apology language; the audit CSV marks a wrong amount. | PASS | FAIL — wrong amount | Human | Explicitly test plausible, empathetic replies that state incorrect amounts; these must remain FAIL. |

The reply text and human failure notes above come from `data/eval/judge_helpful_public.csv`; for HL-028 and HL-035 the public note identifies the error as `sai tiền` without exposing the exact ledger value in the audit output. Do not infer the missing amount.

The tone audit also illustrates why the criteria must stay separate: H-008 and H-017 were human FAIL / judge PASS for overly casual address or wording, while H-042 and H-051 were human PASS / judge FAIL despite correct refund information. A tone rubric should name observable language criteria and avoid treating concise, correct replies as failures just because they omit extra phrasing.

## Conclusion and limits

- Reject `judge_helpful` as a gate because its recall and κ fail the published floors; it lets most human-labeled failures pass.
- `judge_tone` clears the numeric floors on this public replay set, so it is suitable only as a calibrated tone criterion. Keep safety, authorization, and money correctness on deterministic code graders.
- These results use 100 public replay examples. They do not establish performance on new or held-out replies; add fresh human-labeled cases and re-calibrate before relying on the judge beyond this set.
