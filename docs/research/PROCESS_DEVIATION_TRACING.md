# Process-deviation impact tracing: research report

Research only. Branch `research/process-deviation-tracing`, from `5ac0a168` (safety remediation). No code, schema or
architecture decision is made here; nothing is merged or deployed. MSME PRAMAAN untouched.

**Evidence quality.** External prior art below comes from a handful of standard-mode web searches and vendor pages.
"Not found" means *not found in this search*, not "does not exist". Statements marked **[background]** are my own
domain knowledge, not verified in this session. Before any novelty claim is made publicly, the checks in section 9 are required.

## 1. The problem, stated precisely

A *process deviation* is: station/equipment **S**, a time window **W = [t0, t1]** (or a work-order/recipe scope), and a
parameter condition (e.g. press torque outside spec, oven below cure temperature, tool out of calibration). The
question is: *which finished motors and shipments carry a part, or an operation, that was exposed?*

The recall problem we already solved is keyed on **what** was installed (lot, part, slot). This one is keyed on
**when and where** it was processed. That moves the central difficulty from identity to **time and coverage**: whether
a given unit's pass through S falls inside W depends on timestamps that can be missing, late, manually entered, skewed
or contradictory, and on whether we even have the records that would show it did *not*.

## 2. What exists in our system today (gap analysis)

| Capability | Present at 5ac0a168 | Gap for deviations |
| --- | --- | --- |
| Append-only, hash-chained evidence; per-source sequence numbers; capture sessions/coverage | yes | Coverage is per motor source; needs per-*station* coverage |
| `occurredAt`, `recordedAt`, `timeSource` on every event | yes | `timeSource` is carried but **not used to widen uncertainty**; engine treats time as a point |
| Three-valued finding (AFFECTED / UNRESOLVED / EXCLUDED_WITH_EVIDENCE) with fail-closed exclusion | yes (keyed on lot/part/slot) | Needs a second exposure kind |
| Material/bearing/shipment genealogy; slot attribution on install/removal | yes | Station-pass events do not exist: `TYPES` has no station, operation or process-parameter event |
| Versioned decisions, obligations, replay, history chain/anchor | yes (remediated) | Reusable as is for scope revisions |
| Policy = immutable scope per database | yes | A *deviation notice* needs revisions (window changes) |

Reusable almost unchanged: ledger, coverage idea, decision lifecycle v2, obligation registry, replay discipline, UI shell.
New: station registry with clock trust profile, station-pass and parameter events, a deviation-notice object, an exposure
classifier. The pinned v3 engine cannot express "processed at S during W" without extension, so a deviation evaluator would be
a **separate pure module** (a new engine profile or sibling), not an edit of `recall-engine/`. That choice is deferred.

## 3. The core technical questions

