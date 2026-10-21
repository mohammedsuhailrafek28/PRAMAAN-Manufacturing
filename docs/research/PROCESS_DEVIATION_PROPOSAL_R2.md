# Process-deviation tracing: revised technical proposal (R2)

Research and design analysis only. Branch `research/process-deviation-tracing`. No code, no schema change, no architecture
freeze, no merge or deployment. The Phase 3 remediation branch and MSME PRAMAAN are untouched.
This revises the first report (`PROCESS_DEVIATION_TRACING.md`) for Candidates A and C as provisionally approved.

**Evidence labels.** **[V]** verified in this session from a primary artifact (the GS1 EPCIS repository checked out locally at the
documented pin `6f71468…`: JSON schema, example documents, conformance test cases; not the normative PDF). **[W]** read from a web
page (vendor or standards body summary). **[B]** my own background knowledge or design reasoning, not verified externally.
A correction to my first report: I had guessed EPCIS sensor exception codes such as `BELOW_MIN`; the schema defines no such codes (section 7).

## 0. What changed from R1

1. Exposure and damage are now separate, with a mandatory ladder (section 1). R1's "possible = UNRESOLVED" blurred them.
2. The deviation window itself is uncertain, so it has an inner and an outer bound (section 2). R1 treated the window as exact.
3. Interval soundness is defined against a possible-worlds semantics and tested against an exhaustive oracle (sections 3, 7).
4. Exclusion is a conjunction of eight named evidence conditions (section 4).
5. Revision dependencies are enumerated and the dependency index is derived from the evaluator's own reads (section 6).
6. The prototype boundary is smaller on features and larger on assurance; a design stage precedes any build (section 10).

## 1. Exposure established vs possible vs physical defect confirmed

Three different questions that must never share a field or a label:

| Level | Question | Evidence it can rest on | Never inferred from |
| --- | --- | --- | --- |
| L0 Deviation notice | What condition is alleged, where, when, and what counts as qualifying? | A versioned, authored notice | Timestamps |
| L1 Exposure | Was this unit-operation subject to the alleged condition? | Pass records, coverage, trust profile, parameter evidence | Product condition |
| L2 Defect | Is the product physically nonconforming? | A qualified inspection or test result | Any timestamp or genealogy fact |

Output fields (names are proposals, see U1): `exposureStatus` ∈ {`EXPOSURE_ESTABLISHED`, `EXPOSURE_POSSIBLE`, `EXCLUDED_WITH_EVIDENCE`};
`defectStatus` ∈ {`NOT_ASSESSED`, `CONFIRMED_BY_INSPECTION`, `CLEARED_BY_INSPECTION`}; `operationalAction` ∈ {`HOLD`, `RELEASE_ELIGIBLE`};
`reviewRequired`. Timestamp overlap can set only `exposureStatus`. `defectStatus` changes only on an inspection event with a qualified protocol,
mirroring the existing engine's rule that a historical-operation policy needs an explicit PASS protocol and inspection after the announcement.
The word "affected" is avoided in this feature: in the recall engine it means "holds a recalled lot", and reusing it would imply damage.
Operator-facing text must say "exposed to the alleged condition", never "defective".

### Is any qualifying overlap sufficient to establish exposure?
Only under a policy that says so. The notice must declare a **qualifying rule**; there is no default (an unspecified rule is rejected,
as an unspecified recall scope is):

| Qualifying rule | Meaning | Overlap with the certain window | Overlap with the possible window only |
| --- | --- | --- | --- |
| `OPERATED_IN_WINDOW` | Being processed at the station while the condition may have existed is exposure | ESTABLISHED, because the *unit was exposed to a possibly nonconforming station*; this says nothing about product damage | POSSIBLE |
| `PARAMETER_VIOLATED` | Exposure needs the pass's own parameter evidence to violate limits | ESTABLISHED only with in-pass parameter evidence over the whole pass | POSSIBLE; absent parameter evidence also POSSIBLE |
| `STATE_CONDITION` | Exposure needs a recorded station state (mode, tool ID) | Same as above using state records | POSSIBLE |

