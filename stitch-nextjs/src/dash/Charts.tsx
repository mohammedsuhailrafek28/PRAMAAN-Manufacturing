"use client";

// Overview charts. Hand-written SVG/CSS (no chart dependency is installed). Recorded-fact charts stay visible when the gate withdraws decisions; the status chart does not.
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { activity, evLabel, stepLabel, type Flat, type QcState, completeness, eventTypes, qcStates, timeSources } from "./eda";
import type { Snapshot } from "./types";

export function Def({ children }: { children: React.ReactNode }) {
  return <details className="def"><summary aria-label="Definition and limits">i</summary><div className="pop" role="note">{children}</div></details>;
}
const Badge = ({ kind, children }: { kind: "info" | "warn" | "ok" | "bad" | "plain"; children: React.ReactNode }) => <span className={`tag ${kind}`}>{children}</span>;

const FIND: Array<[string, string, string]> = [["AFFECTED", "Affected", "#ba1a1a"], ["UNRESOLVED", "Unresolved", "#d98a00"], ["EXCLUDED_WITH_EVIDENCE", "Excluded with evidence", "#17663a"]];

export function StatusChart({ counts, allowed, gateLabel, active, onPick }: { counts: Record<string, number>; allowed: boolean; gateLabel: string; active: string | null; onPick: (k: string | null) => void }) {
  const total = FIND.reduce((a, [k]) => a + (counts[k] ?? 0), 0);
  return (
    <section className="chart" aria-label="Recall status distribution" data-testid="chart-status">
      <header><h2>Recall status</h2><Badge kind={allowed ? "ok" : "bad"}>{allowed ? "CURRENT DECISION" : "WITHHELD"}</Badge>
        <Def><b>Unit:</b> motors. <b>Definition:</b> the recall engine&apos;s current evidence finding per motor, shown only while the checkpoint is anchored current and the lease is live. It is not a quality metric, and a finding does not clear or release anything by itself.</Def></header>
      {!allowed ? <div className="hatch" data-testid="status-withheld">Withheld · {gateLabel}</div> : total === 0 ? <div className="hatch">No decisions recorded</div> : (
        <>
          <div className="segbar" role="group" aria-label="Filter register by finding">
            {FIND.filter(([k]) => counts[k]).map(([k, l, c]) => <button key={k} type="button" style={{ background: c, flex: counts[k] }} aria-pressed={active === k} onClick={() => onPick(active === k ? null : k)} title={`${l}: ${counts[k]} of ${total} motors`}>{counts[k]}</button>)}
          </div>
          <div className="legend" style={{ marginTop: 8 }}>{FIND.map(([k, l, c]) => <button key={k} type="button" aria-pressed={active === null || active === k} onClick={() => onPick(active === k ? null : k)}><i style={{ background: c }} />{l} · {counts[k] ?? 0}</button>)}</div>
          {active && <small className="na">Register filtered to {active.replace(/_/g, " ").toLowerCase()}. Select again to clear.</small>}
        </>
      )}
    </section>
  );
}

const GR = { bg: "#141c24", grid: "#2a3744", ink: "#e8e0d0", dim: "#8da0b3", bronze: "#c08a52" };
const stamp = (tv: number) => new Date(tv).toISOString().slice(5, 16).replace("T", " ");
const gapText = (m: number) => { const h = Math.floor(m / 3600e3); return h >= 24 ? `${Math.floor(h / 24)} d ${h % 24} h` : `${h} h`; };

