"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { factsOf, isGated, type PageView } from "@/orig/contract/gated";
import { lotChoicesOf, projectImpact } from "@/orig/contract/views";
import { FINDING_TEXT, humanize } from "@/orig/domain/glossary";
import { motorOrder } from "@/orig/impact/layout";
import { filterByFinding, trace, type ImpactGraph, type SelectionKind, type TraceDirection } from "@/orig/impact/projection";
import { short, when } from "@/dash/claims";
import { useGatedView } from "@/dash/gated";
import { ImpactGraphView, ImpactList, IssueList, NodeDetails } from "@/dash/ImpactParts";
import { Simulator } from "@/dash/Simulator";

const DRAW_CAP = 400, MOTOR_WINDOW = 40;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const findingLabel = (f: string) => FINDING_TEXT[f]?.label ?? humanize(f);

function headline(g: ImpactGraph): string {
  const s = g.summary;
  const what = g.selection.kind === "RAW_LOT" ? `Raw-material lot ${g.selection.id}` : `Lot ${g.selection.id}`;
  const motors = `${plural(s.motors, "motor")} ${s.motors === 1 ? "has" : "have"} a ledger-recorded link to it`;
  const ship = `${plural(s.shipmentsRecorded, "motor")} ${s.shipmentsRecorded === 1 ? "has" : "have"} a recorded shipment record`;
  const unc = s.issues.UNCERTAIN + s.issues.CONFLICT;
  const gaps = `${plural(unc, "recorded link")} ${unc === 1 ? "is" : "are"} uncertain, conflicting or missing`;
  if (g.recallStatus === "WITHHELD") return `${what}: ${motors}. ${ship}. ${gaps}. Current recall status is withheld.`;
  const named = g.selection.kind === "BEARING_LOT" ? (g.scope.selectionNamedByRecall ? `named by recall ${g.scope.recallId}` : `not named by recall ${g.scope.recallId}`) : `traced to bearing lots, checked against recall ${g.scope.recallId}`;
  const scope = g.scope.affectedSlots.length ? ` for slot${g.scope.affectedSlots.length === 1 ? "" : "s"} ${g.scope.affectedSlots.join(", ")}` : "";
  const by = g.summary.byFinding ? Object.entries(g.summary.byFinding).filter(([, n]) => n > 0).map(([f, n]) => `${n} ${findingLabel(f).toLowerCase()}`).join(", ") : "";
  return `${what} is ${named}${scope}. ${motors}${by ? ` (${by})` : ""}. ${ship}. ${gaps}.`;
}

export default function ImpactPage() {
  const g = useGatedView();
  if (g.phase === "loading") return <div className="skel" style={{ height: 320 }} />;
  if (g.phase === "withheld") return <><h1>Recall impact graph</h1><div className="banner bad" role="alert" data-testid="withdrawn"><div><b>The impact graph is withdrawn.</b> {g.reason} Nothing from an earlier snapshot is shown, because it can no longer be tied to a verified ledger.</div></div></>;
  return <Impact view={g.view} mode={g.mode} gateReason={g.reason} />;
}