Consequence for the UI and reports: ESTABLISHED means "the policy's qualifying condition certainly held for this pass under the
declared time bounds". Even that is a statement about the process record, not about the part.

## 2. Window semantics: the deviation interval is uncertain too

A deviation is usually discovered, not observed: "last verified good at 10:00, first detected bad at 11:05". Two intervals follow:

* **W_possible** = onset could be anywhere between the last trusted good verification and the first trusted bad detection, to the trusted
  end/correction time. Anything intersecting it may be exposed.
* **W_certain** = times for which a trusted record shows the bad condition. If only isolated bad readings exist, W_certain is those instants,
  **unless the notice declares a continuity assumption** (the condition persisted between bad readings). Continuity is an assumption that
  must be explicit, attributable and revisable (U-continuity); it is never defaulted.

If the end of the deviation is unknown, W_possible is open-ended to the notice's last trusted evidence and the system holds to the present.

## 3. Sound uncertainty intervals

### 3.1 Semantics (possible worlds)
Each event time is an unknown true time within bounds `[lo, hi]`. A *world* assigns every unknown to a value within its bounds and respecting
declared constraints. For a pass with unknown entry `a ∈ [a_lo, a_hi]` and exit `b ∈ [b_lo, b_hi]`, `a ≤ b`:

* overlaps window `[t0, t1]` in a world iff `a ≤ t1 and b ≥ t0`;
* **definitely overlaps** iff it overlaps in all worlds: `a_hi ≤ t1 and b_lo ≥ t0`;
* **definitely disjoint** iff in all worlds `b < t0` or `a > t1`. The cheap sufficient test is `b_hi < t0` or `a_lo > t1`; the exact test needs worlds, which the oracle (section 7) enumerates;
* otherwise it *possibly* overlaps.
Establishing uses W_certain and "definitely"; exclusion uses W_possible and "definitely disjoint" (plus the evidence conditions of section 4).
Interval arithmetic implements this; the oracle checks it against exhaustive world enumeration on discretised time.

### 3.2 Where bounds come from
Declared error alone is not sound unless validated; so each bound is the *intersection* of declared and anchored limits, and a contradiction is a finding:

| Bound | Source | Notes |
| --- | --- | --- |
| Declared `± δ` | Versioned clock trust profile per source/station | An unknown source gets no declared bound, hence no exclusion |
| Upper limit | The ledger's own receipt time of the capture (our clock) | An event cannot be true-timed after we received it. Assumes the ledger clock is sane and flags future-dated claims |
| Lower limit | The same source's previous event, if sequence order is declared time-monotone | An assumption (stated per profile) |
| Cross-entity anchors | A unit's exit at station 1 ≤ its entry at station 2; handoff, scan, gate events | Needs single-location semantics for a unit; conflicts are flagged |
| Sync anchors | NTP/PTP sync records, calibration of the clock | Optional; tighten δ and enable a drift term |
Empty intersection ⇒ **time anomaly**: the pass becomes `EXPOSURE_POSSIBLE`, a `CLOCK_ANOMALY` flag is raised on the source, and no side is chosen.
This is the time-anchor idea from digital forensics applied to manufacturing [W: DFRWS time anchors, 2024]; the application is mine **[B]**.

### 3.3 Missing and open-ended data
| Case | Interval rule |
| --- | --- |
| Entry known, exit missing | `b ∈ [a_lo, B]`, `B` = earliest trusted later event proving the unit left (a later event at a different station, or shipment); if none, `B = +∞`, so it cannot be excluded for any window after `a_lo` |
| Exit known, entry missing | `a ∈ [A, b_hi]`, `A` = latest trusted earlier event for the unit (creation, previous station); none ⇒ `−∞` |
| Both missing but unit is routed through S | Pass is unknown: POSSIBLE for every window within the unit's life interval |
| Two overlapping passes at different stations | Contradiction (single-location), POSSIBLE plus integrity flag |
| Exit before entry | Contradiction, POSSIBLE plus integrity flag |
| Delayed delivery | Not a defect in itself; the receipt-time upper limit handles it. A delivery long after the claimed time widens nothing but is reported |
| Clock steps, DST, missing offset | Times are normalised to UTC at ingestion; an event without a usable offset has no exclusion value |
| Drift | Optional `δ(t) = δ0 + ρ·(t − last_sync)`; omitted from the MVP (U4) |

