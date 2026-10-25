# A7 — Event-ordering ambiguity diagnostic (research prototype)

**Status:** isolated research prototype on branch `research/a7-order-firewall`, created from tag `manufacturing-demo-v1.2` (`6709b0c`). The frozen v1.2 release, its tag and its branches are not modified. It is not part of the v1.2 product and is not deployed.

**What it is:** a read-only diagnostic. For each motor it asks whether the frozen product's current decision (unchanged evaluator `pramaan_recall.evaluate` with `Config.v3`, plus the unchanged identity/integrity guard in `application/lot_identity.py`) stays the same across timelines that the motor's **own declared clock profile** admits. It evaluates a **bounded subset** of those timelines (never all of them). If it finds one where the decision changes, it shows the recorded timeline and one minimal admissible counterexample timeline.

**What it is not:** it **does NOT block shipment**, **does NOT provide clearance**, changes no decision, checkpoint, eligibility, F5 or F6 state, and writes to no live ledger. `NO_COUNTEREXAMPLE_FOUND` means only that none was found in the modelled space; it is not evidence of safety. Timestamps are `SYNTHETIC_SIMULATED` and are never treated as trusted. Its technique is not new (possible-worlds / certain-answer semantics, valid-time indeterminacy, happens-before partial orders, metamorphic testing). What it adds is applying them to the frozen safety logic, used as a black box, over the timelines the system's own clock profile admits.

## Files
| File | Role |
|---|---|
| `research/order_firewall/firewall.py` | the diagnostic library + CLI (`python -B research/order_firewall/firewall.py LEDGER OUT.json`) |
| `research/order_firewall/replay_check.py` | independent admissibility check: replays a timeline through the frozen `Ledger.capture` into a **new** scratch ledger (refuses an existing file) and reads the frozen product's own decision there |
| `research/order_firewall/demo_a7.py` | ~60 s judge demo on a disposable synthetic ledger (about 2 s runtime) |
| `application/test_order_firewall.py` | 19 adversarial / read-only tests (registered in `ci/run_gates.py`, gate D) |

## Semantics check performed first (owner condition)
* `recall-engine/pramaan_recall/ledger.py:509-517` (`clearly_after`) treats two events as ordered only if **both** clocks are trusted, the gap exceeds the skew, and recordedAt agrees. With `trustedTimeSources=[]` (every v1.2 motor, `application/service.py:108-109`), no cross-source order is ever provable. The 300 s `observationClockSkewSeconds` is a margin applied to trusted clocks. It does not bound untrusted clocks.
* The first radar probe was **flawed**. It moved only the replacement install 151 s earlier, which put it before its own source's removal. That violates per-source sequence order, and a test now pins that it is inadmissible (`test_moving_one_event_of_a_source_alone_is_inadmissible`).
* The replacement model (below) is stricter than the frozen model. Its counterexample was then replayed end-to-end through the frozen capture path: every event was accepted, the checkpoint was `ANCHORED_CURRENT` and the result was `RECALL_HOLD` (not eligible). The recorded timeline replays to `RELEASE_ELIGIBLE`. **The counterexample is genuinely admissible, so the result is not NO-GO.**

## Model assumptions (reproducible record)
* **M1** Each source's clock may be off by one unknown constant whole-second offset `d_s`, applied to both `occurredAt` and `recordedAt` of all that source's events. This preserves each source's authoritative sequence order.
* **M2** `|d_s| <= observationClockSkewSeconds` (300 s). This bound is an **assumption**: the frozen evaluator gives untrusted clocks no bound. Every counterexample found here is therefore also admissible for the frozen model, while "no counterexample" covers only this restricted space.
* **M3** A source with any event whose `timeSource` is in `trustedTimeSources` is pinned (`d_s = 0`).
* **M4** A shifted timeline is admissible only if every event passes the frozen `profile.validate_native` (recordedAt ≥ occurredAt, `profile.py:89-129`), per-source recordedAt is non-decreasing, referenced events are recorded no later than the referrer, and recordedAt lies inside the event's authenticated capture session (`integration/pramaan_integration/ledger.py:151-176`).
* **M5** Search runs in two phases:
  * **Phase 1:** single-source offsets at every breakpoint, in increasing magnitude. This gives the minimal witness: fewest shifted sources, then the smallest offset.
  * **Phase 2:** depth-first enumeration of the cross-source orders of `occurredAt` that offsets satisfying M2–M4 can realize. The skew bound, pinned sources, capture-session windows and cross-source reference rules are all encoded as difference constraints (Bellman-Ford). **One** strict realization (every gap ≥ 1 s) and **one** tie realization (gaps may be 0 s) of each order are evaluated.
  * **Coverage claim (bounded):** phase 2 does not evaluate other realizations of the same order. That excludes other tie patterns, other gap sizes and other cross-source `recordedAt` interleavings, and the frozen evaluator does read `recordedAt` order (`engine.py:87`, `:112`). It also excludes clock drift and offsets beyond the declared skew. **No exhaustive-coverage claim is made for any classification.**
  * The search is capped.
