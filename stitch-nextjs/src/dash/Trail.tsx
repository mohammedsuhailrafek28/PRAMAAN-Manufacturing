"use client";

// Resolution Trail: what was flagged, what corrective action is recorded, what confirmation exists, how the decision changed and what still holds.
// Reads the existing snapshot, /decisions and legacy comparison. It computes no decision, records nothing and has no resolve control.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useData, useMotorResourceChecked } from "./data";
import { REASONS, explain, humanize } from "./glossary";
import { assuranceOf, confirmationEvents, correctiveEvents, describe, kindOf, pairOf, type Kind } from "./trailModel";
import type { Checkpoint, DecisionBundle, DecisionCurrent, LedgerEvent, Snapshot } from "./types";
import { ActionTag, FindingTag, fmt, unitOf } from "./ui";

type Body = Record<string, DecisionBundle | Checkpoint | { currentReleaseEligible?: boolean } | undefined>;
const GLYPH: Record<Kind, string> = { WO: "WO", REM: "REM", INS: "INS", MAT: "MAT", MFG: "MFG", OBS: "OBS", QC: "QC" };

function EventRow({ e, motor, mark }: { e: LedgerEvent; motor: string; mark?: string }) {
  const router = useRouter();
  const a = assuranceOf(e), pl = (e.payload ?? {}) as Record<string, unknown>;
  const open = `/dashboard/passport?motor=${motor}&tab=evidence&evidence=${encodeURIComponent(e.eventId)}`;
  return (
    <li className="te" data-testid="trail-event" data-type={e.eventType}>
      <span className="tk" title={e.eventType}>{GLYPH[kindOf(e)]}</span>
      <div className="tb">
        <div><b>{describe(e)}</b> {mark && <span className="tag plain">{mark}</span>}</div>
        <div className="mono dim">{fmt(e.occurredAt)} · {e.actorId ?? "actor not recorded"} <span className="dim">(claimed)</span></div>
        <details>
          <summary>Source evidence</summary>
          <dl className="kv">
            <dt>Event</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{e.eventId}</dd>
            <dt>Source</dt><dd className="mono">{e.sourceId} #{e.sourceSeq}</dd>
            <dt>Clock</dt><dd className="mono">{e.timeSource ?? "not recorded"} <span className="tag warn">NOT A TRUSTED TIME SOURCE</span></dd>
            <dt>Recorded by source</dt><dd>{fmt(e.recordedAt)}</dd>
            <dt>Repository record</dt><dd>{fmt(e.repository?.recordTime)}</dd>
            <dt>Received by ledger</dt><dd>{fmt(e.repository?.localReceivedAt)}</dd>
            {e.evidenceRefs && e.evidenceRefs.length > 0 && <><dt>Evidence refs</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{e.evidenceRefs.join(", ")}</dd></>}
            {e.repository?.eventChainHash && <><dt>Chain hash</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{e.repository.eventChainHash}</dd></>}
            {Object.entries(pl).filter(([, v]) => typeof v !== "object" && v !== null).slice(0, 8).map(([k, v]) => <div key={k} style={{ display: "contents" }}><dt>{humanize(k)}</dt><dd className="mono">{String(v)}</dd></div>)}
            {(kindOf(e) === "OBS" || kindOf(e) === "QC") && <><dt>Assurance</dt><dd>{a.label}</dd></>}
          </dl>
          <button type="button" className="linkbtn" onClick={() => router.push(open)}>Open in passport evidence</button>
        </details>
      </div>
    </li>
  );
}

const Step = ({ n, title, state, children }: { n: string; title: string; state: "rec" | "none" | "withheld"; children: React.ReactNode }) => (
  <li className={`ts ${state}`} data-testid={`trail-step-${n}`}>
    <span className="tn" aria-hidden />
    <div className="th"><span className="mono dim">{n}</span> <b>{title}</b></div>
    <div className="tc">{children}</div>
  </li>
);

function Version({ d, label, muted }: { d?: DecisionCurrent; label: string; muted?: boolean }) {
  if (!d) return <div className={`cmpbox ${muted ? "mut" : ""}`}><div className="mono dim">{label}</div><div className="dim">No earlier version recorded</div></div>;
  return (
    <div className={`cmpbox ${muted ? "mut" : ""}`} data-testid={muted ? "trail-prev" : "trail-cur"}>
      <div className="mono dim">{label} · v{d.version ?? "?"}</div>
      <div style={{ margin: "4px 0" }}><FindingTag v={d.evidenceFinding} /> <ActionTag v={d.operationalAction} /></div>
      <div className="mono" style={{ fontSize: 11 }}>{(d.reasonCodes ?? []).join(" · ") || "no reason codes"}</div>
    </div>
  );
}

