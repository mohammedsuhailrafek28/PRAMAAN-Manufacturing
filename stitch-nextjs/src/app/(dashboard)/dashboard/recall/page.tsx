"use client";

import Link from "next/link";
import { useState } from "react";
import ResolutionTrail from "@/dash/Trail";
import { useData, useMotorResource, useMotorResourceChecked } from "@/dash/data";
import { ResourceNote } from "@/dash/ResourceNote";
import { ACTION_TEXT, FINDING_TEXT, FLAGS, REASONS, explain, humanize } from "@/dash/glossary";
import { ActionTag, FindingTag, NA, currentOf, fmt, unitOf, useMotor, val } from "@/dash/ui";
import type { Checkpoint, DecisionBundle, DecisionCurrent, Lifecycle, ProvenanceRow, Snapshot } from "@/dash/types";

type DecisionsBody = Record<string, DecisionBundle | Checkpoint | { currentReleaseEligible?: boolean }> & { checkpoint?: Checkpoint; eligibility?: { currentReleaseEligible?: boolean } };

export default function RecallPage() {
  const { snap } = useData();
  if (snap.phase === "loading") return <div className="skel" style={{ height: 320 }} />;
  if (snap.phase === "error") return <p>The recall investigation is unavailable because the backend data could not be read.</p>;
  return <Recall s={snap.snap} />;
}

