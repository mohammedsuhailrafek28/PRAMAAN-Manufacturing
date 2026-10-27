"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useData, useMotorResourceChecked } from "@/dash/data";
import { ResourceNote } from "@/dash/ResourceNote";
import { buildGraph, edgePath, NODE_H, NODE_W, pathOf, COL_X, type GEdge, type GNode, type Graph } from "@/dash/graph";
import { ActionTag, FindingTag, NA, currentOf, fmt, unitOf, useMotor, val } from "@/dash/ui";
import type { ProvenanceRow, Snapshot } from "@/dash/types";

type Sel = { t: "node" | "edge"; id: string } | null;
const HEADS: [string, number][] = [["Raw material lot (claimed)", COL_X.raw], ["Bearing lot", COL_X.lot], ["Component install (slot)", COL_X.comp], ["Motor", COL_X.motor], ["Shipment (claim)", COL_X.ship]];

export default function GenealogyPage() {
  const { snap } = useData();
  if (snap.phase === "loading") return <div className="skel" style={{ height: 320 }} />;
  if (snap.phase === "error") return <p>Genealogy is unavailable because the backend data could not be read.</p>;
  return <Genealogy s={snap.snap} />;
}

function Genealogy({ s }: { s: Snapshot }) {
  const [motor, setMotor, href] = useMotor(s);
  const { gate } = useData();
  const g = useMemo(() => buildGraph(s), [s]);
  const [sel, setSel] = useState<Sel>(null);
  const [focus, setFocus] = useState(true);
  const hot = motor ? pathOf(g, motor) : { nodes: new Set<string>(), edges: new Set<string>() };
  const dimN = (n: GNode) => focus && !hot.nodes.has(n.id);
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const selNode = sel?.t === "node" ? byId.get(sel.id) : undefined;
  const selEdge = sel?.t === "edge" ? g.edges.find((e) => e.id === sel.id) : undefined;
  const counts = { raw: g.nodes.filter((n) => n.kind === "raw").length, lot: g.nodes.filter((n) => n.kind === "lot").length, comp: g.nodes.filter((n) => n.kind === "comp").length, motor: g.nodes.filter((n) => n.kind === "motor").length };

  return (
    <div className="inv">
      <h1>Genealogy</h1>
      <p className="lede">From raw material lot to bearing lot, installed component, motor and shipment. Every line is one backend record; click a node or a line to inspect the evidence behind it. Dashed lines are claims the ledger records but cannot independently verify.</p>
      <div className="card" style={{ marginBottom: 12, display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
        <span className="eyebrow">Graph returned</span>
        <b className="mono">{g.nodes.length} nodes · {g.edges.length} edges</b>
        <span className="na">{counts.raw} raw lots · {counts.lot} bearing lots · {counts.comp} installs · {counts.motor} motors</span>
        <label style={{ marginLeft: "auto" }}><input type="checkbox" checked={focus} onChange={(e) => setFocus(e.target.checked)} /> Highlight {motor}&apos;s path, dim the rest</label>
      </div>
      <div className="split genealogy-layout">
        <div>
          <div className="graphwrap" role="region" aria-label="Genealogy graph, scrollable" tabIndex={0}>
            <GraphSvg g={g} sel={sel} setSel={(x) => { setSel(x); if (x?.t === "node") { const n = byId.get(x.id); if (n?.kind === "motor" && n.motor) setMotor(n.motor); } }} hot={hot} focus={focus} dimN={dimN} />
          </div>
          <div className="legend"><span>record-backed link</span><span className="dashed">claim (not independently verified)</span><span>▣ red outline = recalled lot</span><span>dashed box = removed / shipment claim</span></div>
          {g.issues.length > 0 && <div className="card"><h3>Missing links (not drawn)</h3><ul>{g.issues.map((i) => <li key={i}>{i}</li>)}</ul></div>}
          <details><summary>Edges as a table ({g.edges.length})</summary><EdgeTable g={g} onPick={(id) => setSel({ t: "edge", id })} /></details>
        </div>
        <aside className="card inspector" aria-live="polite">
          {!sel && <div><h2>Evidence inspector</h2><p className="na">Select a node or a line in the graph.</p><p className="note">Material relationships come only from the ledger&apos;s lineage and install records. Raw material lots are supplier claims; bearing lots are not raw materials.</p></div>}
          {selNode && <NodeInspector s={s} g={g} n={selNode} allowDecisions={gate.decisionsAllowed} href={href} />}
          {selEdge && <EdgeInspector g={g} e={selEdge} />}
        </aside>
      </div>
    </div>
  );
}

function GraphSvg({ g, sel, setSel, hot, focus, dimN }: { g: Graph; sel: Sel; setSel: (s: Sel) => void; hot: { nodes: Set<string>; edges: Set<string> }; focus: boolean; dimN: (n: GNode) => boolean }) {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  return (
    <svg className="graph" viewBox={`0 0 ${g.width} ${g.height}`} style={{ width: "100%", height: "auto", minWidth: g.width }} role="group" aria-label={`Genealogy graph with ${g.nodes.length} nodes and ${g.edges.length} edges`}>
      {HEADS.map(([t, x]) => <text key={t} x={x} y={22} className="colhead">{t}</text>)}
      {g.edges.map((e) => {
        const a = byId.get(e.from)!, b = byId.get(e.to)!;
        const d = edgePath(a, b); const dim = focus && !hot.edges.has(e.id);
        return (
          <g key={e.id} onClick={() => setSel({ t: "edge", id: e.id })}>
            <path d={d} className={`edge ${e.claim ? "claim" : ""} ${dim ? "dim" : ""} ${sel?.t === "edge" && sel.id === e.id ? "sel" : !dim && focus ? "hot" : ""}`}><title>{e.relation}</title></path>
            <path d={d} className="edge hit" role="button" aria-label={`${a.label} to ${b.label}: ${e.relation}`} />
          </g>
        );
      })}
      {g.nodes.map((n) => (
        <g key={n.id} className={`node k-${n.kind} ${n.affected ? "affected" : ""} ${n.removed ? "removed" : ""} ${dimN(n) ? "dim" : ""} ${sel?.t === "node" && sel.id === n.id ? "sel" : ""}`} transform={`translate(${n.x},${n.y})`}
          tabIndex={0} role="button" aria-label={`${n.kind} ${n.label}. ${n.sub}`} onClick={() => setSel({ t: "node", id: n.id })} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setSel({ t: "node", id: n.id }); } }}>
          <rect width={NODE_W} height={NODE_H} rx={2} />
          <text x={9} y={19} fontWeight={600}>{n.label}</text>
          <text x={9} y={35} className="sub">{n.sub.length > 24 ? `${n.sub.slice(0, 23)}…` : n.sub}</text>
        </g>
      ))}
    </svg>
  );
}

