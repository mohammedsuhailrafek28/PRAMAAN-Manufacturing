"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { diffViews, hasChanges, type ViewChanges } from "@/orig/investigation/diff";
import { factsOf, isHistorical, type Facts, type PageView } from "@/orig/contract/gated";
import { projectInvestigation } from "@/orig/contract/views";
import { explain, FINDING_TEXT, humanize, REASONS } from "@/orig/domain/glossary";
import type { EventRecord } from "@/orig/domain/types";
import { PRIORITY_RULES, type Cluster, type DecisionRef, type GroundedValue, type InvestigationView, type MotorRef, type Task } from "@/orig/investigation/projection";
import { CLASSES, LIMITATIONS, OBLIGATION_NOTE, REASON_HANDLING, REJECTION_TEXT, type EvidenceClass } from "@/orig/investigation/taxonomy";
import { ClaimSentence, short, when } from "@/dash/claims";
import { useGatedView } from "@/dash/gated";
import { FindingTag } from "@/dash/ui";

const FIELD_LABEL: Record<string, string> = {
  slot: "Slot", slots: "Slots", gapKind: "Gap kind", materiality: "Materiality", sourceId: "Source (as recorded)", windowFrom: "Window from", windowTo: "Window to",
  gapEventId: "Exception record", boundedByEventId: "Bounding record", observedPart: "Observed part", observedLot: "Observed lot", observedSerial: "Observed serial",
  observedGranularity: "Identity granularity", rejectedReasons: "Rejected because", actorClaim: "Actor (as recorded; a claim)", method: "Method (as recorded)",
  observationStatus: "Observation status", observedEventId: "Observation record", claimedSlot: "Slot named by the claim", candidates: "Candidate slots", ruledOutSlots: "Slots ruled out",
  unrulableAlternatives: "Alternatives that cannot be ruled out", assurance: "Assurance level", removalEventId: "Removal record", labelScansRecorded: "Slot-label scans recorded",
  rejectedLabelScans: "Rejected label scans", conflictKind: "Conflict kind", reasonCodes: "Reason codes", slotStates: "Recorded slot states", code: "Code", note: "Note", rawMaterialLots: "Raw-material lot (supplier claim)",
};
const EVENT_KEYS = new Set(["gapEventId", "boundedByEventId", "observedEventId", "removalEventId"]);
const PAYLOAD_SHOWN = ["componentType", "slot", "part", "lot", "serial", "identityGranularity", "observedPart", "observedLot", "observedSerial", "method", "provisional", "rawMaterialLot", "disposition", "orderType"];
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export default function EvidencePage() {
  const g = useGatedView();
  if (g.phase === "loading") return <div className="skel" style={{ height: 320 }} />;
  if (g.phase === "withheld") return <><h1>Evidence investigation</h1><div className="banner bad" role="alert"><div><b>The evidence view is withdrawn.</b> {g.reason}</div></div></>;
  if (isHistorical(g.view) || g.mode !== "current") {
    return <><h1>Evidence investigation</h1><div className="banner bad" role="alert" data-testid="iw-banner"><div><b>Evidence items are claims about the current decision, so they are withheld.</b> {g.reason || "The verification lease expired; waiting for a new verified snapshot."} Genealogy and the impact graph still show recorded facts.</div></div></>;
  }
  return <Workspace view={g.view} />;
}

function Workspace({ view: pv }: { view: PageView }) {
  const sp = useSearchParams(), router = useRouter(), path = usePathname();
  const set = (patch: Record<string, string | null>) => { const q = new URLSearchParams(sp.toString()); for (const [k, v] of Object.entries(patch)) { if (v === null) q.delete(k); else q.set(k, v); } router.replace(`${path}?${q.toString()}`, { scroll: false }); };
  const view = useMemo(() => projectInvestigation(pv as Parameters<typeof projectInvestigation>[0]), [pv]);
  const snap = factsOf(pv);
  // Changes since the previous accepted projection in this page session. Dropped whenever the page unmounts (gate withdrawal), so nothing is diffed across a withheld period.
  const prev = useRef<InvestigationView | null>(null);
  const [changes, setChanges] = useState<ViewChanges | null>(null);
  useEffect(() => { if (prev.current && prev.current !== view) { const c = diffViews(prev.current, view); if (hasChanges(c)) setChanges(c); } prev.current = view; }, [view]);
  const cluster = sp.get("cluster"), unit = sp.get("unit"), event = sp.get("event");
  return (
    <div className="iw inv">
      <h1>Evidence investigation</h1>
      <p className="lede">What the ledger lacks, contradicts or distrusts, grouped by exact key and classified by the original evidence taxonomy. Findings and actions are the recall engine&apos;s own; nothing here decides or clears a motor.</p>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}><span className="tag info">[SYNTHETIC DEMONSTRATION DATA]</span><span className="tag plain">[READ-ONLY]</span><span className="tag plain">[NOT A RELEASE AUTHORIZATION]</span></div>
      <Watermark view={view} />
      {changes && <ChangesPanel changes={changes} dismiss={() => setChanges(null)} />}
      {unit && event ? <EvidenceRecord view={view} snap={snap} unitId={unit} eventId={event} back={() => set({ unit: null, event: null })} openCluster={(id) => set({ unit: null, event: null, cluster: id })} />
        : cluster ? <ClusterPage view={view} snap={snap} clusterId={cluster} back={() => set({ cluster: null })} openEvent={(u, e) => set({ unit: u, event: e })} />
          : <Overview view={view} openCluster={(id) => set({ cluster: id })} />}
    </div>
  );
}

