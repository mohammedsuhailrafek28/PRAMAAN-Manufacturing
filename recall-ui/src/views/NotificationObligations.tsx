import { useState } from "react";
import type { RecallSnapshot } from "../domain/types";

type Run = (path: string, body: Record<string, unknown>) => Promise<void>;

/**
 * Obligations stay listed until an operator explicitly resolves them. Resolution is an attestation
 * recorded in the ledger, never a delivery acknowledgement: this application sends nothing.
 */
export function NotificationObligations({ snap, run, busy }: { snap: RecallSnapshot; run?: Run; busy: boolean }) {
  const items = snap.notifications ?? [];
  const [notes, setNotes] = useState<Record<string, string>>({});
  if (items.length === 0) return null;
  const open = items.filter((n) => n.status !== "RESOLVED");
  return (
    <section className="callout" aria-label="Notification obligations">
      <h2>Notification obligations ({open.length} outstanding)</h2>
      <p>
        Conditional obligations from the decision lifecycle. They remain outstanding until explicitly resolved; displaying a decision
        does not mark it communicated, and no notifications are sent by this application.
      </p>
      <ul className="plain">
        {items.map((n) => {
          const id = n.obligationId ?? n.decisionId;
          const resolved = n.status === "RESOLVED";
          return (
            <li key={id} data-testid={resolved ? "obligation-resolved" : "obligation-open"}>
              <a href={`#/unit/${n.unitId}/history`}>{n.unitId}</a>: {n.reason}; if {n.appliesIfDecisionCommunicated} was communicated.{" "}
              <b>{resolved ? "Resolved" : "Outstanding"}</b>. Delivery: {n.deliveryStatus}.
              {resolved && n.resolution && (
                <span className="muted"> Attested by {n.resolution.actor} at {n.resolution.at} ({n.resolution.resolution}): {n.resolution.note}. This is not a delivery acknowledgement.</span>
              )}
              {!resolved && run && n.obligationId && (
                <form onSubmit={(e) => { e.preventDefault(); void run(`notifications/${encodeURIComponent(id)}/resolve`, { resolution: "CORRECTION_COMMUNICATED_ATTESTED", note: notes[id] ?? "" }); }}>
                  <label>Resolution note (who was told, how, when)
                    <input required maxLength={300} value={notes[id] ?? ""} onChange={(e) => setNotes({ ...notes, [id]: e.target.value })} disabled={busy} />
                  </label>
                  <button disabled={busy}>Attest correction communicated</button>
                </form>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