function EdgeTable({ g, onPick }: { g: Graph; onPick: (id: string) => void }) {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  return <div className="scroll"><table className="t"><thead><tr><th>From</th><th>To</th><th>Relation</th><th>Basis</th><th>Evidence events</th></tr></thead><tbody>{g.edges.map((e) => <tr key={e.id} className="click" onClick={() => onPick(e.id)}><td>{byId.get(e.from)?.label}</td><td>{byId.get(e.to)?.label}</td><td>{e.relation}</td><td>{e.claim ? "claim" : "record"}</td><td className="mono">{[...new Set(e.source.flatMap((x) => x.eventIds))].length}</td></tr>)}</tbody></table></div>;
}

function EvidenceRows({ motor, ids }: { motor: string; ids: string[] }) {
  const c = useMotorResourceChecked<ProvenanceRow[]>("provenance", motor), res = c.res;
  if (c.consistency === "MISMATCH") return <ResourceNote c={c} what="The event hashes" />;
  if (!res) return <p className="na">Reading event hashes for {motor}…</p>;
  if (!res.ok) return <p className="warn-t">Event hashes unavailable ({String(res.status)} {res.error}).</p>;
  const rows = new Map(res.body.map((r) => [r.id, r]));
  return <><ul className="evlist">{ids.map((id) => { const r = rows.get(id); return <li key={id}><code>{id}</code>{r ? <div className="na">seq {r.seq} · source {r.source} · received {fmt(r.received)}<br />capture hash <code>{r.hash.slice(0, 16)}…</code> · chain hash <code>{(r.event_chain_hash ?? "").slice(0, 16)}…</code></div> : <div className="na">No provenance row for this id in {motor}&apos;s event list.</div>}</li>; })}</ul><ResourceNote c={c} what="The event hashes" /></>;
}