function ChangesPanel({ changes, dismiss }: { changes: ViewChanges; dismiss: () => void }) {
  const rows: Array<[string, typeof changes.added]> = [["Newly listed", changes.added], ["No longer listed", changes.removed], ["Decision re-evaluated", changes.reevaluated]];
  return (
    <section className="banner" role="status" aria-label="Changes since the previous snapshot" data-testid="changes-panel" style={{ display: "block" }}>
      <b>Changes since the previous verified snapshot.</b>
      {rows.filter(([, r]) => r.length).map(([l, r]) => <div key={l}><span className="tag plain">{l}</span><ul className="evlist">{r.map((c) => <li key={`${l}${c.taskId}`}><code>{c.unitId}</code> · {humanize(c.cls)} — {c.detail}</li>)}</ul></div>)}
      <p className="note">Nothing was closed by hand. Items appear or disappear only because the evaluator&apos;s decision changed.</p>
      <button type="button" className="btn ghost" onClick={dismiss}>Dismiss</button>
    </section>
  );
}

function Watermark({ view }: { view: InvestigationView }) {
  const w = view.watermark;
  return (
    <section className="card" aria-label="Evidence watermark and verification limits" data-testid="watermark" style={{ marginBottom: 12 }}>
      <h2>Evidence watermark</h2>
      <p style={{ margin: "0 0 6px" }}>Verified ledger journal sequence <b>{w.sequence ?? "unknown"}</b>, head <code>{short(w.headHash)}</code>, verified {when(w.verifiedAt)} (valid for {w.maxAgeSeconds ?? "?"} s). Covers {plural(w.ledgerEvents, "ledger record")} and {plural(w.decisions, "current decision")}.</p>
      <details><summary>Verification limits</summary><ul>{LIMITATIONS.map((l) => <li key={l}>{l}</li>)}</ul></details>
    </section>
  );
}

function Overview({ view, openCluster }: { view: InvestigationView; openCluster: (id: string) => void }) {
  const [filter, setFilter] = useState<"ALL" | EvidenceClass>("ALL");
  const classes = useMemo(() => [...new Set(view.clusters.map((c) => c.cls))].sort((a, b) => CLASSES[a].rank - CLASSES[b].rank), [view]);
  const shown = view.clusters.filter((c) => filter === "ALL" || c.cls === filter);
  const motorCount = Object.keys(view.motors).length;
  return (
    <div>
      <p className="lede" data-testid="summary">{plural(view.tasks.length, "evidence item")} across {plural(motorCount, "motor")}, in {plural(view.clusters.filter((c) => c.family === "EVIDENCE_GAP").length, "evidence-gap group")}
        {view.clusters.some((c) => c.family === "RAW_MATERIAL_LOT") ? ` and ${plural(view.clusters.filter((c) => c.family === "RAW_MATERIAL_LOT").length, "shared raw-material-lot group")}` : ""}.</p>
      <details className="card" style={{ marginBottom: 10 }}><summary>How the groups are ordered</summary><ol>{PRIORITY_RULES.map((r) => <li key={r}>{r}</li>)}</ol></details>
      {view.clusters.length > 0 ? <>
        <p><label>Show <select value={filter} onChange={(e) => setFilter(e.target.value as "ALL" | EvidenceClass)}><option value="ALL">All groups</option>{classes.map((c) => <option key={c} value={c}>{CLASSES[c].label}</option>)}</select></label></p>
        <ol className="grid g2" style={{ listStyle: "none", padding: 0 }} aria-label="Evidence-gap groups in priority order">
          {shown.map((c) => <ClusterCard key={c.clusterId} c={c} open={() => openCluster(c.clusterId)} />)}
        </ol>
      </> : <p className="note" data-testid="no-tasks">No evidence items are listed. This is a view of what the recall engine lists; it is not a clearance and does not authorize any release.</p>}
      {view.untasked.length > 0 && <details className="card" style={{ marginTop: 10 }}><summary>Motors with no listed evidence item ({view.untasked.length})</summary>
        <p className="na">Having no item here is not a clearance. Findings below are the recall engine&apos;s own, copied unchanged.</p>
        <ul className="evlist">{view.untasked.map((u) => <li key={u.unitId}><b>{u.unitId}</b> <span className="na">{u.title}</span> <FindingTag v={u.finding} /> <ClaimSentence claim={u} /></li>)}</ul></details>}
      <section className="card" aria-label="Notification obligations" data-testid="obligations" style={{ marginTop: 12 }}>
        <h2>Notification obligations (separate from evidence items)</h2><p>{OBLIGATION_NOTE}</p>
        {view.obligations.length === 0 ? <p className="na">None recorded.</p> : <ul>{view.obligations.map((o) => <li key={o.decisionId}><b>{o.unitId}</b>: <code>{o.reason}</code>, status {o.status || "unknown"}, delivery {o.deliveryStatus}. Acknowledgment: unknown.</li>)}</ul>}
      </section>
    </div>
  );
}

