import { fmtTime, genealogyFor } from "../domain/derive";
import type { RecallSnapshot } from "../domain/types";

const COLS = { lot: 10, comp: 250, motor: 500, ship: 730 };
const W = 940;
const ROW = 70;

function clip(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** Supplier lot -> component -> motor -> shipment. Built from install records; shipment is a synthetic overlay. */
export function GenealogyGraph({ snap, unitId }: { snap: RecallSnapshot; unitId: string }) {
  const g = genealogyFor(snap, unitId);
  if (!g) return <p className="warn" role="alert">No genealogy for {unitId}.</p>;
  const { lots, components, unit } = g;
  if (components.length === 0) return <p className="muted">No component install records for this motor.</p>;

  const lotRows = Math.max(lots.length, 1);
  const rows = Math.max(components.length, lotRows);
  const H = rows * ROW + 50;
  const lotY = (id: string) => 50 + lots.findIndex((l) => l.lotId === id) * ROW * (components.length / lotRows);
  const compY = (i: number) => 50 + i * ROW;
  const motorY = 50 + ((rows - 1) * ROW) / 2;

  return (
    <div>
      <div className="graph-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="gen-title gen-desc" className="graph" style={{ minWidth: 760 }}>
          <title id="gen-title">Genealogy of {unit.unitId}</title>
          <desc id="gen-desc">
            {components.length} component install records link supplier lots to motor {unit.motorSerial}
            {unit.shipment ? ` and synthetic shipment ${unit.shipment.shipmentId}` : ", which has no shipment"}.
          </desc>
          {(["Supplier lot", "Component install", "Motor", "Shipment (synthetic overlay)"] as const).map((t, i) => (
            <text key={t} x={[COLS.lot, COLS.comp, COLS.motor, COLS.ship][i]} y={24} className="g-head">{t}</text>
          ))}

          {components.map((c, i) => {
            const y = compY(i);
            return (
              <g key={`e-${c.componentId}`}>
                {c.lot && <line x1={COLS.lot + 190} y1={lotY(c.lot) + 24} x2={COLS.comp} y2={y + 24} className="g-edge" />}
                <line x1={COLS.comp + 200} y1={y + 24} x2={COLS.motor} y2={motorY + 28} className={`g-edge ${c.removedAt ? "g-removed" : ""}`} />
              </g>
            );
          })}
          <line x1={COLS.motor + 190} y1={motorY + 28} x2={COLS.ship} y2={motorY + 28} className="g-edge g-synthetic" />

          {lots.map((l) => {
            const y = lotY(l.lotId);
            return (
              <g key={l.lotId} transform={`translate(${COLS.lot},${y})`}>
                <rect width={190} height={48} rx={4} className={`g-node ${l.affected ? "g-affected" : ""}`} />
                <text x={8} y={20} className="g-title">Lot {l.lotId}{l.affected ? " ▲" : ""}</text>
                <text x={8} y={38} className="g-sub">{l.affected ? "Recalled" : "Not recalled"} · {clip(l.supplier ?? "supplier unknown", 34)}</text>
              </g>
            );
          })}

          {components.map((c, i) => (
            <g key={c.componentId} transform={`translate(${COLS.comp},${compY(i)})`}>
              <rect width={200} height={48} rx={4} className={`g-node ${c.removedAt || c.supersededBy ? "g-dashed" : ""}`} />
              <text x={8} y={20} className="g-title">Slot {c.slot} · {c.part ?? "part ?"}</text>
              <text x={8} y={38} className="g-sub">
                {c.supersededBy ? "superseded record" : c.removedAt ? `removed ${c.removedAt.slice(0, 10)}` : `installed ${c.installedAt.slice(0, 10)}`}
              </text>
            </g>
          ))}

          <g transform={`translate(${COLS.motor},${motorY})`}>
            <rect width={190} height={56} rx={4} className="g-node g-motor" />
            <text x={8} y={22} className="g-title">Motor {unit.motorSerial}</text>
            <text x={8} y={42} className="g-sub">{unit.unitId}</text>
          </g>

          <g transform={`translate(${COLS.ship},${motorY})`}>
            <rect width={200} height={56} rx={4} className="g-node g-dashed g-synthetic" />
            {unit.shipment ? (
              <>
                <text x={8} y={22} className="g-title">{unit.shipment.shipmentId} · {unit.shipment.shippedAt.slice(0, 10)}</text>
                <text x={8} y={42} className="g-sub">{clip(unit.shipment.customer, 34)}</text>
              </>
            ) : (
              <text x={8} y={32} className="g-sub">Not shipped</text>
            )}
          </g>
        </svg>
      </div>
      <p className="muted">
        Dashed outlines are removed or superseded install records, or the synthetic shipment overlay. The graph shows what records claim; it does not decide exposure.
        The decision comes from the engine&apos;s slot reconciliation.
      </p>
      <details>
        <summary>Genealogy as a table</summary>
        <table className="grid compact">
          <caption className="sr-only">Component install records for {unit.unitId}</caption>
          <thead><tr><th scope="col">Slot</th><th scope="col">Part</th><th scope="col">Lot</th><th scope="col">Serial</th><th scope="col">Installed</th><th scope="col">Removed</th><th scope="col">Note</th></tr></thead>
          <tbody>
            {components.map((c) => (
              <tr key={c.componentId}>
                <td>{c.slot}</td><td>{c.part ?? "?"}</td><td>{c.lot ?? "?"}</td><td>{c.serial ?? "none"}</td>
                <td>{fmtTime(c.installedAt)}</td><td>{c.removedAt ? fmtTime(c.removedAt) : "not removed"}</td>
                <td>{c.supersededBy ? `Superseded by ${c.supersededBy}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
