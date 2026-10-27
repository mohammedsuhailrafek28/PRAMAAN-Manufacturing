"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useData } from "@/dash/data";
import { REASONS, explain } from "@/dash/glossary";
import { evLabel, activity, stepLabel, type Flat } from "@/dash/eda";
import { BASIS, buildReport, isWithdrawnRelease, kpisOf, outcomeOf, shortId, tsOf, type Basis, type Report } from "@/dash/reportModel";
import { buildDailyPdf, pdfFileName } from "@/dash/reportPdf";
import { describe } from "@/dash/trailModel";
import { ActionTag, FindingTag, fmt } from "@/dash/ui";
import type { DecisionCurrent, Snapshot } from "@/dash/types";

const iso = (t: number) => new Date(t).toISOString();
const hhmm = (t?: string) => (t ? t.slice(11, 19) : "—");
const stamp = (t: string) => t.slice(0, 19).replace("T", " ") + " UTC";

export default function ReportPage() {
  const { snap } = useData();
  if (snap.phase === "loading") return <div className="skel" style={{ height: 320 }} />;
  if (snap.phase === "error") return <><h1>Daily operations report</h1><div className="banner bad" role="alert"><div><b>The report is unavailable.</b> The backend data could not be read or verified, so nothing is shown from memory.</div></div></>;
  return <Report s={snap.snap} />;
}

