import type { HistoricalView } from "../contract/gated";
import { factsOf } from "../contract/gated";
import { fmtTime } from "../domain/derive";

/**
 * Shown when the shared gate classifies the live envelope as ANCHORED_PREFIX_ONLY or UNANCHORED.
 * By the approved display policy it carries segregated historical facts only: no decision, recall hold,
 * operational action or clearance, and no wording that lets a reader infer one.
 */
export function CheckpointRequired({ view, cause }: { view: HistoricalView; cause: "PREFIX_ONLY" | "UNANCHORED" }) {
  const facts = factsOf(view);
  const prefix = cause === "PREFIX_ONLY";
  return (
    <section role="alert" aria-label="Checkpoint required" data-testid="checkpoint-required" className="error-panel">
      <h2>{prefix ? "Checkpoint required" : "Trusted anchor required"}</h2>
      <p>
        {prefix
          ? "ANCHORED_PREFIX_ONLY: the ledger holds evidence newer than the independently protected checkpoint."
          : "UNANCHORED: no trusted external checkpoint covers this ledger."}{" "}
        No current decisions, recall holds, operational actions or release clearance are shown, and none may be inferred from this screen.
        <b> Do not ship or release any motor while this state persists.</b>
      </p>
      <p>
        {prefix
          ? "To restore current decisions the owner must export a successor checkpoint, establish its custody independently of this host, and restart the application with it (--trusted-anchor <successor> --previous-anchor <previous>)."
          : "Start the application with an owner-custodied checkpoint (--trusted-anchor)."}{" "}
        Exporting a local candidate does not establish trust, and this page cannot promote one.
      </p>
      <h3>Historical facts (not currently verified)</h3>
      <p className="muted">
        Journal sequence {view.watermark.sequence}{view.watermark.verifiedAt ? `, last verified ${view.watermark.verifiedAt}` : ""}. These are recorded events only.
      </p>
      <table className="grid">
        <caption className="sr-only">Recorded motors and events, historical</caption>
        <thead><tr><th scope="col">Motor</th><th scope="col">Recorded events</th><th scope="col">Last event</th><th scope="col">Shipment record</th></tr></thead>
        <tbody>
          {facts.units.map((u) => {
            const last = u.events.length ? u.events[u.events.length - 1] : null;
            return (
              <tr key={u.unitId}>
                <td>{u.unitId}</td>
                <td>{u.eventCount}</td>
                <td>{last ? `${last.eventType} · ${fmtTime(last.occurredAt)}` : "none"}</td>
                <td>{u.shipment ? u.shipment.shipmentId : "none recorded"}</td>
              </tr>
            );
          })}
          {facts.units.length === 0 && <tr><td colSpan={4}>No motors recorded.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}
