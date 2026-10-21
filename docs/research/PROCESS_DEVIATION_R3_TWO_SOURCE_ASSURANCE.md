# Process-deviation tracing, R3: model-qualified exclusion with two-source capture reconciliation

Research and design analysis only. Branch `research/process-deviation-tracing`. Nothing is implemented, frozen, merged or deployed.
The Phase 3 remediation branch, the pinned v3 engine and MSME PRAMAAN are untouched. This refines `PROCESS_DEVIATION_PROPOSAL_R2.md`.

**Evidence labels.** **[W]** read on a web page this session (vendor or secondary summary; not a normative text). **[V]** verified from a primary artifact
in an earlier step (GS1 schema at the pin). **[B]** my own reasoning or background knowledge, unverified externally.
Numeric ranges quoted from secondary sources are marked as unverified.

## 0. The central claim and its honest limit

Two records are not two independent observations of physical truth. Independence is a property of **how the records could be wrong**, and it is
established by design review and physical audit, then monitored. It cannot be proven from the data itself. Therefore:

* The software's job is to make independence a **declared, versioned, auditable input**, to give credit only where the declaration supports it, and to fail closed otherwise.
* Every exclusion carries the **assurance tier** that supports it (the "model-qualified" part), so a reader can see whether it rested on one source, two, or three.
* Anything that two sources share is treated as **one source** for the failure modes that shared dimension can cause.
* What remains (collusion, undeclared shared causes, a physical bypass nobody knows about) is a stated residual risk with an owner, not something the classifier claims to remove.

Simulated services in one process, or two EPCIS documents in one repository, prove **nothing** about physical independence. In the synthetic MVP, independence is a
property of the world generator's fault channels, and the UI and reports must say "independence simulated".

## 1. What "independent" means for a press station and a downstream checkpoint

