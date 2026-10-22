import { Fragment, useMemo, useState } from "react";
import { fmtTime } from "../domain/derive";
import { FINDING_TEXT, NO_DESCRIPTION, REASONS, humanize } from "../domain/glossary";
import type { ComponentClaim, EvidenceItem, Passport, PassportNote, RecallContext, SlotPassport, TimelineEntry } from "./projection";
import { qrMatrix, qrSvgPath } from "./qr";
import { PASSPORT_TABS, tabHref, type PassportTab } from "./route";

export interface PassportBanner {
  kind: "unverified" | "stale";
  text: string;
}

const NOTE_LABEL: Record<PassportNote["kind"], string> = { NOT_RECORDED: "Not recorded", UNVERIFIED: "Unverified", GAP: "Capture gap" };

function SyntheticTag() {
  return <span className="tag synthetic">Synthetic demonstration data</span>;
}

function ClaimChip({ status }: { status: ComponentClaim["status"] }) {
  const text = status === "CURRENT" ? "Currently recorded claim" : status === "REMOVED" ? "Removed (historical)" : "Corrected (historical)";
  return <span className={`tag pp-status pp-${status.toLowerCase()}`}>{text}</span>;
}

function ClaimCard({ unitId, claim, evidence }: { unitId: string; claim: ComponentClaim; evidence: Passport["evidence"] }) {
  const first = claim.evidence[0]?.eventId;
  return (
    <article className={`pp-claim pp-claim-${claim.status.toLowerCase()}`} aria-label={`${claim.slot} bearing, ${claim.status.toLowerCase()}`}>
      <header>
        <h4>{claim.part ?? "Bearing"} · lot <code>{claim.lot ?? "not recorded"}</code></h4>
        <ClaimChip status={claim.status} />
      </header>
      <dl className="pp-facts">
        <dt>Serial</dt><dd>{claim.serial ? <code>{claim.serial}</code> : `Not recorded (${claim.identityGranularity === "LOT" ? "lot-level identity" : "no serial"})`}</dd>
        <dt>Installed (as recorded)</dt><dd>{fmtTime(claim.installedAt)}</dd>
        {claim.removedAt && <><dt>Removed (as recorded)</dt><dd>{fmtTime(claim.removedAt)}</dd></>}
        <dt>Raw-material lot</dt><dd>{claim.rawMaterialLot ? <code>{claim.rawMaterialLot}</code> : "Not recorded"}</dd>
        <dt>Supplier</dt><dd>{claim.supplierClaim ? <>{claim.supplierClaim} <span className="tag">Unverified claim</span></> : "Not recorded"}</dd>
      </dl>
      {claim.replacedByClaimId && <p className="muted">Replaced by a later installation in this slot.</p>}
      {claim.replacesClaimId && <p className="muted">Installed in place of an earlier bearing in this slot.</p>}
      <ul className="plain pp-links" aria-label="Evidence for this claim">
        {claim.evidence.map((l) => (
          <li key={l.relation + l.eventId}><a href={tabHref(unitId, "evidence", l.eventId)}>{l.relation}</a> <span className="muted">{evidence[l.eventId]?.sourceRoleLabel}</span></li>
        ))}
      </ul>
      {first && <p><a className="pp-button" href={tabHref(unitId, "evidence", first)}>View evidence for this claim</a></p>}
    </article>
  );
}

function SlotSection({ unitId, slot, evidence }: { unitId: string; slot: SlotPassport; evidence: Passport["evidence"] }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="pp-slot" aria-labelledby={`slot-${slot.slot}`}>
      <h3 id={`slot-${slot.slot}`}>{slot.slot === "DE" ? "Drive end (DE)" : slot.slot === "NDE" ? "Non-drive end (NDE)" : slot.slot} bearing</h3>
      {slot.current ? <ClaimCard unitId={unitId} claim={slot.current} evidence={evidence} /> : <p className="warn" role="note">No currently recorded bearing claim for this slot.</p>}
      {slot.history.length > 0 && (
        <div>
          <button type="button" className="pp-button" aria-expanded={open} aria-controls={`hist-${slot.slot}`} onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"} replacement history ({slot.history.length})
          </button>
          <div id={`hist-${slot.slot}`} hidden={!open}>
            {slot.history.map((c) => <ClaimCard key={c.claimId} unitId={unitId} claim={c} evidence={evidence} />)}
          </div>
        </div>
      )}
    </section>
  );
}