### 3.4 What soundness does and does not mean
Soundness is **conditional on the declared bounds being true**. The system can prove its own consistency and detect contradictions against
anchors; it cannot prove that a clock was never silently wrong by more than its declared bound. The mitigation is governance plus
measurement: a profile revision is an authored, versioned object, and a "bound audit" reports how often declared bounds were contradicted
by anchors. The honest claim is "exact given the declared trust model", not "correct whatever the clocks did".

## 4. Evidence required for exclusion

A unit-operation is `EXCLUDED_WITH_EVIDENCE` only if **all** of the following hold and each is recorded as evidence ids in the decision:

| # | Condition | Failure ⇒ |
| --- | --- | --- |
| E1 | **Identity.** Serial identity, or lot-level identity where the whole lot is evaluated together (a lot is excluded only if every possibly-matching unit is) | POSSIBLE, reason `IDENTITY_AMBIGUOUS` |
| E2 | **Route completeness.** The unit's required route is known (routing/work-order evidence) and every route step that could be S, or an equivalent station in the notice's equivalence class, has a trusted pass record or a trusted proof that the step ran elsewhere | POSSIBLE, `ROUTE_UNKNOWN` / `STEP_UNACCOUNTED` |
| E3 | **Unit-stream completeness.** The unit's own event stream has no sequence gap and its sessions are closed, so no pass is missing | POSSIBLE, `UNIT_COVERAGE_GAP` |
| E4 | **Station coverage.** For passes with *missing or open* bounds, station S's capture stream covers the whole uncertainty hull: no gap, session closed. Not needed when the unit has trusted passes and E3 holds, but required for the never-visited path | POSSIBLE, `STATION_COVERAGE_GAP` |
| E5 | **All passes.** Every pass of the unit at S is classified, including every rework or re-pass (rework passes are evidenced through work-order history, E2/E3) | POSSIBLE, `REWORK_PASS_UNACCOUNTED` |
| E6 | **Station identity.** `stationId` resolves in the versioned station registry; if the notice is asset-scoped, the pass records the asset (tool, fixture, head) or the station has exactly one asset | POSSIBLE, `STATION_IDENTITY_UNPROVEN` / `ASSET_UNRECORDED` |
| E7 | **No unresolved conflict.** No contradiction, no pending or unauthorised correction, no error declaration awaiting its corrective event | POSSIBLE, `CONFLICTING_RECORDS` |
| E8 | **Disjointness proof.** Hull disjoint from W_possible (section 3.1), or, under `PARAMETER_VIOLATED`, in-spec parameter evidence spanning the whole pass from a recorded, calibrated device | POSSIBLE, `HULL_OVERLAPS_WINDOW` / `PARAMETER_EVIDENCE_MISSING` |
Two exclusion paths: **positive-pass** (trusted passes all outside the window) and **never-visited** (route proves S is not a step, with E3/E4).
A removed or provisional record never counts as positive evidence. An untrusted (manual or unsynced) time source contributes bounds but cannot satisfy E8 unless
its declared δ is finite and in the profile.

## 5. Safe propagation

### 5.1 Entities and edges
`unit-operation → target entity`, where the notice declares an **effect scope**: `ENTITY_PROCESSED` (the item on the station), `COMPONENTS_INSTALLED_DURING_PASS`
(an assembly station affecting parts it installed), or `WHOLE_ASSEMBLY`. Exposure then flows by inheritance to the assembly and the finished motor and on to shipments.
Lattice: `ESTABLISHED > POSSIBLE > EXCLUDED`; a parent takes the worst of its own operations and every inherited path (monotone join).

