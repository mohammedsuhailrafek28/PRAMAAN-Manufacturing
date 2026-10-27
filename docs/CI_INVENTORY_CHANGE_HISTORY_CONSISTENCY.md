# Evidence-history consistency fix — inventory change and scope

Base: unified candidate `8ab78a794df60940d51e1b05c48b4abde034daf4` (unchanged; this is a separate branch `integration/ps10-history-consistency`).

## What changed

Frontend only. `useMotorResource` previously cached by `${kind}:${motor}` and ignored the verified snapshot, so Recall history, Resolution Trail, Passport and Genealogy could show a per-motor body from an earlier checkpoint beside a newer snapshot.

- `stitch-nextjs/src/dash/consistency.ts` (new, pure): `epochOf(snapshot)` = archive id, audit sequence, head hash, checkpoint state and anchored sequence; `assess()` compares each resource's own metadata with the snapshot.
- `stitch-nextjs/src/dash/data.tsx`: `useMotorResourceChecked` keys the request by epoch, drops the cache and refetches when the epoch changes, discards a response that belongs to an earlier epoch, clears everything when the snapshot is withdrawn or unavailable, and returns `CURRENT`, `UNVERIFIED`, `MISMATCH` or `PENDING`. `useMotorResource` keeps its signature and returns nothing for `MISMATCH`.
- `stitch-nextjs/src/dash/ResourceNote.tsx` (new) and small additions in `Trail.tsx`, Recall, Passport and Genealogy pages: existing note/tag/muted classes only, no style rule added.
- No change to the backend, evaluator, shipment rules, checkpoint logic, the five-second lease, the strict gate, prefix-only handling, report model or PDF code.

## Rules

| Resource | CURRENT when | Otherwise |
|---|---|---|
| decisions | snapshot trusted; response checkpoint is ANCHORED_CURRENT at the snapshot's anchored sequence; same policies, decision ids, versions, history tail and release eligibility as the snapshot | MISMATCH (withheld, reason shown) |
| lifecycle | snapshot trusted; response checkpoint state and anchored sequence equal the snapshot's; event count equals the unit's | wrong checkpoint or count: MISMATCH. Snapshot not current, or no checkpoint/count to compare: UNVERIFIED (recorded fact, labelled) |
| provenance | never (the endpoint returns a bare array without a watermark) | holds an event the snapshot lacks: MISMATCH. Otherwise UNVERIFIED, always labelled |

No backend envelope was added: changing the provenance array into an object is not backward compatible, and a header would be a backend change that was not approved. A watermark on the provenance and lifecycle endpoints remains a possible separately approved change.

## Inventory

Pins updated (none of them is among the original 449): `compatibility/run.py`, `compatibility/tests/unified.test.tsx`, `stitch-nextjs/tsconfig.compat.json`, the Genealogy, Passport and Recall pages, `src/dash/Trail.tsx`, `src/dash/data.tsx`. Pins added: `compatibility/tests/consistency.test.tsx`, `stitch-nextjs/tests/consistency.test.ts`, `src/dash/consistency.ts`, `src/dash/ResourceNote.tsx`. 528 -> 532 entries, zero removals. The old characterization test (14th component check) now asserts the corrected behaviour instead of the defect; no safety assertion was removed or weakened.
