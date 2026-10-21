import { useMemo, useState } from "react";
import { ACTION_TEXT, explain, FINDING_TEXT, humanize, REASONS } from "../domain/glossary";
import type { EventRecord, RecallSnapshot } from "../domain/types";
import type { ViewChanges } from "./diff";
import { hasChanges } from "./diff";
import type { Cluster, DecisionRef, GroundedValue, InvestigationView, MotorRef, Task } from "./projection";
import { PRIORITY_RULES } from "./projection";
import { clusterHref, consoleUnitHref, evidenceHref, type Route } from "./route";
import { CLASSES, LIMITATIONS, OBLIGATION_NOTE, REASON_HANDLING, REJECTION_TEXT, type EvidenceClass } from "./taxonomy";

export interface Banner { kind: "preview" | "stale" | "unverified"; text: string }

const FIELD_LABEL: Record<string, string> = {
  slot: "Slot", slots: "Slots", gapKind: "Gap kind", materiality: "Materiality", sourceId: "Source (as recorded)",
  windowFrom: "Window from", windowTo: "Window to", gapEventId: "Exception record", boundedByEventId: "Bounding record",
  observedPart: "Observed part", observedLot: "Observed lot", observedSerial: "Observed serial", observedGranularity: "Identity granularity",
  rejectedReasons: "Rejected because", actorClaim: "Actor (as recorded; a claim)", method: "Method (as recorded)", observationStatus: "Observation status",
  observedEventId: "Observation record", claimedSlot: "Slot named by the claim", candidates: "Candidate slots", ruledOutSlots: "Slots ruled out",
  unrulableAlternatives: "Alternatives that cannot be ruled out", assurance: "Assurance level", removalEventId: "Removal record",
  labelScansRecorded: "Slot-label scans recorded", rejectedLabelScans: "Rejected label scans", conflictKind: "Conflict kind",
  reasonCodes: "Reason codes", slotStates: "Recorded slot states", code: "Code", note: "Note", rawMaterialLots: "Raw-material lot (supplier claim)",
};
const EVENT_KEYS = new Set(["gapEventId", "boundedByEventId", "observedEventId", "removalEventId"]);
const PAYLOAD_SHOWN = ["componentType", "slot", "part", "lot", "serial", "identityGranularity", "observedPart", "observedLot", "observedSerial", "method", "provisional", "rawMaterialLot", "disposition", "orderType"];

const when = (iso: string | null | undefined) => (iso ? iso.replace("T", " ").replace(/:\d\dZ$/, " UTC").replace(/Z$/, " UTC") : "Not recorded");
const short = (h: string | null) => (h ? `${h.slice(0, 12)}…` : "Not recorded");
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function Tag({ children, tone }: { children: React.ReactNode; tone?: "serious" | "info" | "synthetic" }) {
  return <span className={`tag${tone === "synthetic" ? " synthetic" : ""}${tone === "serious" ? " iw-serious" : ""}`}>{children}</span>;
}

function EventLink({ snap, unitId, eventId }: { snap: RecallSnapshot; unitId: string; eventId: string }) {
  const exists = snap.units.find((u) => u.unitId === unitId)?.events.some((e) => e.eventId === eventId);
  return exists ? <a href={evidenceHref(unitId, eventId)}><code>{eventId}</code></a> : <span><code>{eventId}</code> <span className="muted">(not in this snapshot)</span></span>;
}

function Value({ k, v, snap, unitId }: { k: string; v: GroundedValue; snap: RecallSnapshot; unitId: string }) {
  if (v === null || (Array.isArray(v) && v.length === 0)) return <span className="muted">Not recorded</span>;
  if (Array.isArray(v)) {
    return (
      <ul className="iw-values">
        {v.map((x) => (
          <li key={x}>
            {k === "rejectedReasons" ? <><code>{x}</code> <span className="muted">{REJECTION_TEXT[x] ?? "No description for this rejection code."}</span></> : <code>{x}</code>}
          </li>
        ))}
      </ul>
    );
  }
  if (EVENT_KEYS.has(k)) return <EventLink snap={snap} unitId={unitId} eventId={v} />;
  return <code>{v}</code>;
}

function Facts({ task, snap }: { task: Task; snap: RecallSnapshot }) {
  const rows = Object.entries(task.grounded).filter(([k]) => !k.startsWith("conflict."));
  const extra = Object.entries(task.grounded).filter(([k]) => k.startsWith("conflict."));
  return (
    <dl className="iw-facts">
      {[...rows, ...extra].map(([k, v]) => (
        <div key={k}>
          <dt>{FIELD_LABEL[k] ?? humanize(k.replace(/^conflict\./, ""))}</dt>
          <dd><Value k={k} v={v} snap={snap} unitId={task.unitId} /></dd>
        </div>
      ))}
    </dl>
  );
}

