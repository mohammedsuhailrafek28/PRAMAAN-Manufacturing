"use client";

// Stitch presentation of the original impact-graph view (graph, list, evidence table, node details). Logic and semantics come from src/orig/impact.
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { FINDING_TEXT, humanize } from "@/orig/domain/glossary";
import type { Facts } from "@/orig/contract/gated";
import type { EventRecord } from "@/orig/domain/types";
import { layoutGraph, NODE_H, NODE_W, type Layout } from "@/orig/impact/layout";
import type { EvidenceRef, GEdge, GNode, ImpactGraph, Issue, TraceDirection } from "@/orig/impact/projection";
import { ClaimSentence, ClaimTag, short, when } from "./claims";
import { FindingTag } from "./ui";

export const KIND_LABEL: Record<GNode["kind"], string> = {
  RAW_LOT: "Raw-material claim", BEARING_LOT: "Bearing lot", MANUFACTURE: "Manufacture record", COMPONENT: "Installed component",
  MOTOR: "Motor", SHIPMENT: "Recorded shipment", OBSERVATION: "Rejected observation",
};
const STYLE_TEXT: Record<GEdge["style"], string> = { RECORDED: "recorded link", CONFLICT: "conflicting record", LOT_CLAIM: "lot claim without a manufacture link", UNTRUSTED_CLAIM: "untrusted claim" };

export function nodeAria(n: GNode): string {
  const bits = [`${n.label} ${n.sublabel}`, KIND_LABEL[n.kind]];
  if (n.status) bits.push(FINDING_TEXT[n.status.finding]?.label ?? n.status.finding);
  if (n.kind === "BEARING_LOT" && n.recalled !== null) bits.push(n.recalled ? "named by the recall" : "not named by the recall");
  if (n.lifecycle === "HISTORICAL") bits.push("removed, historical");
  if (n.issueIds.length) bits.push(`${n.issueIds.length} record ${n.issueIds.length === 1 ? "issue" : "issues"}`);
  return bits.join(", ");
}

