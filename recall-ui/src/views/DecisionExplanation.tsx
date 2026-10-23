import {ClaimText} from "../contract/ClearanceChip";
import {useConsoleClaim} from "../contract/ConsoleClaims";
import { DecisionChips } from "../components/StatusChips";
import { missingEvidence } from "../domain/derive";
import {
  ASSURANCE, CONFLICT_KINDS, FINDING_TEXT, FLAGS, GAP_KINDS, OBSERVATION_STATUS, RECONCILIATIONS, REASONS,
  explain, humanize,
} from "../domain/glossary";
import type { Decision, Gap, SlotAttribution, Unit } from "../domain/types";
import { fmtTime } from "../domain/derive";

function Gaps({ gaps }: { gaps: Gap[] }) {
  if (!gaps.length) return <span className="muted">None</span>;
  return (
    <ul className="plain">
      {gaps.map((g, i) => (
        <li key={i}>
          <b>{humanize(g.kind)}</b>
          {g.materiality ? ` (${humanize(String(g.materiality))})` : ""}
          {g.from ? `, ${fmtTime(g.from)} to ${fmtTime(String(g.to ?? ""))}` : ""}
          <div className="muted">{explain(GAP_KINDS, g.kind)}</div>
        </li>
      ))}
    </ul>
  );
}

function Attribution({ a }: { a: SlotAttribution }) {
  return (
    <div className={`callout ${a.ambiguous && !a.cleared ? "callout-warn" : ""}`}>
      <h4>Removal {a.removalEventId}: claimed slot {a.claimedSlot}</h4>
      <p>
        Removed item: part {a.observed.part ?? "?"}, lot {a.observed.lot ?? "?"}, serial {a.observed.serial ?? "not recorded"} (
        {humanize(a.observed.granularity ?? "unknown")} identity).
      </p>
      <p>
        <b>{a.ambiguous && !a.cleared ? "Ambiguous: not cleared." : a.ambiguous ? "Was ambiguous: cleared." : "Not ambiguous."}</b>{" "}
        Assurance <b>{humanize(a.assurance)}</b>. {explain(ASSURANCE, a.assurance)}
        {a.clearedBy ? ` Cleared by ${a.clearedBy}.` : ""}
      </p>
      <table className="grid compact">
        <caption className="sr-only">Candidate slots for removal {a.removalEventId}</caption>
        <thead><tr><th scope="col">Candidate slot</th><th scope="col">Basis</th><th scope="col">Claimed</th><th scope="col">Supporting events</th></tr></thead>
        <tbody>
          {a.candidates.map((c) => (
            <tr key={c.slot}><td>{c.slot}</td><td>{humanize(c.basis)}</td><td>{c.claimed ? "Yes" : "No"}</td><td>{c.supportingEventIds.join(", ")}</td></tr>
          ))}
        </tbody>
      </table>
      {a.ruledOutSlots.length > 0 && <p>Ruled out: {a.ruledOutSlots.join(", ")}.</p>}
      {a.unrulableAlternatives.map((u) => <p key={u.slot}>Cannot rule out slot {u.slot}: {humanize(u.reason)}.</p>)}
      {a.rejectedLabelScans.map((r) => <p key={r.eventId}>Label scan {r.eventId} rejected: {humanize(r.reason)}.</p>)}
    </div>
  );
}