function DecisionSays({ d }: { d: DecisionRef }) {
  const f = FINDING_TEXT[d.finding], a = ACTION_TEXT[d.action];
  return (
    <div>
      <p>
        <strong>{f?.label ?? humanize(d.finding)}.</strong> {f?.explain} <strong>{a?.label ?? humanize(d.action)}:</strong> {a?.explain}
        {d.reviewRequired ? " Review is required." : ""} <span className="muted">Computed by the recall engine and copied here unchanged; this workspace does not decide or change it.</span>
      </p>
      <p className="muted">Decision <code>{d.decisionId}</code> (version {d.version ?? "unknown"}), policy {d.policyId}.</p>
      <ul className="iw-reasons">
        {d.reasonCodes.map((c) => {
          const h = REASON_HANDLING[c];
          const role = !h ? "Not in the reviewed taxonomy" : h.handling === "TASK" ? "Evidence item" : h.handling === "OBLIGATION" ? "Notification obligation, listed separately" : "Explains the decision";
          return <li key={c}><code>{c}</code> <Tag>{role}</Tag> <span className="muted">{explain(REASONS, c)}</span></li>;
        })}
      </ul>
    </div>
  );
}

function TaskBlock({ task, snap, headingLevel = 4 }: { task: Task; snap: RecallSnapshot; headingLevel?: 3 | 4 }) {
  const info = CLASSES[task.cls];
  const H = `h${headingLevel}` as "h3" | "h4";
  return (
    <article className="iw-task" aria-label={`${task.unitId}: ${info.label}`} data-testid={`task-${task.unitId}`}>
      <H>{task.unitId} <span className="muted">{info.label}</span></H>
      <div className="chip-row">
        <Tag>{task.blocksHold ? "Listed as part of the hold" : "Needs a human look; not listed as blocking"}</Tag>
        {task.decision.withdrawnExclusion && <Tag tone="serious">Earlier release-eligible decision withdrawn</Tag>}
        {!task.detailFound && <Tag>Detail not located in this snapshot</Tag>}
      </div>
      <h5>What the existing recall decision says</h5>
      <DecisionSays d={task.decision} />
      <h5>What evidence is missing, conflicting or untrusted</h5>
      <p>{info.statement}</p>
      <h5>Ledger records that support this</h5>
      <Facts task={task} snap={snap} />
      {task.evidenceEventIds.length > 0 ? (
        <ul className="iw-values" aria-label={`Supporting records for ${task.unitId}`}>
          {task.evidenceEventIds.map((id) => <li key={id}><EventLink snap={snap} unitId={task.unitId} eventId={id} /></li>)}
        </ul>
      ) : <p className="muted">No specific supporting record is named in the decision for this item.</p>}
      <h5>What a quality engineer should independently investigate</h5>
      <ul>{info.investigate.map((t) => <li key={t}>{t}</li>)}</ul>
    </article>
  );
}

function MotorBlock({ motor }: { motor: MotorRef }) {
  return (
    <div className="iw-motor">
      <h4><a href={consoleUnitHref(motor.unitId)}>{motor.unitId}</a> <span className="muted">{motor.title}</span></h4>
      <ul className="plain">
        {motor.components.map((c) => (
          <li key={c.componentId}>
            <strong>{c.slot}</strong>: part {c.part ?? "not recorded"}, lot <code>{c.lot ?? "not recorded"}</code>, serial <code>{c.serial ?? "not recorded"}</code>, installed {when(c.installedAt)} as claimed by <code>{c.claimedBy}</code>
            {c.removedAt ? <> · removed {when(c.removedAt)}</> : <> · currently recorded</>}
          </li>
        ))}
        {motor.components.length === 0 && <li className="muted">No component claims recorded.</li>}
        <li>{motor.shipment ? <>Shipment recorded (<code>{motor.shipment.shipmentId}</code>, {when(motor.shipment.shippedAt)}). A shipment record is not an authorization.</> : <span className="muted">No shipment recorded.</span>}</li>
      </ul>
      <p className="muted">Component and shipment lines are claims recorded in the ledger. Customer and destination are not shown here.</p>
    </div>
  );
}