function Recall({ s }: { s: Snapshot }) {
  const { gate } = useData();
  const [motor, setMotor, href] = useMotor(s);
  const rc = s.recall;
  const rows = s.units.map((u) => ({ u, d: currentOf(s, u.unitId), elig: s.eligibility?.[u.unitId]?.currentReleaseEligible }));
  const allowed = gate.decisionsAllowed;
  const n = (f: string) => rows.filter((r) => r.d?.evidenceFinding === f).length;
  const holds = rows.filter((r) => r.d?.operationalAction === "RECALL_HOLD").length;
  const eligible = rows.filter((r) => r.elig === true).length;
  const W = <span className="na">withheld</span>;

  return (
    <div className="inv">
      <h1>Recall investigation</h1>
      <p className="lede">{rows.length} motors, one recall. Each outcome below is the engine&apos;s published decision, read from the backend; this page computes nothing. A hold is an operational action; it is not a finding that the motor is defective.</p>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="eyebrow">Recall {rc.recallId}</div>
        <dl className="kv" style={{ marginTop: 6 }}>
          <dt>Affected part</dt><dd>{val(rc.affectedPart)}</dd>
          <dt>Affected lots</dt><dd>{(rc.affectedLots ?? []).map((l) => <span key={l} style={{ marginRight: 10 }}><span className="tag AFFECTED" style={{ marginRight: 6 }}>{l}</span><Link className="btn ghost" href={`/dashboard/impact?kind=bearing&lot=${encodeURIComponent(l)}`}>Trace lot {l} to motors</Link></span>)}</dd>
          <dt>Covered slots</dt><dd>{(rc.affectedSlots ?? []).join(", ") || NA} <span className="na">({rc.scopeDeclaration ?? "scope not stated"}; exposure basis {rc.exposureBasis ?? "not stated"})</span></dd>
          <dt>Announced</dt><dd>{fmt(rc.announcedAt)}</dd>
          <dt>Checkpoint</dt><dd><span className="tag plain">[{gate.state}]</span> sequence {s.checkpoint?.anchoredSequence ?? "?"} · {s.freshness?.status ?? "freshness unknown"} · verified {fmt(s.freshness?.verifiedAt)}</dd>
        </dl>
      </div>

      <div className="grid g4" style={{ marginBottom: 14 }}>
        <div className="card metric"><span className="eyebrow">Motors investigated</span><b>{rows.length}</b></div>
        <div className="card metric"><span className="eyebrow">Affected</span><b className="bad-t">{allowed ? n("AFFECTED") : W}</b><small>evidence shows the recalled lot installed</small></div>
        <div className="card metric"><span className="eyebrow">Unresolved</span><b className="warn-t">{allowed ? n("UNRESOLVED") : W}</b><small>evidence cannot show it is clear</small></div>
        <div className="card metric"><span className="eyebrow">Excluded with evidence</span><b className="ok-t">{allowed ? n("EXCLUDED_WITH_EVIDENCE") : W}</b><small>evidence shows it is not affected</small></div>
        <div className="card metric"><span className="eyebrow">Recall holds</span><b>{allowed ? holds : W}</b><small>do not ship or release</small></div>
        <div className="card metric"><span className="eyebrow">Release eligible (backend)</span><b>{allowed ? eligible : W}</b><small>evidence-based; not a shipment authorization</small></div>
      </div>

      <div className="split">
        <div className="scroll">
          <table className="t">
            <thead><tr><th>Motor</th><th>Finding</th><th>Action</th><th>Review</th><th>Reasons</th><th>Release eligible</th></tr></thead>
            <tbody>
              {rows.map(({ u, d, elig }) => (
                <tr key={u.unitId} className={`click ${u.unitId === motor ? "sel" : ""}`} onClick={() => setMotor(u.unitId)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") setMotor(u.unitId); }} aria-selected={u.unitId === motor}>
                  <td><b className="mono">{u.unitId}</b></td>
                  {allowed ? <>
                    <td><FindingTag v={d?.evidenceFinding} /></td><td><ActionTag v={d?.operationalAction} /></td>
                    <td>{d?.reviewRequired ? <span className="tag warn">[REVIEW]</span> : <span className="na">none</span>}</td>
                    <td>{(d?.reasonCodes ?? []).map((c) => <div key={c} className="mono">{c}</div>)}</td>
                    <td>{elig === undefined ? NA : elig ? <span className="tag ok">[YES]</span> : <span className="tag plain">[NO]</span>}</td>
                  </> : <td colSpan={5}><span className="tag bad">[WITHHELD · {gate.label}]</span></td>}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">Excluded with evidence means the recorded evidence shows the motor is outside the recall. It is never read as &quot;safe&quot;, and release eligibility is not a shipment authorization.</p>
        </div>
        <aside className="card inspector">{motor && <Reasoning s={s} motor={motor} href={href} />}</aside>
      </div>
      {motor && <ResolutionTrail s={s} motor={motor} setMotor={setMotor} />}
    </div>
  );
}

function Reasoning({ s, motor, href }: { s: Snapshot; motor: string; href: (p: string) => string }) {
  const [tab, setTab] = useState<"decision" | "history" | "events">("decision");
  const { gate } = useData();
  const { res, consistency: decC, reason: decWhy } = useMotorResourceChecked<DecisionsBody>("decisions", gate.decisionsAllowed ? motor : null);
  const lifeC = useMotorResourceChecked<Lifecycle>("lifecycle", motor), life = lifeC.res;
  const provC = useMotorResourceChecked<ProvenanceRow[]>("provenance", motor), prov = provC.res;
  const u = unitOf(s, motor);
  const comps = s.components.filter((c) => c.unitId === motor);
  let body: React.ReactNode;
  if (!gate.decisionsAllowed) body = <div className="banner bad" role="alert" data-testid="decisions-withheld"><div><b>Decision withheld: {gate.label}.</b> {gate.detail} Any decision read earlier for {motor} is withdrawn.</div></div>;
  else if (decC === "MISMATCH") body = <div className="banner bad" role="alert" data-testid="decisions-mismatch"><div><b>Decision withheld for {motor}.</b> The decision read from the backend does not match the verified snapshot ({decWhy}). It is read again when the next verified snapshot arrives.</div></div>;
  else if (!res) body = <p className="na">Reading decisions for {motor} from the backend…</p>;
  else if (!res.ok) body = <div className="banner bad"><div><b>Decisions withheld by the backend</b> <span className="tag bad">[{String(res.status)}{res.state ? ` ${res.state}` : ""}]</span><div>{res.error}. No decision is shown for {motor}.</div></div></div>;
  else {
    const key = Object.keys(res.body).find((k) => k !== "checkpoint" && k !== "eligibility");
    const d = key ? (res.body[key] as DecisionBundle).current : undefined;
    const rows = new Map((prov?.ok ? prov.body : []).map((r) => [r.id, r]));
    body = d ? <>
      <p><FindingTag v={d.evidenceFinding} /> <ActionTag v={d.operationalAction} /> {d.reviewRequired && <span className="tag warn">[REVIEW REQUIRED]</span>}</p>
      <p className="note">{FINDING_TEXT[d.evidenceFinding ?? ""]?.explain ?? "No explanation available."} {ACTION_TEXT[d.operationalAction ?? ""]?.explain}</p>
      <dl className="kv"><dt>Release eligible</dt><dd>{res.body.eligibility?.currentReleaseEligible === undefined ? NA : String(res.body.eligibility.currentReleaseEligible)} <span className="na">(backend, valid only while anchored current)</span></dd></dl>
      <h3 style={{ marginTop: 12 }}>Why (reason codes)</h3>
      <ul className="evlist">{(d.reasonCodes ?? []).map((c) => <li key={c}><b className="mono">{c}</b><div>{explain(REASONS, c)}</div></li>)}</ul>
      {(d.flags?.length ?? 0) > 0 && <><h3>Flags</h3><ul className="evlist">{d.flags!.map((f) => <li key={f}><b className="mono">{f}</b><div>{explain(FLAGS, f)}</div></li>)}</ul></>}
      <h3 style={{ marginTop: 12 }}>Slot verdicts</h3>
      <ul className="evlist">{Object.entries(d.slotVerdicts ?? {}).map(([slot, v]) => <li key={slot}><b>Slot {slot}</b> <FindingTag v={v.finding} /><div className="mono">{(v.reasons ?? []).join(", ")}</div></li>)}</ul>
      <h3 style={{ marginTop: 12 }}>Evidence events ({d.evidenceEventIds?.length ?? 0})</h3>
      <ul className="evlist">{(d.evidenceEventIds ?? []).map((id) => { const r = rows.get(id); return <li key={id}><code>{id}</code>{r && <div className="na">seq {r.seq} · {r.source} · capture hash <code>{r.hash.slice(0, 14)}…</code></div>}</li>; })}</ul>
      <details><summary>Decision record</summary><dl className="kv"><dt>Decision id</dt><dd className="mono">{val(d.decisionId)}</dd><dt>Version</dt><dd>{val(d.version)}</dd><dt>Policy</dt><dd className="mono">{val(d.policyId)}</dd><dt>Engine</dt><dd className="mono">{val(d.engineVersion)} / {val(d.semanticsProfile)}</dd><dt>Integrity issues</dt><dd>{d.integrityIssues?.length ?? 0}</dd><dt>History entries</dt><dd>{key ? ((res.body[key] as DecisionBundle).history?.length ?? 0) : 0}</dd></dl></details>
    </> : <p>No decision recorded for {motor}.</p>;
  }
  return (
    <div className="rs">
      <div className="eyebrow">Decision reasoning</div>
      <h2>{motor}</h2>
      <div className="tabs" role="tablist" aria-label="Decision views">
        <button role="tab" aria-selected={tab === "decision"} onClick={() => setTab("decision")}>Decision</button>
        <button role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>Decision history</button>
        <button role="tab" aria-selected={tab === "events"} onClick={() => setTab("events")}>Event log</button>
      </div>
      <div className="rs-body" data-testid="reasoning-body">
      {tab === "events" ? <EventLog s={s} motor={motor} cited={gate.decisionsAllowed && res?.ok ? citedIds(res.body) : null} />
        : tab === "decision" || !gate.decisionsAllowed ? body : <History s={s} res={res} />}
      <h3 style={{ marginTop: 12 }}>Installed positions (records)</h3>
      <ul className="evlist">{comps.map((c) => <li key={c.componentId}><b>{c.slot}</b> · lot {c.lot ?? "?"} · {c.serial ?? "no serial"}<div className="na">{c.removedAt ? `removed ${fmt(c.removedAt)}` : "installed"} · claimed by {c.claimedBy ?? "unknown"} · lot registry {c.registry?.status ?? "status not recorded"}</div></li>)}</ul>
      <ResourceNote c={lifeC} what="The lifecycle history" seq={s.checkpoint?.anchoredSequence} />
      <details><summary>Lifecycle ({life?.ok ? life.body.eventCount ?? life.body.chronology.length : "…"} events)</summary>
        {life?.ok ? <ul className="evlist">{life.body.chronology.map((e) => <li key={e.eventId}><b className="mono">{humanize(e.eventType)}</b> <span className="na">{fmt(e.occurredAt)}</span><div>{e.summary}</div></li>)}</ul> : <p className="na">{life ? "Lifecycle unavailable." : "Reading…"}</p>}
      </details>
      <p><Link className="btn" href={href("/dashboard/genealogy")}>Open genealogy</Link> <Link className="btn ghost" href={href("/dashboard/passport")}>Passport</Link></p>
      <p className="note">Shipment: {u?.shipment ? `${u.shipment.shipmentId} (a record claim, not a release authorization)` : "none recorded"}.</p>
      </div>
    </div>
  );
}

const changeNote = (prev: DecisionCurrent | undefined, d: DecisionCurrent): string => {
  if (!prev) return "First decision recorded after the recall announcement.";
  const bits: string[] = [];
  if (prev.evidenceFinding !== d.evidenceFinding) bits.push(`Finding changed from ${FINDING_TEXT[prev.evidenceFinding ?? ""]?.label ?? prev.evidenceFinding} to ${FINDING_TEXT[d.evidenceFinding ?? ""]?.label ?? d.evidenceFinding}`);
  if (prev.operationalAction !== d.operationalAction) bits.push("operational action changed");
  const added = (d.reasonCodes ?? []).filter((c) => !(prev.reasonCodes ?? []).includes(c));
  if (added.length) bits.push(`new reasons: ${added.map(humanize).join(", ")}`);
  return bits.length ? `${bits.join("; ")}.` : "Outcome unchanged but reasons or evidence differ.";
};

const citedIds = (b: DecisionsBody): Set<string> | null => { const key = Object.keys(b).find((k) => k !== "checkpoint" && k !== "eligibility"); const d = key ? (b[key] as DecisionBundle).current : undefined; return d ? new Set(d.evidenceEventIds ?? []) : null; };

/** Recorded events for the motor. The events are informational claims and stay visible; the "Cited" column is decision context and is shown only while the gate allows decisions. */
function EventLog({ s, motor, cited }: { s: Snapshot; motor: string; cited: Set<string> | null }) {
  const u = unitOf(s, motor);
  const events = u?.events ?? [];
  const [open, setOpen] = useState<string | null>(null);
  const sel = events.find((e) => e.eventId === open);
  return (
    <div data-testid="event-log">
      <p className="note"><span className="tag info">[INFORMATIONAL]</span> Event facts are recorded claims. {cited ? "The Cited column marks events the current decision relies on." : "The Cited column is withheld because no current decision is shown."}</p>
      {(u?.captureSessions?.length ?? 0) > 0 && <><h3>Capture sessions</h3><ul className="evlist">{u!.captureSessions!.map((c, i) => <li key={i}><b className="mono">{c.sourceId}</b> <span className="na">{fmt(c.from)} to {fmt(c.to)}</span></li>)}</ul></>}
      {events.length === 0 ? <p className="na">No events are recorded for {motor} in this snapshot.</p> : (
        <div className="scroll"><table className="t"><thead><tr><th>Event</th><th>Type</th><th>Occurred</th><th>Recorded</th>{cited && <th>Cited</th>}<th>Detail</th></tr></thead>
          <tbody>{events.map((e) => <tr key={e.eventId}><td className="mono" style={{ wordBreak: "break-all" }}>{e.eventId}</td><td className="mono">{humanize(e.eventType)}</td><td>{fmt(e.occurredAt)}</td><td>{fmt(e.recordedAt)}</td>{cited && <td>{cited.has(e.eventId) ? <span className="tag ok">cited</span> : <span className="na">no</span>}</td>}<td><button type="button" className="linkbtn" onClick={() => setOpen(open === e.eventId ? null : e.eventId)} aria-expanded={open === e.eventId}>Inspect event provenance</button></td></tr>)}</tbody></table></div>
      )}
      {sel && <pre className="mono" data-testid="event-provenance" style={{ overflow: "auto", maxHeight: 280 }}>{JSON.stringify(sel, null, 2)}</pre>}
    </div>
  );
}

/** Only versions the backend returned are shown. Nothing is reconstructed from the current decision. */
function History({ s, res }: { s: Snapshot; res: ReturnType<typeof useMotorResource<DecisionsBody>> }) {
  if (!res) return <p className="na">Reading decision history from the backend…</p>;
  if (!res.ok) return <div className="banner bad"><div><b>Decision history withheld by the backend</b> <span className="tag bad">[{String(res.status)}{res.state ? ` ${res.state}` : ""}]</span><div>{res.error}. The backend only returns decisions while the checkpoint is anchored current. No history is reconstructed here.</div></div></div>;
  const key = Object.keys(res.body).find((k) => k !== "checkpoint" && k !== "eligibility");
  const hist = ((key ? (res.body[key] as DecisionBundle).history : undefined) ?? []) as DecisionCurrent[];
  if (hist.length === 0) return <p className="banner bad" role="alert">The backend returned no decision history for this motor. Nothing is shown rather than inventing a timeline.</p>;
  const events = (motor: string | undefined) => s.units.find((u) => u.unitId === motor)?.events ?? [];
  const cp = res.body.checkpoint;
  return (
    <div>
      <p className="note">Publication versions record material outcome, reasoning, evidence or obligation changes. Earlier versions are kept, never overwritten. {hist.length} version{hist.length === 1 ? "" : "s"} returned by the backend. Checkpoint at read time: <span className="tag plain">[{cp?.state ?? "unknown"}]</span> sequence {cp?.anchoredSequence ?? "?"}.</p>
      <ol className="evlist" style={{ listStyle: "none", padding: 0 }}>
        {hist.map((d, i) => {
          const latest = i === hist.length - 1;
          const trig = d.triggerEventId ? events((d as { motorSerial?: string }).motorSerial).find((e) => e.eventId === d.triggerEventId) : undefined;
          const wm = d.watermark ? Object.entries(d.watermark).reduce((a, [, n]) => a + n, 0) : null;
          return (
            <li key={d.decisionId} data-testid="history-version">
              <b>Version {d.version ?? i + 1}</b> <span className={`tag ${latest ? "ok" : "plain"}`}>{latest ? "Latest recorded" : `Superseded by v${hist[i + 1].version ?? i + 2}`}</span>
              <div><FindingTag v={d.evidenceFinding} /> <ActionTag v={d.operationalAction} /> {d.reviewRequired && <span className="tag warn">[REVIEW]</span>}</div>
              <div>{changeNote(hist[i - 1], d)}</div>
              <dl className="kv" style={{ marginTop: 4 }}>
                <dt>Decision id</dt><dd className="mono">{d.decisionId}</dd>
                <dt>Triggered by</dt><dd>{d.triggerEventId ? <><code>{d.triggerEventId}</code>{trig ? <div className="na">{humanize(trig.eventType)} · occurred {fmt(trig.occurredAt)} · recorded {fmt(trig.recordedAt)}</div> : <div className="na">event not in this snapshot</div>}</> : <>recall announcement state <span className="na">(announced {fmt(s.recall.announcedAt)})</span></>}</dd>
                <dt>Supersedes</dt><dd>{d.supersedesDecisionId ? <code>{d.supersedesDecisionId}</code> : "none (first version)"}</dd>
                <dt>Reasons</dt><dd>{(d.reasonCodes ?? []).map((c) => <div key={c}><b className="mono">{c}</b><div className="na">{explain(REASONS, c)}</div></div>)}</dd>
                <dt>Evidence cited</dt><dd>{d.evidenceEventIds?.length ?? 0} records{wm !== null ? ` · ledger watermark covered ${wm} records at this version` : ""}</dd>
              </dl>
              {d.notificationObligation?.required && <p className="note"><b>Notification obligation.</b> This decision withdraws the earlier release-eligible decision <code>{d.notificationObligation.appliesIfDecisionCommunicated}</code>. If it was communicated to anyone, they must be told it no longer stands. Reason: {humanize(d.notificationObligation.reason ?? "")}. Whether it was communicated is not recorded: {d.notificationObligation.communicated == null ? "unknown" : String(d.notificationObligation.communicated)}.</p>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
