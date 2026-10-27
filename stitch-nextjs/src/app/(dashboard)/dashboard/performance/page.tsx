"use client";

import { useEffect, useState } from "react";
import { useData, type Timing } from "@/dash/data";
import { NA, fmt, useMotor } from "@/dash/ui";

const f = (n: number) => `${n.toFixed(1)} ms`;
const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

export default function PerformancePage() {
  const { snap, timings, get, gate } = useData();
  const s = snap.phase === "ready" ? snap.snap : undefined;
  const [motor] = useMotor(s);
  const [busy, setBusy] = useState(false);
  const [nav, setNav] = useState<{ ttfb: number; dcl: number; load: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { const e = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined; if (e) setNav({ ttfb: e.responseStart - e.startTime, dcl: e.domContentLoadedEventEnd - e.startTime, load: e.loadEventEnd > 0 ? e.loadEventEnd - e.startTime : 0 }); }, []);

  const remeasure = async () => {
    if (!motor) return; setBusy(true);
    for (let i = 0; i < 5; i++) {
      await get("Snapshot (re-measure)", "/api/snapshot");
      await get(`Decisions ${motor} (re-measure)`, `/api/motors/${motor}/decisions`);
      await get(`Lifecycle ${motor} (re-measure)`, `/api/motors/${motor}/lifecycle`);
    }
    setBusy(false);
  };
  const groups = new Map<string, Timing[]>();
  for (const t of timings) { const k = t.label.replace(/ \(re-measure\)$/, ""); groups.set(k, [...(groups.get(k) ?? []), t]); }
  const age = s?.freshness?.verifiedAt ? Math.max(0, (now - Date.parse(s.freshness.verifiedAt)) / 1000) : null;
  const anyServerTiming = timings.some((t) => t.serverTiming);

  return (
    <div className="pp">
      <h1>Performance &amp; integrity</h1>
      <p className="lede">Request latency measured in this browser. Nothing here is a benchmark, an estimate or a figure supplied by the backend.</p>
      <div className="banner"><div><b>How to read these numbers.</b> <span className="tag info">[CLIENT-OBSERVED]</span> Each value is the time this browser waited for a GET through the Next.js proxy to the backend and back, taken with <code>performance.now()</code>. <span className="tag plain">[BACKEND-REPORTED]</span> {anyServerTiming ? "The backend sent a Server-Timing header; it is shown per request below." : "The backend does not send a Server-Timing header on these routes, so its own processing time is not available and is not guessed."}</div></div>

      <div style={{ margin: "0 0 12px" }}><button className="btn" onClick={remeasure} disabled={busy || !motor}>{busy ? "Measuring…" : `Re-measure (15 GET requests for ${motor ?? "…"})`}</button> <span className="na">Read-only: snapshot, decisions and lifecycle, five rounds each.</span></div>

      <div className="scroll"><table className="t"><thead><tr><th>Request</th><th>Samples</th><th>Median (client-observed)</th><th>Min</th><th>Max</th><th>Last status</th><th>Last response size</th></tr></thead>
        <tbody>{[...groups].map(([k, v]) => { const ms = v.map((x) => x.ms); return <tr key={k}><td>{k}</td><td>{v.length}</td><td className="mono">{f(median(ms))}</td><td className="mono">{f(Math.min(...ms))}</td><td className="mono">{f(Math.max(...ms))}</td><td><span className={`tag ${v[0].ok ? "ok" : "bad"}`}>{String(v[0].status)}</span></td><td className="mono">{(v[0].bytes / 1024).toFixed(1)} KB</td></tr>; })}
          {groups.size === 0 && <tr><td colSpan={7} className="na">No requests measured yet.</td></tr>}</tbody></table></div>

      <h2 style={{ marginTop: 18 }}>Every request in this session (newest first)</h2>
      <div className="scroll"><table className="t"><thead><tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th><th>Headers received</th><th>Body read (total)</th><th>Server-Timing</th></tr></thead>
        <tbody>{timings.slice(0, 25).map((t) => <tr key={t.id}><td className="mono">{t.at.slice(11, 19)}</td><td className="mono">GET</td><td className="mono">{t.path}</td><td><span className={`tag ${t.ok ? "ok" : "bad"}`}>{String(t.status)}</span></td><td className="mono">{f(t.headersMs)}</td><td className="mono">{f(t.ms)}</td><td className="mono">{t.serverTiming ?? "not reported"}</td></tr>)}</tbody></table></div>

      <div className="grid g2" style={{ marginTop: 18 }}>
        <div className="card"><h2>This page load (client-observed)</h2>
          {nav ? <dl className="kv"><dt>First byte</dt><dd className="mono">{f(nav.ttfb)}</dd><dt>DOM content loaded</dt><dd className="mono">{f(nav.dcl)}</dd><dt>Load event</dt><dd className="mono">{nav.load ? f(nav.load) : "not finished when read"}</dd></dl> : <p className="na">Navigation timing unavailable.</p>}
          <p className="note">Measured on this configured local synthetic ledger. It says nothing about production scale.</p></div>
        <div className="card"><h2>Integrity state (from the backend)</h2>
          {s ? <dl className="kv"><dt>Checkpoint</dt><dd><span className="tag plain">[{s.checkpoint?.state ?? "UNKNOWN"}]</span> {gate.label}</dd><dt>Gate</dt><dd><span className={`tag ${gate.decisionsAllowed ? "ok" : "bad"}`}>[{gate.state}]</span> <span className="na">original strict gate; lease refreshed every 2 s</span></dd><dt>Anchored sequence</dt><dd>{s.checkpoint?.anchoredSequence ?? NA}</dd><dt>Checkpoint required</dt><dd>{String(s.checkpoint?.checkpointRequired ?? "unknown")}</dd><dt>Freshness</dt><dd className="mono">{s.freshness?.status ?? NA}</dd><dt>Last verified</dt><dd>{fmt(s.freshness?.verifiedAt)}{age !== null && <span className="na"> · {age.toFixed(0)} s ago by this browser&apos;s clock (backend allows {s.freshness?.maxAgeSeconds ?? "?"} s)</span>}</dd><dt>Ledger head hash</dt><dd className="mono" style={{ wordBreak: "break-all" }}>{s.freshness?.headHash ?? NA}</dd></dl> : <p className="na">Unavailable.</p>}
          <p className="note">The checkpoint is a self-exported demo anchor held on the same machine. It detects change since export; it is not independent custody.</p></div>
      </div>
    </div>
  );
}
