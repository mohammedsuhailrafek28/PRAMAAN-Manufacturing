import { fmtTime } from "../domain/derive";
import { humanize } from "../domain/glossary";
import type { Decision, Unit } from "../domain/types";

function summary(p: Record<string, unknown>): string {
  const keys = ["slot", "part", "lot", "serial", "state", "result", "disposition", "reason"];
  return keys.filter((k) => p[k] != null).map((k) => `${k} ${String(p[k])}`).join(", ");
}

export function EventLog({ unit, decision }: { unit: Unit; decision: Decision | undefined }) {
  const cited = new Set(decision?.evidenceEventIds ?? []);
  return (
    <div>
      <p className="muted">Raw synthetic event records for this motor, in the order recorded. Cited events support the current decision.</p>
      <h3>Capture sessions</h3>
      <ul className="plain">
        {unit.captureSessions.map((s, i) => <li key={i}>Source {s.sourceId}: {fmtTime(s.from)} to {fmtTime(s.to)}</li>)}
      </ul>
      <table className="grid responsive">
        <caption className="sr-only">Event log for {unit.unitId}</caption>
        <thead><tr><th scope="col">Event</th><th scope="col">Type</th><th scope="col">Occurred</th><th scope="col">Recorded</th><th scope="col">Detail</th><th scope="col">Cited</th></tr></thead>
        <tbody>
          {unit.events.map((e) => (
            <tr key={e.eventId}>
              <td data-label="Event"><code>{e.eventId}</code><div className="muted">{e.sourceId} #{e.sourceSeq}</div></td>
              <td data-label="Type">{humanize(e.eventType)}{e.supersedesEventId ? <div className="muted">corrects {e.supersedesEventId}</div> : null}</td>
              <td data-label="Occurred">{fmtTime(e.occurredAt)}<div className="muted">{humanize(e.timeSource)}</div></td>
              <td data-label="Recorded">{fmtTime(e.recordedAt)}</td>
              <td data-label="Detail">{summary(e.payload)}</td>
              <td data-label="Cited">{cited.has(e.eventId) ? "Yes" : <span className="muted">No</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
