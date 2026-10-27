"use client";

// Evidence and Timeline tabs of the original passport, over the ORIGINAL passport projection (src/orig/passport/projection.ts).
import { Fragment, useState } from "react";
import { humanize } from "@/orig/domain/glossary";
import type { EvidenceItem, Passport } from "@/orig/passport/projection";
import { when } from "./claims";

export function EvidenceTab({ passport, evidenceId, select }: { passport: Passport; evidenceId: string | null; select: (id: string | null) => void }) {
  const items = Object.values(passport.evidence);
  const selected: EvidenceItem | undefined = evidenceId ? passport.evidence[evidenceId] : undefined;
  return (
    <div className="split" data-testid="passport-evidence">
      <nav aria-label="Recorded events" className="card">
        <h2>Recorded events</h2>
        <ol className="evlist" style={{ listStyle: "none", padding: 0 }}>
          {items.map((e) => (
            <li key={e.eventId}><button type="button" className="linkbtn" aria-current={selected?.eventId === e.eventId ? "true" : undefined} style={selected?.eventId === e.eventId ? { fontWeight: 700 } : undefined} onClick={() => select(e.eventId)}>{e.label}</button>
              <div className="na">{e.sourceRoleLabel} · <code>{e.eventId}</code></div></li>
          ))}
        </ol>
      </nav>
      <section className="card inspector" aria-live="polite" aria-label="Selected evidence">
        {evidenceId && !selected && <p className="warn-t" role="alert">No event <code>{evidenceId}</code> is recorded for this motor.</p>}
        {!selected && !evidenceId && <p className="na">Select an event.</p>}
        {selected && (
          <div data-testid="evidence-detail">
            <h2>{selected.label}</h2>
            <dl className="kv">
              <dt>Event ID</dt><dd><code style={{ overflowWrap: "anywhere" }}>{selected.eventId}</code></dd>
              <dt>Source claim</dt><dd>{selected.sourceRoleLabel} (<code>{selected.sourceId}</code>, sequence {selected.sourceSeq})</dd>
              <dt>Occurred (as claimed)</dt><dd>{when(selected.occurredAt)}</dd>
              <dt>Recorded by source</dt><dd>{when(selected.recordedAt)}</dd>
              <dt>Repository record time</dt><dd>{selected.repositoryRecordTime ? when(selected.repositoryRecordTime) : "Not recorded"}</dd>
              <dt>Received by this ledger</dt><dd>{selected.localReceivedAt ? when(selected.localReceivedAt) : "Not recorded"}</dd>
              <dt>Clock</dt><dd>{humanize(selected.timeSource)} <span className="tag warn">[NOT A TRUSTED TIME SOURCE]</span></dd>
              <dt>Capture SHA-256</dt><dd>{selected.captureSha256 ? <code style={{ overflowWrap: "anywhere" }}>{selected.captureSha256}</code> : "Not recorded"}</dd>
              <dt>Event chain hash</dt><dd>{selected.eventChainHash ? <code style={{ overflowWrap: "anywhere" }}>{selected.eventChainHash}</code> : "Not recorded"}</dd>
              {selected.supersedesEventId && <><dt>Corrects event</dt><dd><button type="button" className="linkbtn" onClick={() => select(selected.supersedesEventId)}><code>{selected.supersedesEventId}</code></button></dd></>}
            </dl>
            {selected.facts.length > 0 && <><h3>Recorded facts</h3><dl className="kv">{selected.facts.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl></>}
            <p className="note"><b>What the hashes show.</b> They show the stored capture and its position in this ledger&apos;s chain have not changed since they were recorded. They do <b>not</b> show who issued the record, that the source identity is genuine, that the clock was right, or that the physical bearing is what the record says. This synthetic data is not independently authenticated.</p>
          </div>
        )}
      </section>
    </div>
  );
}

const CATEGORIES = ["All", "Material", "Assembly", "Rework", "Shipment", "Observation", "Inspection", "Work order"] as const;

export function TimelineTab({ passport, select }: { passport: Passport; select: (id: string) => void }) {
  const [cat, setCat] = useState<(typeof CATEGORIES)[number]>("All");
  const shown = passport.timeline.filter((t) => cat === "All" || t.category === cat);
  const gaps = passport.notes.filter((n) => n.kind === "GAP");
  return (
    <div data-testid="passport-timeline">
      <p className="lede">Events in recorded order. Times come from a simulated clock and are claims, not measurements.</p>
      <div role="group" aria-label="Filter timeline" style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {CATEGORIES.map((c) => <button key={c} type="button" className={cat === c ? "btn" : "btn ghost"} aria-pressed={cat === c} onClick={() => setCat(c)}>{c}</button>)}
      </div>
      {gaps.length > 0 && <div className="banner bad" role="note">{gaps.map((g) => <p key={g.id}><b>{g.title}.</b> {g.detail}</p>)}</div>}
      {shown.length === 0 ? <p className="na">No events in this category.</p> : (
        <ol className="evlist" style={{ listStyle: "none", padding: 0 }}>
          {shown.map((t) => (
            <li key={t.eventId}><b>{t.title}</b> <span className="tag plain">{t.category}</span>
              <div className="na">{when(t.at)}</div><div>{t.detail}</div>
              <button type="button" className="linkbtn" onClick={() => select(t.eventId)}>View evidence</button></li>
          ))}
        </ol>
      )}
      <h3>Notes on what is not recorded or not verified</h3>
      <ul className="evlist">{passport.notes.map((n) => <li key={n.id}><span className="tag plain">{n.kind === "NOT_RECORDED" ? "Not recorded" : n.kind === "UNVERIFIED" ? "Unverified" : "Capture gap"}</span> <b>{n.title}</b><div className="na">{n.detail}</div></li>)}</ul>
    </div>
  );
}
