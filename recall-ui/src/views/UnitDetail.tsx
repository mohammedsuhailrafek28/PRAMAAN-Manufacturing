import { DecisionChips } from "../components/StatusChips";
import { unitDecision } from "../domain/derive";
import type { RecallSnapshot } from "../domain/types";
import { DecisionExplanation } from "./DecisionExplanation";
import { DecisionHistory } from "./DecisionHistory";
import { EventLog } from "./EventLog";
import { GenealogyGraph } from "./GenealogyGraph";

export type UnitTab = "decision" | "genealogy" | "history" | "events";
const TABS: Array<[UnitTab, string]> = [
  ["decision", "Decision explanation"],
  ["genealogy", "Genealogy"],
  ["history", "Decision history"],
  ["events", "Event log"],
];

export function UnitDetail({ snap, unitId, policyId, tab }: { snap: RecallSnapshot; unitId: string; policyId: string; tab: UnitTab }) {
  const unit = snap.units.find((u) => u.unitId === unitId);
  if (!unit) {
    return <p className="warn" role="alert">Unit {unitId} is not in the snapshot. <a href="#/">Back to all motors</a></p>;
  }
  const pd = unitDecision(snap, unitId, policyId);
  return (
    <div>
      <p><a href="#/">← All motors</a></p>
      <h2>{unit.unitId} · {unit.title}</h2>
      <p className="muted">Motor {unit.motorSerial} · scenario family {unit.family} · fixture set {unit.fixtureSet} · {unit.eventCount} events. Policy {policyId}.</p>
      <p>{unit.description}</p>
      {pd ? <DecisionChips d={pd.current} /> : <p className="warn" role="alert">No decision is available for this motor under {policyId}.</p>}
      <div role="tablist" aria-label="Motor views" className="tabs">
        {TABS.map(([id, label]) => (
          <a key={id} role="tab" id={`tab-${id}`} aria-selected={tab === id} aria-controls="tabpanel" href={`#/unit/${unitId}/${id}`}>{label}</a>
        ))}
      </div>
      <div role="tabpanel" id="tabpanel" aria-labelledby={`tab-${tab}`} className="panel">
        {tab === "decision" && (pd ? <DecisionExplanation d={pd.current} unit={unit} /> : <p className="muted">Nothing to explain without a decision.</p>)}
        {tab === "genealogy" && <GenealogyGraph snap={snap} unitId={unitId} />}
        {tab === "history" && <DecisionHistory history={pd?.history ?? []} />}
        {tab === "events" && <EventLog unit={unit} decision={pd?.current} />}
      </div>
    </div>
  );
}