function ClusterCard({ c, open }: { c: Cluster; open: () => void }) {
  const info = CLASSES[c.cls];
  return (
    <li className="card" data-testid="cluster-card" data-cluster-class={c.cls}>
      <h3><span className="tag plain">#{c.rank}</span> <button className="linkbtn" type="button" onClick={open}>{info.label}</button> <span className="na">· {plural(c.unitIds.length, "motor")}{c.unitIds.length > 1 ? " share this exact key" : ""}</span></h3>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "4px 0" }}>
        {c.priority.serious && <span className="tag bad">[UNTRUSTED AFFECTED-LOT OBSERVATION]</span>}
        {c.priority.withdrawn && <span className="tag bad">[WITHDRAWN EARLIER RELEASE-ELIGIBLE DECISION]</span>}
        {c.family === "RAW_MATERIAL_LOT" && <span className="tag info">[SHARED CONTEXT, NOT A GAP]</span>}
        <span className="tag plain">{plural(c.taskIds.length, "item")}</span>
      </div>
      <p>{info.statement}</p>
      <p className="na">Motors: {c.unitIds.join(", ")}</p>
      <details><summary>Exact group key</summary><ul>{c.key.split(" | ").map((p) => <li key={p}><code>{p}</code></li>)}</ul><p className="na">Motors are in one group only when every field above is exactly equal. Nothing is matched loosely.</p></details>
    </li>
  );
}

function EventLink({ snap, unitId, eventId, open }: { snap: Facts; unitId: string; eventId: string; open: (u: string, e: string) => void }) {
  const exists = snap.units.find((u) => u.unitId === unitId)?.events.some((e) => e.eventId === eventId);
  return exists ? <button className="linkbtn" type="button" onClick={() => open(unitId, eventId)}><code>{eventId}</code></button> : <span><code>{eventId}</code> <span className="na">(not in this snapshot)</span></span>;
}

function Val({ k, v, snap, unitId, open }: { k: string; v: GroundedValue; snap: Facts; unitId: string; open: (u: string, e: string) => void }) {
  if (v === null || (Array.isArray(v) && v.length === 0)) return <span className="na">Not recorded</span>;
  if (Array.isArray(v)) return <ul style={{ margin: 0, paddingLeft: 16 }}>{v.map((x) => <li key={x}>{k === "rejectedReasons" ? <><code>{x}</code> <span className="na">{REJECTION_TEXT[x] ?? "No description for this rejection code."}</span></> : <code>{x}</code>}</li>)}</ul>;
  if (EVENT_KEYS.has(k)) return <EventLink snap={snap} unitId={unitId} eventId={v} open={open} />;
  return <code>{v}</code>;
}

