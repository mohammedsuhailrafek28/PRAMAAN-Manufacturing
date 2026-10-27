"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { ACTION_TEXT, FINDING_TEXT, humanize } from "./glossary";
import { useData } from "./data";
import type { DecisionCurrent, Snapshot, Unit } from "./types";

export const NA = <span className="na">Not recorded</span>;
export const val = (v: unknown) => (v === null || v === undefined || v === "" ? NA : <>{String(v)}</>);
export const fmt = (iso?: string | null) => (iso ? iso.replace("T", " ").replace(/Z$/, " UTC") : "—");

export function FindingTag({ v }: { v?: string }) {
  if (!v) return <span className="tag plain">[NO DECISION]</span>;
  const text = FINDING_TEXT[v];
  return <span className={`tag ${v}`} title={text?.explain}>[{(text?.label ?? humanize(v)).toUpperCase()}]</span>;
}
export function ActionTag({ v }: { v?: string }) {
  if (!v) return null;
  return <span className={`tag ${v}`} title={ACTION_TEXT[v]?.explain}>[{(ACTION_TEXT[v]?.label ?? humanize(v)).toUpperCase()}]</span>;
}

/** The single decision the engine published for this motor under the active recall policy (first policy key). */
export function currentOf(snap: Snapshot, motor: string): DecisionCurrent | undefined {
  const d = snap.decisions?.[motor];
  return d ? Object.values(d)[0]?.current : undefined;
}
export const unitOf = (snap: Snapshot, motor: string): Unit | undefined => snap.units.find((u) => u.unitId === motor);

/** Selected motor lives in the URL (?motor=) so every view shows the same one. */
export function useMotor(snap?: Snapshot): [string | null, (m: string) => void, (path: string) => string] {
  const sp = useSearchParams(); const router = useRouter(); const path = usePathname();
  const fromUrl = sp.get("motor");
  const motor = fromUrl && snap?.units.some((u) => u.unitId === fromUrl) ? fromUrl : snap?.units[0]?.unitId ?? null;
  const set = useCallback((m: string) => { const q = new URLSearchParams(sp.toString()); q.set("motor", m); router.replace(`${path}?${q.toString()}`, { scroll: false }); }, [sp, router, path]);
  const href = useCallback((to: string) => (motor ? `${to}?motor=${encodeURIComponent(motor)}` : to), [motor]);
  return [motor, set, href];
}

export function GateBanner() {
  const { snap, gate, reload } = useData();
  if (snap.phase === "loading") return <div className="banner"><div className="skel" style={{ width: "100%", height: 22 }} /></div>;
  if (snap.phase === "error") return <div className="banner bad" role="alert"><div><b>Backend data unavailable</b> <span className="tag bad">[{String(snap.status)}{snap.state ? ` ${snap.state}` : ""}]</span><div>{snap.error}. Nothing is shown from memory, a cache or a sample. <button className="btn ghost" onClick={reload}>Retry read</button></div></div></div>;
  const s = snap.snap;
  return (
    <div className={`banner ${gate.decisionsAllowed ? "ok" : "bad"}`} role={gate.decisionsAllowed ? undefined : "alert"}>
      <div>
        <b>{gate.label}</b> <span className="tag plain">[{gate.state}]</span>{" "}
        <span className="tag plain">checkpoint seq {s.checkpoint?.anchoredSequence ?? "?"}</span>{" "}
        <span className="tag plain">{s.freshness?.status ?? "freshness unknown"}</span>
        <div>{gate.detail} <span className="na">Synthetic demonstration data. The checkpoint is self-exported on the same machine; it shows the ledger was not altered since export, not independent custody.</span></div>
      </div>
    </div>
  );
}

export function SideNav() {
  const path = usePathname(); const { snap } = useData();
  const [, , href] = useMotor(snap.phase === "ready" ? snap.snap : undefined);
  const items = [["/dashboard", "01", "Overview"], ["/dashboard/genealogy", "02", "Genealogy"], ["/dashboard/recall", "03", "Recall investigation"], ["/dashboard/impact", "04", "Impact graph"], ["/dashboard/evidence", "05", "Evidence"], ["/dashboard/passport", "06", "Passport"], ["/dashboard/performance", "07", "Performance & integrity"], ["/dashboard/report", "08", "Daily report"], ["/dashboard/ml-inspection", "09", "Quality Inspection"]];
  return (
    <aside className="rail">
      <Link className="brand" href="/"><b>PRAMAAN</b><span>Manufacturing intelligence</span></Link>
      <nav aria-label="Dashboard views">
        {items.map(([to, n, label]) => <Link key={to} href={href(to)} aria-current={path === to ? "page" : undefined}><i>{n}</i>{label}</Link>)}
      </nav>
      <div className="synthetic">Synthetic demo data · read-only · no commands</div>
      <Link className="back" href="/">← Landing</Link>
    </aside>
  );
}

export function MotorBar() {
  const { snap } = useData();
  const s = snap.phase === "ready" ? snap.snap : undefined;
  const [motor, setMotor] = useMotor(s);
  const { gate } = useData();
  return (
    <div className="top">
      <span className="label">Motor</span>
      <div className="motors" role="group" aria-label="Select motor">
        {s ? s.units.map((u) => { const f = gate.decisionsAllowed ? currentOf(s, u.unitId)?.evidenceFinding : undefined; return <button key={u.unitId} aria-pressed={u.unitId === motor} onClick={() => setMotor(u.unitId)}><span className={`dot ${f ?? ""}`} aria-hidden="true" />{u.unitId}</button>; }) : <span className="na">{snap.phase === "loading" ? "Loading…" : "Unavailable"}</span>}
      </div>
    </div>
  );
}