function ClusterCard({ c }: { c: Cluster }) {
  const info = CLASSES[c.cls];
  return (
    <li className="iw-card" data-testid="cluster-card" data-cluster-class={c.cls}>
      <h3>
        <span className="iw-rank">#{c.rank}</span> <a href={clusterHref(c.clusterId)}>{info.label}</a>
        <span className="muted"> · {plural(c.unitIds.length, "motor")}{c.unitIds.length > 1 ? " share this exact key" : ""}</span>
      </h3>
      <div className="chip-row">
        {c.priority.serious && <Tag tone="serious">Untrusted affected-lot observation</Tag>}
        {c.priority.withdrawn && <Tag tone="serious">Withdrawn earlier release-eligible decision</Tag>}
        {c.family === "RAW_MATERIAL_LOT" && <Tag>Shared context, not a gap</Tag>}
        <Tag>{plural(c.taskIds.length, "item")}</Tag>
      </div>
      <p>{info.statement}</p>
      <p className="muted">Motors: {c.unitIds.map((u, i) => <span key={u}>{i > 0 && ", "}<code>{u}</code></span>)}</p>
      <details>
        <summary>Exact group key</summary>
        <ul className="iw-key">{c.key.split(" | ").map((p) => <li key={p}><code>{p}</code></li>)}</ul>
        <p className="muted">Motors are in one group only when every field above is exactly equal. Nothing is matched loosely.</p>
      </details>
    </li>
  );
}

function Overview({ view, changes, mode }: { view: InvestigationView; changes: ViewChanges | null; mode: "current" | "preview" }) {
  const [filter, setFilter] = useState<"ALL" | EvidenceClass>("ALL");
  const classes = useMemo(() => [...new Set(view.clusters.map((c) => c.cls))].sort((a, b) => CLASSES[a].rank - CLASSES[b].rank), [view]);
  const shown = view.clusters.filter((c) => filter === "ALL" || c.cls === filter);
  const motorCount = Object.keys(view.motors).length;
  return (
    <div>
      <p className="lead" data-testid="summary">
        {plural(view.tasks.length, "evidence item")} across {plural(motorCount, "motor")}, in {plural(view.clusters.filter((c) => c.family === "EVIDENCE_GAP").length, "evidence-gap group")}
        {view.clusters.some((c) => c.family === "RAW_MATERIAL_LOT") ? ` and ${plural(view.clusters.filter((c) => c.family === "RAW_MATERIAL_LOT").length, "shared raw-material-lot group")}` : ""}.
      </p>
      <div role="status" aria-live="polite" data-testid="changes">
        {hasChanges(changes) && (
          <div className="callout">
            <strong>{mode === "current" ? "Updated from a newer verified snapshot." : "Changes compared with the previous preview stage (a captured evidence update, not a live event)."}</strong>
            <ul>
              {changes.removed.map((e) => <li key={`r${e.taskId}`}>{e.unitId}: {CLASSES[e.cls as EvidenceClass]?.label ?? e.cls} {e.detail}.</li>)}
              {changes.added.map((e) => <li key={`a${e.taskId}`}>{e.unitId}: {CLASSES[e.cls as EvidenceClass]?.label ?? e.cls} {e.detail}.</li>)}
              {changes.reevaluated.map((e) => <li key={`e${e.taskId}`}>{e.unitId}: {CLASSES[e.cls as EvidenceClass]?.label ?? e.cls} {e.detail}.</li>)}
            </ul>
            <p className="muted">Nothing was closed by hand. A listing changes only when the recall engine's decision changes.</p>
          </div>
        )}
      </div>
      <details className="iw-rules">
        <summary>How the groups are ordered</summary>
        <ol>{PRIORITY_RULES.map((r) => <li key={r}>{r}</li>)}</ol>
      </details>
      {view.clusters.length > 0 ? (
        <>
          <div className="filters">
            <label htmlFor="iw-class">Show</label>
            <select id="iw-class" value={filter} onChange={(e) => setFilter(e.target.value as "ALL" | EvidenceClass)}>
              <option value="ALL">All groups</option>
              {classes.map((c) => <option key={c} value={c}>{CLASSES[c].label}</option>)}
            </select>
          </div>
          <ol className="iw-cards" aria-label="Evidence-gap groups in priority order">
            {shown.map((c) => <ClusterCard key={c.clusterId} c={c} />)}
          </ol>
        </>
      ) : (
        <p className="callout" data-testid="no-tasks">No evidence items are listed. This is a view of what the recall engine lists; it is not a clearance and does not authorize any release.</p>
      )}
      {view.untasked.length > 0 && (
        <details className="iw-untasked">
          <summary>Motors with no listed evidence item ({view.untasked.length})</summary>
          <p className="muted">Having no item here is not a clearance. Findings below are the recall engine's own, copied unchanged.</p>
          <ul className="plain">
            {view.untasked.map((u) => (
              <li key={u.unitId}><a href={consoleUnitHref(u.unitId)}>{u.unitId}</a> <span className="muted">{u.title}</span> · {FINDING_TEXT[u.finding]?.label ?? humanize(u.finding)} · {ACTION_TEXT[u.action]?.label ?? humanize(u.action)}</li>
            ))}
          </ul>
        </details>
      )}
      <Obligations view={view} />
    </div>
  );
}

