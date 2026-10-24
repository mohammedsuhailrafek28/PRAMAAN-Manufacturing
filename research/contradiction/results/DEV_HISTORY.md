# Development history of the B1 detector (kept for honesty)

The first end-to-end run of B1 (code commit `e641285` + untracked candidate files, not committed) compared against the authored ground truth:

- contradiction detection: strict precision 1.0, recall 1.0 (17/17), class accuracy 17/17
- dependency (finding-sensitive motors): precision 1.0, recall 1.0
- hold-status-sensitive motors: precision 1.0, **recall 0.917 (11/12)**: B10's M101 was missed

Cause: the joint-interpretation enumeration chose one option from *every* contradiction touching a motor and offered no "leave this
contradiction unedited" option for DEFINITE contradictions. In B10 both contradictions are about the same install claim, so every
combination contained a DROP and the lot-adoption reading that would release M101 was never replayed alone. This is a defect of the
detector, not of the ground truth (the truth was authored from the per-contradiction reading and was frozen before the detector existed).
Fix: every contradiction contributes a `NOT_EDITED` option to the product (the all-NOT_EDITED combination is skipped).
