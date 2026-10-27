"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { projectPassport } from "@/orig/contract/views";
import { EvidenceTab, TimelineTab } from "@/dash/PassportTabs";
import { useEffect, useMemo, useState } from "react";
import { qrMatrix, qrSvgPath } from "@/orig/passport/qr";
import { UNIT_ID_PATTERN } from "@/orig/passport/projection";
import { useData, useMotorResourceChecked } from "@/dash/data";
import { ResourceNote } from "@/dash/ResourceNote";
import { explain, humanize, REASONS } from "@/dash/glossary";
import { ActionTag, FindingTag, NA, currentOf, fmt, unitOf, useMotor, val } from "@/dash/ui";
import type { Lifecycle, ProvenanceRow, Snapshot } from "@/dash/types";

export default function PassportPage() {
  const { snap } = useData();
  if (snap.phase === "loading") return <div className="skel" style={{ height: 320 }} />;
  if (snap.phase === "error") return <p>The passport is unavailable because the backend data could not be read.</p>;
  return <Passport s={snap.snap} />;
}

const NOT_RECORDED = ["Nameplate ratings and efficiency class", "Quality or compliance certificates", "Test and inspection measurements", "Carbon footprint and recycled-content figures", "Operating telemetry", "Serviceability and end-of-life data"];