### 3.1 Events, stations, work orders, parameters
Minimum useful record per unit-operation: unit/component identity (serial, or lot-only), station id, operation id, work
order, `in` and `out` events (or one event with a duration), operator/actor, and either a parameter summary
(min/max/mean, spec result) or a pointer to a trace. Station identity needs a registry: stations get replaced, renamed
and shared across lines, and an alias error silently turns "excluded" into "never looked".
Standards supply vocabulary, not these semantics: ISA-95 / IEC 62264 and ISA-88 / IEC 61512 define equipment and
activity models, and B2MML and the OPC UA ISA-95 companion spec carry them
([ISA-95 OPC UA](https://reference.opcfoundation.org/ISA-95/docs/1), [overview](https://teeptrak.com/en/mes-architecture-isa-95-implementation-2026/)).
IPC-1782 (electronics) grades process traceability P1–P4 with "process name/ID and time in and out of each PCB" as common
elements, and levels are agreed between user and supplier ([IPC-1782 TOC](https://www.electronics.org/TOC/IPC-1782.pdf),
[summary](https://emsnow.com/?p=37472)). That is the closest mainstream statement of the data we would need, in a different industry.

### 3.2 Timestamps: missing, delayed, untrusted, conflicting
| Condition | Example | Proposed treatment (research position) |
| --- | --- | --- |
| Missing | `in` without `out` | Pass interval is open-ended up to the next record for that unit/station; cannot be excluded unless a later trusted event bounds it |
| Delayed | offline sync, `recordedAt` ≫ `occurredAt` | `recordedAt − occurredAt` is *evidence about the source clock*, not noise; widen uncertainty, never narrow |
| Untrusted | manual entry, device not synced | Trust tier per `timeSource`; manual time gets a large bound or is non-excluding |
| Conflicting | unit "in" at two stations at once; `out` before `in`; two sources disagree | Treat as integrity issue: unit-operation becomes UNRESOLVED, never silently resolved by picking one |
Model: each timestamp becomes an interval `[t − δ, t + δ]` with δ from the station/source trust profile, tightened only by
*anchors* (an event whose time is corroborated by an independent trusted source). Forensics literature treats exactly this
problem: timestamps are unreliable without a check of whether the clock was right, hence "time anchors"
([Vanini et al., DFRWS](https://dfrws.org/?p=11932), [Schatz et al. 2006](https://dfrws.org/presentation/a-correlation-method-for-establishing-provenance-of-timestamps-in-digital-evidence/));
and distributed-systems practice argues for carrying skew bounds in timestamp comparisons
([arXiv 2604.21361](https://arxiv.org/pdf/2604.21361), [netdev](https://netdevconf.org/0x1A/sessions/tutorial/making-time-uncertainty-a-first-class-concept-in-linux-timing.html)).
Borrowing is therefore *method*, not a manufacturing result.

### 3.3 Definitely vs possibly affected; safe exclusion
Map onto the existing three-valued contract (no new headline vocabulary; "possibly" is UNRESOLVED with reason codes):
* **AFFECTED (definite):** trusted station identity, trusted pass interval wholly inside W (or inside a parameter-out-of-spec span).
* **UNRESOLVED (possible):** interval overlaps W; or interval unknown/open; or timing untrusted; or station identity uncertain; or conflicting records; or processing coverage gap. Operational action: hold.
* **EXCLUDED_WITH_EVIDENCE:** requires *all* of: (1) a positive record that the unit passed S (or never needed S) with trusted identity; (2) the full uncertainty interval disjoint from W, or trace evidence that parameters stayed in spec; (3) station coverage complete over the relevant span (no sequence gap, session closed); (4) no conflicting or superseded record; (5) every re-pass (rework) accounted for; (6) for batch processes (ovens, baths) the batch window, not the unit time.
Absence of a record is never exclusion. This is the same fail-closed rule we proved for slots; here the "slot occupancy gap" becomes a
"station coverage gap". Correlation is not causation either: genealogy only shows what was *shared*, and a timing coincidence is not proof of exposure
([MindSphere traceability](https://documentation.mindsphere.io/MindSphere/apps/traceability/backward-forward-genealogy.html), [vendor-neutral note](https://ifactoryapp.com/article/batch-genealogy-traceability-lot-to-shipment)).
We treat overlap as *possible*, never as proof.

### 3.4 Propagation: component → assembly → motor → shipment
Exposure attaches to a **unit-operation** and is inherited forward through install edges, valid only for the interval the component was actually installed
(our install/removal and supersession evidence already model this). Rules: a deviation at a *component* station taints that component instance, and
the motor taints through its current (non-removed) install; a deviation at an *assembly* station taints components *installed at that station in W*;
a removed-and-replaced component stops tainting the motor only with removal evidence (same as slot exclusion today); a lot-only identity taints the
whole lot-level uncertainty (existing ambiguity logic). Motor finding = worst of its inherited component and own-operation findings
(AFFECTED > UNRESOLVED > EXCLUDED), shipments inherit the motor's. Customer-facing obligations arise when a previously communicated exclusion is withdrawn
(already implemented as obligations in lifecycle v2).

### 3.5 Scope revisions and selective re-evaluation
Deviation scope is itself revised in practice (window widened after more samples fail; narrowed after calibration records; parameter threshold changed; extra station added).
Needed: a versioned deviation notice (immutable versions, like policy), and re-evaluation of **only** units whose uncertainty interval intersects the symmetric difference of old and new scope,
plus units with new evidence. Safety invariants: widening may turn EXCLUDED into AFFECTED/UNRESOLVED (creates an obligation if the exclusion was communicated); narrowing may release only with the
full exclusion evidence above, never merely because the scope shrank; and the incremental result must equal a full re-evaluation (checkable by property test). This is incremental view
maintenance applied to a safety classifier **[background]**; the contribution would be the safety invariants and the equality proof, not the incrementality.

## 4. Prior art and competitors

| Source | What it does | Relevance |
| --- | --- | --- |
| Siemens MindSphere Traceability: backward search to origin, then "same machine/operation/time window", then forward search | The containment workflow we describe, as a query workflow ([docs](https://documentation.mindsphere.io/MindSphere/apps/traceability/backward-forward-genealogy.html)) | Closest to the *question*; found no uncertainty or certified-exclusion semantics (could not read beyond the docs page) |
| Critical Manufacturing "Genealogic" | Interactive explorer over MES genealogy and production history ([page](https://www.criticalmanufacturing.com/mes-for-industry-4-0/apps/genealogic/)) | Exploration UI, not a decision contract |
| GE Vernova / generic MES genealogy | Material/lot/equipment/operator/exception records, as-built record ([blog](https://gevernova.com/software/blog/mes-traceability-genealogy)) | Supplies the data; "complete record" is assumed |
| Siemens Opcenter, Tulip, others | Not found in this search | Must be checked directly; likely have containment features |
| Trace-X / Catena-X (Tractus-X) | Digital twin per component; quality alerts (to customers) and investigations, "1 up – 1 down" across companies ([Cofinity-X](https://www.cofinity-x.com/products/trace-x), [use case](https://www.cofinity-x.com/use-cases/traceability)) | Inter-company notification and part twins; internal station/time-window exposure not described in what I found. Material is marketing level; semantic model not read |
| GS1 EPCIS 2.0 | Object/Aggregation/Transformation events (inputs → outputs), what/when/where/why; 2.0 adds sensor data (`sensorElementList`) and error declarations ([GS1](https://www.gs1.org/epcis), [launch](https://GS1.org/docs/epcis/epcis_2-0_launch.pdf), [genealogy example](https://docs.eon.xyz/news/epcis-capture-genealogy-queries)) | Natural wire format; **I could not confirm** how sensor readings attach to a TransformationEvent or how exceedance is expressed |
| ISA-95/88, B2MML, OPC UA | Equipment/activity models and exchange | Vocabulary for stations and work orders; no exposure semantics |
| IPC-1782 / IPC-CFX | Graded process traceability for electronics; CFX is a machine message standard (not verified here) | Closest data-requirements analogue |
| Forensics time-anchor work, skew-aware tracing | Interval timestamps and corroboration | Method source; none addresses recall or exposure scoping (search found no manufacturing application) |

**Challenge to novelty.** The *query* (which units ran on S in W, then walk the genealogy) is standard, commercial, and not novel. Interval timestamps and three-valued logic are
classic (Allen interval algebra, Kleene logic **[background]**). Incremental re-evaluation is ordinary. What I could not find, and what is the only defensible claim, is the
**combination under a safety contract**: (a) exclusion that requires positive evidence plus coverage, (b) clock-trust-derived uncertainty feeding that rule, (c) forward propagation to shipments with
withdrawal obligations, (d) deterministic replay and an incremental-equals-full guarantee, and (e) a measured false-release count against a naive baseline. That is an *engineering and assurance* contribution,
moderate novelty at best, and should be pitched as "makes the unsafe default impossible", not "new algorithm".

## 5. What differentiates us from an ordinary genealogy query

| Ordinary genealogy query | Our approach |
| --- | --- |
| Boolean join on trusted, complete data | Three-valued over uncertain, possibly incomplete data |
| No record ⇒ not affected | No record ⇒ unresolved ⇒ hold |
| Timestamp is a point | Timestamp is an interval from source trust and anchors |
| Result is a list | Result carries reasons, evidence ids and replays identically |
| Scope change ⇒ re-run and diff by eye | Versioned scope; selective re-evaluation proven equal to full; withdrawn exclusions create obligations |
| Success = "found the affected ones" | Success = **zero false releases**, with over-hold rate reported |

## 6. Candidate approaches

### A. Uncertainty-interval window classifier (clock-trust model)
* **Core contribution:** per-unit-operation classification (definite / possible / excluded-with-evidence) from station-pass intervals widened by source-trust bounds, with coverage-gated exclusion, then forward propagation to motor and shipment.
* **Closest prior art:** MindSphere/MES time-window containment queries; time-anchor and skew-bound methods from forensics and distributed tracing.
* **Safety/correctness risks:** over-holding (δ too large ⇒ everything UNRESOLVED, system useless); under-bounded δ ⇒ false release (mitigate: δ is configured per source and widened by observed `recordedAt − occurredAt`; unknown source ⇒ non-excluding); batch processes and re-passes; station alias errors; DST/time-zone/step changes; ground truth in tests is author-written (circular).
* **Test scenarios:** pass fully inside W (affected); fully outside with trusted clocks (excluded); straddling edge; skewed clock that moves a pass out of W (must not exclude); missing `out`; two stations claiming one unit; coverage gap in S's sequence; rework re-pass inside W; lot-only identity; component removed before shipment (exclusion only with removal evidence); randomized generator comparing against a naive point-timestamp query (expect naive false releases > 0, ours = 0).
* **Complexity:** medium. New pure classifier (~hundreds of lines), station registry, two event types, tests. No UI research needed beyond a timeline.
* **Integration:** new event types in `profile.py` (a profile/version bump), station/clock registry beside sources, a deviation-notice record analogous to `recall_announcements`, new evaluator module returning the existing decision shape; reuse lifecycle v2 and obligations; **no change to `recall-engine/`** if built as a sibling profile.
* **Recommendation: GO** (the core of any prototype), conditional on the over-hold rate being reported honestly.

### B. Sequence-anchored (logical-order) membership
* **Core contribution:** ignore wall clocks; infer membership from per-station sequence order and bracketing: a unit between a known-bad and a known-good unit in the same station FIFO is bounded without trusting time.
* **Closest prior art:** logical/vector clocks and log ordering **[background]**; no manufacturing recall use found.
* **Risks:** relies on FIFO/single-lane assumptions that fail for parallel stations, batch ovens, rework loops and operator reordering; a wrong order assumption yields a *confident* false exclusion, the worst failure mode.
* **Test scenarios:** FIFO line (bracketing works); swapped order; parallel lane; batch load; sequence gap; sequence reset after station restart.
* **Complexity:** medium-high for correctness, low to demo.
* **Integration:** needs per-station sequence capture (we have per-source sequence for motors, not stations); same event additions as A.
* **Recommendation: REVISE** as standalone. Keep only as an *optional evidence tightener* for A (it may narrow UNRESOLVED to EXCLUDED only where the station is declared strictly FIFO and sequence coverage is complete).

### C. Revision calculus for deviation scope (selective re-evaluation with safety invariants)
* **Core contribution:** versioned deviation notices; dependency index from (station, interval) to unit-operations; re-evaluate only the delta; prove incremental == full; generate withdrawal obligations when widening reverses a communicated exclusion.
* **Closest prior art:** incremental view maintenance **[background]**; MES "re-run the query"; our own recall lifecycle v2.
* **Risks:** index bug skips a unit (silent false release); narrowing treated as release; revision races; stale display of old versions.
* **Test scenarios:** widen (exclusion withdrawn ⇒ obligation persists until resolved); narrow without evidence (stays held); narrow with evidence (excluded); threshold change; add station; random revision sequences with property `incremental == full`; replay of every historical version.
* **Complexity:** low-medium *given A*; not meaningful alone.
* **Integration:** nearly all exists (lifecycle v2 signature, obligation registry, history chain); needs a versioned notice table and an index.
* **Recommendation: GO as a thin layer on A**; NO-GO standalone (without A it is bookkeeping).

### D. Parameter-trace exposure (per-unit exposure from sensor time series)
* **Core contribution:** instead of a window, integrate actual process parameter series per unit (EPCIS sensor data / OPC UA) to determine real exposure, so units inside W but within spec are cleared by data.
* **Closest prior art:** statistical process control / MES parameter limits; EPCIS 2.0 sensor data (attachment semantics unconfirmed).
* **Risks:** needs high-fidelity, trusted, time-aligned series (the very thing that is missing); sensor trust and calibration; large data; invites claims we cannot test with real data.
* **Test scenarios:** series in spec inside W; excursion partly overlapping a unit; missing samples; sensor clock offset.
* **Complexity:** high.
* **Integration:** sensor event ingestion, storage, alignment; EPCIS profile extension with unverified details.
* **Recommendation: NO-GO for the 36-hour scope.** Revisit after A; a coarse "parameter-in-spec summary per pass" (already in A's minimum record) captures most of the value.

## 7. Recommended direction (for approval, not frozen)
A + C, with B as an optional tightener and D deferred. Positioning: **"deviation containment you can prove: never releases on missing evidence, tells you why, and
re-scopes safely."**

## 8. Smallest credible 36-hour prototype

Scenario: bearing press-fit torque tool out of calibration 10:20–11:05 on one press station; one 3-station mini line (press → balance → pack); about 12 synthetic motors.
Deliver:
1. Station registry with per-source clock trust tiers, and `STATION_PASS` + parameter-summary events in the existing ledger profile (additive).
2. Classifier as a pure, replayable function: definite / possible / excluded-with-evidence per unit-operation, propagated to motor and shipment (reusing finding/action vocabulary).
3. Deviation-notice revisions (widen, narrow) using lifecycle v2 and obligations.
4. One UI view: timeline lanes per station with uncertainty bars and the deviation window, motor and shipment rollup, reasons per row.
5. Evidence of value: a generator with randomized skew, missing and conflicting records; report **false releases (naive baseline vs ours)** and **over-hold rate**; property check incremental == full.
Rough budget: 0–6 h data model and scenarios; 6–16 classifier and tests; 16–24 ledger integration and revisions; 24–32 UI timeline; 32–36 demo script, honest limitations. Cut line if late: drop revisions' UI, keep the classifier and the false-release comparison.
Explicit non-goals: real sensor streams, multi-company exchange (Trace-X style), certification claims, any change to the pinned v3 recall engine.

## 9. Open items before any novelty claim or freeze
1. Read Siemens Opcenter, Tulip, Critical Manufacturing and Plex documentation for containment features with uncertainty or evidence semantics.
2. Read the Catena-X traceability semantic model and Trace-X specs beyond marketing pages.
3. Read GS1 EPCIS/CBV 2.0 (ISO/IEC 19987) sensor and error-declaration sections to confirm how process readings and corrections are carried.
4. Check IPC-CFX message definitions and IPC-1782B text (paywalled).
5. Patent and academic search: "interval", "recall", "containment", "traceability" with "clock skew" or "uncertain time".
6. Decide with domain experts what δ values and station trust tiers are realistic; none here are measured.
7. The generator's ground truth is written by us; a re-audit should test with independently authored scenarios.

## Sources
[Trace-X (Cofinity-X)](https://www.cofinity-x.com/products/trace-x) ·
[Traceability use case](https://www.cofinity-x.com/use-cases/traceability) ·
[Tractus-X creation review](https://projects.eclipse.org/node/21851) ·
[GS1 EPCIS](https://www.gs1.org/epcis) ·
[EPCIS 2.0 launch](https://GS1.org/docs/epcis/epcis_2-0_launch.pdf) ·
[EPCIS genealogy example](https://docs.eon.xyz/news/epcis-capture-genealogy-queries) ·
[MindSphere backward/forward genealogy](https://documentation.mindsphere.io/MindSphere/apps/traceability/backward-forward-genealogy.html) ·
[Critical Manufacturing Genealogic](https://www.criticalmanufacturing.com/mes-for-industry-4-0/apps/genealogic/) ·
[GE Vernova MES genealogy](https://gevernova.com/software/blog/mes-traceability-genealogy) ·
[Batch genealogy to shipment](https://ifactoryapp.com/article/batch-genealogy-traceability-lot-to-shipment) ·
[ISA-95 OPC UA](https://reference.opcfoundation.org/ISA-95/docs/1) ·
[ISA-95 overview](https://teeptrak.com/en/mes-architecture-isa-95-implementation-2026/) ·
[IPC-1782 TOC](https://www.electronics.org/TOC/IPC-1782.pdf) ·
[IPC-1782 overview](https://emsnow.com/?p=37472) ·
[Vanini et al., DFRWS](https://dfrws.org/?p=11932) ·
[Schatz et al., DFRWS 2006](https://dfrws.org/presentation/a-correlation-method-for-establishing-provenance-of-timestamps-in-digital-evidence/) ·
[arXiv 2604.21361](https://arxiv.org/pdf/2604.21361) ·
[netdev time uncertainty](https://netdevconf.org/0x1A/sessions/tutorial/making-time-uncertainty-a-first-class-concept-in-linux-timing.html)
