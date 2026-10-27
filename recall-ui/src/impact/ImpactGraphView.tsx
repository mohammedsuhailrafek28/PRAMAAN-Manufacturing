import { useMemo, useRef, useState } from "react";
import { FINDING_TEXT } from "../domain/glossary";
import { layoutGraph, NODE_H, NODE_W, type Layout } from "./layout";
import type { GEdge, GNode, ImpactGraph } from "./projection";

export const KIND_LABEL: Record<GNode["kind"], string> = {
  RAW_LOT: "Raw-material claim", BEARING_LOT: "Bearing lot", MANUFACTURE: "Manufacture record", COMPONENT: "Installed component",
  MOTOR: "Motor", SHIPMENT: "Recorded shipment", OBSERVATION: "Rejected observation",
};
const STYLE_TEXT: Record<GEdge["style"], string> = {
  RECORDED: "recorded link", CONFLICT: "conflicting record", LOT_CLAIM: "lot claim without a manufacture link", UNTRUSTED_CLAIM: "untrusted claim",
};

export function nodeAria(n: GNode): string {
  const bits = [`${n.label} ${n.sublabel}`, KIND_LABEL[n.kind]];
  if (n.status) bits.push(FINDING_TEXT[n.status.finding]?.label ?? n.status.finding);
  if (n.kind === "BEARING_LOT" && n.recalled !== null) bits.push(n.recalled ? "named by the recall" : "not named by the recall");
  if (n.lifecycle === "HISTORICAL") bits.push("removed, historical");
  if (n.issueIds.length) bits.push(`${n.issueIds.length} record ${n.issueIds.length === 1 ? "issue" : "issues"}`);
  return bits.join(", ");
}

interface View { x: number; y: number; k: number }
const MIN_K = 0.25;
const MAX_K = 2.5;