function Report({ s }: { s: Snapshot }) {
  const { gate, mode, reload, verifyNow } = useData();
  const sp = useSearchParams(), router = useRouter(), path = usePathname();
  const basis: Basis = sp.get("basis") === "ingest" ? "ingest" : "source";
  const set = (patch: Record<string, string | null>) => { const q = new URLSearchParams(sp.toString()); for (const [k, v] of Object.entries(patch)) { if (v === null) q.delete(k); else q.set(k, v); } router.replace(`${path}?${q.toString()}`, { scroll: false }); };
  const allowed = gate.decisionsAllowed;
  const probe = useMemo(() => buildReport(s, "", basis, false), [s, basis]);
  const latest = probe.dates[probe.dates.length - 1]?.[0];
  const date = /^\d{4}-\d{2}-\d{2}$/.test(sp.get("date") ?? "") ? (sp.get("date") as string) : latest ?? new Date().toISOString().slice(0, 10);
  const r = useMemo(() => buildReport(s, date, basis, allowed), [s, date, basis, allowed]);
  const [generatedAt, setGeneratedAt] = useState(() => new Date().toISOString());
  useEffect(() => { setGeneratedAt(new Date().toISOString()); }, [date, basis]);
  const generate = () => { setGeneratedAt(new Date().toISOString()); reload(); };
  const [exp, setExp] = useState<{ busy: boolean; kind?: "ok" | "warn" | "bad"; msg?: string }>({ busy: false });

  // Export never reuses the page's cached view: it takes one fresh verified read, recomputes the report from it, and builds the PDF from that.
  const exportPdf = async () => {
    setExp({ busy: true, msg: "Revalidating with the backend…" });
    const v = await verifyNow();
    if (!v.ok) { setExp({ busy: false, kind: "bad", msg: `Export unavailable: ${v.error} [${v.state}] No document was produced and nothing from an earlier snapshot was used.` }); return; }
    try {
      const generated = new Date().toISOString(), name = pdfFileName(date, basis);
      const bytes = buildDailyPdf({ snap: v.snap, allowed: v.allowed, state: v.state, label: v.label, detail: v.detail, date, basis, generatedAt: generated, mode: v.allowed ? "current" : "noncurrent" });
      const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
      const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
      setGeneratedAt(generated);
      setExp(v.allowed ? { busy: false, kind: "ok", msg: `Downloaded ${name} · gate ${v.label}, revalidated just now.` } : { busy: false, kind: "warn", msg: `Downloaded ${name} as a NOT CURRENT report · gate ${v.label}. Findings, actions, holds and decision changes are withheld in the file.` });
    } catch (e) { setExp({ busy: false, kind: "bad", msg: `The PDF could not be built: ${e instanceof Error ? e.message : "unknown error"}. No file was downloaded.` }); }
  };

  return (
    <div className="rpt" data-testid="daily-report">
      <div className="rp-bar no-print" data-testid="report-controls">
        <label>Report date (UTC)<input type="date" value={date} onChange={(e) => e.target.value && set({ date: e.target.value })} data-testid="rp-date" /></label>
        <label>Time basis<select value={basis} onChange={(e) => set({ basis: e.target.value, date: null })} data-testid="rp-basis">{(Object.keys(BASIS) as Basis[]).map((b) => <option key={b} value={b}>{BASIS[b].label}</option>)}</select></label>
        <div className="rp-actions">
          <button type="button" className="rp-export" onClick={exportPdf} disabled={exp.busy} data-testid="rp-export">{exp.busy ? "Preparing PDF…" : "Export PDF"}</button>
          <button type="button" className="btn ghost" onClick={generate} data-testid="rp-generate">Refresh data</button>
          <button type="button" className="btn ghost" onClick={() => window.print()} data-testid="rp-print">Print</button>
        </div>
        <div className="rp-dates" aria-label="Dates with records">
          <span>Dates with records · {BASIS[basis].label.toLowerCase()}</span>
          {r.dates.length === 0 ? <span className="na">none</span> : r.dates.map(([d, n]) => <button key={d} type="button" className="chipbtn" aria-pressed={d === date} onClick={() => set({ date: d })}>{d} · {n}</button>)}
        </div>
        {exp.msg && <p className={`rp-status ${exp.kind ?? ""}`} role="status" data-testid="rp-export-status">{exp.msg}</p>}
      </div>

      <div className="rp-paper">
      <header className="rp-mast" data-testid="report-meta">
        <div className="rp-brand">PRAMAAN <span>Manufacturing · synthetic demonstration data</span></div>
        <h1>Daily operations report</h1>
        <p className="rp-date" data-testid="rp-meta-date">{date}</p>
        <dl className="rp-meta">
          <div><dt>Report date</dt><dd>UTC calendar day<br /><span className="mono dim">00:00:00Z to 24:00:00Z</span></dd></div>
          <div><dt>Time basis</dt><dd data-testid="rp-meta-basis">{BASIS[basis].label}<br /><span className="mono dim">{BASIS[basis].field}</span></dd></div>
          <div><dt>Generated</dt><dd className="mono">{stamp(generatedAt)}</dd></div>
        </dl>
      </header>
      {!allowed && <div className="banner bad rpt-withheld" role="alert" data-testid="rp-notcurrent"><div><b>NOT CURRENT · {gate.label}.</b> Findings, actions, holds and decision changes are withheld. Recorded event claims below are historical and carry the limits in section 07.</div></div>}
      <p className="rp-basis">{BASIS[basis].help}</p>

      <Summary r={r} allowed={allowed} s={s} />
      <Activity r={r} basis={basis} date={date} />
      <Quality r={r} />
      <Corrective r={r} allowed={allowed} date={date} gateLabel={gate.label} basis={basis} />
      <Changes r={r} allowed={allowed} basis={basis} date={date} gateLabel={gate.label} />
      <Risks r={r} allowed={allowed} gateLabel={gate.label} />
      <Provenance r={r} s={s} basis={basis} date={date} generatedAt={generatedAt} mode={mode} gateState={gate.state} gateLabel={gate.label} />
      <p className="print-only mono" data-testid="rp-print-gate">Printed with gate state {gate.state} · {gate.label}. {allowed ? "Current decision sections were derived from a live verified snapshot." : "Current decisions are withheld in this printout."}</p>
      </div>
    </div>
  );
}

