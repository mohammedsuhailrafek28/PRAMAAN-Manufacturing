import { ClaimChip } from "../contract/ClearanceChip";
import { FINDING_TEXT, humanize } from "../domain/glossary";
import type { Facts } from "../contract/gated";
import type { EventRecord } from "../domain/types";
import { KIND_LABEL } from "./ImpactGraphView";
import type { EvidenceRef, GNode, ImpactGraph, Issue, TraceDirection } from "./projection";
import { consoleUnitHref } from "./route";

const when = (iso: string | null | undefined) => (iso ? iso.replace("T", " ").replace(/:\d\dZ$/, " UTC").replace(/Z$/, " UTC") : "Not recorded");
const short = (h: string | null | undefined) => (h ? `${h.slice(0, 12)}…` : "Not recorded");

const ATTR_LABEL: Record<string, string> = {
  part: "Part", lot: "Lot", serial: "Serial", recordedAt: "Recorded occurrence time", timeSource: "Time source", suppliers: "Supplier (as recorded; unverified claim)",
  motorSerial: "Motor serial", recordedEvents: "Ledger records for this motor", shippedAt: "Shipment record time", observedLot: "Lot claimed by the observation",
  status: "Observation status", rejectedReasons: "Rejected because", method: "Method (as recorded)", slot: "Slot", lotClaim: "Lot recorded on the install",
  installedAt: "Install time", removedAt: "Removal time", componentType: "Component type",
};

function eventFor(snap: Facts, r: EvidenceRef): EventRecord | undefined {
  return snap.units.find((u) => u.unitId === r.unitId)?.events.find((e) => e.eventId === r.eventId);
}