function motorOfEvent(id: string) { return id.match(/urn:pramaan:(MTR-\d+):/)?.[1]; }
function EvidenceByMotor({ ids }: { ids: string[] }) {
  const by = new Map<string, string[]>();
  for (const id of ids) { const m = motorOfEvent(id); if (m) by.set(m, [...(by.get(m) ?? []), id]); }
  return <>{[...by].map(([m, list]) => <div key={m}><div className="eyebrow">Events recorded under {m}</div><EvidenceRows motor={m} ids={list} /></div>)}</>;
}

function EdgeInspector({ g, e }: { g: Graph; e: GEdge }) {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const ids = [...new Set(e.source.flatMap((x) => x.eventIds))];
  return (
    <div>
      <div className="eyebrow">Edge provenance</div>
      <h2>{byId.get(e.from)?.label} → {byId.get(e.to)?.label}</h2>
      <p>{e.relation}. <span className={`tag ${e.claim ? "warn" : "ok"}`}>[{e.claim ? "CLAIM, NOT INDEPENDENTLY VERIFIED" : "RECORDED"}]</span></p>
      <h3>Backed by {e.source.length} backend record{e.source.length === 1 ? "" : "s"}</h3>
      <ul className="evlist">{e.source.map((x, i) => <li key={i}><b>{x.type}</b><div className="na">{x.note}</div>{x.assurance && <div className="mono">{x.assurance}</div>}{x.backedByLedger !== undefined && <div className="mono">ledger-backed: {String(x.backedByLedger)}</div>}</li>)}</ul>
      <h3>Event hashes</h3>
      <EvidenceByMotor ids={ids} />
    </div>
  );
}