* **Classification:**
  * `ORDER_SENSITIVE`: an admissible timeline under the model changes the decision.
  * `NOT_EXHAUSTIVE`: the cap was hit, or a fixed date the logic compares against (policy `announcedAt`, registry effective dates) lies within the skew of an event. Orders relative to such constants are not enumerated.
  * `NO_COUNTEREXAMPLE_FOUND`: otherwise. It means only that no counterexample was found among the evaluated realizations. It is **not a clearance** and **not exhaustive**.
* **Decision function:** the same calls as `application/service.py:404-409`. Registry-binding findings are omitted because they depend on the checkpoint, not on the timeline. Test `test_decision_function_matches_the_live_product_for_every_motor` checks equality with the live product on the recorded timeline.

## Result (reproducible: `python -B research/order_firewall/demo_a7.py`)
Scenario: the ordinary service commands (the same ones the HTTP routes call):
1. Create MTR-26100 and assemble it (DE bearing BR-310, NDE BR-312).
2. Announce a recall of BR-204 (DE).
3. The operator observes an unregistered label `QX-77` on the DE bearing (HANDHELD source).
4. The DE bearing is replaced 150 s later (REWORK source).

| | Recorded timeline | Counterexample `{HANDHELD: +150 s}` |
|---|---|---|
| sighting QX-77 occurredAt | 2026-10-20T08:01:00Z | 2026-10-20T08:03:30Z (ties the install) |
| replacement install occurredAt | 2026-10-20T08:03:30Z | unchanged |
| identity guard | sighting superseded (install strictly later) | `UNREGISTERED` |
| frozen evaluator | RELEASE_ELIGIBLE / EXCLUDED_WITH_EVIDENCE | unchanged (RELEASE_ELIGIBLE) |
| guarded decision | **RELEASE_ELIGIBLE** | **RECALL_HOLD** |
| frozen replay into scratch ledger | ANCHORED_CURRENT, eligible | ANCHORED_CURRENT, **not eligible** |

* **149 s on the HANDHELD source alone does not flip the decision** (tested), so 150 s is the minimal single-source witness.
* With a declared skew of 149 s a two-source witness still exists: REWORK −149 and HANDHELD +2, for a relative shift of 151 s. Phase 2 returns one feasible realization that shifts other sources too, so it is not minimal.
* With a skew of 74 s no counterexample is found. That motor is `NOT_EXHAUSTIVE` because the announcement lies within 74 s of an event.
* Control MTR-26101 runs the same commands in the opposite order. It is held and is `ORDER_SENSITIVE` in the other direction (HANDHELD −61 s → eligible).
* MTR-DEMO-1 and MTR-26102 are `NO_COUNTEREXAMPLE_FOUND` (89 phase-2 realizations + 61 single-source timelines each). This is **not a clearance** and not exhaustive.

**Interpretation:** one v1.2 release decision rests on a cross-source order that the system's declared clocks cannot establish. The guard compares raw `occurredAt` (`application/lot_identity.py:202-204`), which is weaker than the evaluator's own skew-aware rule for affected-lot sightings. Severity for owner review: **P1 candidate in v1.2 (cross-layer semantic inconsistency)**. It is not an exploit, because single-host demo clocks are in fact ordered. It is **not fixed** here, since the guard is frozen.

## Independent admissibility review of the +150 s witness (owner request, before push)
Reproduced with a separate script on a disposable ledger. Every check uses frozen code or frozen data.