const W = (label: string) => <span className="rp-chip bad" data-testid="rp-withheld">WITHHELD · {label}</span>;
const Sec = ({ id, n, title, tag, children }: { id: string; n: string; title: string; tag?: React.ReactNode; children: React.ReactNode }) => (
  <section className="rp-sec" data-testid={`rp-${id}`}><div className="rp-sec-h"><span className="rp-n">{n}</span><h2>{title}</h2>{tag}</div>{children}</section>
);
const Empty = ({ children }: { children: React.ReactNode }) => <p className="na" data-testid="rp-empty">{children}</p>;
const Id = ({ v }: { v: string }) => <span className="rp-id" title={v}><span className="id-s">{shortId(v)}</span><span className="id-f">{v.replace("urn:pramaan:", "")}</span></span>;
const Hist = ({ d }: { d?: DecisionCurrent }) => (
  <div className="rp-hist"><b>Superseded · historical</b>{isWithdrawnRelease(d) && <span>Release eligibility withdrawn. Not in force.</span>}</div>
);

function Summary({ r, allowed, s }: { r: Report; allowed: boolean; s: Snapshot }) {
  const { gate } = useData();
  return (
    <Sec id="a" n="01" title="Executive overview">
      <div className="rp-kpis">{kpisOf(r, allowed, s.units.length, gate.label).map((k) => <div className="rp-kpi" key={k.id} data-testid={k.id}><span>{k.label}</span><b>{k.value}</b><small>{k.sub}</small></div>)}</div>
    </Sec>
  );
}

function Activity({ r, basis, date }: { r: Report; basis: Basis; date: string }) {
  const flat: Flat[] = r.day.map((x) => ({ unitId: x.unitId, e: x.e, t: x.ts ? Date.parse(x.ts) : null }));
  const act = activity(flat, new Set());
  const max = Math.max(1, ...r.byType.map((t) => t[1]));
  const W2 = 560, H = 110, L = 26;
  return (
    <Sec id="b" n="02" title="Manufacturing activity" tag={<span className="rp-chip">Recorded claims</span>}>
      {r.day.length === 0 ? <Empty>No manufacturing events recorded for {date} on the {BASIS[basis].label.toLowerCase()} basis.</Empty> : (
        <div className="rp-two">
          <figure className="rp-fig" data-testid="rp-timeline">
            <svg viewBox={`0 0 ${W2} ${H + 22}`} role="img" aria-label={`Events per ${stepLabel(act.step)} on ${date}`} style={{ width: "100%" }}>
              {act.bursts.map((u, bi) => {
                const total = act.bursts.length, pw = (W2 - L - 10 - 30 * (total - 1)) / total, x0 = L + bi * (pw + 30), bw = pw / u.bins.length;
                return <g key={bi}><line x1={x0} x2={x0 + pw} y1={H} y2={H} stroke="#8c8577" strokeWidth={1} />
                  {u.bins.map((b, i) => <rect key={i} x={x0 + bw * i + 1} width={Math.max(1, bw - 2)} y={H - (b.count / act.max) * (H - 10)} height={(b.count / act.max) * (H - 10)} fill="#ad7944"><title>{`${iso(b.a).slice(11, 16)}: ${b.count}`}</title></rect>)}
                  <text x={x0} y={H + 15} style={{ font: "11px var(--mono)", fill: "#5b5648" }}>{iso(u.a).slice(11, 16)}</text><text x={x0 + pw} y={H + 15} textAnchor="end" style={{ font: "11px var(--mono)", fill: "#5b5648" }}>{iso(u.b).slice(11, 16)}</text>
                  {bi > 0 && <text x={x0 - 15} y={H / 2} textAnchor="middle" style={{ font: "11px var(--mono)", fill: "#ad7944" }}>⋯</text>}</g>;
              })}
              <text x={0} y={12} style={{ font: "11px var(--mono)", fill: "#5b5648" }}>{act.max}</text>
            </svg>
            <figcaption>Events per {stepLabel(act.step)} (UTC), {BASIS[basis].label.toLowerCase()}. Gaps are not interpolated.</figcaption>
          </figure>
          <table className="rp-t" data-testid="rp-bytype"><thead><tr><th>Event type</th><th className="num">Records</th><th aria-label="Share" /></tr></thead>
            <tbody>{r.byType.map(([t, n]) => <tr key={t} data-type={t}><td>{evLabel(t)}</td><td className="num mono">{n}</td><td className="barc"><span className="bar" style={{ width: `${(n / max) * 100}%` }} /></td></tr>)}</tbody></table>
        </div>
      )}
    </Sec>
  );
}

