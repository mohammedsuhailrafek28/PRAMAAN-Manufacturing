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
  return (
    <section className="provenance" aria-label="Data provenance">
      <div className="prov-row">
        <span className="tag synthetic">Synthetic fixtures. Not real production data.</span>
        <span>
          Decisions by recall engine <b>{p.engine.version}</b> ({p.engine.semanticsProfile}). Source: {sourceLabel}.
        </span>
      </div>
      <div className="prov-row">
        <span>
          Recall <b>{snap.recall.recallId}</b> v{snap.recall.version}, announced {fmtTime(snap.recall.announcedAt)}. Affected part{" "}
          <b>{snap.recall.affectedPart}</b>, lots {snap.recall.affectedLots.join(", ")}, slots {snap.recall.affectedSlots.join(", ")}.
        </span>
      </div>
      <div className="prov-row">
        <label htmlFor="policy-select">Recall policy</label>
        <select id="policy-select" value={policyId} onChange={(e) => onPolicy(e.target.value)}>
          {snap.policies.map((pol) => (
            <option key={pol.policyId} value={pol.policyId}>
              {pol.policyId} · {POLICY_LABEL[pol.policyId] ?? pol.exposureBasis}
            </option>
          ))}
        </select>
        <span className="muted">Shipments and suppliers are a synthetic overlay, not engine output.</span>
      </div>
    </section>
  );
}