| Check | Result |
|---|---|
| Per-source sequence order | Only the HANDHELD source moves, by one constant. It has one event (`HANDHELD:1`). Every other source is untouched. All per-source orders are preserved. |
| occurredAt vs recordedAt | The sighting goes from occurredAt 08:01:00 / recordedAt 08:01:04 to 08:03:30 / 08:03:34. recordedAt ≥ occurredAt is kept (frozen `validate_native` passes). |
| Capture sessions | Every session here spans 2026-01-01 to 2027-12-31, so the session rule is satisfied but does not constrain this witness (vacuous in the synthetic seed). |
| References | The sighting references no event (its only reference is an external `evidenceRefs` record id), and no event references it. Frozen capture accepted every event in the replay. |
| 300 s skew | 300 s is the motor's declared `observationClockSkewSeconds`, used here as an upper bound on an untrusted clock's error. The frozen evaluator itself applies it only as a margin between **trusted** clocks (`ledger.py:509-517`) and gives untrusted clocks no bound. The witness (150 s) is within the bound; 301 s is rejected. |
| Checkpoint | The original replay is `ANCHORED_CURRENT` / eligible. The witness replay is `ANCHORED_CURRENT` / **not eligible** (`RECALL_HOLD`). Both are fresh scratch ledgers anchored by the frozen anchor code. The live demo ledger is untouched. |
| Ties and ordering conventions | At +150 s the sighting and the install share occurredAt 08:03:30 and recordedAt 08:03:34. The guard drops a sighting only if an install is **strictly** later (`lot_identity.py:202-204`), so a tie keeps it. The evaluator's supersession pass processes events in (recordedAt, sourceId, sourceSeq) order (`engine.py:87`); no supersession is involved here. **+151, +200 and +300 s also give RECALL_HOLD** and are admissible. 149 s does not flip. |
| Reported timestamps vs physical history | The witness is an admissible **reported** timeline, not a claim about what happened. On the demo host the commands really ran sighting → removal → install. The host ledger's arrival order (`HANDHELD:1` before `REWORK:1`) is not used by the frozen evaluator, and host capture times are the real wall clock, not comparable with the synthetic event times. For the witness to also match the arrival order physically, the REWORK removal would have to have been delivered at least about 90 s after it was recorded. That is a plausible delay, but it is an assumption. |

**Verdict:** the witness remains defensible as an admissible reported timeline under the stated model. No admissibility assumption failed. The one assumption the frozen system does not itself impose is the 300 s bound, and it only makes the model stricter.

## Read-only and no-alteration evidence (tests)
* The live ledger is never opened by SQLite. It is byte-copied, because even a read-only open of a WAL database creates side files. The directory is fingerprinted before and after and must be byte-identical with no new files.
* Live decisions, eligibility and checkpoint (`ANCHORED_CURRENT`) are unchanged after the diagnostic.
* Static boundary: the library (outside its CLI block) contains no capture/event/announce/replace/observe/ship, checkpoint, evidence-package, federation or server calls, no SQL writes and no `sqlite3.connect`.
* Frozen components (engine, policy, ledger, lot_identity, service, anchors, checkpoint_ops, evidence_package/verify, federation node, integration ledger) are byte-identical to `ci/frozen-source.json`.
* Adversarial tests:
  * same-source order is never broken;
  * single-event moves are inadmissible;
  * trusted clocks pin every source;
  * offsets beyond the skew are rejected;
  * a missing skew is an error, not a default;
  * reference/session violations are rejected;
  * a superseding record cannot be moved before its target;
  * the cap is labelled `NOT_EXHAUSTIVE`;
  * runs are deterministic;
  * forbidden vocabulary is absent.

## Limitations
1. **Coverage is bounded:** phase 2 evaluates one strict and one tie realization per realizable `occurredAt` order. It does not cover every tie pattern, gap size or `recordedAt` interleaving. The +150 s witness is a tie, but +151 s to +300 s (strictly later sighting) also give `RECALL_HOLD`, so the finding does not rest on the tie convention.
2. The per-source constant offset (M1) excludes clock drift and per-event jitter, so the true admissible space is larger. `ORDER_SENSITIVE` is sound under the model; `NO_COUNTEREXAMPLE_FOUND` is not a proof.
3. The 300 s bound is the motor's declared configuration, not an authenticated clock property. No independent clock authentication is claimed.
4. Orders relative to fixed dates (announcement, registry effectivity) are not enumerated; those cases are reported `NOT_EXHAUSTIVE`.
5. Phase-2 witnesses are one feasible realization and are not necessarily minimal.
6. Single-host synthetic data: on the demo host the clocks are in fact ordered. The finding is about what the evidence can establish, not about what happened.
7. A diagnostic shown beside an eligible motor can be misread as a control or a clearance. The UI is not integrated (no product surface). The CLI/demo print the notice on every run.
8. Hosted CI for this branch exists only because its workflow trigger list adds `research/a7-order-firewall` (the only workflow change). A green run validates the gates on that exact commit. It is not a release, tag or deployment decision.
