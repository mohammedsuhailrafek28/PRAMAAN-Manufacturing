import { useCallback, useEffect, useState } from "react";
import type { RecoveryApi, RecoveryStatus, RecoveryProposal } from "../domain/recovery";

/** Restricted stale-checkpoint recovery. Evidence capture, controlled replacement and the PROPOSAL of a successor checkpoint only.
 *  It receives no decision, eligibility or clearance (the server returns none), and offers no shipment, announcement, acceptance or activation. */
export function RecoveryWorkspace({ api, motors }: { api: RecoveryApi; motors: string[] }) {
  const [status, setStatus] = useState<RecoveryStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<RecoveryProposal | null>(null);
  const [motor, setMotor] = useState(motors[0] ?? "");
  const [lot, setLot] = useState("");
  const [slot, setSlot] = useState("DE");
  const [replacement, setReplacement] = useState("BR-312");

  const refresh = useCallback(async () => {
    const res = await api.call(null);
    if (res.status === 200 && res.body.recovery) { setStatus(res.body.recovery); setError(""); }
    else setError(`Recovery is not available (${res.body.error ?? res.status}).`);
  }, [api]);
  useEffect(() => { void refresh(); }, [refresh]);

  const act = async (action: string, body: Record<string, unknown>) => {
    setBusy(true);
    try {
      const res = await api.call(action, body);
      if (res.status === 200 && res.body.recovery) {
        setStatus(res.body.recovery);
        setError("");
        if (action === "propose" && res.body.proposal) setProposal(res.body.proposal);
      } else setError(`Refused (${res.body.error ?? res.status}). Nothing was changed.`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  return <section aria-label="Stale-checkpoint recovery" data-testid="recovery-workspace" className="callout">
    <h2>Recovery workspace</h2>
    <p><b>No motor is cleared here.</b> Recovery records evidence and proposes a successor checkpoint. It cannot ship, release, announce a recall, accept or activate a checkpoint. A motor becomes eligible only after an operator accepts a reviewed checkpoint and restarts the application with it.</p>
    {error && <p role="alert" data-testid="recovery-error">{error}</p>}
    {status && <>
      <p data-testid="recovery-mode">Mode: {status.mode.replaceAll("_", " ").toLowerCase()}. Allowed: {status.allowedActions.join(", ")}.</p>
      <h3>Motors held for investigation</h3>
      {status.heldMotors.length === 0 ? <p>None are held by identity or integrity guards.</p> :
        <ul data-testid="recovery-held">{status.heldMotors.map(h => <li key={h.motor}><b>{h.motor}</b>: {[...h.identityFindings.map(f => `${f.source} ${f.reason}${f.lot ? ` (${f.lot})` : ""}`), ...h.integrityFindings.map(f => f.reason)].join("; ")}. {h.quarantine?.steps?.[0]?.instruction}</li>)}</ul>}
      <fieldset disabled={busy}>
        <legend>Capture evidence or reconcile</legend>
        <label>Motor<select value={motor} onChange={e => setMotor(e.target.value)} data-testid="recovery-motor">{motors.map(m => <option key={m}>{m}</option>)}</select></label>
        <label>Slot<select value={slot} onChange={e => setSlot(e.target.value)}><option value="DE">DE</option><option value="NDE">NDE</option></select></label>
        <form onSubmit={e => { e.preventDefault(); void act("observe", { motor, lot, slot }); setLot(""); }}>
          <label>Sighted label (as read; may be wrong)<input required maxLength={80} value={lot} onChange={e => setLot(e.target.value)} data-testid="recovery-sighting" /></label>
          <button>Record unverified sighting</button>
        </form>
        <form onSubmit={e => { e.preventDefault(); void act("replace", { motor, lot: replacement, slot }); }}>
          <label>Replacement lot (registered)<input required maxLength={80} value={replacement} onChange={e => setReplacement(e.target.value)} data-testid="recovery-replacement" /></label>
          <button>Capture controlled replacement</button>
        </form>
        <button type="button" onClick={() => void act("propose", {})} disabled={!status.custodyConfigured} data-testid="recovery-propose">Propose successor checkpoint (not activated)</button>
        {!status.custodyConfigured && <p className="muted">No custody directory is configured for this server; use the command line proposal.</p>}
      </fieldset>
    </>}
    {proposal && <div data-testid="recovery-proposal">
      <h3>Proposed candidate (not active)</h3>
      <p>Status {proposal.status}. Candidate sha256 <code>{proposal.candidateSha256}</code>.</p>
      <p>Contained, stays held: {proposal.review.containedMotors.length ? proposal.review.containedMotors.join(", ") : "none"}. Refused (candidate cannot be accepted): {proposal.review.refusedForIdentity.length ? proposal.review.refusedForIdentity.join(", ") : "none"}.</p>
      <p>Acknowledgement required for: {proposal.review.requiresAcknowledgement.length ? proposal.review.requiresAcknowledgement.join(", ") : "none"}. Acceptance and activation are operator actions outside this page.</p>
    </div>}
  </section>;
}
