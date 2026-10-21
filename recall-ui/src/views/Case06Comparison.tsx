import { DecisionChips, SyntheticTag } from "../components/StatusChips";
import { POLICY_LABEL, isFalseRelease, safetyAgainstTruth } from "../domain/derive";
import { REASONS, explain, humanize } from "../domain/glossary";
import type { Comparison, Decision, RecallSnapshot } from "../domain/types";

const P1 = "RC-009/P1";

function Side({ title, sub, d, truth }: { title: string; sub: string; d: Decision; truth: Comparison["syntheticGroundTruth"] }) {
  const safety = truth && d.policyId === P1 ? safetyAgainstTruth(d, truth.trueP1Finding) : null;
  return (
    <section className="side" aria-label={title}>
      <h3>{title}</h3>
      <p className="muted">{sub}</p>
      <DecisionChips d={d} />
      <ul className="plain">
        {d.reasonCodes.length === 0 && <li className="muted">No reason codes</li>}
        {d.reasonCodes.map((c) => <li key={c}><b>{humanize(c)}</b><div className="muted">{explain(REASONS, c)}</div></li>)}
      </ul>
      {safety && (
        <p className={`safety safety-${safety.cls}`} data-testid="safety">
          <span aria-hidden="true">{safety.cls === "FALSE_RELEASE" ? "✖" : safety.cls === "CORRECT_RELEASE" ? "✓" : "■"}</span>{" "}
          <b>{safety.label}.</b> {safety.detail}
        </p>
      )}
    </section>
  );
}

export function Case06Comparison({ snap, policyId, unitId }: { snap: RecallSnapshot; policyId: string; unitId: string }) {
  const rows = snap.comparison.filter((c) => c.policyId === policyId);
  const sel = rows.find((c) => c.unitId === unitId) ?? rows[0];
  const p1 = policyId === P1;
  const legacyFalse = rows.filter((r) => isFalseRelease(r, "legacy")).length;
  const currentFalse = rows.filter((r) => isFalseRelease(r, "current")).length;
  const att = sel?.current.slotAttribution?.[0];

  return (
    <div>
      <h2>Case 06 before and after: slot attribution safety</h2>
      <p>
        Left is the original engine semantics ({snap.provenance.comparisonEngine.version}); right is the current engine ({snap.provenance.engine.version}).
        Both ran over the same synthetic events. Wrong-slot scans are the case: a removal that matches two slots must not clear the wrong one.
      </p>
      {rows.length === 0 && <p className="warn" role="alert">No comparison data in the snapshot.</p>}
      {!p1 && <p className="callout">Synthetic ground truth is defined for {POLICY_LABEL[P1]} only, so safety labels are shown for P1. Switch policy to see them.</p>}

      {rows.length > 0 && (
        <>
          <table className="grid responsive">
            <caption className="sr-only">Case 06 variants, original versus current engine</caption>
            <thead><tr><th scope="col">Variant</th><th scope="col">Original engine</th><th scope="col">Current engine</th><th scope="col">Synthetic truth <SyntheticTag /></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.unitId} aria-current={r.unitId === sel?.unitId ? "true" : undefined}>
                  <td data-label="Variant"><a href={`#/case06/${r.unitId}`}>{r.unitId}</a></td>
                  <td data-label="Original">{humanize(r.legacy.evidenceFinding)} · {humanize(r.legacy.operationalAction)}{p1 && isFalseRelease(r, "legacy") ? " ✖ false release" : ""}</td>
                  <td data-label="Current">{humanize(r.current.evidenceFinding)} · {humanize(r.current.operationalAction)}{p1 && isFalseRelease(r, "current") ? " ✖ false release" : ""}</td>
                  <td data-label="Truth">{r.syntheticGroundTruth ? humanize(r.syntheticGroundTruth.trueP1Finding) : "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {p1 && (
            <p role="status" data-testid="false-release-summary">
              False releases across these {rows.length} variants: <b>{legacyFalse}</b> with the original engine, <b>{currentFalse}</b> with the current engine.
            </p>
          )}
        </>
      )}

      {sel && (
        <>
          <h3>Selected: {sel.unitId}</h3>
          <div className="compare">
            <Side title="Before: original engine" sub={`${snap.provenance.comparisonEngine.semanticsProfile}, ${snap.provenance.comparisonEngine.version}`} d={sel.legacy} truth={sel.syntheticGroundTruth} />
            <Side title="After: current engine" sub={`${snap.provenance.engine.semanticsProfile}, ${snap.provenance.engine.version}`} d={sel.current} truth={sel.syntheticGroundTruth} />
          </div>
          {att ? (
            <div className="callout" data-testid="attribution">
              <h4>Why the current engine holds</h4>
              <p>
                The removal {att.removalEventId} was claimed for slot <b>{att.claimedSlot}</b>, but the removed item (lot {att.observed.lot}) also matches{" "}
                {att.candidates.filter((c) => !c.claimed).map((c) => `slot ${c.slot}`).join(", ") || "no other slot"}.
                Assurance is {humanize(att.assurance)}; ambiguity is {att.cleared ? "cleared" : "not cleared"}.
              </p>
              <div className="slots" aria-label="Candidate slots">
                {att.candidates.map((c) => (
                  <div key={c.slot} className={`slotbox ${c.claimed ? "claimed" : ""}`}>
                    <b>Slot {c.slot}</b>
                    <div>{c.claimed ? "Removal claimed here" : "Also matches the removed item"}</div>
                    <div className="muted">{humanize(c.basis)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="muted">The current engine found no slot ambiguity for this variant.</p>
          )}
          <p><a href={`#/unit/${sel.unitId}`}>Open full investigation for {sel.unitId}</a></p>
        </>
      )}
    </div>
  );
}