function Passport({ s }: { s: Snapshot }) {
  const { gate, view, mode, gateReason } = useData();
  const [motor, , href] = useMotor(s);
  const sp = useSearchParams(), router = useRouter(), path = usePathname();
  const tab = sp.get("tab") === "evidence" ? "evidence" : sp.get("tab") === "timeline" ? "timeline" : "overview";
  const evidenceId = sp.get("evidence");
  const setQ = (patch: Record<string, string | null>) => { const q = new URLSearchParams(sp.toString()); for (const [k, v] of Object.entries(patch)) { if (v === null) q.delete(k); else q.set(k, v); } router.replace(`${path}?${q.toString()}`, { scroll: false }); };
  const orig = view && motor ? projectPassport(view, motor, { leaseOk: mode === "current", unavailableReason: gateReason || gate.detail }) : null;
  const lifeC = useMotorResourceChecked<Lifecycle>("lifecycle", motor), life = lifeC.res;
  const provC = useMotorResourceChecked<ProvenanceRow[]>("provenance", motor), prov = provC.res;
  if (!motor) return null;
  const u = unitOf(s, motor)!, d = currentOf(s, motor);
  const comps = s.components.filter((c) => c.unitId === motor);
  const lin = s.lineage.filter((l) => l.unitId === motor);
  const sh = u.shipment;
  return (
    <div className="pp">
      <h1>Product passport · {u.motorSerial}</h1>
      <p className="lede">What the ledger records about this motor. It is a record of claims, not a certificate: nothing here is a compliance, quality or safety attestation.</p>
      <div className="tabs" role="tablist" aria-label="Passport views">
        {([["overview", "Overview"], ["evidence", "Evidence"], ["timeline", "Timeline"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setQ({ tab: k === "overview" ? null : k, evidence: null })}>{l}</button>)}
      </div>
      {tab !== "overview" && (orig && orig.found ? (tab === "evidence" ? <EvidenceTab passport={orig} evidenceId={evidenceId} select={(id) => setQ({ tab: "evidence", evidence: id })} /> : <TimelineTab passport={orig} select={(id) => setQ({ tab: "evidence", evidence: id })} />)
        : <p className="banner bad" role="alert">The passport projection is not available for {motor}.</p>)}
      {tab === "overview" && <>
      <div className="grid g2">
        <div className="card"><h2>Identity</h2>
          <dl className="kv"><dt>Motor serial</dt><dd className="mono">{u.motorSerial}</dd><dt>Record</dt><dd>{val(u.title)}</dd><dt>Family label</dt><dd>{val(u.family)}</dd><dt>Description</dt><dd>{val(u.description)}</dd><dt>Data kind</dt><dd className="mono">{val(u.fixtureSet)}</dd><dt>Ledger events</dt><dd>{val(u.eventCount)}</dd></dl>
        </div>
        <div className="card"><h2>Recall context</h2>
          {gate.decisionsAllowed ? <><p><FindingTag v={d?.evidenceFinding} /> <ActionTag v={d?.operationalAction} /> {s.eligibility?.[motor]?.currentReleaseEligible ? <span className="tag ok">[RELEASE ELIGIBLE]</span> : null}</p>
            <ul className="evlist">{(d?.reasonCodes ?? []).map((c) => <li key={c}><b className="mono">{c}</b><div>{explain(REASONS, c)}</div></li>)}</ul></> : <p><span className="tag bad">[WITHHELD · {gate.label}]</span> Current recall decisions are not shown while integrity is not anchored current.</p>}
          <Link className="btn ghost" href={href("/dashboard/recall")}>Full reasoning</Link>
        </div>
      </div>

      <QrLabel unitId={motor} serial={u.motorSerial} />

      <h2 style={{ marginTop: 18 }}>Components (install records)</h2>
      <div className="scroll"><table className="t"><thead><tr><th>Slot</th><th>Part</th><th>Lot</th><th>Serial</th><th>Installed</th><th>Removed</th><th>Claimed by</th></tr></thead>
        <tbody>{comps.map((c) => <tr key={c.componentId}><td>{c.slot}</td><td>{val(c.part)}</td><td className="mono">{val(c.lot)}{(s.recall.affectedLots ?? []).includes(c.lot ?? "") && <span className="tag AFFECTED" style={{ marginLeft: 6 }}>recalled</span>}</td><td className="mono">{val(c.serial)}</td><td>{fmt(c.installedAt)}</td><td>{c.removedAt ? fmt(c.removedAt) : <span className="na">not removed</span>}</td><td>{val(c.claimedBy)}</td></tr>)}</tbody></table></div>

      <h2 style={{ marginTop: 18 }}>Material lineage (supplier claims)</h2>
      <div className="scroll"><table className="t"><thead><tr><th>Raw material lot</th><th>Supplier</th><th>Bearing lot</th><th>Serial</th><th>Material event</th><th>Assurance</th></tr></thead>
        <tbody>{lin.map((l) => <tr key={l.manufacturingEventId}><td className="mono">{val(l.rawMaterialLot)}</td><td>{val(l.supplierName)}</td><td className="mono">{val(l.lot)}</td><td className="mono">{val(l.serial)}</td><td className="mono" style={{ wordBreak: "break-all" }}>{val(l.materialEventId)}</td><td className="mono">{val(l.provenanceAssurance)}</td></tr>)}</tbody></table></div>
      <p className="note">Ledger integrity does not verify supplier identity, physical origin or quantities.</p>

      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card"><h2>Shipment (claim)</h2>
          {sh ? <dl className="kv"><dt>Shipment</dt><dd className="mono">{sh.shipmentId}</dd><dt>Customer</dt><dd>{val(sh.customer)}</dd><dt>Destination</dt><dd>{val(sh.destination)}</dd><dt>Shipped</dt><dd>{fmt(sh.shippedAt)}</dd><dt>Evidence event</dt><dd className="mono" style={{ wordBreak: "break-all" }}>{val(sh.evidenceEventId)}</dd><dt>Assurance</dt><dd className="mono">{val(sh.provenanceAssurance)}</dd></dl> : <p className="na">No shipment recorded.</p>}
          <p className="note">A shipment record is not a release authorization.</p></div>
        <div className="card"><h2>Not recorded by this backend</h2><ul>{NOT_RECORDED.map((x) => <li key={x}>{x}: {NA}</li>)}</ul></div>
      </div>

      <h2 style={{ marginTop: 18 }}>Lifecycle timeline</h2>
      <ResourceNote c={lifeC} what="The lifecycle history" seq={s.checkpoint?.anchoredSequence} />
      {life && <ResourceNote c={provC} what="The event-hash column" />}
      {!life ? <div className="skel" /> : !life.ok ? <p className="warn-t">Lifecycle unavailable ({String(life.status)} {life.error}).</p> :
        <div className="scroll"><table className="t"><thead><tr><th>Occurred</th><th>Event</th><th>Summary</th><th>Actor</th><th>Time source</th><th>Event hash</th></tr></thead>
          <tbody>{life.body.chronology.map((e) => { const r = prov?.ok ? prov.body.find((p) => p.id === e.eventId) : undefined; return <tr key={e.eventId}><td>{fmt(e.occurredAt)}</td><td className="mono">{humanize(e.eventType)}</td><td>{val(e.summary)}</td><td>{val(e.actorId)}</td><td className="mono">{val(e.timeSource)}</td><td className="mono">{r ? `${r.hash.slice(0, 12)}…` : NA}</td></tr>; })}</tbody></table></div>}
      </>}
    </div>
  );
}

/** Route-only QR: the passport page address for this motor. It encodes no verdict, hash, customer or signature, and it is a link, not proof of authenticity. */
function QrLabel({ unitId, serial }: { unitId: string; serial: string }) {
  const [origin, setOrigin] = useState("");
  useEffect(() => { setOrigin(window.location.origin); }, []);
  const valid = UNIT_ID_PATTERN.test(unitId);
  const url = origin && valid ? `${origin}/dashboard/passport?motor=${encodeURIComponent(unitId)}` : "";
  const svg = useMemo(() => (url ? qrSvgPath(qrMatrix(url)) : null), [url]);
  const local = /^(localhost|127\.|\[::1\]|::1)/.test(origin.replace(/^https?:\/\//, ""));
  return (
    <section className="card" style={{ marginTop: 14 }} aria-label={`QR label for ${unitId}`} data-testid="qr-card">
      <h2>QR label</h2>
      {!valid ? <p className="warn-t">Invalid motor identifier; no QR is generated.</p> : !svg ? <div className="skel" style={{ width: 160 }} /> : (
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-start" }}>
          <figure style={{ margin: 0, textAlign: "center" }}>
            <svg viewBox={svg.viewBox} width={176} height={176} role="img" aria-label={`QR code linking to the passport page for ${unitId}`} shapeRendering="crispEdges" data-testid="qr-svg" style={{ background: "#fff", border: "1px solid var(--line)" }}><path d={svg.path} fill="#000" /></svg>
            <figcaption className="mono" style={{ marginTop: 6, fontSize: 14, fontWeight: 600 }} data-testid="qr-id">{serial}</figcaption>
          </figure>
          <div style={{ flex: 1, minWidth: 240 }}>
            <dl className="kv"><dt>Encodes</dt><dd><code data-testid="qr-url" style={{ overflowWrap: "anywhere" }}>{url}</code></dd><dt>Destination</dt><dd><Link className="btn" href={`/dashboard/passport?motor=${encodeURIComponent(unitId)}`} data-testid="qr-open">Open digital product passport</Link> <button className="btn ghost" type="button" onClick={() => window.print()}>Print label</button></dd></dl>
            {local && <p className="note" data-testid="qr-local">Local demo address. This QR only works on the machine or network that serves this preview; it is not a public link.</p>}
            <p className="note">Synthetic demonstration passport. A QR code is a link, not proof of authenticity: anyone can print a code for any serial, it does not bind to the physical motor and cannot prevent cloning. It carries no certification, verification, recall verdict or customer data.</p>
          </div>
        </div>
      )}
    </section>
  );
}