function Notes({ notes }: { notes: PassportNote[] }) {
  return (
    <ul className="plain pp-notes">
      {notes.map((n) => (
        <li key={n.id} className={`pp-note pp-note-${n.kind.toLowerCase()}`}>
          <span className="tag">{NOTE_LABEL[n.kind]}</span> <b>{n.title}</b>
          <div className="muted">{n.detail}</div>
        </li>
      ))}
    </ul>
  );
}

export function RecallPanel({ recall, unitId }: { recall: RecallContext; unitId: string }) {
  if (recall.state === "UNAVAILABLE") {
    return (
      <div className="callout callout-warn" role="status" data-testid="recall-unavailable">
        <h3>Current recall status unavailable</h3>
        <p>{recall.reason}</p>
        <p>No recall decision is shown here because it could not be verified as current. Earlier decisions elsewhere in the investigation console are historical evidence, not current clearance.</p>
      </div>
    );
  }
  if (recall.state === "NO_RECALL") {
    return <div className="callout" data-testid="recall-none"><h3>No recall announced</h3><p>No recall policy exists in the verified ledger, so there is no recall finding for this motor.</p></div>;
  }
  const held = recall.action === "RECALL_HOLD";
  return (
    <div className={`callout ${held ? "callout-warn" : ""}`} data-testid="recall-current">
      <h3>{held ? "Held under the recall policy" : "No recall hold recorded under this policy"}</h3>
      <p><b>{FINDING_TEXT[recall.finding]?.label ?? humanize(recall.finding)}.</b> {FINDING_TEXT[recall.finding]?.explain}</p>
      {!held && <p>This is a statement about recall evidence only. It is not shipment authorization, a quality release or a certificate.</p>}
      {recall.reviewRequired && <p><b>Review is required.</b> A person must look at this motor.</p>}
      {recall.precautionaryHold && <p><b>Precautionary hold.</b> Held because an earlier exclusion no longer stands.</p>}
      {recall.notificationPending && <p><b>A notification obligation is pending.</b> This application does not send notifications.</p>}
      {recall.reasonCodes.length > 0 && (
        <ul>{recall.reasonCodes.map((c) => <li key={c}><b>{humanize(c)}</b>: {REASONS[c] ?? NO_DESCRIPTION}</li>)}</ul>
      )}
      <p className="muted">Decision <code>{recall.decisionId}</code>{recall.version !== null ? ` (version ${recall.version})` : ""}, policy {recall.policyId}. Computed by the recall engine and copied here unchanged.</p>
      <p><a href={`./index.html#/unit/${encodeURIComponent(unitId)}/decision`}>Open the full recall explanation</a></p>
    </div>
  );
}

function EvidenceView({ passport, evidenceId }: { passport: Passport; evidenceId: string | null }) {
  const items = Object.values(passport.evidence);
  const selected: EvidenceItem | undefined = evidenceId ? passport.evidence[evidenceId] : undefined;
  return (
    <div className="pp-evidence">
      <nav aria-label="Recorded events" className="pp-evidence-list">
        <h3>Recorded events</h3>
        <ol className="plain">
          {items.map((e) => (
            <li key={e.eventId}>
              <a href={tabHref(passport.unitId, "evidence", e.eventId)} aria-current={selected?.eventId === e.eventId ? "true" : undefined}>{e.label}</a>
              <div className="muted">{e.sourceRoleLabel} · <code>{e.eventId}</code></div>
            </li>
          ))}
        </ol>
      </nav>
      <section className="pp-evidence-detail" aria-live="polite" aria-label="Selected evidence">
        {evidenceId && !selected && <p className="warn" role="alert">No event <code>{evidenceId}</code> is recorded for this motor.</p>}
        {!selected && !evidenceId && <p className="muted">Select an event, or use “View evidence” on a component claim.</p>}
        {selected && <EvidenceDetail e={selected} unitId={passport.unitId} />}
      </section>
    </div>
  );
}