function edgePath(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }): string {
  const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
  const dx = Math.max(24, (x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
}

export interface GraphViewProps {
  graph: ImpactGraph;
  visible: ReadonlySet<string> | null;
  selectedId: string | null;
  highlight: { nodeIds: Set<string>; edgeIds: Set<string> } | null;
  onSelect: (id: string) => void;
  height?: number;
}

export function ImpactGraphView({ graph, visible, selectedId, highlight, onSelect, height = 520 }: GraphViewProps) {
  const layout: Layout = useMemo(() => layoutGraph(graph, visible), [graph, visible]);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ px: number; py: number; vx: number; vy: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const nodes = graph.nodes.filter((n) => layout.pos.has(n.id));
  const edges = graph.edges.filter((e) => layout.pos.has(e.from) && layout.pos.has(e.to));

  const zoom = (f: number) => setView((v) => ({ ...v, k: Math.min(MAX_K, Math.max(MIN_K, v.k * f)) }));
  const fit = () => {
    const w = box.current?.clientWidth ?? 800;
    const k = Math.min(1, Math.max(MIN_K, (w - 16) / layout.width));
    setView({ x: 0, y: 0, k });
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    const step = 48;
    const moves: Record<string, [number, number]> = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    if (moves[e.key]) { e.preventDefault(); setView((v) => ({ ...v, x: v.x + moves[e.key][0], y: v.y + moves[e.key][1] })); }
    else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoom(1.2); }
    else if (e.key === "-") { e.preventDefault(); zoom(1 / 1.2); }
    else if (e.key === "0") { e.preventDefault(); setView({ x: 0, y: 0, k: 1 }); }
  };

  const dim = (id: string) => (highlight ? !highlight.nodeIds.has(id) : false);
  const nodeClass = (n: GNode) =>
    ["ig-node", `ig-${n.kind.toLowerCase()}`, n.status ? `ig-f-${n.status.finding}` : "", n.lifecycle === "HISTORICAL" ? "ig-hist" : "", n.issueIds.length ? "ig-issue" : "", n.id === selectedId ? "ig-selected" : "", dim(n.id) ? "ig-dim" : ""].filter(Boolean).join(" ");

  return (
    <div className="ig-wrap">
      <div className="ig-toolbar" role="toolbar" aria-label="Graph view controls">
        <button type="button" onClick={() => zoom(1.2)} aria-label="Zoom in">+</button>
        <button type="button" onClick={() => zoom(1 / 1.2)} aria-label="Zoom out">−</button>
        <button type="button" onClick={fit}>Fit width</button>
        <button type="button" onClick={() => setView({ x: 0, y: 0, k: 1 })}>Reset view</button>
        <span className="muted" aria-live="polite">Zoom {Math.round(view.k * 100)}%</span>
      </div>
      <div
        ref={box} className="ig-canvas" style={{ height }} tabIndex={0} role="group"
        aria-label="Impact graph. Arrow keys pan, plus and minus zoom, Tab moves to nodes, Enter selects a node. The list view has the same information."
        onKeyDown={onKey}
        onWheel={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1); } }}
        onPointerDown={(e) => { if ((e.target as Element).closest(".ig-node")) return; drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y }; (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); }}
        onPointerMove={(e) => { const d = drag.current; if (d) setView((v) => ({ ...v, x: d.vx + e.clientX - d.px, y: d.vy + e.clientY - d.py })); }}
        onPointerUp={() => { drag.current = null; }}
        onPointerCancel={() => { drag.current = null; }}
      >
        <svg width={layout.width * view.k + Math.max(0, view.x)} height={layout.height * view.k + Math.max(0, view.y)} role="presentation" data-testid="impact-svg">
          <defs><clipPath id="ig-clip"><rect x={0} y={0} width={NODE_W - 22} height={NODE_H} /></clipPath></defs>
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
            {layout.columns.map((c) => (
              <text key={c.title} x={c.x} y={22} className="ig-colhead">{c.title}</text>
            ))}
            {edges.map((e) => (
              <path
                key={e.id} d={edgePath(layout.pos.get(e.from)!, layout.pos.get(e.to)!)}
                className={`ig-edge ig-e-${e.style}${e.historical ? " ig-hist" : ""}${highlight && !highlight.edgeIds.has(e.id) ? " ig-dim" : ""}`}
                data-edge-kind={e.kind} data-testid="impact-edge"
              ><title>{`${STYLE_TEXT[e.style]}${e.historical ? ", historical" : ""}: ${e.basis}`}</title></path>
            ))}
            {nodes.map((n) => {
              const p = layout.pos.get(n.id)!;
              return (
                <g
                  key={n.id} className={nodeClass(n)} transform={`translate(${p.x} ${p.y})`} tabIndex={0} role="button" aria-pressed={n.id === selectedId}
                  aria-label={nodeAria(n)} data-node-id={n.id} data-kind={n.kind} data-testid="impact-node"
                  onClick={() => onSelect(n.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(n.id); } }}
                >
                  <rect width={NODE_W} height={NODE_H} rx={4} />
                  <text clipPath="url(#ig-clip)">
                    <tspan x={8} y={20} className="ig-title">{`${n.label} `}</tspan>
                    <tspan x={8} y={38} className="ig-sub">{n.sublabel}</tspan>
                  </text>
                  {n.issueIds.length > 0 && <g className="ig-flag" aria-hidden="true" transform={`translate(${NODE_W - 12} 8)`}><rect x={-1.5} y={0} width={3} height={8} /><rect x={-1.5} y={10} width={3} height={3} /></g>}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <ul className="ig-legend" aria-label="Legend">
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-RECORDED" /></svg> recorded link (ledger reference)</li>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-LOT_CLAIM" /></svg> lot claim, no manufacture link</li>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-CONFLICT" /></svg> conflicting records</li>
        <li><svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" className="ig-edge ig-e-UNTRUSTED_CLAIM" /></svg> untrusted claim</li>
        <li><span className="ig-key ig-hist-key" aria-hidden="true" /> faded: removed (historical) record</li>
        <li><span className="ig-key" aria-hidden="true">!</span> record issue (see details)</li>
      </ul>
    </div>
  );
}
