import { useState } from "react";
import type { RecallSnapshot } from "../domain/types";

export function ManufacturingWorkbench({ snap, run, busy }: {
  snap: RecallSnapshot; run: (path: string, body: Record<string, unknown>) => Promise<void>; busy: boolean;
}) {
  const [serial, setSerial] = useState("MTR-26006");
  const [motor, setMotor] = useState(snap.units[0]?.unitId ?? "");
  const [de, setDe] = useState("BR-204");
  const [nde, setNde] = useState("BR-310");
  const [lot, setLot] = useState("BR-312");
  const [affected, setAffected] = useState("BR-204");
  const [identity, setIdentity] = useState("SERIAL");
  const [scope, setScope] = useState(snap.recall.affectedSlots.length ? snap.recall.affectedSlots.join(",") : "DE,NDE");
  return <details className="workbench" open={snap.units.length === 0}>
    <summary>Manufacturing capture workspace</summary>
    <p>Local synthetic operator commands write EPCIS-compatible evidence to SQLite and re-evaluate with v3. No command authors trusted verification. Assembly and replacement contain multiple durable captures; interrupted work remains incomplete.</p>
    <fieldset disabled={busy}>
      <legend>Create a manufacturing unit</legend>
      <form onSubmit={async e => { e.preventDefault(); await run("units", { serial }); setMotor(serial); }}>
        <label>New motor serial<input required pattern="MTR-[A-Z0-9-]{3,30}" value={serial} onChange={e => setSerial(e.target.value)} /></label>
        <button>Create unit</button>
      </form>
    </fieldset>
    <fieldset disabled={busy || !snap.units.length}>
      <legend>Capture assembly and rework</legend>
      <label>Motor to capture<select value={motor} onChange={e => setMotor(e.target.value)}>{snap.units.map(u => <option key={u.unitId}>{u.unitId}</option>)}</select></label>
      <form onSubmit={e => { e.preventDefault(); void run(`units/${encodeURIComponent(motor)}/assemble`, { deLot: de, ndeLot: nde, identity }); }}>
        <label>DE bearing lot<input required maxLength={80} value={de} onChange={e => setDe(e.target.value)} /></label>
        <label>NDE bearing lot<input required maxLength={80} value={nde} onChange={e => setNde(e.target.value)} /></label>
        <label>Identity evidence<select value={identity} onChange={e => setIdentity(e.target.value)}><option value="SERIAL">Distinct serial markings (synthetic claims)</option><option value="LOT">Lot only (can remain ambiguous)</option></select></label>
        <button>Capture bearing assembly</button>
      </form>
      <button type="button" onClick={() => void run(`units/${encodeURIComponent(motor)}/ship`, {})}>Record synthetic shipment</button>
      <form onSubmit={e => { e.preventDefault(); void run(`units/${encodeURIComponent(motor)}/replace`, { lot }); }}>
        <label>Replacement DE lot<input required maxLength={80} value={lot} onChange={e => setLot(e.target.value)} /></label>
        <button>Capture authorized DE replacement</button>
      </form>
      <p className="muted">Authorized means the configured synthetic REWORK operator is allowed to capture this operation; it does not independently verify physical slot identity.</p>
      <button type="button" onClick={() => void run(`units/${encodeURIComponent(motor)}/observe`, { lot: affected })}>Inject late untrusted affected-lot observation</button>
      <p><a href={`#/unit/${encodeURIComponent(motor)}/genealogy`}>Inspect selected motor genealogy and evidence</a></p>
    </fieldset>
    <fieldset disabled={busy}>
      <legend>Announce a defective bearing lot</legend>
      <form onSubmit={e => { e.preventDefault(); void run("recalls", { lot: affected, affectedSlots: scope.split(",") }); }}>
        <label>Defective bearing lot<input required maxLength={80} value={affected} onChange={e => setAffected(e.target.value)} /></label>
        <label>Recall positions<select value={scope} onChange={e => setScope(e.target.value)}><option value="DE,NDE">Both DE and NDE (conservative default)</option><option value="DE">DE only (explicit restriction)</option><option value="NDE">NDE only (explicit restriction)</option></select></label>
        <button>Announce recall and evaluate</button>
      </form>
    </fieldset>
    {busy && <p role="status">Capturing evidence and evaluating…</p>}
  </details>;
}