function Quality({ r }: { r: Report }) {
  const q = r.qc;
  return (
    <Sec id="c" n="03" title="Quality inspection" tag={<span className="rp-chip">Recorded claims</span>}>
      <div className="rp-qc" data-testid="rp-qc">
        <div><b className="mono">{q.pass}</b><span>Recorded PASS</span></div><div><b className="mono">{q.fail}</b><span>Recorded FAIL</span></div>
        <div><b className="mono">{q.noOutcome}</b><span>Inspection without explicit outcome</span></div><div><b className="mono">{q.motorsWithoutRecord.length}</b><span>Motors with no inspection record on this date</span></div>
      </div>
      {q.total === 0 && <Empty>No inspection records on this date. Missing records are not read as PASS.</Empty>}
      <p className="rp-note">A recorded PASS is an inspector&apos;s claim. It does not clear a recall and does not authorize shipment.</p>
    </Sec>
  );
}

function Corrective({ r, allowed, date, gateLabel, basis }: { r: Report; allowed: boolean; date: string; gateLabel: string; basis: Basis }) {
  return (
    <Sec id="d" n="04" title="Defects and corrective actions" tag={<span className="rp-chip">Recorded claims</span>}>
      {r.motorRows.length === 0 ? <Empty>No corrective, inspection, verification or decision activity recorded for {date}.</Empty> : (
        <div className="rp-motors" data-testid="rp-motors">{r.motorRows.map((m) => {
          const superseded = !!(m.initial && m.current && m.initial.decisionId !== m.current.decisionId);
          return (
            <article className="rp-motor" key={m.unitId} data-motor={m.unitId}>
              <header><b className="mono">{m.unitId}</b><Link className="linkbtn no-print" href={`/dashboard/recall?motor=${m.unitId}#resolution-trail`}>Resolution trail →</Link></header>
              <div className="rp-grid4">
                <div><h4>Initial finding</h4>{!allowed ? W(gateLabel) : m.initial ? <div className={superseded ? "rp-old" : ""}><FindingTag v={m.initial.evidenceFinding} /> <ActionTag v={m.initial.operationalAction} /><div className="mono dim">v{m.initial.version}{superseded ? "" : " · is the current decision"}</div>{superseded && <Hist d={m.initial} />}</div> : <span className="na">not available</span>}</div>
                <div><h4>Corrective events this date</h4>{m.corrective.length === 0 ? <span className="na">none this date</span> : <ul className="rp-list">{m.corrective.map((e) => <li key={e.eventId}><span className="mono dim">{hhmm(tsOf(e, basis))}</span> {describe(e)}</li>)}</ul>}</div>
                <div><h4>Verification evidence</h4>{m.verification.length === 0 ? <span className="na">No independent confirmation recorded</span> : <ul className="rp-list">{m.verification.map((e) => <li key={e.eventId}>{describe(e)} <span className="rp-chip">claim</span></li>)}</ul>}</div>
                <div><h4>Current finding / action</h4>{!allowed ? W(gateLabel) : m.current ? <><FindingTag v={m.current.evidenceFinding} /> <ActionTag v={m.current.operationalAction} /></> : <span className="na">none</span>}
                  {allowed && m.current && m.current.evidenceFinding !== "EXCLUDED_WITH_EVIDENCE" && (m.current.reasonCodes ?? []).length > 0 && <div className="rp-gaps"><h4>Evidence gaps</h4><ul className="rp-list">{(m.current.reasonCodes ?? []).map((c) => <li key={c} title={explain(REASONS, c)} className="mono">{c}</li>)}</ul></div>}</div>
              </div>
            </article>);
        })}</div>
      )}
      <p className="rp-note">A corrective event or closed work order is a record, not a resolution. Where only a recall announcement exists, no defect-identification event is shown.</p>
    </Sec>
  );
}

