import { useMemo, useState } from "react";
import { FINDING_TEXT, humanize } from "../domain/glossary";
import type { RecallSnapshot } from "../domain/types";
import { ImpactGraphView } from "./ImpactGraphView";
import { ImpactList } from "./ImpactList";
import { motorOrder } from "./layout";
import { IssueList, NodeDetails } from "./NodeDetails";
import { buildImpactGraph, filterByFinding, lotChoices, trace, type ImpactGraph, type TraceDirection } from "./projection";
import { lotHref, type Route, type ViewMode } from "./route";

export interface Banner { kind: "preview" | "noncurrent"; text: string }
/** current: freshly verified live ledger. noncurrent: live but unverified or expired. preview: labelled authored data. */
export type Mode = "current" | "noncurrent" | "preview";

/** Above this many nodes the graph draws a window of motors; the list always has everything. */
export const DRAW_CAP = 400;
export const MOTOR_WINDOW = 40;

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const findingLabel = (f: string) => FINDING_TEXT[f]?.label ?? humanize(f);

export function headline(g: ImpactGraph): string {
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

export function ImpactWorkspace({ snap, route, mode, banner, datasetNote }: { snap: RecallSnapshot; route: Route; mode: Mode; banner: Banner | null; datasetNote?: React.ReactNode }) {
  const choices = useMemo(() => lotChoices(snap), [snap]);
  const recallShown = mode !== "noncurrent";
  const graph = useMemo(
    () => (route.page === "lot" ? buildImpactGraph(snap, { kind: route.kind, id: route.lotId }, { recallStatusCurrent: recallShown }) : null),
    [snap, route, recallShown],
  );
  const [traceDir, setTraceDir] = useState<TraceDirection | null>(null);
  const [findings, setFindings] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const mobileDefault = typeof window !== "undefined" && !!window.matchMedia?.("(max-width: 720px)").matches;

  if (route.page === "invalid") return null;
  const lotSelect = (
    <form className="ig-pick" onSubmit={(e) => e.preventDefault()}>
      <label>Bearing lot
        <select value={route.page === "lot" && route.kind === "BEARING_LOT" ? route.lotId : ""} onChange={(e) => { if (e.target.value) window.location.hash = lotHref("BEARING_LOT", e.target.value); }}>
          <option value="">Choose a lot…</option>
          {choices.bearingLots.map((l) => <option key={l.id} value={l.id}>{l.id}{recallShown && l.named ? " (named by the recall)" : ""}</option>)}
        </select>
      </label>
      <label>Raw-material lot (supplier claim)
        <select value={route.page === "lot" && route.kind === "RAW_LOT" ? route.lotId : ""} onChange={(e) => { if (e.target.value) window.location.hash = lotHref("RAW_LOT", e.target.value); }}>
          <option value="">Choose a raw lot…</option>
          {choices.rawLots.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </label>
    </form>
  );

  if (route.page === "home" || !graph) {
    return (
      <div className="ig" data-testid="impact-home">
        <h2>Recall impact graph</h2>
        <p className="lead">Choose a bearing lot, or a raw-material lot, to see every motor the ledger records as linked to it, and every recorded link in between. This page reads the ledger; it does not evaluate or change anything.</p>
        {banner && <p className={`callout ${banner.kind === "preview" ? "callout-warn" : "warn"}`} role="note">{banner.text}</p>}
        {datasetNote}
        {lotSelect}
        <ul className="ig-lots">
          {choices.bearingLots.map((l) => <li key={l.id}><a href={lotHref("BEARING_LOT", l.id)}>Lot {l.id}</a>{recallShown && l.named ? <> <span className="tag">named by the recall</span></> : null}</li>)}
          {choices.rawLots.map((l) => <li key={l}><a href={lotHref("RAW_LOT", l)}>Raw-material lot {l}</a> <span className="tag">supplier claim</span></li>)}
        </ul>
      </div>
    );
  }

  const view: ViewMode = route.view ?? (mobileDefault ? "list" : "graph");
  const selected = route.nodeId ? graph.nodes.find((n) => n.id === route.nodeId) ?? null : null;
  const hl = selected && traceDir ? trace(graph, selected.id, traceDir) : null;

  // ---- which nodes are shown
  let visible = null as Set<string> | null;
  const narrow = (ids: Set<string>) => { visible = visible ? new Set([...visible].filter((x) => ids.has(x))) : ids; };
  let hiddenByFilter = 0;
  if (findings.size > 0) { const f = filterByFinding(graph, findings); narrow(f.nodeIds); hiddenByFilter = f.hiddenMotors; }
  const q = query.trim().toLowerCase();
  if (q) {
    const hits = graph.nodes.filter((n) => n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || (n.unitId ?? "").toLowerCase().includes(q));
    const ids = new Set<string>();
    for (const h of hits) for (const id of trace(graph, h.id, "BOTH").nodeIds) ids.add(id);
    narrow(ids);
  }
  if (hl) narrow(hl.nodeIds);
  const shownCount = visible ? visible.size : graph.nodes.length;
  const windowed = shownCount > DRAW_CAP;
  let graphVisible: ReadonlySet<string> | null = visible;
  let pages = 1;
  let motorTotal = 0;
  if (windowed) {
    const pool = graph.nodes.filter((n) => !visible || visible.has(n.id));
    const motors = pool.filter((n) => n.kind === "MOTOR").sort(motorOrder);
    motorTotal = motors.length;
    pages = Math.max(1, Math.ceil(motors.length / MOTOR_WINDOW));
    const p = Math.min(page, pages - 1);
    const ids = new Set<string>();
    for (const m of motors.slice(p * MOTOR_WINDOW, (p + 1) * MOTOR_WINDOW)) for (const id of trace(graph, m.id, "BOTH").nodeIds) ids.add(id);
    graphVisible = ids;
  }
  const p = Math.min(page, pages - 1);
  const s = graph.summary;
  const current = graph.recallStatus === "CURRENT";
  const toggle = (f: string) => setFindings((prev) => { const n = new Set(prev); if (n.has(f)) n.delete(f); else n.add(f); return n; });
  const select = (id: string) => { window.location.hash = lotHref(route.kind, route.lotId, view, id); };

  return (
    <div className="ig" data-testid="impact-workspace">
      <h2>Recall impact graph: {graph.selection.kind === "RAW_LOT" ? "raw-material lot" : "lot"} <code>{graph.selection.id}</code></h2>
      {banner && <p className={`callout ${banner.kind === "preview" ? "callout-warn" : "warn"}`} role="note" data-testid="impact-banner">{banner.text}</p>}
      {datasetNote}
      {mode === "noncurrent" && (
        <p className="warn" role="note" data-testid="noncurrent-label">
          Not current. This recorded genealogy comes from a snapshot that is not freshly verified. It shows what the ledger recorded at that time; it is not the current state, and recall status, findings and actions are withheld.
        </p>
      )}
      {lotSelect}
      {!graph.knownSelection && (
        <p className="warn" role="alert" data-testid="unknown-lot">The ledger has no record of {graph.selection.kind === "RAW_LOT" ? "raw-material lot" : "lot"} <code>{graph.selection.id}</code>. Nothing is drawn, and this is not evidence that no motor holds it.</p>
      )}
      {graph.knownSelection && (
        <>
          <p className="lead" data-testid="impact-headline">{headline(graph)}</p>
          <p className="muted">These are ledger records, not a physical verification of any motor. Excluded with evidence does not mean safe; removal of a part does not mean the lot is eliminated; a shipment record does not mean delivery.</p>

          <ul className="stats" aria-label="Summary" data-testid="impact-summary">
            <li><b>{s.motors}</b> motors linked</li>
            {s.byFinding && Object.entries(s.byFinding).map(([f, n]) => <li key={f} className={`finding-${f}`}><b>{n}</b> {findingLabel(f)}</li>)}
            <li><b>{s.shipmentsRecorded}</b> recorded shipments</li>
            <li><b>{s.unshippedMotors}</b> without a shipment record</li>
            <li><b>{s.claimOnlyMotors}</b> named only by a rejected claim</li>
            <li><b>{s.issues.UNCERTAIN + s.issues.CONFLICT}</b> uncertain or conflicting links</li>
          </ul>

          <div className="ig-panels">
            <details className="ig-scope" open>
              <summary>Scope and ledger watermark</summary>
              <dl className="defs">
                {current ? (
                  <>
                    <div><dt>Recall</dt><dd><code>{graph.scope.recallId}</code> {graph.scope.announced ? `announced ${graph.scope.announcedAt}` : "not announced"}</dd></div>
                    <div><dt>Affected part</dt><dd><code>{graph.scope.affectedPart}</code></dd></div>
                    <div><dt>Lots named by the recall</dt><dd>{graph.scope.affectedLots.map((l) => <code key={l}>{l} </code>)}</dd></div>
                    <div><dt>Slots named by the recall</dt><dd>{graph.scope.affectedSlots.length ? graph.scope.affectedSlots.map((l) => <code key={l}>{l} </code>) : "none recorded"}</dd></div>
                    <div><dt>Exposure basis</dt><dd>{graph.scope.exposureBasis ? <code>{graph.scope.exposureBasis}</code> : "Not recorded"}</dd></div>
                    <div><dt>Scope declaration</dt><dd>{graph.scope.scopeDeclaration ?? "Not recorded"}</dd></div>
                  </>
                ) : <div><dt>Recall scope</dt><dd>Withheld, because it is a claim about the current recall.</dd></div>}
                <div><dt>Freshness status</dt><dd><code>{graph.watermark.status}</code></dd></div>
                <div><dt>Journal sequence</dt><dd>{graph.watermark.sequence ?? "Not recorded"}</dd></div>
                <div><dt>Head hash</dt><dd><code>{graph.watermark.headHash ? `${graph.watermark.headHash.slice(0, 16)}…` : "Not recorded"}</code></dd></div>
                <div><dt>Verified at</dt><dd>{graph.watermark.verifiedAt ?? "Not recorded"}</dd></div>
                <div><dt>Ledger records in this snapshot</dt><dd>{graph.watermark.ledgerEvents}</dd></div>
              </dl>
            </details>
          </div>

          {graph.issues.length > 0 && (
            <details className="ig-issuebox" data-testid="impact-issuebox">
              <summary>Incomplete or uncertain evidence: {s.issues.CONFLICT} conflicting, {s.issues.UNCERTAIN} uncertain, {s.issues.INFO} notes (open for the list)</summary>
              <IssueList issues={graph.issues} snap={snap} />
            </details>
          )}
          {s.motors === 0 && <p className="callout" data-testid="impact-empty">No motor in this snapshot has a ledger-recorded link to this {graph.selection.kind === "RAW_LOT" ? "raw-material lot" : "lot"}. That says what is recorded, not that none exists.</p>}

          <div className="ig-controls">
            <fieldset className="ig-findings" disabled={!current}>
              <legend>Show motors by engine finding</legend>
              {Object.keys(FINDING_TEXT).map((f) => (
                <label key={f}><input type="checkbox" checked={findings.has(f)} onChange={() => toggle(f)} /> {findingLabel(f)}</label>
              ))}
              {!current && <span className="muted"> Findings are withheld.</span>}
            </fieldset>
            <label className="ig-search">Find a record
              <input type="search" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} placeholder="motor, serial, shipment…" />
            </label>
            <div className="pill-row" role="group" aria-label="View">
              <a className="pill" href={lotHref(route.kind, route.lotId, "graph", route.nodeId)} aria-current={view === "graph" ? "page" : undefined}>Graph</a>
              <a className="pill" href={lotHref(route.kind, route.lotId, "list", route.nodeId)} aria-current={view === "list" ? "page" : undefined}>List</a>
            </div>
          </div>
          {findings.size > 0 && <p className="muted" role="status">{plural(hiddenByFilter, "motor")} hidden by the finding filter. Hidden motors are not cleared.</p>}
          {traceDir && selected && <p className="muted" role="status">Showing the {traceDir === "BOTH" ? "backward and forward" : traceDir.toLowerCase()} trace of {selected.label} along recorded links only.</p>}

          {view === "graph" ? (
            <>
              {windowed && (
                <p className="callout" role="status" data-testid="impact-window">
                  This trace has {shownCount} records, too many to draw at once. The graph shows motors {p * MOTOR_WINDOW + 1}–{Math.min(motorTotal, (p + 1) * MOTOR_WINDOW)} of {motorTotal} in order of finding, then identifier (page {p + 1} of {pages}); the list has every record.{" "}
                  <button type="button" disabled={p === 0} onClick={() => setPage(p - 1)}>Previous motors</button>{" "}
                  <button type="button" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>Next motors</button>
                </p>
              )}
              <ImpactGraphView graph={graph} visible={graphVisible} selectedId={selected?.id ?? null} highlight={hl} onSelect={select} />
            </>
          ) : (
            <ImpactList graph={graph} visible={visible} selectedId={selected?.id ?? null} onSelect={select} />
          )}
          {selected ? (
            <NodeDetails node={selected} graph={graph} snap={snap} traceDir={traceDir} onTrace={setTraceDir} onSelect={select} />
          ) : (
            <p className="muted" data-testid="impact-hint">Select a record in the {view} to see the ledger records behind it.</p>
          )}
          {route.nodeId && !selected && <p className="warn" role="alert">“{route.nodeId}” is not a record in this trace.</p>}
        </>
      )}
    </div>
  );
}
