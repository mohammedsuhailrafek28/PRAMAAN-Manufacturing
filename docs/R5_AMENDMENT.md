# R5 amendment (owner-approved)

Source requirement, `docs/H1_H2_APPROVED_OPTION_A_SPEC.md` row R5 (unchanged text, preserved):
> Legitimate capture after checkpoint | ANCHORED_PREFIX_ONLY; eligibility withheld, holds visible, checkpoint-required banner

## Amendment
Approved by the owner after consolidation checkpoint 1 (`b15285c`). It supersedes **only** the "holds visible" clause, as applied to the UI. All other R1-R20 semantics are unchanged.

1. Backend holds and outstanding obligations remain enforced and preserved (the API still carries them; per-motor decision endpoints answer 409 `CHECKPOINT_REQUIRED`).
2. `ANCHORED_PREFIX_ONLY` with verified H2 may display segregated historical manufacturing facts.
3. No per-motor operational decision, hold chip, release chip or current clearance is displayed.
4. A prominent global CHECKPOINT REQUIRED / DO NOT SHIP OR RELEASE warning is shown.
5. No current eligibility or operational authorization is implied.
6. `ANCHORED_CURRENT` still preserves valid findings, holds, reasons and evidence, with clearance determined independently per motor.
7. INVALID, unknown, missing or contradictory trust metadata remains fully WITHHELD.
8. Backend enforcement is not changed to satisfy the UI.

## Rationale
A hold chip on a PREFIX_ONLY screen is a current operational decision drawn from a ledger newer than the trusted checkpoint. Its absence next to a stale release chip elsewhere could be misread as "no hold", and its presence could be misread as a verified current decision. Showing only recorded facts plus a global stop instruction removes both misreadings without discarding the backend hold.

## Test mapping
| Original assertion | Replacement | Negative |
|---|---|---|
| `checkpoint.spec.ts` "post-checkpoint capture ...": `getByText(/Recall hold remains in effect/)` visible under PREFIX_ONLY | UI: heading "Checkpoint required", `no-shipment-warning`, zero `chip-action`/`chip-finding`/`clearance-chip`. API: state `ANCHORED_PREFIX_ONLY`, every `currentReleaseEligible` false, snapshot still carries `RECALL_HOLD` for MTR-26003 and its notification obligation, decisions endpoint 409 | body text must not match `Release eligible\|Recall hold remains in effect\|Excluded with evidence` |
| (new, M8) | `checkpoint.spec.ts` second test: reload, route navigation, visibility/focus/online events, back/forward and a fresh page load never restore clearance | same |
| (new, M8) | `tests/unit/m8-prefix-no-lease.test.tsx` (5): no lease renewal, repeated PREFIX polls, replayed stale CURRENT, visibility, route navigation | same |

The original test title is kept; its body is migrated (original is in git history at `b15285c`).