/** Single-series activity chart: ledger events per time bin, drawn only inside bursts. Gaps with no events are shown as gaps. Categories are reached by filter, hover and drill-down. */
export function TimelineChart({ s, flat, types, hidden, setHidden, current }: { s: Snapshot; flat: Flat[]; types: string[]; hidden: Set<string>; setHidden: (h: Set<string>) => void; current: boolean }) {
  const router = useRouter();
  const act = useMemo(() => activity(flat, hidden), [flat, hidden]);
  const [pin, setPin] = useState<string | null>(null);
  const [tip, setTip] = useState("");
  const [narrow, setNarrow] = useState(false);
  useEffect(() => { const mq = window.matchMedia("(max-width: 640px)"); const f = () => setNarrow(mq.matches); f(); mq.addEventListener("change", f); return () => mq.removeEventListener("change", f); }, []);
  const src = timeSources(flat);
  const visible = flat.filter((x) => !hidden.has(x.e.eventType)).length;
  // Wide screens: bursts side by side on one shared y axis. Narrow screens: one stacked panel per burst (same scale), so nothing needs horizontal scrolling.
  const W = narrow ? 360 : 880, L = 30, R = 8, TOP = 10, PH = narrow ? 84 : 150, GAP = 46, GAPV = 40, MINW = 120, PANEL = PH + 18;
  const n = act.bursts.length, avail = W - L - R - GAP * Math.max(0, n - 1);
  const spans = act.bursts.map((u) => u.b - u.a), tot = spans.reduce((p, q) => p + q, 0) || 1;
  // Equal pixels per minute across bursts, with a floor so a short burst stays legible.
  const raw = spans.map((sp) => Math.max(MINW, (avail * sp) / tot)); const k = Math.min(1, avail / (raw.reduce((p, q) => p + q, 0) || 1));
  let acc = L; const lay = act.bursts.map((u, i) => { const w = narrow ? W - L - R : raw[i] * k; const r = { u, x0: narrow ? L : acc, w, oy: narrow ? TOP + i * (PANEL + GAPV) : TOP }; acc += w + GAP; return r; });
  const H = narrow ? TOP + n * PANEL + Math.max(0, n - 1) * GAPV + 6 : TOP + PH + 24;
  const y = (c: number, oy: number) => oy + PH - (c / act.max) * PH;
  const toggle = (tp: string) => { const nx = new Set(hidden); if (nx.has(tp)) nx.delete(tp); else nx.add(tp); setHidden(nx); };
  const breakdown = (ev: Flat[]) => { const m = new Map<string, number>(); for (const x of ev) if (!hidden.has(x.e.eventType)) m.set(x.e.eventType, (m.get(x.e.eventType) ?? 0) + 1); return [...m].map(([tp, c]) => `${evLabel(tp)} ${c}`).join(", ") || "none"; };
  const key = (bi: number, i: number) => `${bi}:${i}`;
  const pinned = pin ? (() => { const [bi, i] = pin.split(":").map(Number); return act.bursts[bi]?.bins[i]; })() : undefined;
  const yTicks = [0, Math.ceil(act.max / 2), act.max].filter((v, i, a2) => a2.indexOf(v) === i);
  return (
    <section className="chart dark wide" aria-label="Manufacturing event activity" data-testid="chart-timeline">
      <header><h2>Manufacturing event activity</h2><Badge kind="info">RECORDED CLAIMS</Badge>{!current && <Badge kind="warn">NOT CURRENT</Badge>}
        <Def><b>Unit:</b> ledger events per {stepLabel(act.step)} bin, placed by each event&apos;s claimed <i>occurredAt</i>{src.length ? <> (clock: {src.join(", ").replace(/_/g, " ").toLowerCase()}, not a trusted time source)</> : null}. The line is drawn only inside periods that have events; the gaps between them contain none and are not interpolated. {act.untimed} events without an occurredAt are not plotted. A count shows that records exist, not that the work was done correctly. Select a bin to list its events and open their evidence.</Def></header>
      <div className="legend" role="group" aria-label="Filter event types">{types.map((tp) => <button key={tp} type="button" aria-pressed={!hidden.has(tp)} onClick={() => toggle(tp)}>{evLabel(tp)}</button>)}</div>
      {act.bursts.length === 0 ? <div className="hatch">No events with a recorded time</div> : (
        <div className="scrollx"><svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }} role="group" aria-label={`Event counts per ${stepLabel(act.step)}, ${n} activity ${n === 1 ? "period" : "periods"}`}>
          <defs><pattern id="gaphatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke={GR.grid} strokeWidth="1" /></pattern></defs>
                    {lay.map(({ u, x0, w, oy }, bi) => {
            const bw = w / u.bins.length, cx = (i: number) => x0 + bw * (i + 0.5);
            const pts = u.bins.map((bn, i) => [cx(i), y(bn.count, oy)] as const);
            const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
            const area = `${line} L${pts[pts.length - 1][0].toFixed(1)} ${y(0, oy)} L${pts[0][0].toFixed(1)} ${y(0, oy)} Z`;
            return (
              <g key={bi}>
                {yTicks.map((v) => <g key={v}><line x1={narrow ? L : L} x2={x0 + w} y1={y(v, oy)} y2={y(v, oy)} stroke={GR.grid} strokeWidth={0.6} />{(narrow || bi === 0) && <text x={L - 6} y={y(v, oy) + 3} textAnchor="end" style={{ font: "10px var(--mono)", fill: GR.dim }}>{v}</text>}</g>)}
                <line x1={x0} x2={x0 + w} y1={y(0, oy)} y2={y(0, oy)} stroke={GR.dim} strokeWidth={0.8} />
                <path d={area} fill={GR.bronze} opacity={0.1} /><path d={line} fill="none" stroke={GR.bronze} strokeWidth={1.1} strokeLinejoin="round" />
                {u.bins.length === 1 && <circle cx={pts[0][0]} cy={pts[0][1]} r={2} fill={GR.bronze} />}
                {u.bins.map((bn, i) => <rect key={i} x={x0 + bw * i} y={oy} width={bw} height={PH} fill={pin === key(bi, i) ? "rgba(232,224,208,.14)" : "transparent"} stroke={pin === key(bi, i) ? GR.ink : "none"} strokeWidth={0.8} tabIndex={0} role="button" data-testid="tl-bin" data-count={bn.count}
                  aria-label={`${stamp(bn.a)} to ${stamp(bn.b).slice(6)} UTC: ${bn.count} events. ${breakdown(bn.events)}`} aria-pressed={pin === key(bi, i)} style={{ cursor: "pointer", outline: "none" }}
                  onMouseEnter={() => setTip(`${stamp(bn.a)}–${stamp(bn.b).slice(6)} UTC · ${bn.count} events · ${breakdown(bn.events)}`)} onFocus={() => setTip(`${stamp(bn.a)}–${stamp(bn.b).slice(6)} UTC · ${bn.count} events · ${breakdown(bn.events)}`)}
                  onClick={() => setPin(pin === key(bi, i) ? null : key(bi, i))} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPin(pin === key(bi, i) ? null : key(bi, i)); } }} />)}
                <text x={x0} y={oy + PH + 14} style={{ font: "10px var(--mono)", fill: GR.ink }}>{stamp(u.a)}</text>
                <text x={x0 + w} y={oy + PH + 14} textAnchor="end" style={{ font: "10px var(--mono)", fill: GR.dim }}>{stamp(u.b).slice(6)}</text>
                {bi > 0 && (() => {
                  const text = gapText(u.first - act.bursts[bi - 1].last), pv = lay[bi - 1];
                  if (narrow) { const gy = pv.oy + PH + 20, gh = GAPV - 26; return <g data-testid="tl-gap"><rect x={L} y={gy} width={W - L - R} height={Math.max(8, gh)} fill="url(#gaphatch)" /><text x={W / 2} y={gy + 11} textAnchor="middle" style={{ font: "9px var(--mono)", fill: GR.bronze, paintOrder: "stroke", stroke: GR.bg, strokeWidth: 3 }}>no events · {text}</text></g>; }
                  const gx = pv.x0 + pv.w, mid = (gx + x0) / 2;
                  return <g data-testid="tl-gap"><rect x={gx + 4} y={TOP} width={x0 - gx - 8} height={PH} fill="url(#gaphatch)" /><text x={mid} y={TOP + PH / 2 - 4} textAnchor="middle" style={{ font: "9px var(--mono)", fill: GR.bronze }}>no events</text><text x={mid} y={TOP + PH / 2 + 8} textAnchor="middle" style={{ font: "9px var(--mono)", fill: GR.bronze }}>{text}</text></g>;
                })()}
              </g>
            );
          })}
        </svg></div>
      )}
      <small className="mono" aria-live="polite" data-testid="tl-tip">{tip || `${visible} of ${flat.length} events shown · ${stepLabel(act.step)} bins · hover or focus a bin`}</small>
      {pinned && (
        <div className="binlist" data-testid="bin-list" role="region" aria-label="Events in the selected bin">
          <b className="mono">{stamp(pinned.a)}–{stamp(pinned.b).slice(6)} UTC</b>
          <ul>{pinned.events.filter((x) => !hidden.has(x.e.eventType)).map((x) => <li key={x.e.eventId}><button type="button" className="linkbtn" data-testid="bin-event" onClick={() => router.push(`/dashboard/passport?motor=${x.unitId}&tab=evidence&evidence=${encodeURIComponent(x.e.eventId)}`)}>{x.unitId} · {evLabel(x.e.eventType)}</button> <span className="mono">{x.e.occurredAt?.slice(11, 19)}</span></li>)}</ul>
        </div>
      )}
      <small className="mono" style={{ display: "block", marginTop: 6, color: GR.dim }} data-testid="tl-prov">Times are source claims, not verified · snapshot seq {s.freshness?.sequence ?? "?"} verified {s.freshness?.verifiedAt ? s.freshness.verifiedAt.slice(11, 19) + " UTC" : "unknown"} · {current ? "checkpoint current" : "not current"}</small>
      <details style={{ marginTop: 6 }}><summary className="mono" style={{ color: GR.dim, cursor: "pointer" }}>Data table</summary>
        <table className="heat" style={{ color: GR.ink }}><thead><tr><th className="r">Bin (UTC)</th><th>Events</th></tr></thead><tbody>{act.bursts.flatMap((u) => u.bins.map((bn) => <tr key={bn.a}><th className="r">{stamp(bn.a)}</th><td>{bn.count}</td></tr>))}</tbody></table></details>
    </section>
  );
}