function EvidenceDetail({ e, unitId }: { e: EvidenceItem; unitId: string }) {
  return (
    <div data-testid="evidence-detail">
      <h3>{e.label}</h3>
      <dl className="pp-facts">
        <dt>Event ID</dt><dd><code>{e.eventId}</code></dd>
        <dt>Source claim</dt><dd>{e.sourceRoleLabel} (<code>{e.sourceId}</code>, sequence {e.sourceSeq})</dd>
        <dt>Occurred (as claimed)</dt><dd>{fmtTime(e.occurredAt)}</dd>
        <dt>Recorded by source</dt><dd>{fmtTime(e.recordedAt)}</dd>
        <dt>Repository record time</dt><dd>{e.repositoryRecordTime ? fmtTime(e.repositoryRecordTime) : "Not recorded"}</dd>
        <dt>Received by this ledger</dt><dd>{e.localReceivedAt ? fmtTime(e.localReceivedAt) : "Not recorded"}</dd>
        <dt>Clock</dt><dd>{humanize(e.timeSource)} <span className="tag">Not a trusted time source</span></dd>
        <dt>Capture SHA-256</dt><dd>{e.captureSha256 ? <code>{e.captureSha256}</code> : "Not recorded"}</dd>
        <dt>Event chain hash</dt><dd>{e.eventChainHash ? <code>{e.eventChainHash}</code> : "Not recorded"}</dd>
        {e.supersedesEventId && <><dt>Corrects event</dt><dd><a href={tabHref(unitId, "evidence", e.supersedesEventId)}><code>{e.supersedesEventId}</code></a></dd></>}
      </dl>
      {e.facts.length > 0 && (
        <>
          <h4>Recorded facts</h4>
          <dl className="pp-facts">{e.facts.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>
        </>
      )}
      <div className="callout">
        <b>What the hashes show.</b> They show the stored capture and its position in this ledger's chain have not changed since they were
        recorded. They do <b>not</b> show who issued the record, that the source identity is genuine, that the clock was right, or that the
        physical bearing is what the record says.
      </div>
    </div>
  );
}

const CATEGORIES = ["All", "Material", "Assembly", "Rework", "Shipment", "Observation", "Inspection", "Work order"] as const;

function Timeline({ passport }: { passport: Passport }) {
  const [cat, setCat] = useState<(typeof CATEGORIES)[number]>("All");
  const shown: TimelineEntry[] = passport.timeline.filter((t) => cat === "All" || t.category === cat);
  const gaps = passport.notes.filter((n) => n.kind === "GAP");
  return (
    <div>
      <p className="muted">Events in recorded order. Times come from a simulated clock and are claims, not measurements.</p>
      <div role="group" aria-label="Filter timeline" className="pp-filters">
        {CATEGORIES.map((c) => <button key={c} type="button" className="pp-button" aria-pressed={cat === c} onClick={() => setCat(c)}>{c}</button>)}
      </div>
      {gaps.length > 0 && <div className="callout callout-warn" role="note">{gaps.map((g) => <p key={g.id}><b>{g.title}.</b> {g.detail}</p>)}</div>}
      {shown.length === 0 ? <p className="muted">No events in this category.</p> : (
        <ol className="pp-timeline">
          {shown.map((t) => (
            <li key={t.eventId} className={`pp-t-${t.category.toLowerCase().replace(/\s/g, "")}`}>
              <div className="pp-t-head"><b>{t.title}</b> <span className="tag">{t.category}</span></div>
              <div className="muted">{fmtTime(t.at)}</div>
              <div>{t.detail}</div>
              <a href={tabHref(passport.unitId, "evidence", t.eventId)}>View evidence</a>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function QrLabel({ unitId, url }: { unitId: string; url: string }) {
  const svg = useMemo(() => qrSvgPath(qrMatrix(url)), [url]);
  return (
    <div>
      <figure className="qr-label" aria-label={`QR label for ${unitId}`}>
        <svg viewBox={svg.viewBox} role="img" aria-label={`QR code linking to the passport route for ${unitId}`} shapeRendering="crispEdges" data-testid="qr-svg">
          <rect width={svg.size} height={svg.size} fill="#fff" />
          <path d={svg.path} fill="#000" />
        </svg>
        <figcaption>
          <b>{unitId}</b>
          <div className="qr-url"><code data-testid="qr-url">{url}</code></div>
          <div className="qr-note">Synthetic demonstration passport. This code is a link, not proof of authenticity.</div>
        </figcaption>
      </figure>
      <p><button type="button" className="pp-button" onClick={() => window.print()}>Print QR label</button></p>
      <div className="callout callout-warn" role="note">
        <b>Scanning from another device will not work while this application is restricted to 127.0.0.1.</b> A phone would try to reach itself,
        not this computer. This build does not expose the server on the network and is not deployed.
      </div>
      <ul>
        <li>The code encodes only the passport page address and the motor identifier shown above. It contains no customer, shipment, evidence, hash, signature claim or recall verdict.</li>
        <li>A QR code is a link. Anyone can print a code for any serial; it does not bind to the physical motor and cannot prevent cloning.</li>
        <li>The application has no access control. Leaving fields out of this passport is not API-level protection.</li>
      </ul>
    </div>
  );
}

function Overview({ passport }: { passport: Passport }) {
  const lc = passport.lifecycle;
  const recall = passport.recall;
  return (
    <div>
      <section aria-labelledby="pp-identity">
        <h3 id="pp-identity">Identity (as recorded)</h3>
        <dl className="pp-facts">
          <dt>Motor serial</dt><dd><code>{passport.unitId}</code></dd>
          <dt>Description</dt><dd>{passport.title} <span className="muted">(free text; no structured specification recorded)</span></dd>
          <dt>Product family label</dt><dd>{passport.family}</dd>
          <dt>Recorded events</dt><dd>{passport.eventCount}{passport.firstOccurredAt ? `, from ${fmtTime(passport.firstOccurredAt)} to ${fmtTime(passport.lastOccurredAt)}` : ""}</dd>
          <dt>Recorded lifecycle</dt><dd>{lc.assembled ? "Assembly completed" : "Assembly completion not recorded"} · {lc.shipped ? "Shipment recorded (not an authorization)" : "No shipment recorded"} · {lc.reworkOrders} rework order{lc.reworkOrders === 1 ? "" : "s"}</dd>
        </dl>
      </section>
      <section aria-labelledby="pp-comp-sum">
        <h3 id="pp-comp-sum">Currently recorded components</h3>
        <ul className="pp-summary">
          {passport.slots.map((s) => (
            <li key={s.slot}>
              <b>{s.slot}</b>: {s.current ? <>lot <code>{s.current.lot ?? "?"}</code>{s.current.serial ? <>, serial <code>{s.current.serial}</code></> : ", lot-level identity"} <ClaimChip status={s.current.status} /></> : "no currently recorded claim"}
              {s.history.length > 0 && <> · {s.history.length} earlier</>}
            </li>
          ))}
        </ul>
        <p><a href={tabHref(passport.unitId, "components")}>Open component history</a></p>
      </section>
      <section aria-labelledby="pp-recall-sum">
        <h3 id="pp-recall-sum">Recall context</h3>
        <RecallPanel recall={recall} unitId={passport.unitId} />
      </section>
      <section aria-labelledby="pp-notes">
        <h3 id="pp-notes">Not recorded and unverified</h3>
        <Notes notes={passport.notes} />
      </section>
    </div>
  );
}

export function PassportExplorer({ passport, tab, evidenceId, qrUrl, banner, sourceLabel }: {
  passport: Passport; tab: PassportTab; evidenceId: string | null; qrUrl: string; banner?: PassportBanner | null; sourceLabel: string;
}) {
  return (
    <div className="pp">
      <p><a href="#/">← All motors</a></p>
      <header className="pp-header">
        <h2>Digital product passport · <code>{passport.unitId}</code></h2>
        <p className="muted">{passport.title}</p>
        <p><SyntheticTag /> <span className="tag">Source: {sourceLabel}</span> <span className="tag">Not a certified DPP</span></p>
      </header>
      {banner && <div className={`callout callout-warn`} role="status" data-testid="passport-banner"><b>{banner.kind === "stale" ? "Records may be outdated." : "Records are not currently verified."}</b> {banner.text}</div>}
      <nav aria-label="Passport sections" className="pp-nav">
        <ul>
          {PASSPORT_TABS.map(([id, label]) => (
            <li key={id}><a href={tabHref(passport.unitId, id)} aria-current={tab === id ? "page" : undefined}>{label}</a></li>
          ))}
        </ul>
      </nav>
      <div className="panel pp-panel" id="pp-panel" tabIndex={-1}>
        {tab === "overview" && <Overview passport={passport} />}
        {tab === "components" && <div>{passport.slots.map((s) => <SlotSection key={s.slot} unitId={passport.unitId} slot={s} evidence={passport.evidence} />)}</div>}
        {tab === "evidence" && <EvidenceView passport={passport} evidenceId={evidenceId} />}
        {tab === "timeline" && <Timeline passport={passport} />}
        {tab === "recall" && <RecallPanel recall={passport.recall} unitId={passport.unitId} />}
        {tab === "qr" && <QrLabel unitId={passport.unitId} url={qrUrl} />}
      </div>
    </div>
  );
}