function DecisionSays({ d }: { d: DecisionRef }) {
  const f = FINDING_TEXT[d.finding];
  return (
    <div>
      <p><b>{f?.label ?? humanize(d.finding)}.</b> {f?.explain} <ClaimSentence claim={d} />{d.reviewRequired ? " Review is required." : ""} <span className="na">Computed by the recall engine and copied here unchanged; this workspace does not decide or change it.</span></p>
      <p className="na">Decision <code>{d.decisionId}</code> (version {d.version ?? "unknown"}), policy {d.policyId}.</p>
      <ul className="evlist">{d.reasonCodes.map((c) => { const h = REASON_HANDLING[c]; const role = !h ? "Not in the reviewed taxonomy" : h.handling === "TASK" ? "Evidence item" : h.handling === "OBLIGATION" ? "Notification obligation, listed separately" : "Explains the decision"; return <li key={c}><code>{c}</code> <span className="tag plain">{role}</span> <span className="na">{explain(REASONS, c)}</span></li>; })}</ul>
    </div>
  );
}

function TaskBlock({ task, snap, open }: { task: Task; snap: Facts; open: (u: string, e: string) => void }) {
  const info = CLASSES[task.cls];
  const rows = Object.entries(task.grounded);
  return (
    <article className="card" aria-label={`${task.unitId}: ${info.label}`} data-testid={`task-${task.unitId}`} style={{ marginBottom: 10 }}>
      <h3>{task.unitId} <span className="na">{info.label}</span></h3>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span className="tag plain">{task.blocksHold ? "Listed as part of the hold" : "Needs a human look; not listed as blocking"}</span>
        {task.decision.withdrawnExclusion && <span className="tag bad">[EARLIER RELEASE-ELIGIBLE DECISION WITHDRAWN]</span>}
        {!task.detailFound && <span className="tag warn">[DETAIL NOT LOCATED IN THIS SNAPSHOT]</span>}
      </div>
      <h3 style={{ marginTop: 10 }}>What the existing recall decision says</h3><DecisionSays d={task.decision} />
      <h3>What evidence is missing, conflicting or untrusted</h3><p>{info.statement}</p>
      <h3>Ledger records that support this</h3>
      <dl className="kv">{rows.map(([k, v]) => <><dt key={`${k}t`}>{FIELD_LABEL[k] ?? humanize(k.replace(/^conflict\./, ""))}</dt><dd key={`${k}d`}><Val k={k} v={v} snap={snap} unitId={task.unitId} open={open} /></dd></>)}</dl>
      {task.evidenceEventIds.length > 0 ? <ul className="evlist" aria-label={`Supporting records for ${task.unitId}`}>{task.evidenceEventIds.map((id) => <li key={id}><EventLink snap={snap} unitId={task.unitId} eventId={id} open={open} /></li>)}</ul> : <p className="na">No specific supporting record is named in the decision for this item.</p>}
      <h3>What a quality engineer should independently investigate</h3><ul>{info.investigate.map((t) => <li key={t}>{t}</li>)}</ul>
    </article>
  );
}

function MotorBlock({ motor }: { motor: MotorRef }) {
  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <h3>{motor.unitId} <span className="na">{motor.title}</span></h3>
      <ul className="evlist">
        {motor.components.map((c) => <li key={c.componentId}><b>{c.slot}</b>: part {c.part ?? "not recorded"}, lot <code>{c.lot ?? "not recorded"}</code>, serial <code>{c.serial ?? "not recorded"}</code>, installed {when(c.installedAt)} as claimed by <code>{c.claimedBy}</code>{c.removedAt ? <> · removed {when(c.removedAt)}</> : <> · currently recorded</>}</li>)}
        {motor.components.length === 0 && <li className="na">No component claims recorded.</li>}
        <li>{motor.shipment ? <>Shipment recorded (<code>{motor.shipment.shipmentId}</code>, {when(motor.shipment.shippedAt)}). A shipment record is not an authorization.</> : <span className="na">No shipment recorded.</span>}</li>
      </ul>
      <p className="na">Component and shipment lines are claims recorded in the ledger. Customer and destination are not shown here.</p>
    </div>
  );
}