const QC: Array<[QcState, string, string]> = [["PASS", "Recorded PASS", "#17663a"], ["FAIL", "Recorded FAIL", "#ba1a1a"], ["NO_RECORD", "No inspection record", "#9aa7b4"]];
export function QcChart({ q, active, onPick }: { q: ReturnType<typeof qcStates>; active: QcState | null; onPick: (k: QcState | null) => void }) {
  const total = q.per.length;
  return (
    <section className="chart" aria-label="Quality inspection results" data-testid="chart-qc">
      <header><h2>Quality inspection</h2><Badge kind="info">RECORDED CLAIMS</Badge>
        <Def><b>Unit:</b> motors, by their latest inspection/quality/test record that carries an explicit PASS or FAIL outcome. A motor with no such record is shown as <i>no inspection record</i>, never as a pass. <b>A QC PASS is not recall clearance:</b> it says nothing about which bearing lot is installed.</Def></header>
      {total === 0 ? <div className="hatch">No motors</div> : (
        <>
          <div className="segbar" role="group" aria-label="Filter register by inspection record">
            {QC.filter(([k]) => q[k]).map(([k, l, c]) => <button key={k} type="button" style={{ background: c, flex: q[k] }} aria-pressed={active === k} onClick={() => onPick(active === k ? null : k)} title={`${l}: ${q[k]} of ${total}`}>{q[k]}</button>)}
          </div>
          <div className="legend" style={{ marginTop: 8 }}>{QC.map(([k, l, c]) => <button key={k} type="button" aria-pressed={active === null || active === k} onClick={() => onPick(active === k ? null : k)}><i style={{ background: c }} />{l} · {q[k]}</button>)}</div>
          <small className="na" data-testid="qc-related">Not QC results: {q.related.workOrdersClosed} work orders closed · {q.related.labelReads} slot label reads ({q.related.provisionalLabelReads} provisional).</small>
        </>
      )}
    </section>
  );
}