export default function ResolutionTrail({ s, motor, setMotor }: { s: Snapshot; motor: string; setMotor: (m: string) => void }) {
  const { gate, mode } = useData();
  const router = useRouter();
  const allowed = gate.decisionsAllowed;
  const { res, consistency, reason } = useMotorResourceChecked<Body>("decisions", allowed ? motor : null);
  const mismatch = allowed && consistency === "MISMATCH";
  const u = unitOf(s, motor);
  const events = u?.events ?? [];
  const byId = new Map(events.map((e) => [e.eventId, e]));
  const corrective = correctiveEvents(events), confirm = confirmationEvents(events);
  const [all, setAll] = useState(false);

  let bundle: DecisionBundle | undefined;
  if (res?.ok) { const k = Object.keys(res.body).find((x) => x !== "checkpoint" && x !== "eligibility"); bundle = k ? (res.body[k] as DecisionBundle) : undefined; }
  const pair = pairOf(bundle?.current, (bundle?.history ?? []) as DecisionCurrent[]);
  const first = pair.versions[0], cur = pair.cur;
  const legacy = allowed ? s.comparison?.find((c) => c.unitId === motor)?.legacy : undefined;
  const trigger = cur?.triggerEventId ? byId.get(cur.triggerEventId) : undefined;
  const held = cur?.operationalAction === "RECALL_HOLD";
  const W = (why: string) => <div className="hatch" data-testid="trail-withheld">Withheld · {why}</div>;
  const decisionPending = allowed && !res && !mismatch;
  const decisionFailed = allowed && (mismatch || (res && !res.ok));

  return (
    <section id="resolution-trail" className="trail" aria-label={`Resolution trail for ${motor}`} data-testid="resolution-trail">
      <header className="trail-h">
        <h2>Resolution trail</h2>
        <span className="tag info">RECORDED CLAIMS</span>
        {!allowed && <span className="tag warn" data-testid="trail-notcurrent">NOT CURRENT</span>}
        <div className="chips" role="group" aria-label="Select motor" style={{ margin: 0, marginLeft: "auto" }}>
          {s.units.map((x) => <button key={x.unitId} type="button" className="chipbtn" aria-pressed={x.unitId === motor} onClick={() => setMotor(x.unitId)}>{x.unitId}</button>)}
        </div>
      </header>

      {mismatch && <div className="trail-note" role="status" data-testid="trail-mismatch"><b>Decision history withheld.</b> It does not match the verified snapshot ({reason}). It is read again when the next verified snapshot arrives.</div>}
      {allowed && cur && corrective.length > 0 && held && (
        <div className="trail-note" data-testid="trail-holdnote"><b>Corrective action recorded · hold not lifted.</b> A recorded replacement or closed work order is not a resolution.</div>
      )}

      <ol className="tl">
        <Step n="01" title="Defect flagged" state={allowed && first ? "rec" : allowed ? "none" : "withheld"}>
          <div className="mono dim">Recall {s.recall.recallId} announced {fmt(s.recall.announcedAt)} · lot {(s.recall.affectedLots ?? []).join(", ")} · slot {(s.recall.affectedSlots ?? []).join(", ")}</div>
          {!allowed ? W(gate.label) : decisionPending ? <div className="skel" style={{ height: 40 }} /> : decisionFailed ? <div className="warn-t">Decisions unavailable from the backend.</div> : first ? (
            <div style={{ marginTop: 6 }}><span className="mono dim">First recorded decision · v{first.version ?? "?"}</span><div><FindingTag v={first.evidenceFinding} /> <ActionTag v={first.operationalAction} /> <span className="mono" style={{ fontSize: 11 }}>{(first.reasonCodes ?? []).join(" · ")}</span></div></div>
          ) : <div className="na">No decision recorded.</div>}
        </Step>

        <Step n="02" title="Corrective action recorded" state={corrective.length ? "rec" : "none"}>
          {corrective.length === 0 ? <div className="na" data-testid="trail-no-corrective">No corrective action recorded for {motor}.</div> : (
            <ol className="evs">{corrective.map((e) => <EventRow key={e.eventId} e={e} motor={motor} mark={e.eventType === "WORK_ORDER_CLOSED" ? "closure ≠ resolution" : undefined} />)}</ol>
          )}
        </Step>

        <Step n="03" title="Evidence confirmation" state={confirm.length ? "rec" : "none"}>
          <div className="statusline" data-testid="trail-confirmation"><span className="tag bad">NO INDEPENDENT CONFIRMATION RECORDED</span> {confirm.length > 0 && <span className="dim">Records below are claims.</span>}</div>
          {confirm.length === 0 ? <div className="na">No inspection or verification record.</div> : <ol className="evs">{confirm.map((e) => <EventRow key={e.eventId} e={e} motor={motor} mark={assuranceOf(e).label.split(".")[0]} />)}</ol>}
        </Step>

        <Step n="04" title="Decision reevaluated" state={allowed ? (pair.prev ? "rec" : "none") : "withheld"}>
          {!allowed ? W(gate.label) : decisionPending ? <div className="skel" style={{ height: 60 }} /> : decisionFailed ? <div className="warn-t">Decision history unavailable.</div> : !cur ? <div className="na">No decision recorded.</div> : (
            <>
              <div className="cmp">
                <Version d={pair.prev} label="Previous" muted />
                <span className="arrow" aria-hidden>→</span>
                <Version d={cur} label="Current" />
              </div>
              <div className="mono dim" style={{ marginTop: 6 }} data-testid="trail-trigger">
                {pair.prev ? (trigger ? <>Triggered by <button type="button" className="linkbtn" onClick={() => router.push(`/dashboard/passport?motor=${motor}&tab=evidence&evidence=${encodeURIComponent(trigger.eventId)}`)}>{describe(trigger)}</button> ({fmt(trigger.occurredAt)}, claimed)</> : cur.triggerEventId ? <>Trigger event <code>{cur.triggerEventId}</code> is not in this motor&apos;s events.</> : "No trigger event recorded.") : "Single version; no reevaluation recorded."}
              </div>
              {legacy && <div className="mono dim" style={{ marginTop: 4 }} data-testid="trail-legacy">Earlier engine profile (comparison only, not a decision): {humanize(legacy.evidenceFinding ?? "")}.</div>}
              {pair.versions.length > 2 && <button type="button" className="linkbtn" onClick={() => setAll(!all)}>{all ? "Hide" : "All"} {pair.versions.length} versions</button>}
              {all && <ul className="evlist">{pair.versions.map((v) => <li key={v.decisionId}>v{v.version} · {humanize(v.evidenceFinding ?? "")} / {humanize(v.operationalAction ?? "")} · <span className="mono">{(v.reasonCodes ?? []).join(", ")}</span></li>)}</ul>}
            </>
          )}
        </Step>

        <Step n="05" title="Current outcome" state={allowed ? "rec" : "withheld"}>
          {!allowed ? W(gate.label) : decisionPending ? <div className="skel" style={{ height: 60 }} /> : decisionFailed || !cur ? <div className="warn-t">No current decision to show.</div> : (
            <div data-testid="trail-outcome">
              <div><FindingTag v={cur.evidenceFinding} /> <ActionTag v={cur.operationalAction} /> {cur.reviewRequired && <span className="tag warn">REVIEW REQUIRED</span>}</div>
              {held && <div style={{ marginTop: 6 }}><b>Why the hold remains</b><ul className="evlist">{(cur.reasonCodes ?? []).map((c) => <li key={c}><span className="mono">{c}</span> <span className="dim">{explain(REASONS, c)}</span></li>)}</ul></div>}
              {!held && <div className="note">An engine outcome, not a shipment authorization.</div>}
              {cur.notificationObligation?.required && <div className="mono dim" style={{ marginTop: 4 }}>Notification obligation: {cur.notificationObligation.deliveryStatus ?? "status not recorded"}</div>}
              <div style={{ marginTop: 6 }}><Link className="linkbtn" href={`/dashboard/evidence`}>Open evidence tasks</Link></div>
            </div>
          )}
        </Step>
      </ol>
      <div className="mono dim" style={{ marginTop: 8, fontSize: 11 }} data-testid="trail-prov">Times and actors are source claims, not verified · snapshot seq {s.freshness?.sequence ?? "?"} · {mode === "current" ? "checkpoint current" : "not current"}</div>
    </section>
  );
}