function Changes({ r, allowed, basis, date, gateLabel }: { r: Report; allowed: boolean; basis: Basis; date: string; gateLabel: string }) {
  const card = (c: Report["changesDay"][number], undated: boolean) => (
    <article className="rp-chg" key={c.to.decisionId} data-motor={c.unitId} data-undated={undated ? "1" : "0"}>
      <header><b className="mono">{c.unitId}</b><span className="mono dim">v{c.from.version} → v{c.to.version}</span></header>
      <div className="rp-ba">
        <div className="rp-before"><Hist d={c.from} /><div className="rp-old"><FindingTag v={c.from.evidenceFinding} /> <ActionTag v={c.from.operationalAction} /></div></div>
        <div className="rp-arrow" aria-hidden>→</div>
        <div className="rp-after"><span className={c.toCurrent ? "rp-curtag" : "rp-curtag later"}>{c.toCurrent ? "Current decision" : "Later superseded"}</span><div><FindingTag v={c.to.evidenceFinding} /> <ActionTag v={c.to.operationalAction} /></div></div>
      </div>
      <dl className="rp-why">
        <dt>Triggering event</dt><dd>{c.trigger ? <>{describe(c.trigger)}<div className="mono dim">{BASIS[basis].label}: {c.triggerTs ? fmt(c.triggerTs) : "unknown"}</div></> : <span className="na">trigger event not recorded</span>}</dd>
        <dt>Reason change</dt><dd className="mono">{c.addedReasons.length ? `+ ${c.addedReasons.join(", ")}` : ""}{c.removedReasons.length ? ` − ${c.removedReasons.join(", ")}` : ""}{!c.addedReasons.length && !c.removedReasons.length ? "reasons unchanged" : ""}</dd>
      </dl>
    </article>);
  return (
    <Sec id="e" n="05" title="Decision changes" tag={allowed ? <span className="rp-chip ok">Current decision history</span> : W(gateLabel)}>
      {!allowed ? <Empty>Decision history is withheld while the checkpoint is not anchored current.</Empty> : (
        <>
          {r.changesDay.length === 0 ? <Empty>No decision change is attributable to {date}.</Empty> : <div className="rp-chgs" data-testid="rp-changes">{r.changesDay.map((c) => card(c, false))}</div>}
          {r.undated.length > 0 && <><h3 className="rp-h3">Undated changes <span className="rp-chip warn">timing not established</span></h3><div className="rp-chgs" data-testid="rp-undated">{r.undated.map((c) => card(c, true))}</div></>}
          <p className="rp-note">The backend gives a decision version no timestamp. A change is placed on a date only through its trigger event&apos;s {BASIS[basis].label.toLowerCase()}; that is the cause&apos;s time, not when the decision was issued.</p>
        </>
      )}
    </Sec>
  );
}

function Risks({ r, allowed, gateLabel }: { r: Report; allowed: boolean; gateLabel: string }) {
  const grp = (title: string, list: Report["risks"]["affected"], note?: string) => (
    <div className="rp-risk"><h3>{title} <span className="mono">{list.length}</span></h3>
      {list.length === 0 ? <span className="na">none</span> : <ul>{list.map((x) => <li key={x.unitId}><b className="mono">{x.unitId}</b> <ActionTag v={x.d?.operationalAction} /><div className="mono dim">{(x.d?.reasonCodes ?? []).join(" · ")}</div></li>)}</ul>}
      {note && <small>{note}</small>}</div>);
  return (
    <section className="rp-sec rp-now" data-testid="rp-f">
      <div className="rp-sec-h"><span className="rp-n">06</span><h2>Outstanding operational risks</h2><span className="rp-chip now" data-testid="rp-currentstate">Current state at report generation</span></div>
      {!allowed ? <p>{W(gateLabel)} <span className="na">Active holds, findings and eligibility are withheld.</span></p> : (
        <><div className="rp-holds"><b>{r.risks.holds}</b><span>active recall holds</span></div>
          <div className="rp-risks" data-testid="rp-risks">{grp("Affected", r.risks.affected)}{grp("Unresolved", r.risks.unresolved)}{grp("Excluded with evidence", r.risks.excluded, "Not a certification of safety and not an authorization to ship.")}</div></>
      )}
      <p className="rp-note">This section is the current state, not the state on the report date.</p>
    </section>
  );
}