export function Heatmap({ s, flat, hidden, setHidden }: { s: Snapshot; flat: Flat[]; hidden: Set<string>; setHidden: (h: Set<string>) => void }) {
  const router = useRouter();
  const h = useMemo(() => completeness(s, flat), [s, flat]);
  return (
    <section className="chart" aria-label="Evidence completeness heatmap" data-testid="chart-heatmap">
      <header><h2>Evidence completeness</h2><Badge kind="info">RECORDED CLAIMS</Badge>
        <Def><b>Unit:</b> ledger records per motor and event type. Empty (hatched) means no such record is in this snapshot; that is a gap in the record, not proof the step did not happen. Hashes show the record is unchanged, not that it is true. Select a cell to open that motor&apos;s evidence; select a column name to filter the timeline.</Def></header>
      <div className="scrollx"><table className="heat"><thead><tr><th className="r" /> {h.types.map((t) => <th key={t}><button type="button" aria-pressed={!hidden.has(t)} title={evLabel(t)} onClick={() => { const n = new Set(hidden); if (n.has(t)) n.delete(t); else n.add(t); setHidden(n); }}>{evLabel(t)}</button></th>)}</tr></thead>
        <tbody>{h.rows.map((r) => <tr key={r.unitId}><th className="r">{r.unitId}</th>{r.cells.map((n, i) => <td key={i}><button type="button" data-testid="heat-cell" data-count={n} aria-label={`${r.unitId}, ${evLabel(h.types[i])}: ${n} records`} title={`${r.unitId} · ${evLabel(h.types[i])}: ${n}`}
          style={n ? { background: `rgba(173,121,68,${0.2 + 0.8 * (n / h.max)})`, color: n / h.max > .55 ? "#fff" : "var(--ink)" } : { background: "repeating-linear-gradient(45deg,#eaf1f8,#eaf1f8 4px,#fff 4px,#fff 8px)", color: "var(--ink-3)" }}
          onClick={() => router.push(`/dashboard/passport?motor=${r.unitId}&tab=evidence`)}>{n || ""}</button></td>)}</tr>)}</tbody></table></div>
    </section>
  );
}

export { eventTypes, qcStates };