### 1.1 Definition
For a claim C (for example "unit U was not pressed during W"), two sources are independent **for failure mode F** if the circumstances that make source 1 wrong about C under F
do not also make source 2 wrong. Independence is therefore **per failure mode**, not a global yes/no. This follows the common-cause-failure idea in functional-safety engineering:
redundancy only helps to the extent that channels do not fail from a shared cause, and diversity plus separation reduce but never remove that shared part
(β-factor; IEC 61508 Annex D, where I saw ranges of 0.005 to 0.05 for programmable equipment and 0.01 to 0.1 for field equipment quoted by a secondary source, **unverified against the standard**)
[W: [exida](https://exida.com/Blog/the-importance-of-considering-common-cause-with-redundant-systems), [ABB diverse redundancy](https://library.e.abb.com/public/c8ebe6fed0204975852575ac0061e959/1462_DiverseRedundancy_Final.pdf)].
The lesson I take, and no more: **the common-cause term, not the independent term, dominates the residual risk**, so it must be enumerated, not assumed small.

### 1.2 Dimensions to assess (the Independence Claim Record)
Each dimension is `SEPARATE(evidence)`, `SHARED(what)`, or `UNKNOWN`. **`UNKNOWN` is treated as `SHARED`.**

| # | Dimension | What "separate" must mean | Typical shared trap | Failure modes it can cause jointly |
| --- | --- | --- | --- | --- |
| D1 | Observation mechanism | Different physical phenomenon or sensor chain (ram stroke proximity sensor or power draw vs optical read of a mark vs PLC program state) | Counter derived from the PLC bit that also triggers the station record | miss, phantom, mistime |
| D2 | Identity source | Unit identity read from the physical part by an independent reader, not copied from MES/work-order assumption or from one upstream scan | Both read the same label; both inherit a positional MES assignment | mislabel, swap |
| D3 | Credentials and authorship | Distinct producer keys/accounts, distinct ledger capabilities, no shared service account, producer cannot write the other's stream | One gateway account posts both; one admin can edit both | forged, phantom, backfill |
| D4 | Sequence authority | Each stream's sequence number is assigned at its own device, so a drop is visible per stream | A gateway or integration layer assigns sequence numbers or buffers and drops oldest | silent drop, reorder |
| D5 | Clock | Separate time sources, or a declared common clock with a bound | Same NTP server, same PLC clock, same host | common offset, step, drift |
| D6 | Infrastructure | Separate power, network path, gateway, storage, ingestion | One switch, one edge box, one database, one ledger host | joint outage, joint loss |
| D7 | People | Different operators and no shared supervisor/maintainer who can reconfigure both | Same person runs the press and the scanner; same technician swaps both | skip, collusion, mass attest |
| D8 | Physical path | The checkpoint cannot be walked around: enforced by interlock, single conveyor, locked cell; or the gap is declared | A forklift route, manual carry, rework re-entry that skips the gate | bypass |
D1–D8 are my working list **[B]**; they are not from a standard. The ALCOA+ expectations (attributable, contemporaneous, original, accurate, complete, consistent, enduring, available; audit trails; access control)
cover the *record-keeping* side of D3 and D4 [W: [FDA data-integrity guidance summary](https://www.assurx.com/understanding-alcoa-principles-and-data-integrity-for-pharma/)]; they do not address physical independence.

### 1.3 The credit calculus (deterministic, no probabilities)
Each source pair has an ICR with a `validFrom/validTo`, an author, a physical-audit date and the evidence. For each failure mode, a pair is **credited as two sources** only if every dimension that can cause that mode jointly is `SEPARATE`:

| Failure mode | Dimensions that must be SEPARATE for two-source credit |
| --- | --- |
| Dropped record (silent) | D4, D6 |
| Mis-timed record / common offset | D5 (else merge δ as one clock) |
| Mislabelled unit / swap | D2 |
| Phantom record (nothing happened) | D1, D3 |
| Skipped scan / unrecorded operation | D7, D8 |
| Collusion / backfill | D3, D7 (never fully creditable, see 1.5) |
Otherwise the two sources count as **one** for that mode, and the evidence condition that needs two (for example corroborated identity) is **not met**.

### 1.4 Separate sequence streams, clocks and infrastructure: precise consequences
* **Sequence streams.** Independent streams let the reconciler see "stream A has a gap" without trusting B. If a gateway assigns sequence numbers, a drop upstream of the gateway is invisible, so D4 is `SHARED`.
  Prefer a **cumulative counter register** (a monotone count with epoch id) over per-cycle events: a lost message then loses no cycles, only timing detail (section 3.2).
* **Clocks.** A shared clock error cancels in *differences* between the two sources but corrupts both against the absolute window. Relative checks (order, transit time) still work; the window test needs the common δ. Shared D5 means one δ, and a mismatch can never reveal the common offset.
  The ledger's own receipt time is a further, partly independent upper bound, but it shares infrastructure with the ledger (D6 for everything captured through it).
* **Shared infrastructure.** One ingestion path means a restore from backup, a full-disk pause or a gateway bug can drop both streams for the same interval. Detection then depends on the ledger's history chain and an external anchor (existing mechanism), on device-originated heartbeats, and on gaps against a source-side sequence.
  Concrete real-world flavour: an integration adapter documented as keeping a bounded queue of transaction ids that "deletes the oldest entry" when full (default 100) is exactly a silent, shared-path loss [W: [Critical Manufacturing IPC-CFX track-in](https://help.criticalmanufacturing.com/userguide/industrytemplates/smt/equipmentintegration/ipccfx/trackin.md)].
  I use it only as an illustration that middleware can lose data silently; I did not evaluate that product.
* **Heartbeats** are only evidence of coverage if they originate on the device and are sequence-numbered; a gateway-generated heartbeat during a device outage is a false-coverage counterexample (CE10).

### 1.5 Shared operators, collusion, physical bypass
* **Shared operators (D7).** If the same person operates both, one person's omission or deliberate act can defeat both: skip the scan and run an extra stroke. The pair is not credited for *skip / unrecorded operation*. Recording actor ids lets the system see the overlap; it cannot see intent.
* **Collusion.** Two cooperating people with legitimate credentials can create mutually consistent false records. No reconciliation of data can detect this. Mitigations are organisational (role separation, dual control, random physical audit, tamper-evident seals) and are **owner decisions**; the system can record who attested what and require a non-self approver, and the residual stays on the books.
* **Physical checkpoint bypass (D8).** A checkpoint is a *gate* only if the process physically forces every unit through it. Otherwise it is a sensor on one path. Software cannot know which. The route topology and a **bypass class** (`PHYSICALLY_ENFORCED`, `PROCEDURAL`, `NONE`) are declared by the owner with a physical-audit date; `PROCEDURAL` and `NONE` mean absence of a checkpoint read is **not** evidence of absence of a press cycle, and the checkpoint contributes only positive corroboration, never completeness.

### 1.6 What cannot be proven by any of this
That the unit is the one the label says; that no operation happened on a path nobody instrumented; that the clocks stayed within their bounds; that the people were honest; that the record was not fabricated by someone holding every credential. The contract (section 6) states each as a residual.

## 2. The three assurance models

Definitions. **Station (S):** press-side record with unit id, entry/exit, operator. **Checkpoint (G):** independently controlled downstream unit-identification gate (reads the physical mark, own credentials/sequence/clock where possible). **Counter (K):** an independent cycle counter bound to the press asset (for example a ram-stroke sensor or power-signature detector), exposing a **cumulative register** with epochs and optional timestamped cycle events.

### 2.1 What each can prove
"Under F" means under the declared single-fault model of section 5.2 and the ICR credits. Everything marked "cannot" is outside any model's reach unless stated.

| Question | A. S + G | B. S + K | C. S + G + K |
| --- | --- | --- | --- |
| **Unit identity** | Corroborated for units seen by both with a time-feasible transit. A swap is detectable when transit/order is inconsistent; undetectable inside the swap-resolution margin ε. Cannot show the mark is on the right part | **Single source (S only).** K carries no identity. Identity is not corroborated; swaps with consistent counts are invisible | Corroborated as in A; K adds cycle times that make swaps inside a boundary easier to expose |
| **Station visits (positive)** | Pass record plus downstream presence ⇒ the unit reached the checkpoint after the claimed exit (an upper bound on exit time) | Pass record, and K shows a cycle at that time | Both, and a three-way match |
| **Unrecorded operations (extra strokes, dry cycles, manual jogs)** | **Cannot see them** unless every extra pass re-enters the gate | **Detects excess cycles** (count balance); cannot say which unit | Detects excess cycles; checkpoint reads narrow which units could be involved |
| **Rework passes** | Only if rework routes back through G (a second read). Otherwise invisible | Visible as extra cycles; attribution to a unit only via S | Visible as extra cycles and re-reads; strongest |
| **Actual process timing** | Indirect: G time gives `exit ≤ T_G − τ_min`; S time is a claim | **Best direct timing of the press event** (K cycle time), independent clock if D5 separate | K gives the event, G bounds the unit's departure; the combination yields the tightest per-unit interval |
| **Complete capture** | Detects drops visible as gaps in either stream; cannot detect a joint drop (shared D6) or a unit that never entered either | Detects S losses that K still counted; cannot detect K undercount unless S exceeds K | Strongest: cycles = records = reads is a closure check; still blind to joint failure of all three (shared D6) and to unknown units |
| **Physical-bypass resilience** | Station record without G read ⇒ mismatch (detected). Pressed unit with **no** station record and no G read ⇒ **invisible**; only the route-completeness rule (an expected pass is missing) catches a *known* unit | Bypass of a gate is irrelevant (no gate); a hidden press shows as excess cycles | Hidden press shows as an excess cycle; carry-around shows as a cycle with no read |
| **Common-mode surface** | Clock, ingestion, operator, identity source can be shared | Press PLC is a prime shared cause if K is PLC-derived | Largest component count; the **reconciler itself** is a new single point and a new shared D6 |
| **Hardware and effort** | Gate reader, lane control | A counter on the asset | Both, plus reconciliation and closure discipline |
| **Expected unnecessary holds** | Medium | High when identity is uncorroborated (many holds near boundaries) | Lowest, if closure points are frequent |

### 2.2 Assurance tiers (what the decision says)
* **Tier-C:** exclusion rests on S + G + K, three-way reconciled over a closed epoch, each credited for the failure modes it covers.
* **Tier-B:** S + K reconciled; identity single-source. Allowed only if the notice records an owner-accepted identity residual.
* **Tier-A:** S + G; allowed only by bracketing (the downstream read precedes the possible window, or the upstream read follows it) on a one-way route; never as proof of no extra strokes.
* **Tier-0:** single source or unreconciled: no exclusion.
The notice declares the **minimum tier** required for release. Anything weaker is POSSIBLE.

### 2.3 Recommendation on the options
* **A alone: REVISE.** Cannot show absence of unrecorded operations; useful as the bracketing path and as a degraded mode.
* **B alone: REVISE.** Proves cycle completeness but cannot corroborate identity; acceptable only with a recorded owner acceptance and a large swap margin.
* **C: GO as the target contract**, conditional on a truthful ICR for every pair, closure points, and the sealed adversarial pack. It is also the most complex and introduces the reconciler as a common cause.
* The MVP should therefore **simulate A, B and C on the same worlds** and let measured false exclusions and holds support the choice (section 9).

## 3. Exact matching and mismatch semantics

### 3.1 Objects
* `Cycle k` from K: epoch `e`, cumulative count `n`, optional per-cycle time interval `[k_lo,k_hi]`. **Register snapshot** `(e, n, t)`.
* `Pass s` from S: `(sSeq, unitId, [in], [out], actor, workOrder)`.
* `Read g` from G: `(gSeq, unitId, [t], lane, direction)`.
* Declared constants (versioned inputs): transit bounds `τ_min ≤ τ ≤ τ_max` between press exit and the gate; expected cycles per pass `[c_min,c_max]` per route step (default exactly 1); debounce `τ_dup`; swap-resolution margin `ε`; closure-point rule.

### 3.2 Counter semantics
* A **register** is preferred over per-cycle events: dropping a snapshot loses time detail, not count. Between two snapshots in one epoch, the number of cycles is exactly `n₂ − n₁`. Outside bracketing snapshots it is unknown.
* **Epoch change** (reset, rollover, replacement, maintenance swap, firmware reflash) ⇒ the count across the change is unknown ⇒ an explicit **count gap** until a new bracket is established. Epochs need an asset binding (the counter is bound to this press by a commissioning record); an unbound counter counts nothing.
* If both a register and per-cycle events exist, **their sums must agree**; disagreement is itself a mismatch class (it exposes a lossy event path), and the register wins for *count*, events for *time*.
* The counter must **not** be derived from checkpoint counts or from S records (CE9).

### 3.3 Matching rule
A **feasible assignment** attributes each cycle to at most one pass and each pass to the cycles that explain it, such that: the cycle time lies within the pass interval (hulls), the pass has between `c_min` and `c_max` cycles, and each pass with a matching read satisfies `T_G ∈ [out_lo + τ_min, out_hi + τ_max]` for the same `unitId`.
Classification is over the **set of feasible assignments** (worlds), not a greedy match: a unit is only excluded if **no** feasible assignment gives it a pass overlapping the possible window. Greedy matching would pick one story and miss another.

### 3.4 Mismatch table
Each row gives detection, classification and the population consequence (section 4). "Hold" means POSSIBLE for the named population.

| Condition | Detected by | Status effect | Notes |
| --- | --- | --- | --- |
| **Missing S record**, cycle and read present | Cycle with no pass; read with no pass | Unit may be reconstructed from G identity + K time **only if** the cycle↔read link is unique under `τ`; ambiguous ⇒ all candidates POSSIBLE | Flag `STATION_RECORD_MISSING`; tier drops to B-like for that unit |
| **Missing G read**, pass and cycle present | Pass with no read within `τ_max` after exit | Identity uncorroborated ⇒ POSSIBLE under default policy (`IDENTITY_UNCORROBORATED`); exposure per S time stands if inside the window | Causes: bypass, checkpoint outage, WIP, scrap. Recorded outage explains but does not restore credit |
| **Missing K data** | Register snapshots absent/epoch gap | Count completeness lost only for the unbracketed span; if a later snapshot brackets, the *count* is intact | Graceful degradation toward Tier-A/B |
| **Excess cycles** (K > matched) | Count balance | **Residual `r` cycles**, each with a candidate set (section 4) ⇒ POSSIBLE for all candidates | No tolerance (3.5) |
| **Excess records** (S or G > K) | Count balance | Counter reliability for that span is in doubt ⇒ completeness **not** proven ⇒ hold per section 4 | Cannot tell phantom record from counter miss |
| **Duplicate read** inside `τ_dup` | Same id twice | Treated as one observation, flagged | Re-read |
| **Duplicate read** outside `τ_dup` | Same id twice | Conflict: a second visit, a re-labelled unit, or a loop. POSSIBLE for the unit and neighbours inside `ε` | If K shows two cycles for it, it is a plausible rework |
| **Duplicate pass** same content, new event id | Content digest | Idempotent merge, flagged | Retransmission |
| **Clock conflict** (read earlier than `out_lo + τ_min`, or cycle outside its pass) | Infeasible interval | Both sources' times for that unit widen to the union hull; `CLOCK_CONFLICT` on both sources; repeated conflicts demote a source (fail-closed auto-action) | Cannot say which source is wrong (shared clock hides it) |
| **Late record** | Receipt time vs event time and vs notice | Revision. A record **first received after the notice** claiming earlier times is `POST_NOTICE_PROVENANCE`: it may add risk freely, may support exclusion only per owner policy | Anti-backfill (CE7) |
| **Count inconsistency** (registers disagree with event sums) | Section 3.2 | Event path unreliable; use register for count, widen time | |
| **Unmatched identity at G** (not in ledger) | Read id unknown | `UNTRACKED_UNIT`: population closure fails for the span ⇒ closure failure | Unknown units cannot be enumerated |
| **Unmatched identity at S** (never read at G) | See "missing G read" | | |
| **Misread id** (fails check digit / format) | Syntax | Treated as an unmatched observation, flagged | |
| **Partial outage** of one source over `[o₁,o₂]` | Source-side seq gap, missing heartbeat, declared outage | That source contributes nothing in the span; tiers recompute over the remaining sources; units whose hull intersects the span lose the credit that needed that source | |
| **Silent outage** (no seq gap possible, no heartbeat) | Absence of device heartbeats | Treated as an outage from the last heartbeat to the next | Heartbeats are required for coverage |
| **Reconciliation correction** | New event superseding a record, or an attested explanation | The affected interval is re-reconciled; result is a new versioned `ReconRun`; flips in either direction follow section 5.3 | An attested explanation has lower credit than a device record |

### 3.5 No tolerance, but explained categories
Pharmaceutical packaging reconciliation accounts for components issued, used, rejected, returned and destroyed, and treats unexplained differences as investigation triggers, often with a tolerance; informal rework and undocumented sampling are named causes of drift
[W: [component count reconciliation](https://sgsystemsglobal.com/glossary/packaging-component-count-reconciliation/), [yield reconciliation note](https://seal.run/blueprints/pharmaceutical-packaging-line-clearance)].
That is a *useful analogy* (closure by accounting for every item) but not a standard I verified. For recall exclusion a tolerance is unsafe: one hidden pass is the hazard.
Rule: **zero unexplained residual**. Legitimate non-product cycles (calibration, setup, dry strokes) must be recorded as typed events by an authorised role, with evidence, and are subject to the attestation limits in 6 (S24).

## 4. Conservatively bounding the affected population when reconciliation fails

### 4.1 Presence hull
For each unit u define **PresenceHull(u)**: the interval during which u could have been at the press. Its bounds come only from anchors **independent of the failed source**: the latest trusted event proving u is upstream of the press (gate, creation) and the earliest trusted event proving it is downstream (checkpoint, shipment), each widened by clock bounds and transit bounds. No anchor ⇒ unbounded on that side. This requires the route to be **one-way** or loop-backs to be declared (a unit seen downstream can return upstream for rework, which would reopen the hull, so a declared loop-back makes the downstream anchor non-excluding).

### 4.2 Failure interval and affected population
Let `I` be the span over which reconciliation failed, expanded by clock bounds to `I⁺`, and bounded by the nearest **closure points** on each side (4.3).
**AP(I) = { u : PresenceHull(u) ∩ I⁺ ≠ ∅ } ∪ UNTRACKED**. All of AP is POSSIBLE. Lot-only identities expand to the whole lot.

Key refinements and their limits:
* **Residual cycles can belong to units that already have a clean record** (an extra stroke on a known unit). So the candidate set is *not* limited to units lacking records; it is every unit whose hull intersects the residual cycle's time. With only register snapshots (no per-cycle times) the residual's time is the whole bracket, so AP is the whole bracket. Per-cycle timestamps shrink AP to the units present at that cycle time. This is the main reason to want **both** register and timestamped cycle events.
* A residual count `r` is reported as information ("at most r units are exposed beyond the recorded ones") but **does not release any candidate**: we cannot tell which.
* An unknown unit seen at G proves the unit population is not closed; every hull intersecting the span is held.
* If the failing source is the only evidence for a unit's identity, that unit is in AP regardless of hull.

### 4.3 Closure points (reconciliation epochs)
A **closure point** is a time at which all three sources balance and every unit that has entered is accounted for (a counted-out batch boundary, shift end with line clearance, lot change). It is an explicit, authored event with evidence (the counts and the persons), not an assumption.
Failures are confined between consecutive closure points, so the blast radius is bounded by closure cadence. More frequent closures ⇒ smaller AP and fewer unnecessary holds; this is a measurable trade-off (section 9). A forced or operator-asserted closure ("force balance") is an attestation and carries only the credit the owner allows (CE12).

### 4.4 Worked example (illustrative numbers)
Possible window `W⁺ = [10:00, 11:05]`. K register: `n=1200` at 09:55, `n=1252` at 11:10 ⇒ exactly 52 cycles in the bracket. S has 51 passes in the bracket, G has 51 matching reads. Residual `r=1`.
* With **registers only**, the residual cycle time is `[09:55, 11:10]`. AP = every unit whose hull intersects that bracket, including the 51 clean ones (the extra stroke may be a re-press of any of them) plus any unit without anchors.
* With **per-cycle timestamps** the 51 cycles pin to 51 passes, leaving one cycle at, say, 10:41±1 min. AP = units whose hull covers 10:41 only, typically a handful.
* If a **closure point** sits at 10:30, the failing span is `[10:30, 11:10]`, so units wholly before 10:30 stay excludable.
The comparison of these three AP sizes is the quantity the MVP measures.

## 5. Effect on R2: E1–E8, possible worlds, revision lifecycle

### 5.1 Changes to the exclusion contract
| R2 | Change in R3 |
| --- | --- |
| E1 Identity | Graded: **I0** asserted/positional, **I1** read at the station (single source), **I2** independently corroborated at G with a feasible transit. Default release requires I2 for Tier-C; I1 only with a recorded owner acceptance (Tier-B) |
| E2 Route completeness | Unchanged in spirit; the checkpoint supplies route proofs for downstream arrival only |
| E3 Unit-stream completeness | Applies to the union of the unit's S and G streams; gaps judged against **device-side** sequences (D4) |
| E4 Station coverage | Becomes **capture completeness**: S, G and K each covered over the hull by device heartbeats/sequence, **and** the cycle balance closes (new E9) |
| E5 All passes | Satisfied by cycle accounting (B, C) or by re-scan rules (A), never by S alone |
| E6 Station identity | Adds **asset binding** of the counter to the press; wrong or unbound counter ⇒ fails |
| E7 No conflict | Extended to every mismatch class in 3.4 |
| E8 Disjointness | Uses the tighter hull, **plus margin `ε`** against swaps; a unit whose hull is within `ε` of the window boundary stays POSSIBLE |
| **E9** Cycle-balance closure | The reconciliation run for the epoch containing the hull has zero unexplained residual; else exclusion only by bracketing outside the failed span |
| **E10** Independence credit | Each proof element rests on sources credited for the failure modes it must survive (1.3); expired or downgraded ICR ⇒ fails |
| **E11** Provenance | Evidence first received after the notice is admitted per owner policy; attested explanations never alone suffice |

### 5.2 Possible-worlds classification under an explicit fault model
Classification is relative to a **fault model F** chosen by the owner. Proposed default **F1**: for any single claim, at most one *credited-independent* source is faulty (dropped, mis-timed within bound, mislabelled, phantom); sources that share a dimension for that mode are merged into one source for that mode; collusion and double independent faults are outside F1 (residual).
* Under F1, two sources that **agree** are taken as true; two that **disagree** mean at least one is faulty and we do not know which, so the worlds include both alternatives ⇒ POSSIBLE.
* Worlds also enumerate cycle-to-pass assignments and unknown-unit presence as in 3.3 and 4.
* ESTABLISHED: exposed in all worlds. EXCLUDED: exposed in none **and** E1–E11 hold. Otherwise POSSIBLE.
* **Soundness is now one-sided.** The production classifier may be coarser than the oracle but must never release a unit the oracle holds (**classifier ⊑ oracle**). Equality is desirable (tightness) and measured as the over-hold gap, but is no longer the safety criterion, because exact enumeration of assignments is exponential.
* The agreement-implies-truth step is exactly what shared dimensions break. This is the single most important reason independence must be declared per mode.
* A double independent fault is assumed negligible only if each fault is rare; the observed mismatch rate gives a rough single-source error estimate, but under a common cause the true false-agreement risk is at least `β·p`, which the data cannot reveal. The report shows the observed mismatch rate and states that the residual cannot be derived from it.

### 5.3 Revision lifecycle
New versioned, digest-pinned inputs (all appear in a decision's read-set): the **ICR** per pair/mode, transit bounds `τ`, `ε`, cycles-per-pass, debounce, tier requirement, counter epochs and asset binding, closure points, outage declarations, mismatch-explanation attestations, and the **ReconRun** artifact (inputs digests, matched assignments, residuals, mismatch classes).
* **Downgrade of an ICR is retroactive**: discovering a shared PLC or a shared operator invalidates every exclusion that relied on that credit over the claim's validity; all such units are re-evaluated and each withdrawn exclusion creates a durable obligation (S12).
  **Upgrade is prospective**; a retroactive upgrade needs owner-approved physical-audit evidence that the independence held at the time, and a second approver.
* Reconciliation is **epoch-global**, so incremental re-evaluation is scoped by closure epoch plus descendants, and INC==FULL must be tested across epoch boundaries and with revisions arriving between events.
* Tightening `τ_max` or `ε` (less conservative) can newly exclude and needs authored justification; loosening withdraws exclusions with obligations. A `τ` set tighter than the truth silently hides swaps and late transit (CE14), so `τ` validity is asymmetric: it must be a proven **lower bound on safety margin**, validated by measurement.
* Automatic actions are limited to the **fail-closed direction** (demoting a source after repeated conflicts, holding on an outage). Releases never happen automatically from a revision of anything but evidence.

## 6. Revised safety contract (R3)

Carried from R2 unchanged: S1 epistemic separation, S2 fail closed, S3 proof-carrying exclusion, S5 monotone under information loss, S6 unknown trust is non-excluding, S7 contradictions surfaced, S8 worst-of propagation, S9 shipment honesty, S10 explicit scope, S11 immutable digest-pinned versions, S12 withdrawal obligation, S14 order insensitivity, S15 replay, S16 history integrity, S17 no release by scope change alone.

| ID | Amended or new invariant |
| --- | --- |
| S4′ | Under the declared fault model F and ICR credits, **classifier ⊑ oracle**: it never releases a unit the possible-worlds oracle holds. Tightness is reported, not required |
| S13′ | INC == FULL including reconciliation epochs, ICR revisions and corrections between events |
| S18 | **Independence is declared per failure mode.** `UNKNOWN` = `SHARED`. A pair is credited as two sources only for modes whose joint dimensions are all `SEPARATE`, with an unexpired ICR |
| S19 | **Model-qualified exclusion.** Every exclusion records its assurance tier (C/B/A); a tier below the notice's minimum cannot exclude |
| S20 | **No tolerance.** Any unexplained residual cycle, unmatched identity or infeasible interval within the unit's hull prevents exclusion for the affected population |
| S21 | **Reconciliation is a versioned artifact**, digest-pinned in the decision and replayable |
| S22 | **Registers over events** for counts; epoch changes create count gaps; counters must be asset-bound and never derived from S or G data |
| S23 | **Population bounded from independent anchors.** AP is computed per 4.2; unknown units and unbounded hulls are always in AP |
| S24 | **Attestation is not a source.** Human explanations and forced closures may only reduce credit-requirements as the owner policy allows, need a non-self approver, are logged with identity, and are never sufficient alone |
| S25 | **Post-notice provenance.** Records first received after the notice can add risk; they support exclusion only under an owner-approved class |
| S26 | **Fail-closed automation only.** Automatic demotion/hold is allowed; automatic release is not |
| S27 | **Honest display.** The UI and exports show the tier, the ICR status (including "simulated"), the residual risks and the reason codes; they never say "verified physical truth" |
| S28 | **Residual statement.** Each decision exports the list of unproven assumptions it depends on (clock bounds, bypass class, identity credit, F) |

## 7. Critical counterexamples

| ID | Scenario | Why it defeats a weaker design | Expected R3 behaviour |
| --- | --- | --- | --- |
| CE1 | **Label swap** between adjacent units Y (pressed in W) and Z (before W); counts balance, each unit has one record, timing differs by seconds | Count reconciliation cannot see permutations | Detected only if transit/order is inconsistent. Within `ε` of the boundary both stay POSSIBLE; a swap larger than `ε` must be caught by G feasibility |
| CE2 | **Shared PLC**: the counter increments from the PLC bit that also writes the station record; a manual jog stroke bypasses the PLC | "Two separate services" are one mechanism (D1) | ICR marks D1 `SHARED`; K not credited for unrecorded operations; hold. If the ICR is falsely `SEPARATE`, a false exclusion occurs (residual demo) |
| CE3 | **Carry-around**: unit pressed in W, carried around the gate, station record also dropped | A sees nothing; B sees +1 cycle; C sees +1 cycle, no read | A: only route-completeness catches a *known* unit; B/C: residual cycle ⇒ AP hold |
| CE4 | **Shared clock** offset +4 min across S, G, K | All sources agree, all wrong against W | D5 `SHARED` ⇒ one δ ⇒ boundary units POSSIBLE. If undeclared, false exclusion (residual demo) |
| CE5 | **Counter replaced** mid-window with a value that happens to balance | Naive differences look fine | Epoch + asset binding ⇒ count gap ⇒ hold over the span |
| CE6 | **Dry cycles** "explained" by an operator after the fact | Opens a release channel for collusion | S24: attestation insufficient alone; needs a non-self approver and evidence |
| CE7 | **Backfill**: after the notice, an insider with all credentials inserts consistent S/G/K records for the window | Data cannot reveal fabrication | `POST_NOTICE_PROVENANCE` blocks exclusion by default; history chain and anchor show the late insertion; residual stated |
| CE8 | **Multi-unit stroke** (pallet, multi-cavity fixture) | Breaks 1 cycle = 1 unit | Cycles-per-pass must be declared per route step; else B/C cannot balance and hold |
| CE9 | **Double-counting at G** offsets a missed unit | If G counts are used as completeness, totals balance falsely | Matching is by identity and feasibility, never by count alone; K must be independent of G |
| CE10 | **Gateway heartbeat spoof** during a device outage | Silent outage looks like coverage | Heartbeats must be device-originated and sequenced; otherwise D4/D6 `SHARED` and coverage unproven |
| CE11 | **Register wrap** or a counter fitted to a different press | Looks like a normal delta | Monotonicity check, epoch rule, asset binding |
| CE12 | **Force closure** by an operator | A hand-set balance releases everything | S24; closure points need independent evidence |
| CE13 | **Late correction** reverses an exclusion for an already shipped unit | | S12 obligation; shipment inheritance |
| CE14 | **Transit bound too loose** (misses swaps) vs too tight (false mismatches) | One direction is silently unsafe | `τ` validity is asymmetric; loose `τ` must be treated as widening ambiguity |
| CE15 | **ICR downgrade discovered a year later** | Past exclusions were credited on a false claim | Retroactive re-evaluation and obligations |
| CE16 | **Unknown unit at the gate** | Population cannot be enumerated | Closure failure for the span |
| CE17 | **Gate reads a neighbouring label** or reads a label sheet instead of the part | Identity corroboration is of the label, not the part | Cannot be detected by data; physical-audit residual; D2 reflects what is read |

## 8. Independently authored adversarial scenario pack

### 8.1 Independence of authorship
* At least two authors who have not seen the implementation: one process/quality engineer (realistic factory behaviour) and one adversarial tester (attack and failure creativity). Neither reads the classifier code, its helpers, or this report's expected answers beyond the contract.
* A **sealed format**: each scenario is a plain document with the sections below; the pack is hash-committed before any implementation reads it. A third party runs the harness. The implementer receives pass/fail and the diff, but not the rest of the pack.
* A **mutation list** (disable each rule E1–E11, each mismatch class, the asset binding, the epoch rule, the margin) is applied by the third party; each mutant must be killed by at least one scenario. The implementer does not see which scenarios kill which mutant.
* Results are labelled **non-independent** if the author overlaps with the implementer.

### 8.2 Scenario document
`world` (true units, true cycles with true times, true presences, true bypass events), `channels` (per source: drops, duplicates, offsets, steps, delay, outages, heartbeat behaviour, mislabel, what is shared), `icr` (declared independence per dimension, **and separately the true independence** for the residual-risk class), `declared` (τ, ε, c_min/c_max, closure points, tier required), `observations` (exactly what the classifier receives), `notice` (versions), `expected` per unit: `trueExposed`, and one of `MUST_HOLD`, `MAY_HOLD`, `MUST_EXCLUDE_ALLOWED` (the author asserts the evidence suffices), with reason codes, and `clause` references.

### 8.3 Scenario classes and coverage
1. **Baseline**: perfect sources, window inside/outside/straddling.
2. **Single faults**: each source drops, duplicates, mis-times, mislabels, in turn.
3. **Matching**: every row of 3.4, including ambiguous cycle-to-read links and adjacent swaps crossing the boundary.
4. **Counter**: reset, rollover, replacement, snapshot loss, event/register disagreement, dry cycles, multi-unit strokes.
5. **Outages**: partial, silent, heartbeat spoof, outage exactly covering the boundary.
6. **Corrections and revisions**: `did_not_occur` of a positive record, corrected time moving a pass into W, ICR downgrade/upgrade, `τ` revision, closure added/removed, backfill after notice, late coverage closure.
7. **Common-mode (the key class)**: shared clock, shared PLC counter, shared gateway drop, shared power, shared operator skipping scan and running an extra stroke, shared identity source. Each exists **in pairs**: (a) the ICR **truthfully** declares the shared dimension ⇒ expected: no false exclusion; (b) the ICR **falsely** declares separation ⇒ expected: a false exclusion **does** occur, and the harness records it as a *residual-risk demonstration* showing exactly what the declaration is protecting against. Class (b) results are never counted as classifier passes or failures; they are reported as evidence of dependence on honest declarations.
8. **Physical bypass**: forklift carry-around, rework re-entry skipping the gate, reader aimed at the wrong lane, scrap-bin recovery, two units scanned as one, label sheet scanned instead of parts, cross-read of an adjacent label, gate with `PROCEDURAL` vs `PHYSICALLY_ENFORCED` declaration.
9. **Collusion/insider**: consistent fabricated triple, mass attestation, forced closure; expected result is stated as *undetectable by data*, with the mitigation being process, so these are residual demonstrations too.
10. **Lifecycle**: INC vs FULL under random revision sequences across epoch boundaries; replay of every historical version; order insensitivity.

### 8.4 Metrics (measured, not asserted)
For every scenario and every tier (A, B, C): **false exclusions** (classifier excluded a truly exposed unit), **unnecessary holds** (held a truly unexposed unit that the author marks `MUST_EXCLUDE_ALLOWED`), hold-set size versus the oracle, AP size by closure cadence, over-hold gap to the oracle. Acceptance: **zero false exclusions** in every class except the labelled residual demonstrations; unnecessary-hold rates reported with their sensitivity to δ, τ, ε, outage rate and closure cadence. A metric is only credible with the ground truth supplied by someone other than the implementer.

## 9. Smallest honest synthetic MVP (proposal, not frozen)

**Purpose.** Not to certify a factory. To (1) test the reconciliation logic under declared faults, (2) measure false exclusions versus unnecessary holds for Models A, B and C on identical worlds, and (3) demonstrate how the result depends on honest independence declarations. It must say so on screen.

**Design.**
* A world generator with hidden ground truth: units, true press cycles and times, flow, rework.
* Fault channels per source with explicit toggles for each shared dimension (clock, PLC, gateway, operator, identity, power) and for physical bypass.
* Three simulated sources (S, G, K with register + optional cycle events), device-side sequences and heartbeats.
* One classifier core implementing the R2 contract with R3 changes, **degrading** gracefully when sources are removed so A, B and C are the same code with different inputs.
* A separate possible-worlds oracle (independent code) for small instances.
* One view: station timeline with hulls, residual cycles, AP highlighted, tier badge, ICR status with "simulated", reason codes.
* Outputs: the metric tables of 8.4 across models.

**Explicit assumptions.**
A1 sources are independent exactly as the generator's ICR declares; A2 fault model F1; A3 counter is a cumulative register with epochs and asset binding; A4 one cycle per pass unless declared; A5 `τ`, `ε` known and conservative; A6 one-way flow except declared rework; A7 the ledger clock and chain are sound; A8 checkpoint enforcement is a declared attribute, not verified; A9 closure points are authored events; A10 no tolerance.

**Out of scope.** Real hardware, real clocks, parameter-trace exposure, batch processes, multi-station networks, multiple concurrent notices, cross-company exchange, any change to the pinned v3 engine, any statement about real factories.

**Exit criteria (design stage, before any build is approved).** Named independent scenario authors and a third-party harness runner; owner decisions O1–O6, O11 and O12 below recorded; F, the tiers and the closure cadence chosen; the oracle specified before the classifier.
**Exit criteria (prototype).** Zero false exclusions in all classes except labelled residual demonstrations; the demonstrations show false exclusions exactly where declared separation is false; mutation kill rate 100%; INC==FULL across epochs; reported hold rates by model and cadence.

## 10. Unresolved owner decisions

| ID | Decision | Notes / recommendation |
| --- | --- | --- |
| O1 | Minimum tier for release (C, B or A) per notice | Recommend C; B only with a signed residual acceptance |
| O2 | Who accepts residual risk and how it is signed | Named role, dated, in the notice |
| O3 | Identity credit required (I2 vs I1) | Recommend I2 |
| O4 | Physical bypass declaration: who attests, how often audited | Per gate, with audit date and expiry |
| O5 | Collusion policy: role separation, dual control, random audit | Process, not software |
| O6 | Post-notice backfill: allowed classes, approver | Recommend deny exclusion by default |
| O7 | Closure-point cadence and who authors them | Drives hold size; to be measured |
| O8 | May an operator attest explanations for unmatched cycles? | Recommend only logged, non-self-approved, never alone |
| O9 | Counter hardware and ownership (ram sensor vs power signature) | Must not be PLC-derived |
| O10 | Source of `τ`, `ε`, cycles-per-pass | Measured, not guessed, and revalidated |
| O11 | Fault model F (single fault vs two-fault) | Recommend F1 for MVP, state residual |
| O12 | ICR governance: author, approver, expiry, retroactive upgrade rule | Recommend downgrade retroactive, upgrade prospective |
| O13 | Lot-level identities across the gate | Lot-wide expansion by default |
| O14 | Rework loops: model them, or require new work order and re-scan | Recommend the latter |
| O15 | Multi-unit strokes and pallets | Out of MVP; hold |
| O16 | Who authors, seals and runs the scenario pack | Must not be the implementer |
| O17 | Retention and external anchoring of the history chain | Needed for CE7/CE15 detection |

## 11. Limitations of this research
* Standards evidence is from secondary summaries (IEC 61508 beta ranges, FDA data-integrity, pharmaceutical reconciliation, IPC-CFX adapter notes). I did not read the normative texts, and the numeric ranges are unverified.
* I found no manufacturing-genealogy product that documents cycle-count reconciliation for exclusion; that is absence in what I read, not proof of absence. Pharmaceutical packaging reconciliation is the nearest accounting analogue, not a precedent for recall exclusion.
* The independence dimensions, tiers, credit calculus, closure points and fault model F1 are **my proposals** and have not been reviewed by a quality, safety or controls engineer.
* No real clock, counter or route data exists; every number here is illustrative.
* A software contract can make false assumptions visible and costly. It cannot make them true.

## Sources
[exida: common cause with redundant systems](https://exida.com/Blog/the-importance-of-considering-common-cause-with-redundant-systems) ·
[ABB: diverse redundancy](https://library.e.abb.com/public/c8ebe6fed0204975852575ac0061e959/1462_DiverseRedundancy_Final.pdf) ·
[ALCOA+ summary](https://www.assurx.com/understanding-alcoa-principles-and-data-integrity-for-pharma/) ·
[Packaging component count reconciliation](https://sgsystemsglobal.com/glossary/packaging-component-count-reconciliation/) ·
[Packaging line clearance blueprint](https://seal.run/blueprints/pharmaceutical-packaging-line-clearance) ·
[Critical Manufacturing IPC-CFX track-in](https://help.criticalmanufacturing.com/userguide/industrytemplates/smt/equipmentintegration/ipccfx/trackin.md) ·
[Critical Manufacturing IPC-CFX track-out](https://help.criticalmanufacturing.com/userguide/industrytemplates/smt/equipmentintegration/ipccfx/trackout.md) ·
[FactoryLogix CFX message list](https://factorylogix.atlassian.net/wiki/x/jAA5Bw) ·
[GS1 EPCIS repository](https://github.com/gs1/EPCIS) (pin `6f71468…`, checked earlier) ·
[Vanini et al., DFRWS time anchors](https://dfrws.org/?p=11932)
