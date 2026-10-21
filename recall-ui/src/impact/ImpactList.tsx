import { useState } from "react";
import { FINDING_TEXT } from "../domain/glossary";
import { KIND_LABEL, nodeAria } from "./ImpactGraphView";
import type { GNode, ImpactGraph } from "./projection";

const ORDER: GNode["kind"][] = ["RAW_LOT", "BEARING_LOT", "MANUFACTURE", "COMPONENT", "OBSERVATION", "MOTOR", "SHIPMENT"];
const PAGE = 100;

/** Accessible equivalent of the graph: every node and what it is recorded as linked to. */
export function ImpactList({ graph, visible, selectedId, onSelect }: { graph: ImpactGraph; visible: ReadonlySet<string> | null; selectedId: string | null; onSelect: (id: string) => void }) {
  const [shown, setShown] = useState(PAGE);
  const nodes = graph.nodes.filter((n) => !visible || visible.has(n.id)).sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const links = new Map<string, string[]>();
  for (const e of graph.edges) {
    const a = byId.get(e.from), b = byId.get(e.to);
    if (!a || !b) continue;
    (links.get(a.id) ?? links.set(a.id, []).get(a.id)!).push(`→ ${b.label}`);
    (links.get(b.id) ?? links.set(b.id, []).get(b.id)!).push(`← ${a.label}`);
  }
  const rows = nodes.slice(0, shown);
  return (
    <div className="ig-list">
      <table className="grid compact responsive" data-testid="impact-list">
        <caption className="sr-only">Every record in the trace, grouped by kind, with the recorded links to neighbouring records</caption>
        <thead><tr><th>Kind</th><th>Record</th><th>Detail</th><th>Engine finding</th><th>Recorded links</th><th>Issues</th></tr></thead>
        <tbody>
          {rows.map((n) => (
            <tr key={n.id} aria-current={n.id === selectedId ? "true" : undefined} data-node-id={n.id}>
              <td data-label="Kind">{KIND_LABEL[n.kind]}</td>
              <td data-label="Record"><button type="button" className="ig-linkbtn" aria-label={`Select: ${nodeAria(n)}`} onClick={() => onSelect(n.id)}>{n.label}</button></td>
              <td data-label="Detail">{n.sublabel}{n.lifecycle === "HISTORICAL" && " · historical"}</td>
              <td data-label="Engine finding">{n.status ? FINDING_TEXT[n.status.finding]?.label ?? n.status.finding : "—"}</td>
              <td data-label="Recorded links">{(links.get(n.id) ?? []).slice(0, 6).join("; ") || "none"}{(links.get(n.id)?.length ?? 0) > 6 ? ` (+${(links.get(n.id)!.length) - 6} more)` : ""}</td>
              <td data-label="Issues">{n.issueIds.length || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {nodes.length > shown && (
        <p><button type="button" onClick={() => setShown((s) => s + PAGE)}>Show {Math.min(PAGE, nodes.length - shown)} more of {nodes.length - shown} remaining</button></p>
      )}
    </div>
  );
}
