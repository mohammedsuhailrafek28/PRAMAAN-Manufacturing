# Process-deviation tracing, R4: Tier C sufficiency design review

Research and design review only. Branch `research/process-deviation-tracing`. Nothing is implemented, frozen, merged or deployed.
The pinned v3 engine, the Phase 3 safety-remediation branch and MSME PRAMAAN are untouched. This reviews `PROCESS_DEVIATION_R3_TWO_SOURCE_ASSURANCE.md`
and supersedes it where stated in section 10. No new external research was needed: this report is design analysis. Statements are **[B]** (my reasoning, unverified externally)
unless they cite R2/R3, which carried their own evidence labels.

## 0. Verdict first

| Item | Assessment |
| --- | --- |
| R3's safety invariants and fault model as written | **REVISE.** They contain 20 logical gaps (section 10), including an undefined aggregation rule, an under-specified F1 scope, and no statement of which physical phenomena any channel can see |
| Tier C as a *sufficiency rule* | **GO to a design stage**, in the single-fault-masked form defined in section 3 (not majority voting) |
| Implementation of Tier C now | **NO-GO** until owner decisions O1–O6, O11, O12, O16 (R3) and the new decisions in section 12 are made and an independent scenario author is named |
| A 36-hour build of full Tier C (classifier, independence records, certificate, independent verifier, revisions, sealed pack) | **NO-GO.** Not credible at the rigour required |
| A reduced "Tier C simulator and oracle" (section 9, stages 0–1) | **GO**, with claims limited to logic under declared faults |
| Release by operator attestation, or by a count tolerance | **NO-GO** |
If Tier C proves too expensive, the recommendation is to **remove functionality** (rework, lot-level identity, attestation, late-record admission, UI) and keep the release threshold: nothing below "survives the loss of any one independence group" may release a unit.

## 1. The target proposition and the exposure-path assumption

For unit `u` and possible window `W⁺`, exclusion must establish
`¬X(u)`: *no press cycle whose subject is `u` occurred in `W⁺`.*
Equivalently: for every physical cycle `c` that might lie in `W⁺`, `u` is not its subject. That decomposes into three separate things:

1. **Cycle population** `P(W⁺)`: which physical cycles occurred in or possibly in `W⁺` (a completeness question).
2. **Cycle timing**: when each occurred.
3. **Cycle subject**: which unit each acted on (an identity question).

It silently assumes an **exposure-path assumption** (**A-EVT**): the deviation condition is exposed only through *discrete press cycles of the bound asset*, each acting on one unit (**A-ONEPRESS**: `unitsPerCycle = 1`, `c_max = 1` per route step).
If exposure can also occur by other means (hand press, another machine, a continuous condition, a multi-unit pallet), Tier C **does not apply** and the notice must say so. R3 did not state this applicability limit.

## 2. What each channel establishes independently

Each channel is assessed on its own, within its *observation envelope* (the phenomena it can physically see) and its *fault envelope* (how it can be wrong).

| | **S: station** | **G: checkpoint** | **K: counter** |
| --- | --- | --- | --- |
| Observes | A claim that unit `u` was processed at entry/exit times by an actor | That an identifiable mark was read at the gate at time `T_G`, in a lane/direction | That a press cycle occurred at time `t_k` on the bound asset (cumulative register; optional timed events) |
| Establishes (if correct and complete) | Subject-of-cycle assignment; per-unit pass intervals; rework passes it recorded | `u` existed downstream by `T_G`: any pass ended `≤ T_G − τ_min`; presence of identity; with physical enforcement (D8), the *set* of units that have left the press | The *number* and timing of physical cycles; completeness of the cycle population in a bracketed span |
| Does **not** establish | Completeness (unrecorded passes), truth of its identity source, that a cycle physically happened | That `u` visited the press at all, when, how many times, or that unread units did not pass | Identity of anything; whether a cycle carried a product; strokes outside its capability (jog, inch, dry); whether it is bound to the right press |
| Fault envelope | omission, phantom, mislabel, mistime, backfill | omission (bypass, outage), double read, misread, cross-read, wrong lane | miss (weak stroke), phantom (vibration), epoch change, wrong asset, wrap, drift |
| Needs from others | Completeness from K, identity corroboration from G | Pass/cycle linkage from S and K | Subject from S or G |
**Pairs.**
* **S ∩ G:** identity corroboration (same id, feasible transit), an upper bound on exit time, order consistency if FIFO is declared. No completeness.
* **S ∩ K:** pass↔cycle alignment, count balance, and time cross-check of the press event. No independent identity.
* **G ∩ K:** an *S-free reconstruction*: a cycle at `t_k` can be linked to the unit read at `T_G ∈ [t_k + τ_min, t_k + τ_max]`. This is the independent derivation of the subject of an unattributed cycle and is the main reason three channels beat two.
Importantly, **the three channels do not observe the same variable**. Identity is observed by only S and G; cycles only by K (and S by claim); presence downstream only by G. There is nothing to "vote" on except constraints.