### 5.2 Removed components and historical exposure
The notice declares a **propagation basis**, parallel to the engine's `exposureBasis`:

| Basis | Removed exposed component | Motor result |
| --- | --- | --- |
| `CURRENT_INSTALLATION` | Motor is cleared of that component only with trusted removal evidence (not provisional, not untrusted) | Motor excluded for that path, but the **removed component stays exposed as an object**: it may sit in stock, be scrapped, or be reinstalled elsewhere; serial identity is followed, lot-only identity propagates lot-wide to every possible use |
| `HISTORICAL_CONTACT` | Removal does not clear (the component may have damaged neighbours, contaminated, over-torqued) | Motor stays at the component's level until a qualified PASS inspection protocol after the announcement clears it (reusing the engine's historical-operation concept) |
Unknown slot occupant, or an install/removal gap, is POSSIBLE (the existing slot-reconciliation behaviour), never excluded.

### 5.3 Shipments
A shipment inherits the motor's status via the ledger-backed shipment event. Rules: shipment before the notice still inherits and creates a notification
obligation (existing mechanism, never a delivery claim); a shipment event *after* a hold is a **hold breach** flag; a motor with an exposed status and no shipment record is "shipment status unknown", not "not shipped" (no phantom shipment, as today);
field replacements or rework after shipment are invisible to the ledger and are a stated limit.

## 6. Revision dependencies beyond time windows

A decision is a pure function of a closed set of inputs. Every input is a versioned, digest-identified object, and the decision stores the digests it read:

