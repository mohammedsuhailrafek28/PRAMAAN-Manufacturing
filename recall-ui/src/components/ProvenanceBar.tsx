import { fmtTime } from "../domain/derive";
import { POLICY_LABEL } from "../domain/derive";
import type { RecallSnapshot } from "../domain/types";

export function ProvenanceBar({ snap, policyId, onPolicy, sourceLabel }: {
  snap: RecallSnapshot;
  policyId: string;
  onPolicy: (p: string) => void;
  sourceLabel: string;
}) {
  const p = snap.provenance;
  const live = p.dataKind === "LIVE_LEDGER_SYNTHETIC";
  return (
    <section className="provenance" aria-label="Data provenance">
      <div className="prov-row">
        <span className="tag synthetic">{live ? "Live ledger. Synthetic manufacturing data; not production." : "Synthetic fixtures. Not real production data."}</span>
        <span>
          Decisions by recall engine <b>{p.engine.version}</b> ({p.engine.semanticsProfile}). Source: {sourceLabel}.
        </span>
      </div>
      <div className="prov-row">
        <span>
          Recall <b>{snap.recall.recallId}</b> v{snap.recall.version}, {snap.recall.announcedAt ? `announced ${fmtTime(snap.recall.announcedAt)}` : "not announced; no recall decisions issued"}. Affected part{" "}
          <b>{snap.recall.affectedPart}</b>, lots {snap.recall.affectedLots.join(", ")}, slots {snap.recall.affectedSlots.join(", ")}.
        </span>
      </div>
      {snap.lotIdentity && (
        <div className="prov-row" data-testid="lot-registry-note">
          <span>
            Lot identity registry <b>{snap.lotIdentity.registry.registryId}</b> v{snap.lotIdentity.registry.version} ({snap.lotIdentity.registry.provenance.replaceAll("_", " ").toLowerCase()}).{" "}
            Registry membership does not prove a bearing's physical identity and is not supplier authentication.
          </span>
        </div>
      )}
      <div className="prov-row">
        <label htmlFor="policy-select">Recall policy</label>
        <select id="policy-select" value={policyId} onChange={(e) => onPolicy(e.target.value)}>
          {snap.policies.map((pol) => (
            <option key={pol.policyId} value={pol.policyId}>
              {pol.policyId} · {POLICY_LABEL[pol.policyId] ?? pol.exposureBasis}
            </option>
          ))}
        </select>
        <span className="muted">{live ? "Supplier and shipment links require ledger events. Physical truth is not independently certified." : "Shipments and suppliers are a synthetic overlay, not engine output."}</span>
      </div>
    </section>
  );
}