function Impact({ view, mode, gateReason }: { view: PageView; mode: "current" | "noncurrent"; gateReason: string }) {
  const sp = useSearchParams(), router = useRouter(), path = usePathname();
  const kind: SelectionKind | null = sp.get("kind") === "raw" ? "RAW_LOT" : sp.get("kind") === "bearing" ? "BEARING_LOT" : null;
  const lot = sp.get("lot"), nodeId = sp.get("node"), listView = sp.get("view") === "list";
  const motorQ = sp.get("motor");
  const set = (patch: Record<string, string | null>) => { const q = new URLSearchParams(sp.toString()); for (const [k, v] of Object.entries(patch)) { if (v === null) q.delete(k); else q.set(k, v); } router.replace(`${path}?${q.toString()}`, { scroll: false }); };
  const choices = useMemo(() => lotChoicesOf(view), [view]);
  const snap = factsOf(view);
  const graph = useMemo(() => (kind && lot ? projectImpact(view, { kind, id: lot }, { mode }) : null), [view, kind, lot, mode]);
  const [simOpen, setSimOpen] = useState(false);
  const [traceDir, setTraceDir] = useState<TraceDirection | null>(null);
  const [findings, setFindings] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const recallShown = mode === "current";
  const motorHref = (u: string) => `/dashboard/recall?motor=${encodeURIComponent(u)}`;

  const pick = (
    <div className="card" style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
      <label>Bearing lot<br /><select value={kind === "BEARING_LOT" ? lot ?? "" : ""} onChange={(e) => e.target.value && set({ kind: "bearing", lot: e.target.value, node: null })}>
        <option value="">Choose a lot…</option>{choices.bearingLots.map((l) => <option key={l.id} value={l.id}>{l.id}{recallShown && l.named ? " (named by the recall)" : ""}</option>)}</select></label>
      <label>Raw-material lot (supplier claim)<br /><select value={kind === "RAW_LOT" ? lot ?? "" : ""} onChange={(e) => e.target.value && set({ kind: "raw", lot: e.target.value, node: null })}>
        <option value="">Choose a raw lot…</option>{choices.rawLots.map((l) => <option key={l} value={l}>{l}</option>)}</select></label>
    </div>
  );
  const simBtn = <p><button type="button" className={simOpen ? "btn ghost" : "btn"} aria-expanded={simOpen} onClick={() => setSimOpen((o) => !o)} data-testid="sim-open">{simOpen ? "Hide simulator" : "Simulate impact"}</button></p>;
  const simPanel = simOpen ? <Simulator view={view} mode={mode} motors={snap.units.map((u) => u.unitId)} choices={choices} initial={kind && lot ? { kind, id: lot } : null} /> : null;
  const banner = mode === "noncurrent" ? (
    <div className="banner bad" role="note" data-testid="noncurrent-label"><div><b>Not current.</b> {gateReason || "The verification lease expired; waiting for a new verified snapshot."} Recorded genealogy is shown as what the ledger recorded; recall status, findings and actions are withheld.</div></div>
  ) : null;

  if (!graph) {
    return (
      <div className="inv" data-testid="impact-home">
        <h1>Recall impact graph</h1>
        <p className="lede">Choose a bearing lot, or a raw-material lot, to see every motor the ledger records as linked to it, and every recorded link in between. This page reads the ledger; it does not evaluate or change anything.</p>
        {banner}{pick}{simBtn}{simPanel}
        <ul className="evlist">
          {choices.bearingLots.map((l) => <li key={l.id}><Link href={`${path}?kind=bearing&lot=${encodeURIComponent(l.id)}${motorQ ? `&motor=${motorQ}` : ""}`}>Lot {l.id}</Link>{recallShown && l.named ? <span className="tag AFFECTED" style={{ marginLeft: 8 }}>named by the recall</span> : null}</li>)}
          {choices.rawLots.map((l) => <li key={l}><Link href={`${path}?kind=raw&lot=${encodeURIComponent(l)}${motorQ ? `&motor=${motorQ}` : ""}`}>Raw-material lot {l}</Link> <span className="tag plain">supplier claim</span></li>)}
        </ul>
      </div>
    );
  }

  const selected = nodeId ? graph.nodes.find((n) => n.id === nodeId) ?? null : null;
  const hl = selected && traceDir ? trace(graph, selected.id, traceDir) : null;
  let visible: Set<string> | null = null;
  const narrow = (ids: Set<string>) => { visible = visible ? new Set([...visible].filter((x) => ids.has(x))) : ids; };
  let hiddenByFilter = 0;
  if (findings.size > 0) { const f = filterByFinding(graph, findings); narrow(f.nodeIds); hiddenByFilter = f.hiddenMotors; }
  const q = query.trim().toLowerCase();
  if (q) { const ids = new Set<string>(); for (const h of graph.nodes.filter((n) => n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || (n.unitId ?? "").toLowerCase().includes(q))) for (const id of trace(graph, h.id, "BOTH").nodeIds) ids.add(id); narrow(ids); }
  if (hl) narrow(hl.nodeIds);
  const vis = visible as Set<string> | null;
  const shownCount = vis ? vis.size : graph.nodes.length;
  const windowed = shownCount > DRAW_CAP;
  let graphVisible: ReadonlySet<string> | null = vis; let pages = 1, motorTotal = 0;
  if (windowed) {
    const motors = graph.nodes.filter((n) => (!vis || vis.has(n.id)) && n.kind === "MOTOR").sort(motorOrder);
    motorTotal = motors.length; pages = Math.max(1, Math.ceil(motors.length / MOTOR_WINDOW));
    const p = Math.min(page, pages - 1); const ids = new Set<string>();
    for (const m of motors.slice(p * MOTOR_WINDOW, (p + 1) * MOTOR_WINDOW)) for (const id of trace(graph, m.id, "BOTH").nodeIds) ids.add(id);
    graphVisible = ids;
  }
  const p = Math.min(page, pages - 1);
  const s = graph.summary, current = graph.recallStatus === "CURRENT";
  const toggle = (f: string) => setFindings((prev) => { const n = new Set(prev); if (n.has(f)) n.delete(f); else n.add(f); return n; });
  const select = (id: string) => set({ node: id });

  return (
    <div className="inv" data-testid="impact-workspace">
      <h1>Recall impact graph: {kind === "RAW_LOT" ? "raw-material lot" : "lot"} <code>{graph.selection.id}</code></h1>
      {banner}{pick}{simBtn}{simPanel}
      {!graph.knownSelection && <p className="banner bad" role="alert" data-testid="unknown-lot">The ledger has no record of {kind === "RAW_LOT" ? "raw-material lot" : "lot"} <code>{graph.selection.id}</code>. Nothing is drawn, and this is not evidence that no motor holds it.</p>}
      {graph.knownSelection && <>
        <p className="lede" data-testid="impact-headline">{headline(graph)}</p>
        <p className="note">These are ledger records, not a physical verification of any motor. Excluded with evidence does not mean safe; removal of a part does not mean the lot is eliminated; a shipment record does not mean delivery. Graph connection never decides an outcome: findings are the evaluator&apos;s decisions.</p>
        <div className="grid g4" style={{ margin: "12px 0" }} data-testid="impact-summary">
          <div className="card metric"><span className="eyebrow">Motors linked</span><b>{s.motors}</b></div>
          {s.byFinding && Object.entries(s.byFinding).map(([f, n]) => <div key={f} className="card metric"><span className="eyebrow">{findingLabel(f)}</span><b className={f === "AFFECTED" ? "bad-t" : f === "UNRESOLVED" ? "warn-t" : "ok-t"}>{n}</b></div>)}
          <div className="card metric"><span className="eyebrow">Recorded shipments</span><b>{s.shipmentsRecorded}</b><small>{s.unshippedMotors} without a shipment record</small></div>
          <div className="card metric"><span className="eyebrow">Named only by a rejected claim</span><b>{s.claimOnlyMotors}</b></div>
          <div className="card metric"><span className="eyebrow">Uncertain or conflicting links</span><b className="warn-t">{s.issues.UNCERTAIN + s.issues.CONFLICT}</b></div>
        </div>
        <details className="card" open style={{ marginBottom: 10 }}><summary>Scope and ledger watermark</summary>
          <dl className="kv" style={{ marginTop: 8 }}>
            {current ? <>
              <dt>Recall</dt><dd><code>{graph.scope.recallId}</code> {graph.scope.announced ? `announced ${graph.scope.announcedAt}` : "not announced"}</dd>
              <dt>Affected part</dt><dd><code>{graph.scope.affectedPart}</code></dd>
              <dt>Lots named</dt><dd>{graph.scope.affectedLots.map((l) => <code key={l}>{l} </code>)}</dd>
              <dt>Slots named</dt><dd>{graph.scope.affectedSlots.length ? graph.scope.affectedSlots.map((l) => <code key={l}>{l} </code>) : "none recorded"}</dd>
              <dt>Exposure basis</dt><dd>{graph.scope.exposureBasis ? <code>{graph.scope.exposureBasis}</code> : "Not recorded"}</dd>
              <dt>Scope declaration</dt><dd>{graph.scope.scopeDeclaration ?? "Not recorded"}</dd></> : <><dt>Recall scope</dt><dd>Withheld, because it is a claim about the current recall.</dd></>}
            <dt>Freshness</dt><dd><code>{graph.watermark.status}</code></dd><dt>Journal sequence</dt><dd>{graph.watermark.sequence ?? "Not recorded"}</dd>
            <dt>Head hash</dt><dd><code>{short(graph.watermark.headHash)}</code></dd><dt>Verified at</dt><dd>{when(graph.watermark.verifiedAt)}</dd><dt>Ledger records</dt><dd>{graph.watermark.ledgerEvents}</dd>
          </dl></details>
        {graph.issues.length > 0 && <details className="card" style={{ marginBottom: 10 }} data-testid="impact-issuebox"><summary>Incomplete or uncertain evidence: {s.issues.CONFLICT} conflicting, {s.issues.UNCERTAIN} uncertain, {s.issues.INFO} notes (open for the list)</summary><IssueList issues={graph.issues} snap={snap} /></details>}
        {s.motors === 0 && <p className="note" data-testid="impact-empty">No motor in this snapshot has a ledger-recorded link to this {kind === "RAW_LOT" ? "raw-material lot" : "lot"}. That says what is recorded, not that none exists.</p>}

        <div className="card" style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "end", marginBottom: 10 }}>
          <fieldset disabled={!current} style={{ border: 0, padding: 0, margin: 0 }}><legend className="eyebrow">Show motors by engine finding</legend>
            {Object.keys(FINDING_TEXT).map((f) => <label key={f} style={{ marginRight: 12 }}><input type="checkbox" checked={findings.has(f)} onChange={() => toggle(f)} /> {findingLabel(f)}</label>)}
            {!current && <span className="na"> Findings are withheld.</span>}</fieldset>
          <label>Find a record<br /><input type="search" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} placeholder="motor, serial, shipment…" /></label>
          <div role="group" aria-label="View" style={{ display: "flex", gap: 6 }}>
            <button className={!listView ? "btn" : "btn ghost"} type="button" aria-current={!listView ? "page" : undefined} onClick={() => set({ view: "graph" })}>Graph</button>
            <button className={listView ? "btn" : "btn ghost"} type="button" aria-current={listView ? "page" : undefined} onClick={() => set({ view: "list" })}>List</button>
          </div>
        </div>
        {findings.size > 0 && <p className="na" role="status">{plural(hiddenByFilter, "motor")} hidden by the finding filter. Hidden motors are not cleared.</p>}
        {traceDir && selected && <p className="na" role="status">Showing the {traceDir === "BOTH" ? "backward and forward" : traceDir.toLowerCase()} trace of {selected.label} along recorded links only.</p>}

        {!listView ? <>
          {windowed && <p className="note" role="status" data-testid="impact-window">This trace has {shownCount} records, too many to draw at once. Showing motors {p * MOTOR_WINDOW + 1}–{Math.min(motorTotal, (p + 1) * MOTOR_WINDOW)} of {motorTotal}; the list has every record. <button type="button" className="btn ghost" disabled={p === 0} onClick={() => setPage(p - 1)}>Previous motors</button> <button type="button" className="btn ghost" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>Next motors</button></p>}
          <ImpactGraphView graph={graph} visible={graphVisible} selectedId={selected?.id ?? null} highlight={hl} onSelect={select} />
        </> : <ImpactList graph={graph} visible={vis} selectedId={selected?.id ?? null} onSelect={select} />}
        {selected ? <NodeDetails node={selected} graph={graph} snap={snap} traceDir={traceDir} onTrace={setTraceDir} onSelect={select} motorHref={motorHref} /> : <p className="na" data-testid="impact-hint">Select a record in the {listView ? "list" : "graph"} to see the ledger records behind it.</p>}
        {nodeId && !selected && <p className="banner bad" role="alert">“{nodeId}” is not a record in this trace.</p>}
        {isGated(view) ? null : <p className="note">Historical view: decisions are not part of this view.</p>}
      </>}
    </div>
  );
}
