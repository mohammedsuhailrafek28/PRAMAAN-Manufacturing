"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { initReveal } from "@/motion/reveal";
import { Def, Heatmap, QcChart, StatusChart, TimelineChart } from "@/dash/Charts";
import { eventTypes, flatEvents, qcStates, type QcState } from "@/dash/eda";
import { useData } from "@/dash/data";
import { ActionTag, FindingTag, NA, currentOf, fmt, useMotor, val } from "@/dash/ui";
import type { Snapshot } from "@/dash/types";

export default function OverviewPage() {
  const { snap } = useData();
  if (snap.phase === "loading") return <div className="grid g4"><div className="skel" /><div className="skel" /><div className="skel" /><div className="skel" /></div>;
  if (snap.phase === "error") return <><h1>Overview</h1><p>The operational summary is unavailable because the backend data could not be read. Nothing is shown from memory or samples.</p></>;
  return <Overview s={snap.snap} />;
}

function Overview({ s }: { s: Snapshot }) {
  const { gate, mode } = useData();
  const [motor, setMotor, href] = useMotor(s);
  const [statusF, setStatusF] = useState<string | null>(null);
  const [qcF, setQcF] = useState<QcState | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  // Noncritical recorded-fact cards (inspection chart, event heatmap) and the investigation path ease in as they scroll into view.
  // KPIs, the status chart, the timeline (it carries the not-current badge and freshness line) and the register are never animated.
  useEffect(() => {
    const eda = document.querySelector(".ov .eda");
    const cards = eda ? [eda.children[1], eda.children[3]].filter((x): x is Element => !!x) : [];
    return initReveal([...cards, ...document.querySelectorAll(".ov .chips")], { skipCritical: true });
  }, []);
  const flat = useMemo(() => flatEvents(s), [s]);
  const types = useMemo(() => eventTypes(flat), [flat]);
  const qc = useMemo(() => qcStates(s, flat), [s, flat]);
  const a = gate.decisionsAllowed;
  const rows = s.units.map((u) => ({ u, d: a ? currentOf(s, u.unitId) : undefined, de: s.components.filter((c) => c.unitId === u.unitId && !c.removedAt) }));
  const counts: Record<string, number> = {};
  for (const r of rows) if (r.d?.evidenceFinding) counts[r.d.evidenceFinding] = (counts[r.d.evidenceFinding] ?? 0) + 1;
  const shown = rows.filter((r) => (!statusF || r.d?.evidenceFinding === statusF) && (!qcF || qc.per.find((p) => p.unitId === r.u.unitId)?.state === qcF));
  const W = <span className="na">withheld</span>;
  const rc = s.recall;
  const age = s.freshness?.verifiedAt ? fmt(s.freshness.verifiedAt).slice(11, 19) : "—";
  return (
    <div className="ov">
      <header className="pagehead"><h1>Operational overview</h1><p className="lede">{s.units.length} motors under recall {rc.recallId}. Findings and holds appear only while the checkpoint is anchored current.</p></header>
      <div className="kpis" data-testid="kpis">
        <div className="kpi"><span className="eyebrow">Motors</span><b>{s.units.length}</b><small>{s.components.length} installs</small></div>
        <div className="kpi"><span className="eyebrow">Ledger events</span><b>{flat.length}</b><small>{types.length} types</small></div>
        <div className="kpi"><span className="eyebrow">Recall</span><b className="mono">{rc.recallId}</b><small>lot {(rc.affectedLots ?? []).join(", ") || "—"} · slot {(rc.affectedSlots ?? []).join(", ") || "—"}</small></div>
        <div className="kpi"><span className="eyebrow">Recall holds</span><b>{a ? rows.filter((r) => r.d?.operationalAction === "RECALL_HOLD").length : W}</b><small>{a ? "of " + rows.length : gate.label}</small></div>
        <div className="kpi"><span className="eyebrow">Inspections recorded</span><b>{qc.PASS + qc.FAIL}</b><small>of {s.units.length} motors</small></div>
        <div className="kpi"><span className="eyebrow">Checkpoint</span><b>{s.checkpoint?.anchoredSequence ?? "?"}</b><small>{mode === "current" ? "current" : "not current"} · {age}</small></div>
      </div>

      <div className="eda">
        <StatusChart counts={counts} allowed={a} gateLabel={gate.label} active={statusF} onPick={setStatusF} />
        <QcChart q={qc} active={qcF} onPick={setQcF} />
        <TimelineChart s={s} flat={flat} types={types} hidden={hidden} setHidden={setHidden} current={mode === "current"} />
        <div className="wide"><Heatmap s={s} flat={flat} hidden={hidden} setHidden={setHidden} /></div>
      </div>

      <div className="sect-h"><h2>Motor register</h2><span className="na" data-testid="register-count">{shown.length} of {rows.length}</span>{(statusF || qcF) && <button className="btn ghost" onClick={() => { setStatusF(null); setQcF(null); }}>Clear filters</button>}</div>
      <div className="scroll">
        <table className="t">
          <thead><tr><th>Motor</th><th>Record</th><th>Finding</th><th>Action</th><th>DE lot</th><th>Shipment (claim)</th><th>Open</th></tr></thead>
          <tbody>
            {shown.map(({ u, d, de }) => {
              const lot = de.find((c) => c.slot === "DE")?.lot;
              return (
                <tr key={u.unitId} className={u.unitId === motor ? "sel" : ""} onClick={() => setMotor(u.unitId)}>
                  <td><b className="mono">{u.unitId}</b></td>
                  <td>{u.title ?? NA}<div className="na">{u.family} · {u.eventCount} events</div></td>
                  <td>{a ? <FindingTag v={d?.evidenceFinding} /> : <span className="tag bad">[WITHHELD]</span>}</td>
                  <td>{a ? <ActionTag v={d?.operationalAction} /> : null}</td>
                  <td className="mono">{lot ?? NA}</td>
                  <td>{u.shipment ? <><span className="mono">{u.shipment.shipmentId}</span><div className="na">{u.shipment.destination}</div></> : <span className="na">none</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}><Link className="btn ghost" href={`/dashboard/recall?motor=${u.unitId}`}>Reasoning</Link> <Link className="btn ghost" href={`/dashboard/genealogy?motor=${u.unitId}`}>Genealogy</Link> <Link className="btn ghost" href={`/dashboard/passport?motor=${u.unitId}`}>Passport</Link></td>
                </tr>
              );
            })}
            {shown.length === 0 && <tr><td colSpan={7} className="na">No motors match the filters.</td></tr>}
          </tbody>
        </table>
      </div>

      <nav className="chips" aria-label="Investigation path">
        {[["/dashboard/genealogy", "1 Genealogy"], ["/dashboard/recall", "2 Recall reasoning"], ["/dashboard/impact", "3 Impact graph"], ["/dashboard/evidence", "4 Evidence"], ["/dashboard/passport", "5 Passport"], ["/dashboard/performance", "6 Performance"]].map(([to, t]) => <Link key={to} href={href(to)}>{t}</Link>)}
        <span style={{ marginLeft: "auto" }}><Def>Data kind: {s.provenance?.dataKind ?? "unknown"} · engine {s.provenance?.engine?.version ?? "unknown"} / {s.provenance?.engine?.semanticsProfile ?? "unknown"}. Announced {fmt(rc.announcedAt)}; exposure basis {rc.exposureBasis ?? "not stated"}. Figures come from the anchored backend and nothing is estimated in the browser. Import and field-mapping results are not exposed by this backend, so they are not shown.</Def></span>
      </nav>
    </div>
  );
}
