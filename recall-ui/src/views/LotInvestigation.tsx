import { DecisionChips, SyntheticTag } from "../components/StatusChips";
import { fmtTime, investigateLot } from "../domain/derive";
import type { RecallSnapshot } from "../domain/types";

export function LotInvestigationView({ snap, policyId, lotId }: { snap: RecallSnapshot; policyId: string; lotId: string }) {
  const inv = investigateLot(snap, lotId, policyId);
  return (
    <div>
      <h2>Lot investigation</h2>
      <nav aria-label="Supplier lots" className="pill-row">
        {snap.lots.map((l) => (
          <a key={l.lotId} href={`#/lot/${l.lotId}`} aria-current={l.lotId === lotId ? "page" : undefined} className="pill">
            {l.lotId}{l.affected ? " ▲ recalled" : ""}
          </a>
        ))}
      </nav>
      {!inv ? (
        <p className="warn" role="alert">Lot {lotId} is not in the snapshot.</p>
      ) : (
        <>
          <p>
            Lot <b>{inv.lot.lotId}</b>, part {inv.lot.part}.{" "}
            {inv.lot.affected ? <b>This lot is named by the recall.</b> : "This lot is not named by the recall."}{" "}
            Supplier: {inv.lot.supplier ?? "unknown"} <SyntheticTag />
          </p>
          <p className="muted">
            {inv.rows.length} motor{inv.rows.length === 1 ? "" : "s"} have this lot in their install records. Decisions are the engine&apos;s
            under {policyId}; they depend on the whole motor history, not only this lot.
          </p>
          <table className="grid responsive">
            <caption className="sr-only">Motors with lot {inv.lot.lotId}</caption>
            <thead><tr><th scope="col">Motor</th><th scope="col">Where this lot was installed</th><th scope="col">Decision</th><th scope="col">Shipment <SyntheticTag /></th></tr></thead>
            <tbody>
              {inv.rows.map(({ unit, components, decision }) => (
                <tr key={unit.unitId}>
                  <td data-label="Motor"><a href={`#/unit/${unit.unitId}`}>{unit.unitId}</a><div className="muted">{unit.title}</div></td>
                  <td data-label="Installed">
                    {components.map((c) => (
                      <div key={c.componentId}>
                        Slot {c.slot}, installed {fmtTime(c.installedAt)}
                        {c.removedAt ? `, removed ${fmtTime(c.removedAt)}` : ", still recorded as installed"}
                        {c.supersededBy ? " (record later corrected)" : ""}
                      </div>
                    ))}
                  </td>
                  <td data-label="Decision">{decision ? <DecisionChips d={decision} /> : <span className="warn">No decision available</span>}</td>
                  <td data-label="Shipment">{unit.shipment ? unit.shipment.shipmentId : <span className="muted">Not shipped</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