| Input | Examples of revision | Direction risk |
| --- | --- | --- |
| Deviation notice | window, stations, qualifying rule, effect scope, propagation basis, continuity assumption, asset scope | Widening ⇒ exclusion may be withdrawn (obligation). Narrowing ⇒ release only through full E1–E8, never by "shrinking" |
| Parameter limits | spec tightened/loosened | Same as above, per pass with parameter evidence |
| Station registry | alias, equivalence class, asset set, routing/route definitions | A merged or split station changes E2/E6 for many units |
| Clock trust profile | δ per source, monotonicity declarations, drift | Smaller δ can newly exclude (needs authored justification); larger δ can withdraw exclusions (obligation) |
| Source and station coverage | a session closed late (enables E4), a gap discovered | Can newly enable *or* remove exclusion |
| Unit event stream | late events, out-of-order delivery | Order must not change the result at the same watermark |
| Genealogy corrections | EPCIS-style error declarations (section 7), supersession, install/removal corrections | A corrected pass time may move a pass into the window |
| Shipment and inspection events | new shipment, inspection result | Shipment adds obligations; inspection can change `defectStatus` only |
| Evaluator version | classifier change | Treated as a new semantics profile, never rewriting history (as the engine's profiles are) |
**Dependency index.** The evaluator returns the set of input keys it consulted (e.g., `unit:U#stream`, `coverage:S@[t_a,t_b]`, `profile:src@v`,
`registry:S@v`, `notice:N@v`). An index maps key → decisions. A revision invalidates the readers of the changed key, intersected with the changed interval where applicable.
Deriving the read-set from the evaluator, instead of maintaining it by hand, is what keeps the index a superset of true dependencies. Missing reads are the main way an
incremental scheme silently releases a unit, so this is a safety property, not an optimisation.

## 7. GS1 EPCIS 2.0: sensor and correction semantics (verified against the pinned repository)

Source: `gs1/EPCIS` at `6f71468231838e424bb5dfa836e006e8dc69615c`, JSON schema, example documents and conformance test case TCR-53. The normative PDF text
was not available to me; statements about intent beyond the schema are marked.

**Sensor data [V].**
* `sensorElementList` is allowed on ObjectEvent, AggregationEvent, TransactionEvent, TransformationEvent and AssociationEvent.
* A `SensorElement` has an optional `sensorMetadata` and required `sensorReport[]`.
* `sensorMetadata`: `time`, `startTime`, `endTime`, `deviceID`, `deviceMetadata`, `rawData`, `dataProcessingMethod`, `bizRules`.
* `sensorReport` (only `type` required): `type` (a measurement type such as Force, Angle, Temperature, Frequency, Count… or a vendor URI), `exception`, `time`, `value`, `minValue`, `maxValue`, `meanValue`, `sDev`, `percRank`, `percValue`, `uom`, `stringValue`, `booleanValue`, `hexBinaryValue`, `uriValue`, `component`, `deviceID`, `deviceMetadata`, `rawData`, `dataProcessingMethod`, `bizRules`, and others.
* **`exception` is only `ALARM_CONDITION` or `ERROR_CONDITION`** (or a vendor URI). It carries neither the violated limit nor its direction. The limits are not in the event; `bizRules` is just a URI reference. Therefore an EPCIS sensor flag can be *evidence that an alarm was raised*, but our own parameter-limit object (section 6) is required to decide anything.
* Inline attributes may appear in `sensorMetadata` or in `sensorReport` but must not appear in both (TCR-53 step 29: capture refuses such a document).
* `startTime`/`endTime` give a **measurement interval**; EPCIS events themselves carry a single `eventTime`. There is no native "pass interval" for an event and no uncertainty or accuracy field on any time.

**Time [V].** Common properties: `eventTime`, `recordTime` (optional in the schema; example documents omit it), `eventTimeZoneOffset` (pattern `±hh:mm`, range to ±14:00), `eventID`, `errorDeclaration`. Nothing models clock trust, so the trust profile is necessarily ours.
Implication: a pass is either two events (start, end), or one event with `sensorMetadata.startTime/endTime`; both are profile decisions (U3).

**Transformation [V].** `TransformationEvent` has `inputEPCList`/`inputQuantityList`, `outputEPCList`/`outputQuantityList`, `transformationID`, `bizStep`, `disposition`, `readPoint`, `bizLocation`, `sensorElementList`, `ilmd`. It fits "operation consumed inputs and produced outputs at a readPoint" and lets a station be a `readPoint`. A station identity registry is still ours; `readPoint` is a URI, not a verified asset.

**Corrections [V schema/examples; intent partly W/B].**
* `errorDeclaration` = {`declarationTime` (required), `reason` ∈ {`did_not_occur`, `incorrect_data`} or a vendor URI, `correctiveEventIDs[]`}.
* The official example document contains the declared-erroneous event **and** the corrective event: the erroneous event is annotated, not removed. A third-party guide describes the declaration as re-capturing the erroneous event under the same `eventID` with the declaration added [W, unverified against the spec].
* Mapping to our ledger: the declaration is an append-only correction event that supersedes the original (our `supersedesEventId`), never a deletion.
  `did_not_occur` removes the pass as positive evidence (a unit whose only evidence of passing outside the window was that pass returns to POSSIBLE). `incorrect_data` replaces it with the corrective events, whose times may move the pass into the window.
  `declarationTime` after the decision's watermark is a late correction, hence a revision trigger and, if it withdraws an exclusion, an obligation.
  The declaration itself must be an authorised actor's event: a forged `did_not_occur` could remove a positive record.

## 8. Prior art, re-examined

| System | What I found | Gap relative to this proposal |
| --- | --- | --- |
| **Siemens Opcenter Execution Discrete 2507** [W] | Containment feature: nonconforming items found (via Opcenter/Insights Hub Traceability) raise a Containment Request; Execution Discrete imports it and marks units "In Containment" so they cannot advance; **cancelling the request releases them through the same import**. Genealogy finds related production items. | Containment is driven by a request and release by cancelling it; I found no evidence-of-exclusion rule, no timestamp uncertainty, no coverage condition. Parameter-level exposure linkage is **not documented** in what I read |
| **Siemens Opcenter Execution Medical Device & Diagnostics** [W brochure] | Forward/backward genealogy of product, process and quality data; automatic nonconformance generation; single as-built record | Marketing level; same gap |
| **Siemens MindSphere Traceability** [W] | backward search to origin, then same machine/operation/time window, then forward search | The query workflow; no uncertainty semantics found |
| **Tulip** [W] | Records component, operator and machine data per station; trace a serial or lot forward/backward to locate and contain affected units after a warranty claim; routing can **hold a batch when an out-of-spec measurement is recorded** | Point-of-detection control and genealogy lookup. Retrospective window exposure with uncertain clocks and certified exclusion: not found |
| **Trace-X / Catena-X CX-0125** [W] | Quality Investigations (to suppliers), Quality Alerts (to customers) and Block Information; parts referenced by Catena-X IDs (Industry Core Part Instance, CX-0127); partners see only direct neighbours | Cross-company notification and part identity. Which parts are exposed inside one factory under uncertainty is not what this models. Normative payload fields not read |
| **GS1 EPCIS 2.0** [V] | Events, sensor data, error declaration (section 7) | Carries facts; no exposure, uncertainty or exclusion semantics |
Updated novelty assessment: unchanged in kind. The query is commodity; interval timestamps, three-valued logic and incremental maintenance are known techniques.
The claim that remains defensible is the **assurance combination**: an explicit epistemic ladder, possible-worlds-exact classification under a declared trust model, evidence-gated exclusion, revision-aware
re-evaluation proven equal to full evaluation, and measured false-release counts. The Opcenter containment-by-request model and Tulip hold-on-measurement are the closest *workflow* competitors; neither is a rival on
*assurance semantics*, but I could not read their full documentation and cannot rule out undocumented features.

## 9. Safety invariants

Each is a testable property. IDs are stable for the audit.

| ID | Invariant |
| --- | --- |
| S1 | **Epistemic separation.** `exposureStatus` is never derived from, and never implies, `defectStatus`. `defectStatus` changes only on a qualified inspection event |
| S2 | **Fail closed.** Absence of a record never yields `EXCLUDED_WITH_EVIDENCE`; every status other than excluded yields `HOLD` |
| S3 | **Proof-carrying exclusion.** Exclusion requires E1–E8; the decision lists the evidence ids and the profile, registry, notice and coverage digests used |
| S4 | **Exactness under the declared model.** Classification equals the possible-worlds oracle on all small instances |
| S5 | **Monotone under information loss.** Removing any single event, widening any bound, or removing a coverage session never makes a status safer |
| S6 | **Unknown trust is non-excluding.** A source or station without a profile entry cannot support E8 |
| S7 | **Contradiction is surfaced.** Contradictory times, locations or corrections yield POSSIBLE plus a flag; no side is silently chosen |
| S8 | **Worst-of propagation.** Parent status ≥ every inherited child status; clearing a removed component requires trusted removal evidence and basis `CURRENT_INSTALLATION`; lot-only identity propagates lot-wide |
| S9 | **Shipment honesty.** Shipments inherit; unknown shipment status is not "not shipped"; shipment after hold raises a breach flag |
| S10 | **Explicit scope.** A notice without stations, window bounds, qualifying rule, effect scope and propagation basis is rejected; nothing is defaulted |
| S11 | **Immutable, digest-pinned versions.** A decision stores the version digest of every input it read; a revision creates a new version and never edits the old |
| S12 | **Withdrawal creates a durable obligation.** Any change from excluded to non-excluded for a unit whose exclusion was recorded creates an obligation until explicit resolution; no delivery is ever claimed |
| S13 | **Incremental equals full.** For every history and every revision sequence, `INCREMENTAL == FULL` on decision bodies |
| S14 | **Order insensitivity.** Delivering the same event set in any order at the same watermark yields identical decisions |
| S15 | **Replay.** Every issued decision replays identically under its recorded input digests, and a replay is compared to the stored decision, not merely run |
| S16 | **History integrity.** The existing decision chain, anchor and obligation-log protections cover the new decision kind |
| S17 | **No release by scope change alone.** Narrowing a notice or profile can release a unit only by that unit passing E1–E8 under the new inputs |

## 10. Unresolved decisions

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| U1 | Vocabulary | Reuse `AFFECTED/UNRESOLVED` or the new `EXPOSURE_*` plus `defectStatus` | New names (S1); keep chip layout |
| U2 | Qualifying rule set | Only `OPERATED_IN_WINDOW`, or all three | MVP: only `OPERATED_IN_WINDOW` and `PARAMETER_VIOLATED` as *evidence of non-exclusion*, not exclusion by parameters |
| U3 | Pass representation | Two events; one event with `sensorMetadata.startTime/endTime`; `TransformationEvent` + `readPoint` | Two events (entry, exit) in our native profile, mappable to EPCIS later |
| U4 | Drift model | None, linear drift with sync anchors | None in MVP; declare δ conservatively |
| U5 | Routing source | Work-order/routing events in the ledger, or an external MES import | Ledger events authored by an authorised MES source |
| U6 | Asset vs station scope | Station only, or asset | Station only in MVP; asset-scoped notice ⇒ POSSIBLE unless the station has one asset |
| U7 | Release via inspection | Allow `CLEARED_BY_INSPECTION` to release, or hold regardless | No release via inspection in MVP; record only |
| U8 | Trust-profile governance | Who authors, approves and signs a profile revision | Single authorised role with an authored justification; audit log |
| U9 | Continuity assumption | Default off, or per notice | Per notice, explicit, default absent (⇒ point-only W_certain) |
| U10 | Engine placement | Sibling pure module with its own pinned tree and replay, or extending `recall-engine` | Sibling module; do not touch the pinned v3 engine |
| U11 | Batch processes (ovens, baths) | Per-unit passes, or batch windows with membership | Out of MVP; any batch step ⇒ POSSIBLE until modelled |
| U12 | Time normalisation | Reject events lacking a UTC offset, or treat them as non-excluding | Accept but non-excluding |
| U13 | Read-set granularity | Per unit/interval, or coarse per source | Per unit and coverage interval; coarse is safe but defeats the point |
| U14 | What attests station-stream closure | A source-session close event, an operator attestation, or a heartbeat | Source-session close (as today for motors) |
| U15 | Hold semantic for shipped goods | Notification obligation only, or also customer-facing recall flow | Obligation only; no external delivery |

## 11. Independent adversarial testing and the equivalence claim

**Independence.** Tests I write against my own classifier prove consistency, not correctness. Required: (a) a scenario pack authored by a party who has not seen the implementation, in a declared plain format with hand-derived expected status and a rationale; (b) an **exhaustive possible-worlds oracle** written separately from the interval code; (c) a generator that shares no helper code with the classifier; (d) mutation testing of the dependency index. Until (a) exists, results are labelled non-independent.

**Properties and checks.**
* S4 exactness: random small instances (integer time grid, bounded unknowns) compared with the oracle: classification must equal oracle-derived status under the evidence conditions.
* S5 monotonicity: delete one event / widen one bound / drop one coverage session ⇒ status never moves toward excluded.
* S13 equivalence: for random histories and random revision sequences over **all** input kinds in section 6, `INC == FULL`; reported with the count of revisions applied, and including revisions that arrive between events.
* Mutation test: remove one key from the evaluator's read-set; the equivalence suite must fail. A suite that cannot detect this is too weak.
* S14: shuffled arrival order, same watermark, identical result.
* Scenario families the independent author should cover: onset uncertainty, isolated bad readings with and without continuity, open-ended and double-missing passes, rework passes with one pass lost, correction `did_not_occur` of the only positive record, corrected time moving a pass into the window, clock anomaly against an anchor, alias/merged stations, lot-only identity with partial removal, removal followed by reinstall elsewhere, motor shipped before the notice, hold breach, late coverage closure that enables an exclusion, profile tightening that withdraws one, narrowing without evidence.
* Baselines for the value claim: a naive "point timestamp, no-record means unaffected" query must show false releases on the same scenarios; the classifier must show zero, with the over-hold rate reported against the skew bound.

## 12. Minimum viable prototype boundary (proposal, not frozen)

Gate: **design approval first.** The prototype is not started until the independent scenario pack author is named and U1, U3, U5, U7 and U10 are decided.

**In scope.**
* One station, one deviation notice with explicit W_possible, W_certain (point-only unless continuity is declared), qualifying rule `OPERATED_IN_WINDOW`, effect scope `ENTITY_PROCESSED`, propagation basis `CURRENT_INSTALLATION`.
* Entry/exit pass events; static clock trust profile with receipt-time, same-source monotone and cross-station handoff anchors; clock anomaly detection.
* Open-ended and missing passes, rework passes, conflicting records, `did_not_occur`/`incorrect_data` corrections as supersession.
* Propagation to component → motor → shipment, with removal handling and lot-only identity.
* Revisions of: notice window, trust profile, coverage, genealogy correction, with dependency read-set capture and an obligation on every withdrawn exclusion.
* The oracle, the property suite, mutation test of the index, and an independently authored scenario pack.
* One UI view: station timeline with uncertainty hulls, the two windows, per-row reasons, and the exposure/defect separation.

**Out of scope (named so nobody assumes otherwise).** Parameter-trace exposure and sensor ingestion beyond storing an `ALARM_CONDITION` flag; sequence-bracketing inference; drift; batch processes; asset-level scope; inspection-based release; multiple concurrent notices; cross-company notification; any change to the pinned v3 engine; external delivery of notices.

**Cut line under time pressure.** Keep, in order: classifier + oracle + independent scenarios; propagation; revisions with INC==FULL; obligations; UI. Drop the UI before dropping any assurance item. A 36-hour build is only credible if the oracle and scenario pack exist; otherwise the headline claim (zero false releases) cannot be made honestly. If that cannot be arranged, the recommendation is to demo the design and the oracle, not an unproven classifier.

## 13. Limitations of this research
* Prior art for Opcenter, Tulip and Trace-X rests on vendor documentation and summaries. Absence of a feature in what I read is not evidence it does not exist.
* EPCIS facts come from the pinned repository's schema, examples and conformance cases, not the normative specification text; semantic intent (for example, how repositories assign `recordTime`) is not verified.
* No real clock-error data, route data or station data was available; all numbers in examples are illustrative.
* The invariants are my proposal; they have not been reviewed by a manufacturing quality engineer.
* The "exact under the declared model" claim does not cover clocks that are wrong by more than their declared bound.

## Sources
[Opcenter Execution Discrete 2507](https://blogs.sw.siemens.com/opcenter/whats-new-in-opcenter-execution-discrete-2507/) ·
[Opcenter Execution Discrete](https://www.siemens.com/en-us/products/opcenter/execution/discrete/) ·
[Opcenter Execution Medical Device & Diagnostics brochure](https://www.plm.automation.siemens.com/media/global/en/Siemens-SW-Siemens-Opcenter-Execution-Medical-Device-and-Diagnostics-FS-45024-C13_tcm27-61667.pdf) ·
[Tulip: genealogy and traceability use case](https://support.tulip.co/docs/genealogy-and-traceability-use-case) ·
[Tulip: industrial equipment](https://tulip.co/industries/industrial-equipment/) ·
[Tulip: defect and non-conformance management](https://tulip.co/quality/non-conformance-management/) ·
[CX-0125 Traceability Use Case](https://catenax-ev.github.io/docs/next/standards/CX-0125-TraceabilityUseCase) ·
[Traceability KIT](https://eclipse-tractusx.github.io/docs-kits/kits/traceability-kit/adoption-view/) ·
[Industry Core KIT notifications](https://eclipse-tractusx.github.io/docs-kits/kits/industry-core-kit/software-development-view/notifications/) ·
[Walmart EPCIS error declaration (third-party description)](https://developer.walmart.com/suppliers/docs/error-declaration) ·
[GS1 EPCIS repository](https://github.com/gs1/EPCIS) (pin `6f71468…`, checked out locally) ·
[MindSphere backward/forward genealogy](https://documentation.mindsphere.io/MindSphere/apps/traceability/backward-forward-genealogy.html) ·
[Vanini et al., DFRWS (time anchors)](https://dfrws.org/?p=11932)
