import {useConsoleClaims} from "../contract/ConsoleClaims";
import {isCurrentClearance} from "../contract/clearance";
import { useMemo, useState } from "react";
import { DecisionChips, SyntheticTag } from "../components/StatusChips";
import { countDecisions, fmtTime, unitDecision } from "../domain/derive";
import type { Finding, RecallSnapshot } from "../domain/types";

export function FleetBoard({ snap, policyId }: { snap: RecallSnapshot; policyId: string }) {
  const {claims,preview}=useConsoleClaims();
  const cleared=claims ? [...claims.byMotor.values()].filter(isCurrentClearance).length : 0;
  const [finding, setFinding] = useState<"ALL" | Finding>("ALL");
  const [family, setFamily] = useState("ALL");
  const [q, setQ] = useState("");
  const counts = useMemo(() => countDecisions(snap, policyId), [snap, policyId]);
  const families = useMemo(() => [...new Set(snap.units.map((u) => u.family))].sort(), [snap]);

  const rows = snap.units.filter((u) => {
    const d = unitDecision(snap, u.unitId, policyId)?.current;
    if (finding !== "ALL" && d?.evidenceFinding !== finding) return false;
    if (family !== "ALL" && u.family !== family) return false;
    const needle = q.trim().toLowerCase();
    return !needle || `${u.unitId} ${u.title} ${u.motorSerial}`.toLowerCase().includes(needle);
  });

  return (
    <div>
      <h2>Motor decisions</h2>
      <ul className="stats" aria-label="Decision counts">
        <li><b>{counts.total}</b> motors</li>
        <li className="finding-AFFECTED"><b>{counts.byFinding.AFFECTED}</b> <span aria-hidden="true">▲</span> affected</li>
        <li className="finding-UNRESOLVED"><b>{counts.byFinding.UNRESOLVED}</b> <span aria-hidden="true">?</span> unresolved</li>
        <li className="finding-EXCLUDED_WITH_EVIDENCE"><b>{counts.byFinding.EXCLUDED_WITH_EVIDENCE}</b> <span aria-hidden="true">✓</span> excluded with evidence</li>
        <li><b>{counts.hold}</b> on recall hold</li>
        <li><b>{cleared}</b> current clearance{preview ? ` (synthetic recorded releases: ${counts.release}; not authorization)` : ""}</li>
        <li><b>{counts.review}</b> review required</li>
      </ul>

      <div className="filters">
        <label>
          Evidence finding
          <select value={finding} onChange={(e) => setFinding(e.target.value as "ALL" | Finding)}>
            <option value="ALL">All</option>
            <option value="AFFECTED">Affected</option>
            <option value="UNRESOLVED">Unresolved</option>
            <option value="EXCLUDED_WITH_EVIDENCE">Excluded with evidence</option>
          </select>
        </label>
        <label>
          Scenario family
          <select value={family} onChange={(e) => setFamily(e.target.value)}>
            <option value="ALL">All</option>
            {families.map((f) => <option key={f}>{f}</option>)}
          </select>
        </label>
        <label>
          Search
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="case id or title" />
        </label>
      </div>
      <p className="muted" role="status">Showing {rows.length} of {snap.units.length} motors.</p>

      <table className="grid responsive">
        <caption className="sr-only">Motor decisions under {policyId}</caption>
        <thead>
          <tr>
            <th scope="col">Unit</th><th scope="col">Scenario</th><th scope="col">Decision</th>
            <th scope="col">Versions</th><th scope="col">Shipment <SyntheticTag /></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => {
            const pd = unitDecision(snap, u.unitId, policyId);
            return (
              <tr key={u.unitId}>
                <td data-label="Unit"><a href={`#/unit/${u.unitId}`}>{u.unitId}</a><div className="muted">{u.motorSerial}</div></td>
                <td data-label="Scenario">{u.title}<div className="muted">{u.family}</div></td>
                <td data-label="Decision">{pd ? <DecisionChips d={pd.current} /> : <span className="warn">No decision available</span>}</td>
                <td data-label="Versions">{pd ? pd.history.length : "n/a"}</td>
                <td data-label="Shipment">
                  {u.shipment ? <>{u.shipment.shipmentId}<div className="muted">{fmtTime(u.shipment.shippedAt)}</div></> : <span className="muted">Not shipped</span>}
                </td>
              </tr>
            );
          })}
          {rows.length === 0 && <tr><td colSpan={5}>No motors match the filters.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