## 3. The aggregation rule: single-fault-masked sufficiency (SFMS)

### 3.1 Why majority voting is the wrong rule
* **Different observables.** Two channels cannot out-vote a third about a variable the third does not observe, and identity has only two observers.
* **Asymmetric risk.** A false exposure costs a hold; a false exclusion can ship a defect. The aggregation must be AND for release and OR for suspicion: *any credible channel suggesting exposure is enough to hold; all scenarios must agree before release*.
* **Correlated votes.** If two channels share a cause they are one vote counted twice, and a correct dissenter gets outvoted.
* **Silence.** Two channels silent because they share infrastructure look like agreement that "nothing happened".

### 3.2 Definition
Channels are partitioned by **independence group per failure mode** from the Independence Claim Record (R3 §1.3). A **fault scenario** is a pair `(mode m, group g)`: every channel in `g` may behave arbitrarily with respect to mode `m` (its claims of that kind are *non-evidence*); all other channels are correct and complete **within their observation envelope**. The scenario `0` has no fault.
Modes: omission, phantom, mistime, mislabel, unrecorded operation. A scenario is **feasible** if some assignment of the physical world is consistent with all non-faulty claims.

**Tier C sufficiency (SFMS).** A unit `u` may be `EXCLUDED_WITH_EVIDENCE` only if
1. scenario `0` is feasible and excludes `u`; and
2. for **every** scenario `(m,g)`, either it is infeasible (the evidence contradicts that hypothesis) or it excludes `u`; and
3. at least one scenario is feasible (otherwise the evidence contradicts every single-fault explanation: `MODEL_VIOLATION`, hold and incident); and
4. the evidence conditions E1–E12 hold in each feasible scenario.
Tier is the set of scenarios survived. **Tier C = survives the loss of any one of three distinct independence groups for each failure mode.** If S and K share a cause for a mode (say the PLC), there are only two groups for that mode, the claim is "Tier 2G", and Tier C is unavailable.

### 3.3 Why this differs from voting, with an example
Unit `u`, `W⁺ = [10:00, 11:05]`. S: pass `09:10–09:12`. K: cycle `09:11`. G: read `09:17`. `τ ∈ [4,10]` min.
* Scenario 0: consistent; `u`'s cycle at `09:11`; excluded.
* Drop S (S arbitrary): `u`'s cycle ∈ `[09:07, 09:13]` from G alone; excluded.
* Drop G: S+K place the cycle at `09:11`; excluded (identity single-source in this scenario, so E1 must be satisfied by S alone: allowed only if the owner accepted I1 for this scenario, otherwise this scenario *fails* ⇒ hold).
* Drop K: S+G: pass `09:10–09:12`, read `09:17`; excluded, but K was supposed to prove completeness; with K arbitrary, S is taken as complete.
All scenarios exclude ⇒ certificate. A *voting* rule would have said the same here; the difference shows below.

### 3.4 Cases where two-of-three agreement is logically insufficient
| ID | Case | Why agreement fails | SFMS response |
| --- | --- | --- | --- |
| L1 | **Agreeing silence.** S, G, K all report nothing for 10:40–10:50 because a shared gateway dropped all three | Unanimous absence is not evidence when liveness is shared | Each channel needs device-originated liveness (heartbeat/sequence) for the span; otherwise it is absent, not silent |
| L2 | **Correlated pair outvotes dissenter.** S and K are both PLC-derived and agree a unit was pressed at 09:11 outside the window; G reads the unit's mark at 10:55 (late; transit impossible for a 09:11 pass unless it queued) | Majority says G is wrong | Groups for mislabel/mistime: S,K are one group. Scenario "drop {S,K}": G alone cannot exclude (time) ⇒ hold |
| L3 | **Hidden stroke invisible to S and K, seen only by the unit's presence.** Manual jog stroke on `u` after the recorded pass; K cannot sense it, S not recorded | S and K agree there was one stroke | G sees nothing new either. **No channel observes it**: outside the observation envelope; Tier C is inapplicable unless K's declared capability includes jog and was proof-tested |
| L4 | **Identity has two observers.** S and G disagree on id | No majority exists | Disagreement ⇒ both scenarios feasible ⇒ hold |
| L5 | **Consistent but wrong from a shared declaration.** `τ`, FIFO, `c_max`, asset binding or the gate's "physically enforced" claim is wrong for all three | All three are consistent *with the declaration*, not with the world | Declarations are a fourth shared input (A-DECL); they appear in the certificate's residual list |
| L6 | **Persistent fault.** K's threshold drifted and misses light strokes for a week; a transient S drop coincides | "At most one fault per event" still holds per event but two channels were faulty in the hull | F1 must be scoped to the certificate's evidence hull, not to an event (section 10, G1) |
| L7 | **Faults on different claims combine.** One claim uses S for identity, another uses K for count; each claim has a single fault, but a certificate uses both claims | Per-claim F1 permits several faults in one certificate | F1 is scoped per certificate: one active scenario for all claims used |
| L8 | **Time agreement by shared bias.** S and G share NTP, both +4 min; K independent | Two of three agree on time | K's independent clock disagrees: conflict detected, scenario "mistime {S,G}" feasible, hull widens. If K also shared, undetectable (residual) |
| L9 | **Same mark.** S and G both read the same wrong label | Corroboration is of the label, not the part | Shared D2: one group for mislabel; hold unless the owner accepts the residual (A-ID-MARK) |
| L10 | **Gate completeness unsound.** Bypass class `PROCEDURAL`: units skip G | G's "no read" is not "unit not pressed" | G contributes positive corroboration only; Tier C unavailable for G-derived candidate sets |
| L11 | **Ordering collapse.** Non-FIFO buffering makes G order uninformative | Order-based swap detection fails | FIFO may be used only if declared, evidenced and physically enforced |