function Obligations({ view }: { view: InvestigationView }) {
  return (
    <section className="callout" aria-label="Notification obligations" data-testid="obligations">
      <h3>Notification obligations (separate from evidence items)</h3>
      <p>{OBLIGATION_NOTE}</p>
      {view.obligations.length === 0 ? <p className="muted">None recorded.</p> : (
        <ul>
          {view.obligations.map((o) => (
            <li key={o.decisionId}><a href={consoleUnitHref(o.unitId, "history")}>{o.unitId}</a>: <code>{o.reason}</code>, status {o.status || "unknown"}, delivery {o.deliveryStatus}. Acknowledgment: unknown.</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ClusterPage({ view, snap, clusterId }: { view: InvestigationView; snap: RecallSnapshot; clusterId: string }) {
  const c = view.clusters.find((x) => x.clusterId === clusterId);
  if (!c) return <p className="warn" role="alert" data-testid="unknown-cluster">This group is not in the current projection; its decision may have changed. <a href="#/">Back to all groups</a></p>;
  const info = CLASSES[c.cls];
  const tasks = view.tasks.filter((t) => c.taskIds.includes(t.taskId));
  const byUnit = c.unitIds.map((u) => ({ motor: view.motors[u], tasks: tasks.filter((t) => t.unitId === u) }));
  return (
    <div>
      <nav aria-label="Breadcrumb"><a href="#/">← All groups</a></nav>
      <h3>#{c.rank} {info.label} <span className="muted">· {plural(c.unitIds.length, "motor")}</span></h3>
      <p>{info.statement}</p>
      <section aria-label="Exact group key">
        <h4>Exact group key</h4>
        <ul className="iw-key">{c.key.split(" | ").map((p) => <li key={p}><code>{p}</code></li>)}</ul>
        <p className="muted">Rank {c.rank}: {c.priority.serious ? "has an untrusted affected-lot observation; " : ""}{c.priority.withdrawn ? "has a withdrawn earlier release-eligible decision; " : ""}{plural(c.priority.motors, "distinct motor")}. This is an ordering, not a risk score.</p>
      </section>
      {c.family === "RAW_MATERIAL_LOT" && <p className="callout">This group is shared context taken from the ledger's lineage records. It is not a gap, and supplier and lot information are claims by the source stream.</p>}
      {byUnit.map(({ motor, tasks: ts }) => (
        <section key={motor.unitId} className="iw-motor-section" aria-label={`Motor ${motor.unitId}`}>
          <MotorBlock motor={motor} />
          {ts.map((t) => <TaskBlock key={t.taskId} task={t} snap={snap} />)}
        </section>
      ))}
    </div>
  );
}

function EvidencePage({ view, snap, unitId, eventId }: { view: InvestigationView; snap: RecallSnapshot; unitId: string; eventId: string }) {
  const unit = snap.units.find((u) => u.unitId === unitId);
  const event: EventRecord | undefined = unit?.events.find((e) => e.eventId === eventId);
  if (!unit || !event) return <p className="warn" role="alert" data-testid="unknown-evidence">No record <code>{eventId}</code> for {unitId} is in this snapshot. <a href="#/">Back to all groups</a></p>;
  const citing = view.tasks.filter((t) => t.unitId === unitId && t.evidenceEventIds.includes(eventId));
  const shown = PAYLOAD_SHOWN.filter((k) => k in event.payload);
  return (
    <div data-testid="evidence-page">
      <nav aria-label="Breadcrumb"><a href="#/">← All groups</a>{citing[0] && <> · <a href={clusterHref(citing[0].clusterId)}>Back to the group</a></>}</nav>
      <h3>Ledger record <code>{event.eventId}</code></h3>
      <dl className="iw-facts">
        <div><dt>Motor</dt><dd><a href={consoleUnitHref(unitId, "events")}>{unitId}</a></dd></div>
        <div><dt>Record type</dt><dd><code>{event.eventType}</code></dd></div>
        <div><dt>Source (as recorded)</dt><dd><code>{event.sourceId}</code> · sequence {event.sourceSeq}</dd></div>
        <div><dt>Actor (as recorded; a claim)</dt><dd><code>{event.actorId}</code></dd></div>
        <div><dt>Occurred (claimed)</dt><dd>{when(event.occurredAt)} · clock <code>{event.timeSource}</code></dd></div>
        <div><dt>Recorded</dt><dd>{when(event.recordedAt)}</dd></div>
        <div><dt>Work order</dt><dd>{event.workOrderId ? <code>{event.workOrderId}</code> : <span className="muted">Not recorded</span>}</dd></div>
        <div><dt>Supersedes</dt><dd>{event.supersedesEventId ? <EventLink snap={snap} unitId={unitId} eventId={event.supersedesEventId} /> : <span className="muted">Nothing</span>}</dd></div>
        <div><dt>Evidence references</dt><dd>{event.evidenceRefs.length ? event.evidenceRefs.map((r) => <code key={r}>{r} </code>) : <span className="muted">Not recorded</span>}</dd></div>
        {shown.map((k) => <div key={k}><dt>{humanize(k)}</dt><dd><code>{String(event.payload[k])}</code></dd></div>)}
        <div><dt>Capture hash</dt><dd>{event.repository ? <code>{event.repository.captureSha256}</code> : <span className="muted">Not recorded</span>}</dd></div>
        <div><dt>Event chain hash</dt><dd>{event.repository ? <code>{event.repository.eventChainHash}</code> : <span className="muted">Not recorded</span>}</dd></div>
      </dl>
      <p className="muted">The hashes show that this record is in the ledger unchanged since capture. They do not show that what the record says is true.</p>
      <h4>Items that cite this record</h4>
      {citing.length === 0 ? <p className="muted">No current item cites this record.</p> : (
        <ul>{citing.map((t) => <li key={t.taskId}><a href={clusterHref(t.clusterId)}>{CLASSES[t.cls].label}</a></li>)}</ul>
      )}
    </div>
  );
}

export function WatermarkPanel({ view, mode }: { view: InvestigationView; mode: "current" | "preview" }) {
  const w = view.watermark;
  return (
    <section className="iw-watermark" aria-label="Evidence watermark and verification limits" data-testid="watermark">
      <h3>Evidence watermark</h3>
      {mode === "current" ? (
        <p>
          Verified ledger journal sequence <strong>{w.sequence ?? "unknown"}</strong>, head <code>{short(w.headHash)}</code>, verified {when(w.verifiedAt)} (valid for {w.maxAgeSeconds ?? "?"} s). Covers {plural(w.ledgerEvents, "ledger record")} and {plural(w.decisions, "current decision")}.
        </p>
      ) : (
        <p>Preview data. Not a verified watermark: status <code>{w.status}</code>. Covers {plural(w.ledgerEvents, "ledger record")} and {plural(w.decisions, "decision")}.</p>
      )}
      <details>
        <summary>Verification limits</summary>
        <ul>{LIMITATIONS.map((l) => <li key={l}>{l}</li>)}</ul>
      </details>
    </section>
  );
}

export function InvestigationWorkspace({ view, snap, route, banner, changes, mode, stageNote }: {
  view: InvestigationView; snap: RecallSnapshot; route: Route; banner: Banner | null; changes: ViewChanges | null; mode: "current" | "preview"; stageNote?: React.ReactNode;
}) {
  return (
    <div className="iw">
      <h2>Evidence-guided investigation</h2>
      <div className="chip-row" aria-label="Page status">
        <Tag tone="synthetic">Synthetic demonstration data</Tag>
        <Tag>Read-only</Tag>
        <Tag>Not a release authorization</Tag>
        {mode === "preview" && <Tag tone="serious">Preview: not current</Tag>}
      </div>
      {banner && <div className="callout callout-warn" role="status" data-testid="iw-banner">{banner.text}</div>}
      {stageNote}
      <WatermarkPanel view={view} mode={mode} />
      {route.page === "overview" && <Overview view={view} changes={changes} mode={mode} />}
      {route.page === "cluster" && <ClusterPage view={view} snap={snap} clusterId={route.clusterId} />}
      {route.page === "evidence" && <EvidencePage view={view} snap={snap} unitId={route.unitId} eventId={route.eventId} />}
    </div>
  );
}