function ClusterPage({ view, snap, clusterId, back, openEvent }: { view: InvestigationView; snap: Facts; clusterId: string; back: () => void; openEvent: (u: string, e: string) => void }) {
  const c = view.clusters.find((x) => x.clusterId === clusterId);
  if (!c) return <p className="banner bad" role="alert" data-testid="unknown-cluster">This group is not in the current projection; its decision may have changed. <button className="linkbtn" onClick={back}>Back to all groups</button></p>;
  const info = CLASSES[c.cls];
  const tasks = view.tasks.filter((t) => c.taskIds.includes(t.taskId));
  return (
    <div>
      <p><button className="btn ghost" type="button" onClick={back}>← All groups</button></p>
      <h2>#{c.rank} {info.label} <span className="na">· {plural(c.unitIds.length, "motor")}</span></h2>
      <p>{info.statement}</p>
      <section aria-label="Exact group key" className="card" style={{ marginBottom: 10 }}><h3>Exact group key</h3><ul>{c.key.split(" | ").map((p) => <li key={p}><code>{p}</code></li>)}</ul>
        <p className="na">Rank {c.rank}: {c.priority.serious ? "has an untrusted affected-lot observation; " : ""}{c.priority.withdrawn ? "has a withdrawn earlier release-eligible decision; " : ""}{plural(c.priority.motors, "distinct motor")}. This is an ordering, not a risk score.</p></section>
      {c.family === "RAW_MATERIAL_LOT" && <p className="note">This group is shared context taken from the ledger&apos;s lineage records. It is not a gap, and supplier and lot information are claims by the source stream.</p>}
      {c.unitIds.map((u) => <section key={u} aria-label={`Motor ${u}`}><MotorBlock motor={view.motors[u]} />{tasks.filter((t) => t.unitId === u).map((t) => <TaskBlock key={t.taskId} task={t} snap={snap} open={openEvent} />)}</section>)}
    </div>
  );
}

function EvidenceRecord({ view, snap, unitId, eventId, back, openCluster }: { view: InvestigationView; snap: Facts; unitId: string; eventId: string; back: () => void; openCluster: (id: string) => void }) {
  const unit = snap.units.find((u) => u.unitId === unitId);
  const event: EventRecord | undefined = unit?.events.find((e) => e.eventId === eventId);
  if (!unit || !event) return <p className="banner bad" role="alert" data-testid="unknown-evidence">No record <code>{eventId}</code> for {unitId} is in this snapshot. <button className="linkbtn" onClick={back}>Back</button></p>;
  const citing = view.tasks.filter((t) => t.unitId === unitId && t.evidenceEventIds.includes(eventId));
  const shown = PAYLOAD_SHOWN.filter((k) => k in event.payload);
  return (
    <div data-testid="evidence-page">
      <p><button className="btn ghost" type="button" onClick={back}>← Back</button> {citing[0] && <button className="btn ghost" type="button" onClick={() => openCluster(citing[0].clusterId)}>Back to the group</button>}</p>
      <h2>Ledger record <code style={{ overflowWrap: "anywhere" }}>{event.eventId}</code></h2>
      <dl className="kv card">
        <dt>Motor</dt><dd><Link href={`/dashboard/recall?motor=${unitId}`}>{unitId}</Link></dd>
        <dt>Record type</dt><dd><code>{event.eventType}</code></dd>
        <dt>Source (as recorded)</dt><dd><code>{event.sourceId}</code> · sequence {event.sourceSeq}</dd>
        <dt>Actor (a claim)</dt><dd><code>{event.actorId}</code></dd>
        <dt>Occurred (claimed)</dt><dd>{when(event.occurredAt)} · clock <code>{event.timeSource}</code></dd>
        <dt>Recorded</dt><dd>{when(event.recordedAt)}</dd>
        <dt>Work order</dt><dd>{event.workOrderId ? <code>{event.workOrderId}</code> : <span className="na">Not recorded</span>}</dd>
        <dt>Supersedes</dt><dd>{event.supersedesEventId ? <code>{event.supersedesEventId}</code> : <span className="na">Nothing</span>}</dd>
        <dt>Evidence references</dt><dd>{event.evidenceRefs.length ? event.evidenceRefs.map((r) => <code key={r}>{r} </code>) : <span className="na">Not recorded</span>}</dd>
        {shown.map((k) => <><dt key={`${k}t`}>{humanize(k)}</dt><dd key={`${k}d`}><code>{String(event.payload[k])}</code></dd></>)}
        <dt>Capture hash</dt><dd>{event.repository ? <code style={{ overflowWrap: "anywhere" }}>{event.repository.captureSha256}</code> : <span className="na">Not recorded</span>}</dd>
        <dt>Event chain hash</dt><dd>{event.repository ? <code style={{ overflowWrap: "anywhere" }}>{event.repository.eventChainHash}</code> : <span className="na">Not recorded</span>}</dd>
      </dl>
      <p className="note">The hashes show that this record is in the ledger unchanged since capture. They do not show that what the record says is true. Source and actor are as recorded (claims); this synthetic data is not independently authenticated.</p>
      <h3>Items that cite this record</h3>
      {citing.length === 0 ? <p className="na">No current item cites this record.</p> : <ul>{citing.map((t) => <li key={t.taskId}><button className="linkbtn" onClick={() => openCluster(t.clusterId)}>{CLASSES[t.cls].label}</button></li>)}</ul>}
    </div>
  );
}