export function DecisionExplanation({ d, unit }: { d: Decision; unit: Unit }) {
  const claim = useConsoleClaim(d.decisionId);
  const missing = missingEvidence(d, unit);
  const cited = new Set(d.evidenceEventIds);
  const events = unit.events.filter((e) => cited.has(e.eventId));
  const finding = FINDING_TEXT[d.evidenceFinding];
  return (
    <div>
      <DecisionChips d={d} />
      {typeof d.publicationProfile === 'string' && <p className="muted">Publication lifecycle: {d.publicationProfile}. Exposure evaluation uses the recorded engine semantics; lifecycle history is stored separately.</p>}
      <p className="lead">{finding?.explain} {claim ? <ClaimText claim={claim}/> : "Recorded evaluator output only; this is not current clearance."}</p>
      {d.reviewRequired && <p><b>Review is required.</b> A person must look at this motor, separately from the hold.</p>}
      {d.precautionaryHold && <p><b>Precautionary hold.</b> Held because an earlier release no longer stands.</p>}

      <h3>Why: reason codes</h3>
      {d.reasonCodes.length === 0 ? <p className="muted">The engine recorded no reason codes.</p> : (
        <dl className="defs">
          {d.reasonCodes.map((c) => (<div key={c}><dt>{humanize(c)} <code>{c}</code></dt><dd>{explain(REASONS, c)}</dd></div>))}
        </dl>
      )}
      {d.flags.length > 0 && (
        <>
          <h3>Flags</h3>
          <dl className="defs">{d.flags.map((c) => (<div key={c}><dt>{humanize(c)} <code>{c}</code></dt><dd>{explain(FLAGS, c)}</dd></div>))}</dl>
        </>
      )}

      {d.slotAttribution && d.slotAttribution.length > 0 && (
        <>
          <h3>Slot attribution and ambiguity</h3>
          {d.slotAttribution.map((a) => <Attribution key={a.removalEventId} a={a} />)}
        </>
      )}

      {d.untrustedObservations && d.untrustedObservations.length > 0 && (
        <>
          <h3>Untrusted observations</h3>
          <ul className="plain">
            {d.untrustedObservations.map((o) => (
              <li key={o.eventId}>
                <b>{o.eventId}</b>: {humanize(o.status)}. Saw part {o.observed.part ?? "?"}, lot {o.observed.lot ?? "?"} in slot {o.slot ?? "unknown"}.
                <div className="muted">{explain(OBSERVATION_STATUS, o.status)}</div>
                {o.rejectedReasons?.length ? <div>Why unreliable: {o.rejectedReasons.map(humanize).join("; ")}.</div> : null}
                {o.resolvedBy ? <div>Answered by {o.resolvedBy}.</div> : null}
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>Slot evidence and capture gaps</h3>
      <table className="grid responsive">
        <caption className="sr-only">Per-slot reconciliation</caption>
        <thead><tr><th scope="col">Slot</th><th scope="col">Reconciliation</th><th scope="col">Lot per records</th><th scope="col">Capture gaps</th><th scope="col">Conflicts</th></tr></thead>
        <tbody>
          {Object.entries(d.slots).map(([name, s]) => (
            <tr key={name}>
              <td data-label="Slot">{name}<div className="muted">{humanize(s.policyRelevance ?? "")}</div></td>
              <td data-label="Reconciliation"><b>{humanize(s.reconciliation)}</b><div className="muted">{explain(RECONCILIATIONS, s.reconciliation)}</div></td>
              <td data-label="Lot per records">{s.currentLotPerRecords ?? "unknown"}<div className="muted">{humanize(s.baseline ?? "")}</div></td>
              <td data-label="Capture gaps"><Gaps gaps={s.gaps ?? []} /></td>
              <td data-label="Conflicts">
                {(s.conflicts ?? []).length === 0 ? <span className="muted">None</span> : (
                  <ul className="plain">{(s.conflicts ?? []).map((c, i) => <li key={i}><b>{humanize(c.kind)}</b><div className="muted">{explain(CONFLICT_KINDS, c.kind)}</div></li>)}</ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Evidence the decision cites</h3>
      {missing.length > 0 && (
        <p className="warn" role="alert">
          Incomplete evidence: {missing.length} cited event{missing.length === 1 ? " is" : "s are"} missing from the event log ({missing.join(", ")}).
          Treat this decision as unverifiable here.
        </p>
      )}
      {events.length === 0 ? <p className="muted">No cited events are available.</p> : (
        <ul className="plain">
          {events.map((e) => (
            <li key={e.eventId}><code>{e.eventId}</code> {humanize(e.eventType)} · {fmtTime(e.occurredAt)} · source {e.sourceId} ({humanize(e.timeSource)})</li>
          ))}
        </ul>
      )}
      {d.integrityIssues.length > 0 && <p className="warn">Integrity issues reported by the engine: {d.integrityIssues.length}.</p>}
      {d.assuranceWarnings && d.assuranceWarnings.length > 0 && <p className="warn">Assurance warnings: {d.assuranceWarnings.map(humanize).join("; ")}.</p>}

      <h3>Provenance of this decision</h3>
      <dl className="meta">
        <div><dt>Decision id</dt><dd><code>{d.decisionId}</code></dd></div>
        <div><dt>Engine</dt><dd>{d.engineVersion} ({d.semanticsProfile})</dd></div>
        <div><dt>Coverage digest</dt><dd><code>{d.coverageDigest.slice(0, 16)}</code></dd></div>
        <div><dt>Policy</dt><dd>{d.policyId}</dd></div>
        <div><dt>Ingestion watermark</dt><dd><code>{JSON.stringify(d.watermark)}</code></dd></div>
      </dl>
    </div>
  );
}
