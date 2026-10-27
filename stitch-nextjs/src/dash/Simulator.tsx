"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { projectImpact, type lotChoicesOf } from "@/orig/contract/views";
import type { PageView } from "@/orig/contract/gated";
import { useData } from "@/dash/data";
import { epochOf } from "@/dash/consistency";
import { HYPOTHETICAL, reachText, simulate, summaryText } from "@/dash/simulate";
import { smoothTo } from "@/motion/scroll";

type Pick = { kind: "BEARING_LOT" | "RAW_LOT"; id: string };
type Ran = Pick & { epoch: string | null };

/** Hypothetical, read-only blast-radius simulation over the existing genealogy projection. It is not a recall decision and writes nothing. */
export function Simulator({ view, mode, motors, choices, initial }: { view: PageView; mode: "current" | "noncurrent"; motors: string[]; choices: ReturnType<typeof lotChoicesOf>; initial: Pick | null }) {
  const { snap } = useData();
  const epoch = epochOf(snap.phase === "ready" ? snap.snap : null);
  const [sel, setSel] = useState(initial ? `${initial.kind}|${initial.id}` : "");
  const [ran, setRan] = useState<Ran | null>(null);
  const [copied, setCopied] = useState("");
  const [rerun, setRerun] = useState(false);
  const results = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLElement>(null);

  useEffect(() => { smoothTo(root.current); }, []);
  const run = () => {
    const [kind, id] = sel.split("|");
    if (!kind || !id) return;
    setCopied(""); setRerun(false); setRan({ kind: kind as Pick["kind"], id, epoch });
    window.setTimeout(() => smoothTo(results.current), 30);
  };
  // The result is always recomputed from the view the dashboard currently holds, so a new snapshot epoch re-runs it instead of leaving a stale answer.
  const graph = useMemo(() => (ran ? projectImpact(view, { kind: ran.kind, id: ran.id }, { mode }) : null), [ran, view, mode]);
  const sim = useMemo(() => (graph ? simulate(graph, motors) : null), [graph, motors]);
  const label = useMemo(() => { const m = new Map((graph?.nodes ?? []).map((n) => [n.id, n.label])); return (id: string) => m.get(id) ?? id; }, [graph]);
  useEffect(() => { if (ran && ran.epoch !== epoch) { setRan({ ...ran, epoch }); setRerun(true); } }, [epoch]); // eslint-disable-line react-hooks/exhaustive-deps
  const text = sim ? summaryText(sim, label) : "";
  const copy = async () => { try { await navigator.clipboard.writeText(text); setCopied("Copied. Nothing was sent or saved."); } catch { setCopied("Copy is not available in this browser; select the text above instead."); } };

  return (
    <section ref={root} id="simulator" tabIndex={-1} className="card sim" data-testid="sim" aria-label="Recall blast-radius simulator">
      <div className="sim-head"><h2>Simulate impact</h2><span className="tag warn" data-testid="sim-label">{HYPOTHETICAL}</span></div>
      <p className="note">Pick a bearing lot or raw-material lot from the ledger and follow its recorded links forward to the motors they reach. This is a what-if for investigators. It is not a recall decision, creates no evidence, and cannot hold, clear or release anything.</p>
      <div className="sim-pick">
        <label>Batch or lot<br />
          <select value={sel} onChange={(e) => setSel(e.target.value)} data-testid="sim-select">
            <option value="">Choose a lot…</option>
            <optgroup label="Bearing lots">{choices.bearingLots.map((l) => <option key={l.id} value={`BEARING_LOT|${l.id}`}>{l.id}</option>)}</optgroup>
            <optgroup label="Raw-material lots (supplier claim)">{choices.rawLots.map((l) => <option key={l} value={`RAW_LOT|${l}`}>{l}</option>)}</optgroup>
          </select></label>
        <button type="button" className="btn" disabled={!sel} onClick={run} data-testid="sim-run">Run simulation</button>
      </div>

      <div ref={results} id="sim-results" tabIndex={-1} aria-live="polite">
        {sim && ran && (
          <div data-testid="sim-results">
            {rerun && <p className="banner bad" role="status" data-testid="sim-rerun"><span>The snapshot changed; this result was re-run against the new evidence.</span></p>}
            <div className="banner bad" role="note"><div><b>{HYPOTHETICAL}.</b> Exposure below is graph reachability from {sim.selection.kind === "RAW_LOT" ? "raw-material lot" : "lot"} <code>{sim.selection.id}</code> along recorded links. It is not a verified recall decision.</div></div>
            {!sim.found ? <p className="banner bad" role="alert" data-testid="sim-unknown">The ledger has no record of <code>{sim.selection.id}</code>. Nothing was traversed.</p> : <>
              <div className="grid g4" style={{ margin: "10px 0" }} data-testid="sim-summary">
                <div className="card metric"><span className="eyebrow">Potentially exposed motors</span><b data-testid="sim-count">{sim.exposedMotors}</b></div>
                <div className="card metric"><span className="eyebrow">Not counted (conflict or untrusted)</span><b>{sim.exposures.filter((x) => x.reach === "UNCONFIRMED").length}</b></div>
                <div className="card metric"><span className="eyebrow">Gaps in the evidence</span><b className="warn-t">{sim.gaps.length}</b></div>
                <div className="card metric"><span className="eyebrow">No recorded path</span><b>{sim.notLinked.length}</b><small>absence of a record, not safety</small></div>
              </div>
              {sim.exposedMotors === 0 && <p className="note" data-testid="sim-zero">No known exposure is recorded for this lot. That describes the records; it does not mean the lot is safe.</p>}
              {sim.exposures.length > 0 && <div className="scroll"><table className="t" data-testid="sim-table">
                <thead><tr><th>Motor</th><th>Reach</th><th>Recorded path</th><th>Shipment</th><th>Current verified decision (engine)</th></tr></thead>
                <tbody>{sim.exposures.map((x) => (
                  <tr key={x.nodeId}>
                    <td><Link href={`/dashboard/recall?motor=${encodeURIComponent(x.motor)}`}>{x.motor}</Link></td>
                    <td><span className={`tag ${x.reach === "CONFIRMED" ? "bad" : "warn"}`}>{x.reach === "UNCONFIRMED" ? "NOT COUNTED" : x.reach}</span><div className="na">{reachText(x.reach)}{x.historical ? "; historical link" : ""}</div></td>
                    <td className="mono">{x.paths.slice(0, 2).map((p, i) => <div key={i}>{p.map(label).join(" → ")}</div>)}{x.paths.length > 2 || x.pathsCapped ? <div className="na">{x.paths.length > 2 ? `+${x.paths.length - 2} more path(s)` : ""}{x.pathsCapped ? " (path list capped)" : ""}</div> : null}</td>
                    <td>{x.shipped ? "recorded" : <span className="na">none recorded</span>}</td>
                    <td data-testid="sim-decision">{sim.decisionsShown && x.status ? <><span className="tag info">CURRENT</span> {x.status.finding}{x.status.hold ? " · RECALL HOLD" : ""}</> : <span className="na">Withheld: verification is not current</span>}</td>
                  </tr>))}</tbody></table></div>}
              {sim.gaps.length > 0 && <details className="card" style={{ marginTop: 10 }} data-testid="sim-gaps"><summary>Incomplete or uncertain evidence ({sim.gaps.length})</summary><ul>{sim.gaps.slice(0, 20).map((g, i) => <li key={i}><span className="tag warn">{g.severity}</span> {g.message}</li>)}</ul></details>}
              {sim.notLinked.length > 0 && <p className="na" data-testid="sim-notlinked">No recorded path from this lot: {sim.notLinked.join(", ")}.</p>}
              <p className="note">Simulated exposure and the engine&apos;s decisions are different things. A motor missing here is not cleared, and a motor listed here is not thereby held or recalled.{!sim.decisionsShown && " Current decisions are withheld because verification is not current."}</p>
              <h3 style={{ marginTop: 12 }}>Investigation summary</h3>
              <pre className="ml-note mono sim-note" data-testid="sim-note">{text}</pre>
              <button type="button" className="btn ghost" onClick={() => void copy()} data-testid="sim-copy">Copy summary</button> <span className="na" role="status">{copied}</span>
            </>}
          </div>
        )}
      </div>
    </section>
  );
}