// ---------------------------------------------------------------- graph
interface View { x: number; y: number; k: number }
const MIN_K = 0.25, MAX_K = 2.5;
const edgePath = (a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) => {
  const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2, dx = Math.max(24, (x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
};

export function ImpactGraphView({ graph, visible, selectedId, highlight, onSelect, height = 540 }: { graph: ImpactGraph; visible: ReadonlySet<string> | null; selectedId: string | null; highlight: { nodeIds: Set<string>; edgeIds: Set<string> } | null; onSelect: (id: string) => void; height?: number }) {
  const layout: Layout = useMemo(() => layoutGraph(graph, visible), [graph, visible]);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 0.8 });
  const drag = useRef<{ px: number; py: number; vx: number; vy: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const nodes = graph.nodes.filter((n) => layout.pos.has(n.id));
  const edges = graph.edges.filter((e) => layout.pos.has(e.from) && layout.pos.has(e.to));
  const zoom = (f: number) => setView((v) => ({ ...v, k: Math.min(MAX_K, Math.max(MIN_K, v.k * f)) }));
  const fit = () => { const w = box.current?.clientWidth ?? 800; setView({ x: 0, y: 0, k: Math.min(1, Math.max(MIN_K, (w - 16) / layout.width)) }); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    const moves: Record<string, [number, number]> = { ArrowLeft: [48, 0], ArrowRight: [-48, 0], ArrowUp: [0, 48], ArrowDown: [0, -48] };
    if (moves[e.key]) { e.preventDefault(); setView((v) => ({ ...v, x: v.x + moves[e.key][0], y: v.y + moves[e.key][1] })); }
    else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoom(1.2); } else if (e.key === "-") { e.preventDefault(); zoom(1 / 1.2); }
  };
  const dim = (id: string) => (highlight ? !highlight.nodeIds.has(id) : false);
  const cls = (n: GNode) => ["ig-node", `ig-${n.kind.toLowerCase()}`, n.status ? `ig-f-${n.status.finding}` : "", n.lifecycle === "HISTORICAL" ? "ig-hist" : "", n.issueIds.length ? "ig-issue" : "", n.id === selectedId ? "ig-selected" : "", dim(n.id) ? "ig-dim" : ""].filter(Boolean).join(" ");
  return (
    <div className="graphwrap">
      <div className="ig-toolbar" role="toolbar" aria-label="Graph view controls">
        <button className="btn ghost" type="button" onClick={() => zoom(1.2)} aria-label="Zoom in">+</button>
        <button className="btn ghost" type="button" onClick={() => zoom(1 / 1.2)} aria-label="Zoom out">−</button>
        <button className="btn ghost" type="button" onClick={fit}>Fit width</button>
        <button className="btn ghost" type="button" onClick={() => setView({ x: 0, y: 0, k: 1 })}>Reset</button>
        <span className="na" aria-live="polite">Zoom {Math.round(view.k * 100)}% · drag to pan</span>
      </div>
      <div ref={box} className="ig-canvas" style={{ height }} tabIndex={0} role="group"
        aria-label="Impact graph. Arrow keys pan, plus and minus zoom, Tab moves to nodes, Enter selects a node. The list view has the same information."
        onKeyDown={onKey}
        onWheel={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1); } }}
        onPointerDown={(e) => { if ((e.target as Element).closest(".ig-node")) return; drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y }; (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); }}
        onPointerMove={(e) => { const d = drag.current; if (d) setView((v) => ({ ...v, x: d.vx + e.clientX - d.px, y: d.vy + e.clientY - d.py })); }}
        onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <svg width={layout.width * view.k + Math.max(0, view.x)} height={layout.height * view.k + Math.max(0, view.y)} role="presentation" data-testid="impact-svg">
          <defs><clipPath id="ig-clip"><rect x={0} y={0} width={NODE_W - 22} height={NODE_H} /></clipPath></defs>
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
            {layout.columns.map((c) => <text key={c.title} x={c.x} y={22} className="ig-colhead">{c.title}</text>)}
            {edges.map((e) => (
              <path key={e.id} d={edgePath(layout.pos.get(e.from)!, layout.pos.get(e.to)!)} data-edge-kind={e.kind} data-testid="impact-edge"
                className={`ig-edge ig-e-${e.style}${e.historical ? " ig-hist" : ""}${highlight && !highlight.edgeIds.has(e.id) ? " ig-dim" : ""}`}><title>{`${STYLE_TEXT[e.style]}${e.historical ? ", historical" : ""}: ${e.basis}`}</title></path>
            ))}
            {nodes.map((n) => {
              const p = layout.pos.get(n.id)!;
              return (
                <g key={n.id} className={cls(n)} transform={`translate(${p.x} ${p.y})`} tabIndex={0} role="button" aria-pressed={n.id === selectedId} aria-label={nodeAria(n)} data-node-id={n.id} data-kind={n.kind} data-testid="impact-node"
                  onClick={() => onSelect(n.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(n.id); } }}>
                  <rect width={NODE_W} height={NODE_H} rx={2} />
                  <text clipPath="url(#ig-clip)"><tspan x={8} y={20} className="ig-title">{`${n.label} `}</tspan><tspan x={8} y={38} className="ig-sub">{n.sublabel}</tspan></text>
                  {n.issueIds.length > 0 && <g aria-hidden="true" transform={`translate(${NODE_W - 12} 8)`}><rect x={-1.5} y={0} width={3} height={8} fill="#8a5300" /><rect x={-1.5} y={10} width={3} height={3} fill="#8a5300" /></g>}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <ul className="legend" aria-label="Legend" style={{ margin: 8, listStyle: "none", padding: 0 }}>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-RECORDED" /></svg> recorded link (ledger reference)</li>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-LOT_CLAIM" /></svg> lot claim, no manufacture link</li>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-CONFLICT" /></svg> conflicting records</li>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-UNTRUSTED_CLAIM" /></svg> untrusted claim</li>
        <li>faded = removed (historical) record · amber ! = record issue</li>
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- list
const ORDER: GNode["kind"][] = ["RAW_LOT", "BEARING_LOT", "MANUFACTURE", "COMPONENT", "OBSERVATION", "MOTOR", "SHIPMENT"];
export function ImpactList({ graph, visible, selectedId, onSelect }: { graph: ImpactGraph; visible: ReadonlySet<string> | null; selectedId: string | null; onSelect: (id: string) => void }) {
  const [shown, setShown] = useState(100);
  const nodes = graph.nodes.filter((n) => !visible || visible.has(n.id)).sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const links = new Map<string, string[]>();
  for (const e of graph.edges) { const a = byId.get(e.from), b = byId.get(e.to); if (!a || !b) continue; (links.get(a.id) ?? links.set(a.id, []).get(a.id)!).push(`→ ${b.label}`); (links.get(b.id) ?? links.set(b.id, []).get(b.id)!).push(`← ${a.label}`); }
  return (
    <div className="scroll">
      <table className="t" data-testid="impact-list">
        <thead><tr><th>Kind</th><th>Record</th><th>Detail</th><th>Engine finding</th><th>Recorded links</th><th>Issues</th></tr></thead>
        <tbody>
          {nodes.slice(0, shown).map((n) => (
            <tr key={n.id} className={`click ${n.id === selectedId ? "sel" : ""}`} onClick={() => onSelect(n.id)}>
              <td>{KIND_LABEL[n.kind]}</td>
              <td><button type="button" className="linkbtn" aria-label={`Select: ${nodeAria(n)}`}>{n.label}</button></td>
              <td>{n.sublabel}{n.lifecycle === "HISTORICAL" && " · historical"}</td>
              <td>{n.status ? <FindingTag v={n.status.finding} /> : "—"}</td>
              <td>{(links.get(n.id) ?? []).slice(0, 6).join("; ") || "none"}{(links.get(n.id)?.length ?? 0) > 6 ? ` (+${links.get(n.id)!.length - 6} more)` : ""}</td>
              <td>{n.issueIds.length || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {nodes.length > shown && <p><button type="button" className="btn ghost" onClick={() => setShown((s) => s + 100)}>Show more ({nodes.length - shown} remaining)</button></p>}
    </div>
  );
}

// ---------------------------------------------------------------- evidence + details
const eventFor = (snap: Facts, r: EvidenceRef): EventRecord | undefined => snap.units.find((u) => u.unitId === r.unitId)?.events.find((e) => e.eventId === r.eventId);

export function EvidenceTable({ snap, refs }: { snap: Facts; refs: EvidenceRef[] }) {
  if (refs.length === 0) return <p className="na">No ledger record is cited by this item.</p>;
  return (
    <div className="scroll"><table className="t" aria-label="Ledger records cited">
      <thead><tr><th>Role</th><th>Record</th><th>Type</th><th>Source and sequence</th><th>Occurred</th><th>Recorded</th><th>Event-chain hash</th></tr></thead>
      <tbody>
        {refs.map((r) => { const e = eventFor(snap, r); return (
          <tr key={`${r.unitId}|${r.eventId}|${r.role}`}>
            <td>{r.role}</td><td><code style={{ overflowWrap: "anywhere" }}>{r.eventId}</code>{!e && <span className="na"> (not in this snapshot)</span>}</td>
            <td>{e ? <code>{e.eventType}</code> : "—"}</td><td>{e ? <><code>{e.sourceId}</code> #{e.sourceSeq}</> : "—"}</td>
            <td>{e ? <>{when(e.occurredAt)} <span className="na">({e.timeSource})</span></> : "—"}</td><td>{e ? when(e.recordedAt) : "—"}</td>
            <td><code title={e?.repository?.eventChainHash ?? ""}>{short(e?.repository?.eventChainHash)}</code></td>
          </tr>); })}
      </tbody>
    </table></div>
  );
}

export function IssueList({ issues, snap }: { issues: Issue[]; snap: Facts }) {
  if (issues.length === 0) return null;
  return (
    <ul className="evlist">
      {issues.map((i) => (
        <li key={i.id} data-testid="impact-issue" data-issue-kind={i.kind}>
          <span className={`tag ${i.severity === "CONFLICT" ? "bad" : i.severity === "UNCERTAIN" ? "warn" : "plain"}`}>[{i.severity}]</span> <b>{humanize(i.kind)}</b>: {i.message}
          {i.evidence.length > 0 && <details><summary>Cited records ({i.evidence.length})</summary><EvidenceTable snap={snap} refs={i.evidence} /></details>}
        </li>
      ))}
    </ul>
  );
}

const ATTR_LABEL: Record<string, string> = {
  part: "Part", lot: "Lot", serial: "Serial", recordedAt: "Recorded occurrence time", timeSource: "Time source", suppliers: "Supplier (as recorded; unverified claim)",
  motorSerial: "Motor serial", recordedEvents: "Ledger records for this motor", shippedAt: "Shipment record time", observedLot: "Lot claimed by the observation",
  identityGranularity: "Identity granularity", status: "Observation status", rejectedReasons: "Rejected because", method: "Method (as recorded)", slot: "Slot", installedAt: "Install time", removedAt: "Removal time",
};

export function NodeDetails({ node, graph, snap, traceDir, onTrace, onSelect, motorHref }: { node: GNode; graph: ImpactGraph; snap: Facts; traceDir: TraceDirection | null; onTrace: (d: TraceDirection | null) => void; onSelect: (id: string) => void; motorHref: (unitId: string) => string }) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const issues = graph.issues.filter((i) => node.issueIds.includes(i.id));
  const incident = graph.edges.filter((e) => e.from === node.id || e.to === node.id);
  const attrs = Object.entries(node.attrs).filter(([, v]) => v !== null && v !== "");
  const slotRows = node.unitId && node.slot ? snap.components.filter((c) => c.unitId === node.unitId && c.slot === node.slot) : [];
  const d = node.status;
  return (
    <section className="card" aria-labelledby="ig-detail-h" data-testid="impact-details" style={{ marginTop: 12 }}>
      <div className="eyebrow">{KIND_LABEL[node.kind]}</div>
      <h2 id="ig-detail-h">{node.label}</h2>
      <p className="na">{node.sublabel}</p>
      <div role="group" aria-label="Trace along recorded links" style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0" }}>
        {(["BACKWARD", "FORWARD", "BOTH"] as TraceDirection[]).map((x) => (
          <button key={x} type="button" className={x === traceDir ? "btn" : "btn ghost"} aria-pressed={traceDir === x} onClick={() => onTrace(traceDir === x ? null : x)}>
            {x === "BACKWARD" ? "Trace back to source" : x === "FORWARD" ? "Trace forward to motors" : "Trace both ways"}
          </button>
        ))}
        {traceDir && <button type="button" className="btn ghost" onClick={() => onTrace(null)}>Clear trace</button>}
      </div>
      {d && (
        <div data-testid="impact-decision" className="banner" style={{ display: "block" }}>
          <p style={{ margin: "0 0 6px" }}><FindingTag v={d.finding} /> <ClaimTag claim={d} /> {d.reviewRequired && <span className="tag warn">[REVIEW REQUIRED]</span>} {d.withdrawnExclusion && <span className="tag bad">[EXCLUSION WITHDRAWN]</span>}</p>
          <p className="na" style={{ margin: 0 }}>Copied from the evaluator&apos;s recorded decision <code>{d.decisionId}</code>{d.version !== null ? ` (version ${d.version})` : ""}; this page does not evaluate anything. {FINDING_TEXT[d.finding]?.explain} <ClaimSentence claim={d} />
            {d.finding === "EXCLUDED_WITH_EVIDENCE" && " Excluded for this recall scope only; this is not a statement that the motor is safe."}</p>
          {d.reasonCodes.length > 0 && <p style={{ margin: "6px 0 0" }}>Reason codes: {d.reasonCodes.map((c) => <code key={c} style={{ marginRight: 8 }}>{c}</code>)}</p>}
        </div>
      )}
      {node.kind === "BEARING_LOT" && node.recalled !== null && <p>{node.recalled ? "This lot is named by the recall." : "This lot is not named by this recall. That is not a statement about the lot's quality."}</p>}
      {node.kind === "SHIPMENT" && <p className="note">A shipment record shows a shipping event was logged. It does not show delivery, receipt, or that any customer action was taken.</p>}
      {node.lifecycle === "HISTORICAL" && <p className="note">Recorded as removed. Removal of a part is not proof that the affected lot was eliminated, and the removed part&apos;s whereabouts are not recorded here.</p>}
      {node.kind === "OBSERVATION" && <p className="note">This observation claim was rejected by the evidence rules. It is not evidence that the lot is in the motor.</p>}
      {issues.length > 0 && <><h3>Record issues</h3><IssueList issues={issues} snap={snap} /></>}
      {attrs.length > 0 && <dl className="kv" style={{ margin: "10px 0" }}>{attrs.map(([k, v]) => <><dt key={`${k}t`}>{ATTR_LABEL[k] ?? humanize(k)}</dt><dd key={`${k}d`}><code>{v}</code></dd></>)}
        {node.slot && <><dt>Slot</dt><dd><code>{node.slot}</code> {node.slotInScope === null ? "" : node.slotInScope ? <span className="tag info">in the recall&apos;s slot scope</span> : <span className="tag plain">outside the recall&apos;s slot scope</span>}</dd></>}</dl>}
      <h3>Recorded links ({incident.length})</h3>
      {incident.length === 0 ? <p className="na">No recorded link reaches this item in the visible trace.</p> : (
        <ul className="evlist">{incident.map((e) => { const otherId = e.from === node.id ? e.to : e.from; const other = byId.get(otherId); return (
          <li key={e.id} data-testid="impact-link">{e.from === node.id ? "to" : "from"} <button type="button" className="linkbtn" onClick={() => onSelect(otherId)}>{other ? `${KIND_LABEL[other.kind]} ${other.label}` : otherId}</button>{e.historical && <span className="tag plain"> historical</span>}<div className="na">{e.basis}</div></li>); })}</ul>
      )}
      {slotRows.length > 0 && <><h3>History of slot {node.slot} on {node.unitId}</h3><ul className="evlist">{slotRows.map((c) => (
        <li key={`${c.unitId}|${c.componentId}`}><code>{c.componentId}</code> · lot <code>{c.lot ?? "not recorded"}</code>{c.serial ? <> · serial <code>{c.serial}</code></> : " · lot-level identity only"}{c.removedAt ? ` · removed ${when(c.removedAt)}` : " · no removal recorded"}{c.supersededBy ? " · record superseded" : ""}</li>))}</ul></>}
      <h3>Ledger records behind this item</h3>
      <EvidenceTable snap={snap} refs={node.evidence} />
      {node.unitId && <p><Link className="btn ghost" href={motorHref(node.unitId)}>Open {node.unitId} recall reasoning</Link></p>}
    </section>
  );
}