## 4. Feasible assignment semantics

### 4.1 Model
* Left nodes: observed cycles (K, with time hulls), **ghost cycles** for every count gap (unknown number at unknown times inside the gap), typed non-product events (calibration, dry cycles; authorised role).
* Right nodes: tracked units, each with capacity `[c_min, c_max]` cycles for press-required route steps (`0` if route evidence proves the step is not required; `[0, c_max]` if unknown), and `UNTRACKED` slots (unbounded) whenever G completeness is not credited.
* Edge `(c,u)`: **time-compatible** (c's hull meets `u`'s presence hull), and consistent with non-faulty S claims (c inside `u`'s pass hull if S has a pass), and with non-faulty G (`T_G(u) ∈ [t_c + τ_min, t_c + τ_max]`), and with declared ordering (FIFO) if used.
* A **feasible assignment** gives every cycle exactly one subject, respects unit capacities, and satisfies all constraints of the non-faulty channels in the scenario.

### 4.2 Allowed edges instead of enumerating assignments
An edge is **allowed** if it belongs to at least one feasible assignment. Whether `u` is exposed is: *some allowed edge from `u` to a cycle in `C_W`*, where `C_W = {c : hull(c) ∩ W⁺ ≠ ∅}` plus ghosts whose gap meets `W⁺`.
For the bipartite structure with capacity bounds, deciding which edges lie in some feasible assignment is a flow-feasibility problem with lower bounds, solvable in polynomial time (edges between strongly connected components of the residual graph are unusable) **[B, standard matching/flow theory; to be confirmed in the design stage]**. R3 called exact enumeration exponential; for the matching component that was too pessimistic. Coupling constraints (a unit in one place at a time, FIFO order, joint timing) can break polynomiality, so the production rule is **conservative**: it may treat an edge as allowed when it is not (extra holds), never the reverse.

### 4.3 Exclude versus hold
* **Exclude `u`** iff, in every feasible scenario, `u` has no allowed edge to any cycle in `C_W`, and E1–E12 hold.
* **Hold `u`** iff some feasible scenario gives `u` an allowed edge, or the evidence needed is missing.
* **Exposed (established)** iff in every feasible scenario `u` has a forced edge to a cycle certainly inside `W_certain` and the notice's qualifying rule is met.
* Ambiguity never resolves toward release: an ambiguous link (two candidate cycles, two candidate units) puts **all** candidates in the hold set.

### 4.4 Why this pins down things R3 left coarse
Capacities make `c_max = 1` bite: if a unit's one cycle is forced elsewhere (outside `C_W`), a very wide presence hull no longer implies exposure, because the only cycle it could use is taken. This lowers unnecessary holds without lowering the release threshold, and it is what "cycle balance" actually means.

### 4.5 Checkable witness
For each excluded unit, the certificate lists, per scenario, a feasible assignment as witness and the evidence that each candidate edge to `C_W` is infeasible (interval arithmetic for time incompatibility; a labelled strongly-connected-component certificate for matching-theoretic infeasibility). A small **independent verifier** (separate code, separate author preferably) checks these in linear time. In the minimum prototype, only time-incompatibility witnesses are used (section 9); matching-theoretic pruning is a later stage.

## 5. Conservative affected-population bounds

Notation: `AP = ⋃ over feasible scenarios (m,g) of the units with an allowed edge into C_W`, plus `UNTRACKED` where completeness is not credited, plus the units whose evidence is absent. Each rule gives the added population.

| Situation | Feasible scenarios | Affected population added |
| --- | --- | --- |
| **Unit unmatched, pass but no read** | G omission (bypass/outage/WIP); S phantom | The unit itself unless an independent anchor (upstream-after, downstream-before) places it outside `W⁺`; if its pass hull meets `C_W`, it holds; because G completeness is in doubt for the span, `UNTRACKED` joins |
| **Unit unmatched, read but no pass** | S omission | Reconstruct from G+K: cycles in `[T_G − τ_max, T_G − τ_min]` not attributed elsewhere; the unit is held if any such cycle can lie in `C_W`; if several unattributed cycles fit, **every unit read near them** is held |
| **Counts disagree: more cycles than passes (`r>0`)** | S omission; K phantom | For each residual: units whose G read implies a cycle time inside the residual's hull (G must be credited complete, else add `UNTRACKED` and all units without reads). `r` is reported but releases nothing |
| **Counts disagree: more passes than cycles (`r<0`)** | K miss; S phantom | The units owning the unbacked passes (their S exposure stands under "K miss"); other units unaffected because each scenario assumes the remaining channels complete |
| **Cycles missing (register gap, epoch break, snapshot loss unbracketed)** | K is non-evidence in the span | Tier degrades in the span to "S+G": units are excluded only if both S-hull and G-derived interval clear `W⁺` with margins; units lacking either are held. Unknown number of ghost cycles, so hold-by-default for any unit with a hull in the gap |
| **Checkpoint bypassed or outage** | G omission | Identity corroboration lost; G completeness lost ⇒ `UNTRACKED` joins every residual in the span; units read by G elsewhere still anchor |
| **Station identity or mapping changes** (stationId→press, rename, replacement) | S non-evidence from `t_change − δ` to `t_change + δ` | Passes in the transition are unbound; units with hull meeting it are held unless K+G alone exclude |
| **Counter identity changes** (replacement, reset, wrong asset) | K non-evidence for the epoch gap | As "cycles missing" over `[last bracketing snapshot before, first after]` |
| **Checkpoint identity changes** (gate moved, reader replaced, lane remap) | `τ` invalid | G supplies identity only, no timing; G's anchors are void until recommissioned |
| **Time bounds conflict** | one scenario per candidate faulty clock group | Presence hulls use the **union** of the hypotheses; if no scenario is feasible: `MODEL_VIOLATION`, the epoch's whole population in the span is held |
| **Unknown unit at G** | closure fails | Everything with a hull in the span, plus the unknown unit |
Blast radius is limited by **closure points** and **proof-test intervals** (section 8): failures are confined to the span between valid anchors on each side.
A hold bound is "sound" if it never omits a unit that any feasible scenario exposes; "tight" is how close it is to the oracle, and is measured, not required.

## 6. Within-model tests versus assumption-violation demonstrations

**Class WM (within model).** The world obeys the declared assumptions and the fault stays inside the active scenario (one group, one mode, within the hull). Expected: **zero false exclusions**; unnecessary holds measured. Failure of a WM test is a defect.
**Class AV (assumption violation).** The world violates a registered assumption `A-*`. Each AV test states which assumption, and its expected outcome is one of:
* **AV-D (detectable):** the violation produces an inconsistency the system must catch ⇒ hold plus a `MODEL_VIOLATION` or conflict flag. A failure is a defect.
* **AV-U (undetectable):** the violation leaves all channels consistent. Expected: **a false exclusion occurs**, and the harness records it as a *residual-risk demonstration*. It is never counted as a classifier pass or fail. It exists to show what the assumption is protecting and to quantify sensitivity.
The harness reports three tables, never merged: WM results, AV-D results, AV-U demonstrations (with the assumption id and the amount of violation).
**Assumption registry** (stable ids used by tests and certificates): A-F (F1c scope), A-ICR, A-PHY-G, A-K-ENV, A-EVT, A-ONEPRESS, A-ROUTE, A-TAU, A-FIFO (if used), A-CLK, A-ID-MARK, A-ASSET, A-PROOF, A-LEDGER, A-NOCOLLUDE, A-DECL, A-CLOSE.
For each AV-U assumption a **sensitivity sweep** reports false exclusions against the amount of violation (for example clock error `1×, 2×, 5×` the declared δ). That gives the owner a measured picture of what each declaration is worth.

## 7. Adversarial test specification

Format for every test: `id`, `class` (WM/AV-D/AV-U), `assumption`, `world` (hidden truth), `channels` (faults and what is shared), `declared` (ICR, τ, ε, capacities, bypass class, capability), `observations`, `expected` per unit (`trueExposed`; `MUST_HOLD` / `MAY_HOLD` / `EXCLUDE_ALLOWED`), `reason codes`, `clauses`. Authored and run as in R3 §8.1 (independent authors, sealed, third-party harness, mutation list).

### 7.1 Required scenarios
| ID | Scenario | Class | Expected (summary) |
| --- | --- | --- | --- |
| T01 | **Adjacent-label swap**, positional identity at S, FIFO declared and enforced; order of reads reversed | WM | Swap detected from order; both units held |
| T02 | Adjacent swap, **no FIFO**, reads within τ spread, units straddle the window boundary | WM | Both held (margin ε_swap ≥ τ spread); neither excluded |
| T03 | Adjacent swap far from the boundary (units clearly outside `W⁺ ± ε`) | WM | Excluded; swap is irrelevant to exposure |
| T04 | Swap with **S reading the mark** and G reading the same mark (shared D2); the physical part carries the wrong mark | AV-U (A-ID-MARK) | False exclusion recorded; with truthful ICR (D2 shared) ⇒ hold |
| T05 | **Duplicate scan** inside debounce | WM | One observation; no effect |
| T06 | Duplicate scan outside debounce with **two K cycles** for the unit (rework) | WM | Plausible rework; unit and neighbours held per rework rule |
| T07 | Duplicate scan outside debounce, **one cycle**, G double-counting offsets a missed unit | WM | Conflict; neighbours held; counts alone not used |
| T08 | **Shared PLC counter**: K derived from the PLC bit that also writes S; manual jog stroke | AV-U (A-ICR/A-K-ENV) with truthful ICR variant WM | Truthful (D1 shared): K not credited for unrecorded operations ⇒ hold. False (declared separate): false exclusion recorded |
| T09 | K proof-tested including jog but jog stroke occurs on a bypassed sensor channel | AV-U (A-K-ENV) | Residual demo |
| T10 | **Common-mode clock**: S and G share NTP, +4 min; K independent clock | AV-D | Conflict detected through K ⇒ hull widens ⇒ boundary units held |
| T11 | Common-mode clock shared by **all three** | AV-U (A-CLK) | False exclusion recorded; sweep over offset |
| T12 | **Missing cycle**: K drops one event while register intact | WM | Register wins for count; time detail widened; hold only where timing matters |
| T13 | **Missing cycles**: register snapshots lost across the window | WM | Tier degrades to S+G in the span; units outside by both clocks excluded, others held |
| T14 | K phantom cycle (vibration) in the window | WM | Residual; G-derived candidates held; K phantom scenario feasible; no release |
| T15 | **Rework bypass**: rework re-enters the press with no new work order and no re-scan | AV-D if K counts the extra stroke; AV-U if K blind | K sees excess cycle ⇒ hold; K blind ⇒ residual demo |
| T16 | Rework with new work order and re-scan | WM | Both passes accounted; unit held if either overlaps |
| T17 | **Post-notice backfill** of a consistent S/G/K triple by an insider with all credentials | AV-U (A-NOCOLLUDE) | Post-notice provenance blocks exclusion by default; chain/anchor shows late insertion; residual stated |
| T18 | Legitimate store-and-forward after outage, device-signed, sequence-continuous | WM | Admitted under the signed-device class; flagged late |
| T19 | **False independence declaration** for each dimension D1–D8 in turn | AV-U | One test per dimension: false exclusion recorded where the truth violates it; truthful twin ⇒ hold |
| T20 | **Counter epoch change**: reset to a value that happens to balance | WM | Epoch break ⇒ count gap ⇒ hold per section 5 |
| T21 | Counter replaced, `deviceID` changed, no commissioning record | AV-D | Unbound counter counts nothing |
| T22 | Counter register wrap | WM | Monotonic check ⇒ gap |
| T23 | Counter fitted to a different press | AV-D | Asset binding fails ⇒ K absent |
| T24 | Counter replaced and **bound record wrongly says same asset** | AV-U (A-ASSET) | Residual |
| T25 | **Retroactive independence downgrade**: a shared PLC found; ICR invalidated from date `T0` | WM (lifecycle) | All exclusions relying on that credit since `T0` re-evaluated; each withdrawn exclusion creates an obligation; old certificates still replay under their recorded ICR version; current status flips; shipped units flagged |
| T26 | Downgrade with unknown start date | WM | Default: invalid since the last passing audit |
| T27 | Retroactive upgrade without approval | WM | Rejected |
| T28 | **Proof-test failure** discovered at `t` | WM | Credit void from the last passing proof test; the interval is re-evaluated |
| T29 | Unrecorded multi-unit stroke (pallet) | AV-D if capacity violated | Balance fails ⇒ hold; or Tier C not applicable |
| T30 | Gate bypass physically (`PROCEDURAL`): unit pressed in `W⁺`, no read | WM (truthful) / AV-U (declared enforced) | Truthful ⇒ hold. False ⇒ residual |
| T31 | Unknown unit at G | WM | Closure fails; span held |
| T32 | Forced closure / attested explanation | WM | Never sufficient alone; Tier C rejects attested components |
| T33 | Silent outage with gateway-spoofed heartbeats | AV-U (A-ICR/D4) | Residual; with device-signed heartbeats ⇒ AV-D |
| T34 | `τ` too tight (false mismatches) and too loose (hidden swaps) | WM / AV-U | Tight ⇒ more holds; loose ⇒ margin widens, and if undeclared ⇒ residual |
| T35 | Station renamed/mapped to a new press during the window | WM | S absent in the transition |
| T36 | Late record arriving inside the hull, within bound | WM | Revision; may only add risk unless admitted class |
| T37 | Correction `did_not_occur` removes the only positive S record | WM | Unit returns to hold; obligation if previously excluded |
| T38 | INC vs FULL under random revision sequences across closure epochs, ICR and `τ` revisions | WM | Equal; mutation of the read-set is caught |
| T39 | Delivery order permutations at one watermark | WM | Identical certificates |
| T40 | Exposure event not a discrete cycle (continuous condition) | WM | Tier C not applicable ⇒ hold |

### 7.2 Properties checked on random worlds
* **P1 SFMS soundness:** for random small worlds inside the declared model, no unit excluded by the classifier is exposed in any scenario of the oracle (**classifier ⊑ oracle**).
* **P2 channel-removal monotonicity:** removing all records of any one channel from a Tier-C-required unit never leaves it excluded (it must become hold or lower-tier).
* **P3 information-loss monotonicity:** dropping any record or widening any bound never moves a unit toward excluded.
* **P4 AND/OR asymmetry:** adding a record that suggests exposure never produces exclusion; the only way to gain exclusion is adding corroboration that also survives every scenario.
* **P5 replay and verifier agreement:** every certificate replays identically and passes the independent verifier; a deliberately altered certificate fails it.
* **P6 assumption sweeps:** for each AV-U assumption, false exclusions as a function of violation magnitude are reported.
* **Mutation testing:** disable each rule (each E, each mismatch class, asset binding, epoch break, margin, scenario family) and require at least one test to fail.

## 8. The Tier C exclusion certificate

A machine-readable object, content-addressed, issued per excluded unit (or per epoch with per-unit sections), replayable and checkable by a separate verifier. Illustrative shape:

| Section | Contents |
| --- | --- |
| `certificateId`, `unitId`, `tier: "C"`, `status: "EXCLUDED_WITH_EVIDENCE"` | identity of the claim |
| `validAsOf` | per-source device sequence/ledger watermark; the certificate is a statement *as of* this point |
| `notice` | notice id, **version**, digest; `W⁺`, `W_certain`; qualifying rule; exposure-event type (`DISCRETE_CYCLE`); required tier |
| `evaluator` | name, version, pinned source-tree id, semantics profile; verifier name and version |
| `faultModel` | F1c scope (the evidence hull), scenario set, failure modes, groups per mode |
| `independence` | ICR ids, versions, digests, per-mode credit table, `validFrom/validTo`, **expiry**, physical-audit date and approver |
| `channels` | for S, G, K: source ids, device-side sequence ranges covered, heartbeat evidence ids, **capture ids and event ids** used |
| `counter` | **epoch id**, asset binding record id, counter `deviceID`, bracketing register snapshots `(n,t)`, capability declaration (auto/jog/inch/dry), proof-test ids and their validity window |
| `declarations` | `τ`, `ε_swap`, `δ` per source, `c_min/c_max`, `unitsPerCycle`, FIFO flag, bypass class and audit, route one-way/loop-back, closure points, declaration author |
| `hull` | the unit's presence hull and the anchor ids that bound it |
| `reconciliation` | **ReconRun** id and digest, the epoch's cycle list digest, residual (must be zero unexplained), candidate sets for cycles in `C_W` or their digest, **per-scenario witness** (assignment, infeasibility proofs for edges into `C_W`), margins |
| `conditions` | E1–E12 each with satisfied/evidence ids per scenario |
| `identityCredit` | I2 (with the S/G ids and times) or the signed owner acceptance if lower |
| `postNotice` | any evidence first received after the notice and its admitted class |
| `integrity` | ledger chain head and anchor at issuance, receipt times used |
| `replay` | list of input digests and the deterministic recomputation command; digest of the expected output |
| `unprovenAssumptions` | the assumption ids relied on (from the registry) with evidence, approver and expiry, plus those *not* covered (A-NOCOLLUDE, A-ID-MARK, A-LEDGER …) |
| `revocation` | the events that would invalidate it: ICR downgrade, proof-test failure, notice revision, late record in the hull, correction, `τ` revision, epoch break |
| `supersedes` / `supersededBy` | lifecycle chain; revocation never edits an old certificate |
A certificate with a missing section is not a certificate. Display text must say "excluded under the declared model and assumptions"; it must never say "verified safe".

## 9. Complexity, and the smallest meaningful synthetic Tier C

### 9.1 Where the cost is
| Component | Why it costs | Essential for the Tier C claim? |
| --- | --- | --- |
| Independence records, groups per mode | Needs a model and governance | **Yes** |
| SFMS scenario evaluation | Several runs of one reconciliation | **Yes** |
| Cycle↔pass↔read reconciliation with ghosts | Core logic; hull handling | **Yes** |
| Counter register, epochs, asset binding | Distinct data model | **Yes** |
| Proof-test windows | Credit intervals | **Yes** (latent faults) |
| Zero-tolerance balance with closure points | Prevents availability collapse | **Yes** |
| Certificate + independent verifier | Second implementation | **Yes**: this is the checkable-evidence argument |
| Oracle on small worlds | Third implementation | **Yes** |
| Independent scenario pack | People, not code | **Yes** |
| Matching-theoretic pruning (allowed edges) | Algorithmic | No: lowers holds only |
| Revision lifecycle incl. ICR retroactivity | Many dependency kinds | Needed for the lifecycle claim, can be staged |
| UI | Presentation | No |
| Rework, lot-level identity, attestation, post-notice classes | Many corner cases | No: **remove** |

### 9.2 Staged ladder (each stage is meaningful by itself)
* **Stage 0 (design):** assumption registry, scenario schema, oracle specification, certificate schema, verifier specification, owner decisions. No code.
* **Stage 1 (simulator + oracle):** world generator with hidden truth and fault channels (including shared-dimension toggles); SFMS classifier with **time-compatibility edges only**; independent oracle on ≤8 units and an integer time grid; reports WM / AV-D / AV-U tables for models A, B, C. Claims limited to logic.
* **Stage 2:** certificate issuance and the independent verifier; replay.
* **Stage 3:** revisions: notice, ICR retroactive downgrade, `τ`, proof-test failure, corrections; INC==FULL across closure epochs; obligations.
* **Stage 4:** matching-theoretic pruning; sealed independent pack run; sensitivity sweeps.

### 9.3 What to remove if resources are short (never lower the threshold)
Remove in this order: UI; matching-theoretic pruning; rework (any unit with rework history is held); lot-level identity (held); attested explanations (not supported); post-notice admission (denied); per-cycle K events (registers only: larger holds); drift; retroactive upgrades; dimension granularity (model only D1, D2, D5, D6, D7 and fix D3, D4, D8 as declared constants, labelled). Do **not** remove: SFMS, zero tolerance, independence per mode, the checkable certificate, the oracle, the AV/WM separation, the honest labels.

### 9.4 Honest sizing **[B]**
A rigorous Stage 1 is a few focused days for one engineer; Stages 2–4 plus a sealed independent pack are weeks, mostly authoring and review. A 36-hour hackathon can credibly show Stage 1 and the counterexamples. It cannot honestly claim Tier C release capability.

## 10. Logical gaps in R3's invariants and fault model, and the correction for each

| ID | Gap in R3 | Correction |
| --- | --- | --- |
| G1 | F1 stated per claim; scope (event, claim, certificate, epoch; transient vs persistent) undefined | F1c: at most one active fault scenario across **all claims of one certificate** over its evidence hull, persistent faults included |
| G2 | "Agreement implies truth" (R3 §5.2) assumes the channels observe the same variable and are independent | Withdrawn. Replaced by SFMS (section 3) |
| G3 | No definition of aggregation (AND/OR) | Release is AND over scenarios; suspicion is OR |
| G4 | No observation-envelope or exposure-path coverage | A-EVT, A-ONEPRESS, A-K-ENV; Tier C inapplicable outside them |
| G5 | Latent faults ignored; no proof tests | Proof-test windows; credit intervals; retroactive taint to the last passing test (A-PROOF) |
| G6 | Declarations (`τ`, `ε`, FIFO, `c_max`, bypass class, binding) treated as inputs but not as a shared failure source | A-DECL: independently authored, reviewed, measured, expiring; listed in the certificate |
| G7 | S24 "reduce credit-requirements" ambiguous | Attestation may never contribute to Tier C. Anything attested is a lower tier that cannot release |
| G8 | Oracle and classifier can share a mis-specified model | Assumption registry with sweeps, WM/AV separation, independent authors for the oracle spec |
| G9 | "No tolerance" can make Tier C unusable if K has a legitimate miss/phantom rate | Measure K's baseline in the synthetic world; unexplained residual ⇒ hold the epoch's AP (closure-bounded). If that releases nothing, the answer is better K or smaller epochs, not tolerance |
| G10 | Exactness claimed against an exponential oracle | Allowed-edge formulation (polynomial for the matching part); one-sided soundness; checkable witnesses |
| G11 | S25 post-notice rule cannot distinguish a legitimate store-and-forward from backfill | Device-signed, sequence-continuous batches (D3/D4) are a distinct class; unsigned late records never support exclusion |
| G12 | Only counter epochs handled; S and G asset identity changes missing | Channel↔asset binding matrix with validity intervals for all three channels |
| G13 | ICR downgrade scope undefined | Invalid from the declared start; if unknown, from the last passing physical audit |
| G14 | `UNTRACKED` unbounded blocks everything in the span | Intended (fail closed). Typed resolution requires a signed physical reconciliation and still cannot release alone. Measured as availability cost |
| G15 | ε conflates swap-resolution and clock uncertainty | `ε_swap` (permutation ambiguity, from τ spread and FIFO) and `δ` (clock) kept separate |
| G16 | Multi-unit strokes and non-discrete exposure not in the applicability statement | `unitsPerCycle = 1` and `DISCRETE_CYCLE` are preconditions for Tier C |
| G17 | A closure point is itself an exclusion-relevant claim | Closure requires SFMS balance across all three channels; forced closure invalid |
| G18 | Certificate is not explicitly time-scoped or revocable | `validAsOf` and `revocation` sections |
| G19 | Majority-like reasoning in reason codes could leak into the UI | UI shows scenarios survived and failed, never a "2 of 3" count |
| G20 | R3's AP bound (all units with hull meeting the bracket) is sound but coarse and ignores G-derived attribution | SFMS candidate sets (section 5) are tighter and still sound **only if G completeness is credited (D8 enforced)**; otherwise fall back to the coarse bound |

## 11. Critical counterexamples (new or sharpened)

| ID | Counterexample | Lesson |
| --- | --- | --- |
| C1 | Agreeing silence by shared gateway (L1) | Liveness must be per device; silence is not a vote |
| C2 | Correlated S+K outvote correct G (L2) | Groups, not channels |
| C3 | Jog stroke invisible to K and S (L3) | Observation envelope must include every exposing phenomenon, proof-tested |
| C4 | Two persistent faults over a week (L6) | F1c scope and proof-test windows |
| C5 | S and K both blind on a stroke but S+K "balance" because a phantom K cycle cancels a missed real one | Equal counts do not imply equal sets; matching is by feasibility with times, not by count |
| C6 | An epoch break that coincidentally balances | Epoch break creates a gap regardless of the arithmetic |
| C7 | A ghost cycle population unbounded across a long gap | Hold by default; shorten epochs |
| C8 | Retroactive downgrade after shipping | Obligations; certificates remain replayable under their recorded ICR |
| C9 | The verifier shares code with the classifier | No independent check: verifier must be a separate implementation |
| C10 | A certificate valid when issued, silently invalid later | `validAsOf`, `revocation`, and a lifecycle that can only supersede |
| C11 | Declared `τ` correct yesterday, wrong after a conveyor speed change | Declarations expire and are revalidated by measurement |
| C12 | Attested "dry cycle" is the real product stroke | Attestation cannot release |
| C13 | Two gates exist; one removed during maintenance, nobody updates the registry | Channel↔asset binding validity and proof-tests |
| C14 | Reconciler bug releases everyone | Independent verifier and oracle; mutation tests |

## 12. Unresolved owner decisions

Carried from R3 and still needed: O1 minimum tier (now fixed to **C** for exclusion), O2 residual-risk acceptor, O3 identity credit (I2), O4 bypass attestation and audit cadence, O5 collusion controls, O6 post-notice policy, O7 closure cadence, O9 counter hardware and ownership, O10 `τ`/`ε`/capacity sources, O11 fault model (now **F1c**), O12 ICR governance, O16 who authors/seals/runs the pack, O17 anchoring and retention.
New from this review:

| ID | Decision | Recommendation |
| --- | --- | --- |
| O18 | Scope of F1c: hull length, and whether a stricter fault model (two groups) is required for high-severity notices | F1c with the hull bounded by proof-test intervals; two-fault tier for severe hazards, deferred |
| O19 | Proof-test procedure, frequency, and who performs it (must include jog/dry modes) | Per shift, by someone other than the press operator |
| O20 | Counter observation envelope required by policy (which press modes must K see) | All modes that can move the ram; otherwise Tier C is not available |
| O21 | Applicability statement: which deviation types qualify as discrete-cycle exposures | Only those; others stay at hold |
| O22 | Device signing and sequence authority for S, G, K (who holds keys) | Required for any late-record admission; otherwise deny |
| O23 | Whether any residual (I1, A-ID-MARK, PROCEDURAL bypass) can ever be accepted in place of Tier C | No for Tier C; a lower tier cannot release |
| O24 | Authority and form of the independent verifier and who owns it | Separate team and repository |
| O25 | Acceptable availability cost (hold rate) before the programme reduces functionality instead | Set a target before Stage 1 results are seen |
| O26 | Behaviour when `MODEL_VIOLATION` triggers: who is paged, what is held, who can clear | Incident, epoch held, clearance by two roles |
| O27 | Retention period and format of certificates and replay inputs | Equal to product liability horizon; owner to state |

## 13. Limitations of this review
* This is design reasoning; none of it has been implemented or tested. The polynomial allowed-edge claim, the SFMS formulation and the certificate layout are proposals.
* The assumption and failure-mode lists are mine and have not been reviewed by a controls, quality or functional-safety engineer.
* SFMS limits the aggregation logic; it does not remove assumption risk. A world that violates the assumption registry can still produce a false exclusion, which is why AV-U demonstrations and the unproven-assumptions list exist.
* Numbers in examples are illustrative; no real clock, counter or route data was available.
* Independence of simulated services is a generator property, not physical evidence.