function Provenance({ r, s, basis, date, generatedAt, mode, gateState, gateLabel }: { r: Report; s: Snapshot; basis: Basis; date: string; generatedAt: string; mode: string; gateState: string; gateLabel: string }) {
  const [full, setFull] = useState(false);
  const hash = s.freshness?.headHash;
  return (
    <Sec id="g" n="07" title="Evidence and provenance">
      <dl className="rp-kv" data-testid="rp-prov">
        <dt>Report</dt><dd>{date} · {BASIS[basis].label} · UTC · generated {stamp(generatedAt)}</dd>
        <dt>Checkpoint</dt><dd className="mono">sequence {s.checkpoint?.anchoredSequence ?? "?"} · ledger sequence {s.freshness?.sequence ?? "?"} · {s.freshness?.status ?? "freshness unknown"}</dd>
        <dt>Head hash</dt><dd className="mono">{hash ? <span className="rp-id" title={hash}><span className="id-s">{hash.slice(0, 16)}…{hash.slice(-8)}</span><span className="id-f">{hash}</span></span> : "not available"}</dd>
        <dt>Gate</dt><dd><span className="rp-chip">{gateState}</span> {gateLabel} · {mode === "current" ? "current" : "not current"} · verified {fmt(s.freshness?.verifiedAt)}</dd>
        <dt>Data</dt><dd>Synthetic ledger demonstration ({s.units.length} motors; {r.rows.length} ledger events). {r.unknown > 0 ? `${r.unknown} events have no timestamp on this basis and are in no date.` : "Every event has a timestamp on this basis."}</dd>
      </dl>
      <ul className="rp-limits">
        <li>The checkpoint is a self-exported anchor held on the same machine. It shows the ledger was not altered since export; it is not independent custody.</li>
        <li>Event times and actors are source claims from a simulated clock. Ingestion time is when this ledger received the event, not when the work happened.</li>
        <li>Hashes show a stored record is unchanged. They do not show who issued it or that it is true.</li>
        <li>A repair record or a recorded QC PASS does not clear a recall.</li>
      </ul>
      <div className="rp-refs-h"><h3 className="rp-h3">Source event references ({r.day.length})</h3>{r.day.length > 0 && <button type="button" className="linkbtn no-print" onClick={() => setFull((v) => !v)} aria-pressed={full} data-testid="rp-fullids">{full ? "Show shortened identifiers" : "Show full identifiers"}</button>}</div>
      {r.day.length === 0 ? <Empty>No events on this date.</Empty> : (
        <div className="rp-scroll"><table className={`rp-t refs ${full ? "full" : ""}`} data-testid="rp-refs"><thead><tr><th>{BASIS[basis].label}</th><th>Motor</th><th>Type</th><th>Event</th><th>Source #</th><th>Ingested</th></tr></thead>
          <tbody>{r.day.map((x) => <tr key={x.e.eventId} data-outcome={outcomeOf(x.e)}><td className="mono">{x.ts ? x.ts.slice(11, 19) : "unknown"}</td><td className="mono">{x.unitId}</td><td>{evLabel(x.e.eventType)}</td><td className="mono"><Id v={x.e.eventId} /></td><td className="mono">{x.e.sourceId}#{x.e.sourceSeq}</td><td className="mono">{x.e.repository?.localReceivedAt?.slice(0, 19).replace("T", " ") ?? "unknown"}</td></tr>)}</tbody></table></div>
      )}
    </Sec>
  );
}
