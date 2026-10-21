import { DecisionChips } from "../components/StatusChips";
import { FINDING_TEXT, humanize } from "../domain/glossary";
import type { Decision } from "../domain/types";

function changeNote(prev: Decision | undefined, d: Decision): string {
  if (!prev) return "First decision after the recall announcement.";
  const bits: string[] = [];
  if (prev.evidenceFinding !== d.evidenceFinding) {
    bits.push(`Finding changed from ${FINDING_TEXT[prev.evidenceFinding]?.label} to ${FINDING_TEXT[d.evidenceFinding]?.label}`);
  }
  if (prev.operationalAction !== d.operationalAction) bits.push("operational action changed");
  const added = d.reasonCodes.filter((c) => !prev.reasonCodes.includes(c));
  if (added.length) bits.push(`new reasons: ${added.map(humanize).join(", ")}`);
  return bits.length ? `${bits.join("; ")}.` : "Outcome unchanged but reasons or evidence differ.";
}

export function DecisionHistory({ history }: { history: Decision[] }) {
  if (history.length === 0) return <p className="warn" role="alert">No decision history is available.</p>;
  return (
    <div>
      <p className="muted">
        A new version is issued only when the outcome changes. Earlier versions are kept, never overwritten.
      </p>
      <ol className="history">
        {history.map((d, i) => {
          const superseded = i < history.length - 1;
          return (
            <li key={d.decisionId} className={superseded ? "superseded" : "latest"}>
              <h3>
                Version {d.version ?? i + 1} · <code>{d.decisionId}</code>{" "}
                <span className="tag">{superseded ? `Superseded by v${history[i + 1].version ?? i + 2}` : "Current"}</span>
              </h3>
              <DecisionChips d={d} />
              <p>{changeNote(history[i - 1], d)}</p>
              <dl className="meta">
                <div><dt>Triggered by event</dt><dd>{d.triggerEventId ? <code>{d.triggerEventId}</code> : "recall announcement state"}</dd></div>
                <div><dt>Supersedes</dt><dd>{d.supersedesDecisionId ? <code>{d.supersedesDecisionId}</code> : "none (first version)"}</dd></div>
                <div><dt>Reasons</dt><dd>{d.reasonCodes.length ? d.reasonCodes.map(humanize).join("; ") : "none recorded"}</dd></div>
              </dl>
              {d.notificationObligation?.required && (
                <div className="callout callout-warn" role="note">
                  <b>Notification obligation.</b> This decision withdraws the earlier release-eligible decision{" "}
                  <code>{d.notificationObligation.appliesIfDecisionCommunicated}</code>. If that decision was communicated
                  to anyone, they must be told it no longer stands. Reason: {humanize(d.notificationObligation.reason)}. Whether it was
                  communicated is not recorded: {d.notificationObligation.communicated == null ? "unknown" : String(d.notificationObligation.communicated)}.
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