export function EvidenceTable({ snap, refs }: { snap: Facts; refs: EvidenceRef[] }) {
  if (refs.length === 0) return <p className="muted">No ledger record is cited by this item.</p>;
  return (
    <table className="grid compact responsive" aria-label="Ledger records cited">
      <thead><tr><th>Role</th><th>Record</th><th>Type</th><th>Source and sequence</th><th>Occurred</th><th>Recorded</th><th>Record hash</th></tr></thead>
      <tbody>
        {refs.map((r) => {
          const e = eventFor(snap, r);
          return (
            <tr key={`${r.unitId}|${r.eventId}|${r.role}`}>
              <td data-label="Role">{r.role}</td>
              <td data-label="Record"><code>{r.eventId}</code>{!e && <span className="muted"> (not in this snapshot)</span>}</td>
              <td data-label="Type">{e ? <code>{e.eventType}</code> : "—"}</td>
              <td data-label="Source and sequence">{e ? <><code>{e.sourceId}</code> #{e.sourceSeq}</> : "—"}</td>
              <td data-label="Occurred">{e ? <>{when(e.occurredAt)} <span className="muted">({e.timeSource})</span></> : "—"}</td>
              <td data-label="Recorded">{e ? when(e.recordedAt) : "—"}</td>
              <td data-label="Record hash"><code title={e?.repository?.eventChainHash ?? ""}>{short(e?.repository?.eventChainHash)}</code></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function IssueList({ issues, snap }: { issues: Issue[]; snap: Facts }) {
  if (issues.length === 0) return null;
  return (
    <ul className="ig-issues">
      {issues.map((i) => (
        <li key={i.id} className={`ig-sev-${i.severity}`} data-testid="impact-issue" data-issue-kind={i.kind}>
          <strong>{i.severity === "CONFLICT" ? "Conflict" : i.severity === "UNCERTAIN" ? "Uncertain" : "Note"}</strong> · {humanize(i.kind)}: {i.message}
          {i.evidence.length > 0 && <details><summary>Cited records ({i.evidence.length})</summary><EvidenceTable snap={snap} refs={i.evidence} /></details>}
        </li>
      ))}
    </ul>
  );
}

export interface DetailProps {
  node: GNode;
  graph: ImpactGraph;
  snap: Facts;
  traceDir: TraceDirection | null;
  onTrace: (d: TraceDirection | null) => void;
  onSelect: (id: string) => void;
}

export function NodeDetails({ node, graph, snap, traceDir, onTrace, onSelect }: DetailProps) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const issues = graph.issues.filter((i) => node.issueIds.includes(i.id));
  const incident = graph.edges.filter((e) => e.from === node.id || e.to === node.id);
  const attrs = Object.entries(node.attrs).filter(([, v]) => v !== null && v !== "");
  const slotRows = node.unitId && node.slot ? snap.components.filter((c) => c.unitId === node.unitId && c.slot === node.slot) : [];
  const decision = node.status;

  return (
    <section className="ig-details panel" aria-labelledby="ig-detail-h" data-testid="impact-details">
      <h3 id="ig-detail-h">{KIND_LABEL[node.kind]}: {node.label}</h3>
      <p className="muted">{node.sublabel}</p>
      <div className="ig-trace" role="group" aria-label="Trace along recorded links">
        {(["BACKWARD", "FORWARD", "BOTH"] as TraceDirection[]).map((d) => (
          <button key={d} type="button" aria-pressed={traceDir === d} onClick={() => onTrace(traceDir === d ? null : d)}>
            {d === "BACKWARD" ? "Trace back to source" : d === "FORWARD" ? "Trace forward to motors" : "Trace both ways"}
          </button>
        ))}
        {traceDir && <button type="button" onClick={() => onTrace(null)}>Clear trace</button>}
      </div>

      {decision && (
        <div className="ig-decision" data-testid="impact-decision">
          <p>
            <span className={`chip finding-${decision.finding}`}><span className="chip-cap">Engine finding</span><span className="chip-body">{FINDING_TEXT[decision.finding]?.label ?? humanize(decision.finding)}</span></span>{" "}
            <ClaimChip claim={decision} />
            {decision.reviewRequired && <> <span className="tag">Review required</span></>}
            {decision.withdrawnExclusion && <> <span className="tag iw-serious">Exclusion withdrawn</span></>}
          </p>
          <p className="muted">
            Copied from the evaluator’s recorded decision <code>{decision.decisionId}</code>{decision.version !== null ? ` (version ${decision.version})` : ""}; this page does not evaluate anything.
            {" "}{FINDING_TEXT[decision.finding]?.explain}
            {decision.finding === "EXCLUDED_WITH_EVIDENCE" && " Excluded for this recall scope only; this is not a statement that the motor is safe."}
          </p>
          {decision.reasonCodes.length > 0 && <p>Reason codes: {decision.reasonCodes.map((c) => <code key={c}>{c}</code>).reduce<React.ReactNode[]>((a, c, i) => (i ? [...a, ", ", c] : [c]), [])}</p>}
        </div>
      )}
      {node.kind === "BEARING_LOT" && node.recalled !== null && (
        <p>{node.recalled ? "This lot is named by the recall." : "This lot is not named by this recall. That is not a statement about the lot’s quality."}</p>
      )}
      {node.kind === "SHIPMENT" && <p className="callout">A shipment record shows a shipping event was logged. It does not show delivery, receipt, or that any customer action was taken, and customer and destination details are not shown here.</p>}
      {node.lifecycle === "HISTORICAL" && <p className="callout callout-warn">This component was recorded as removed. Removal of a part is not proof that the affected lot was eliminated from the motor or from the product, and the removed part’s whereabouts are not recorded here.</p>}
      {node.kind === "OBSERVATION" && <p className="callout callout-warn">This observation claim was rejected by the evidence rules. It is shown separately and is not evidence that the lot is in the motor.</p>}

      {issues.length > 0 && <><h4>Record issues</h4><IssueList issues={issues} snap={snap} /></>}

      {attrs.length > 0 && (
        <dl className="defs ig-attrs">
          {attrs.map(([k, v]) => <div key={k}><dt>{ATTR_LABEL[k] ?? humanize(k)}</dt><dd><code>{v}</code></dd></div>)}
          {node.slot && <div><dt>Slot</dt><dd><code>{node.slot}</code> {node.slotInScope === null ? "" : node.slotInScope ? <span className="tag">In the recall’s slot scope</span> : <span className="tag">Outside the recall’s slot scope</span>}</dd></div>}
        </dl>
      )}

      <h4>Recorded links ({incident.length})</h4>
      {incident.length === 0 ? <p className="muted">No recorded link reaches this item in the visible trace.</p> : (
        <ul className="ig-links">
          {incident.map((e) => {
            const otherId = e.from === node.id ? e.to : e.from;
            const other = byId.get(otherId);
            return (
              <li key={e.id} data-testid="impact-link">
                {e.from === node.id ? "to" : "from"}{" "}
                <button type="button" className="ig-linkbtn" onClick={() => onSelect(otherId)}>{other ? `${KIND_LABEL[other.kind]} ${other.label}` : otherId}</button>
                {e.historical && <> <span className="tag">historical</span></>}
                <br /><span className="muted">{e.basis}</span>
              </li>
            );
          })}
        </ul>
      )}

      {slotRows.length > 0 && (
        <>
          <h4>History of slot {node.slot} on {node.unitId}</h4>
          <ul className="history">
            {slotRows.map((c) => (
              <li key={`${c.unitId}|${c.componentId}`} className={c.supersededBy ? "superseded" : ""}>
                <code>{c.componentId}</code> · lot <code>{c.lot ?? "not recorded"}</code>{c.serial ? <> · serial <code>{c.serial}</code></> : " · lot-level identity only"}
                {c.removedAt ? ` · removed ${when(c.removedAt)}` : " · no removal recorded"}
                {c.supersededBy ? " · record superseded" : ""}
              </li>
            ))}
          </ul>
        </>
      )}

      <h4>Ledger records behind this item</h4>
      <EvidenceTable snap={snap} refs={node.evidence} />
      {node.unitId && <p><a href={consoleUnitHref(node.unitId, "genealogy")}>Open {node.unitId} in the recall console</a></p>}
    </section>
  );
}