function NodeInspector({ s, g, n, allowDecisions, href }: { s: Snapshot; g: Graph; n: GNode; allowDecisions: boolean; href: (p: string) => string }) {
  const byId = new Map(g.nodes.map((x) => [x.id, x]));
  const neighbours = (dir: "in" | "out") => g.edges.filter((e) => (dir === "in" ? e.to === n.id : e.from === n.id)).map((e) => byId.get(dir === "in" ? e.from : e.to)!);
  const evIds = [...new Set(g.edges.filter((e) => e.from === n.id || e.to === n.id).flatMap((e) => e.source.flatMap((x) => x.eventIds)))];
  let body: React.ReactNode = null;
  if (n.kind === "motor" && n.motor) {
    const u = unitOf(s, n.motor), d = currentOf(s, n.motor), comps = s.components.filter((c) => c.unitId === n.motor);
    body = <>
      <dl>
        <dt>Decision</dt><dd>{allowDecisions ? <><FindingTag v={d?.evidenceFinding} /> <ActionTag v={d?.operationalAction} /></> : <span className="tag bad">[WITHHELD · integrity not current]</span>}</dd>
        <dt>Positions</dt><dd>{comps.map((c) => <div key={c.componentId}>{c.slot}: {c.lot ?? "lot ?"} <span className="na">{c.removedAt ? `(removed ${fmt(c.removedAt)})` : "(installed)"}</span></div>)}</dd>
        <dt>Shipment</dt><dd>{u?.shipment ? <>{u.shipment.shipmentId} <span className="na">claim</span></> : "Not shipped"}</dd>
        <dt>Events</dt><dd>{u?.eventCount ?? NA} recorded</dd>
      </dl>
      <p><Link className="btn" href={href("/dashboard/recall")}>Recall reasoning</Link> <Link className="btn ghost" href={href("/dashboard/passport")}>Passport</Link></p>
    </>;
  } else if (n.kind === "lot") {
    const lot = n.label, info = s.lots.find((l) => l.lotId === lot), installs = s.components.filter((c) => c.lot === lot);
    body = <>
      <dl>
        <dt>Recall status</dt><dd>{(s.recall.affectedLots ?? []).includes(lot) ? <span className="tag AFFECTED">[RECALLED · {s.recall.recallId}]</span> : <span className="tag plain">[NOT IN RECALL]</span>}</dd>
        <dt>Part</dt><dd>{val(info?.part)}</dd><dt>Supplier (claim)</dt><dd>{val(info?.supplier)}</dd>
        <dt>Raw material</dt><dd>{val(info?.rawMaterialLot)} <span className="na">claim</span></dd>
        <dt>Registry</dt><dd>{val(info?.registry?.status)}</dd><dt>Assurance</dt><dd className="mono">{val(info?.provenanceAssurance)}</dd>
        <dt>Installed in</dt><dd>{installs.map((c) => <div key={c.componentId}>{c.unitId} {c.slot} {c.removedAt ? <span className="na">removed</span> : ""}</div>)}</dd>
      </dl>
    </>;
  } else if (n.kind === "comp") {
    const c = s.components.find((x) => `comp:${x.componentId}` === n.id)!;
    body = <dl>
      <dt>Motor / slot</dt><dd>{c.unitId} · {c.slot}</dd><dt>Part</dt><dd>{val(c.part)}</dd><dt>Lot</dt><dd>{val(c.lot)}</dd><dt>Serial</dt><dd>{val(c.serial)}</dd>
      <dt>Installed</dt><dd>{fmt(c.installedAt)}</dd><dt>Removed</dt><dd>{c.removedAt ? fmt(c.removedAt) : "not removed"}</dd><dt>Claimed by</dt><dd>{val(c.claimedBy)}</dd>
      <dt>Lot registry</dt><dd>{val(c.registry?.status)} {c.registry?.viaAlias ? "(via alias)" : ""}</dd><dt>Record id</dt><dd className="mono">{c.componentId}</dd></dl>;
  } else if (n.kind === "raw") {
    body = <dl><dt>Feeds lots</dt><dd>{neighbours("out").map((x) => <div key={x.id}>{x.label}</div>)}</dd><dt>Basis</dt><dd>Supplier material claim archived as a ledger event; supplier identity and physical origin are not verified.</dd></dl>;
  } else {
    const u = s.units.find((x) => `ship:${x.shipment?.shipmentId}` === n.id)!, sh = u.shipment!;
    body = <dl><dt>Motor</dt><dd>{u.unitId}</dd><dt>Customer</dt><dd>{val(sh.customer)}</dd><dt>Destination</dt><dd>{val(sh.destination)}</dd><dt>Shipped</dt><dd>{fmt(sh.shippedAt)}</dd><dt>Basis</dt><dd className="mono">{val(sh.provenanceAssurance)}</dd><dt>Note</dt><dd>A shipment record is not a release authorization.</dd></dl>;
  }
  return (
    <div>
      <div className="eyebrow">{({ raw: "Raw material lot", lot: "Bearing lot", comp: "Component install", motor: "Motor", ship: "Shipment" })[n.kind]}</div>
      <h2>{n.kind === "comp" ? `${n.motor} · ${n.label.split("·")[1]?.trim()}` : n.label}</h2>
      <div className="inspector">{body}</div>
      {evIds.length > 0 && <><h3 style={{ marginTop: 12 }}>Evidence events ({evIds.length})</h3><EvidenceByMotor ids={evIds} /></>}
    </div>
  );
}
