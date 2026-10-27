"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { GateTracker, SEGREGATED_REASON } from "@/orig/contract/gate";
import { isGated, type PageView } from "@/orig/contract/gated";
import { assess, epochOf, type Consistency } from "./consistency";
import type { Snapshot } from "./types";

/** One measured GET. `ms` = browser time until the JSON body was read; `headersMs` = browser time until response headers arrived. Both are client-observed. */
export type Timing = { id: number; label: string; path: string; status: number | "NETWORK_ERROR"; ok: boolean; ms: number; headersMs: number; bytes: number; serverTiming: string | null; at: string };
export type Fetched<T> = { ok: true; body: T; status: number } | { ok: false; status: number | "NETWORK_ERROR"; error: string; state?: string };

type Status = number | "NETWORK_ERROR" | "WITHHELD";
type SnapState = { phase: "loading" } | { phase: "ready"; snap: Snapshot } | { phase: "error"; status: Status; error: string; state?: string };
export type Gate = { decisionsAllowed: boolean; state: string; label: string; detail: string };

type Ctx = {
  /** Decisions and eligibility are removed from this snapshot whenever the original gate is not CURRENT with a live lease. */
  snap: SnapState; gate: Gate; timings: Timing[];
  /** The original branded view (GatedSnapshot or HistoricalView) behind `snap`; null while loading or withdrawn. */
  view: PageView | null; mode: "current" | "noncurrent"; gateReason: string;
  reload: () => void;
  /** Fresh authoritative read for export: one new GET /api/snapshot through the same strict gate. Never reuses the cached view. */
  verifyNow: () => Promise<Verified>;
  get: <T,>(label: string, path: string) => Promise<Fetched<T>>;
  /** Raw status + body, for the shared gate. Throws on a network error. */
  getRaw: (label: string, path: string, log?: boolean) => Promise<{ status: number; body: unknown }>;
};
export type Verified = { ok: true; snap: Snapshot; allowed: boolean; state: string; label: string; detail: string; verifiedAt: string } | { ok: false; state: string; error: string };
const DataCtx = createContext<Ctx | null>(null);
export const useData = () => { const c = useContext(DataCtx); if (!c) throw new Error("DataProvider missing"); return c; };

export function DataProvider({ children }: { children: React.ReactNode }) {
  const [timings, setTimings] = useState<Timing[]>([]);
  const seq = useRef(0);

  const get = useCallback(async <T,>(label: string, path: string): Promise<Fetched<T>> => {
    const id = ++seq.current;
    const t0 = performance.now();
    let headersMs = 0, bytes = 0, status: number | "NETWORK_ERROR" = "NETWORK_ERROR", serverTiming: string | null = null, result: Fetched<T>;
    try {
      const res = await fetch(path, { method: "GET", cache: "no-store" });
      headersMs = performance.now() - t0; status = res.status; serverTiming = res.headers.get("server-timing");
      const text = await res.text(); bytes = text.length;
      let parsed: unknown = null; try { parsed = JSON.parse(text); } catch { /* non-JSON body */ }
      if (res.ok && parsed !== null) result = { ok: true, body: parsed as T, status: res.status };
      else { const b = (parsed ?? {}) as { error?: string; state?: string }; result = { ok: false, status: res.status, error: b.error ?? `HTTP ${res.status}`, state: b.state }; }
    } catch {
      result = { ok: false, status: "NETWORK_ERROR", error: "The backend could not be reached." };
    }
    const ms = performance.now() - t0;
    setTimings((p) => [{ id, label, path, status, ok: result.ok, ms, headersMs, bytes, serverTiming, at: new Date().toISOString() }, ...p].slice(0, 80));
    return result;
  }, []);

  const getRaw = useCallback(async (label: string, path: string, log = true) => {
    const id = ++seq.current;
    const t0 = performance.now();
    let status: number | "NETWORK_ERROR" = "NETWORK_ERROR", headersMs = 0, bytes = 0, serverTiming: string | null = null;
    try {
      const res = await fetch(path, { method: "GET", cache: "no-store" });
      headersMs = performance.now() - t0; status = res.status; serverTiming = res.headers.get("server-timing");
      const text = await res.text(); bytes = text.length;
      let body: unknown = null; try { body = JSON.parse(text); } catch { /* non-JSON body */ }
      if (log) { const ms = performance.now() - t0; setTimings((p) => [{ id, label, path, status, ok: res.ok, ms, headersMs, bytes, serverTiming, at: new Date().toISOString() }, ...p].slice(0, 80)); }
      return { status: res.status, body };
    } catch (e) {
      if (log) setTimings((p) => [{ id, label, path, status: "NETWORK_ERROR" as const, ok: false, ms: performance.now() - t0, headersMs, bytes, serverTiming, at: new Date().toISOString() }, ...p].slice(0, 80));
      throw e;
    }
  }, []);

  const verifyRef = useRef<() => Promise<Verified>>(async () => ({ ok: false, state: "LOADING", error: "Not ready." }));
  const verifyNow = useCallback(() => verifyRef.current(), []);

  // ---- the ORIGINAL strict gate (src/orig/contract/gate.ts) drives every view: strict metadata checks, regression detection and the short verification lease.
  const tracker = useRef(new GateTracker());
  const [raw, setRaw] = useState<{ phase: "loading" } | { phase: "error"; status: Status; error: string; state?: string } | { phase: "ready"; view: PageView; snap: Snapshot; current: boolean; leaseOk: boolean; reason: string; cause: string }>({ phase: "loading" });
  const [tick, setTick] = useState(0);
  verifyRef.current = async () => {
    let res;
    try { res = await getRaw("Snapshot (export revalidation)", "/api/snapshot"); } catch { return { ok: false, state: "TRANSPORT", error: "The backend could not be reached." }; }
    const g = tracker.current.evaluate(res);
    if (g.kind === "WITHHELD") return { ok: false, state: g.cause, error: g.reason };
    const body = res.body as Snapshot, verifiedAt = new Date().toISOString();
    if (g.kind === "CURRENT" && g.leaseMs > 0 && isGated(g.view)) return { ok: true, snap: body, allowed: true, state: "ANCHORED_CURRENT", label: "Anchored current", detail: "Verified by the original strict gate at export time.", verifiedAt };
    // Not trusted: the same stripping the live view applies, so no decision can reach the document.
    const cause = g.kind === "SEGREGATED" ? g.cause : "LEASE_EXPIRED";
    return { ok: true, snap: { ...body, decisions: {}, eligibility: undefined, comparison: undefined }, allowed: false, state: cause === "PREFIX_ONLY" ? "ANCHORED_PREFIX_ONLY" : cause === "UNANCHORED" ? "UNANCHORED" : "LEASE_EXPIRED", label: cause === "PREFIX_ONLY" ? "Anchored prefix only" : cause === "UNANCHORED" ? "Unanchored" : "Verification lease expired", detail: g.kind === "SEGREGATED" ? g.reason : "The verification lease had no time left.", verifiedAt };
  };
  const reload = useCallback(() => { setRaw({ phase: "loading" }); setTick((n) => n + 1); }, []);

  useEffect(() => {
    let alive = true, inFlight = false, first = true;
    let lease: ReturnType<typeof setTimeout> | undefined;
    const expire = () => setRaw((p) => (p.phase === "ready" ? { ...p, leaseOk: false } : p));
    const refresh = async () => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        let res;
        try { res = await getRaw(first ? "Snapshot" : "Snapshot (gate poll)", "/api/snapshot", first); first = false; }
        catch { if (alive) { clearTimeout(lease); const g = tracker.current.transport() as { reason: string }; setRaw({ phase: "error", status: "NETWORK_ERROR", error: g.reason, state: "TRANSPORT" }); } return; }
        if (!alive) return;
        const gate = tracker.current.evaluate(res);
        clearTimeout(lease);
        if (gate.kind === "WITHHELD") { setRaw({ phase: "error", status: "WITHHELD", error: gate.reason, state: gate.cause }); return; }
        const current = gate.kind === "CURRENT";
        setRaw({ phase: "ready", view: gate.view, snap: res.body as Snapshot, current, leaseOk: current, reason: gate.kind === "SEGREGATED" ? gate.reason : "", cause: gate.kind === "SEGREGATED" ? gate.cause : "CURRENT" });
        if (current) lease = setTimeout(expire, Math.max(0, gate.leaseMs));
      } finally { inFlight = false; }
    };
    const onVisibility = () => { clearTimeout(lease); expire(); if (!document.hidden) void refresh(); };
    void refresh();
    const timer = setInterval(refresh, 2000);
    document.addEventListener("visibilitychange", onVisibility);
    return () => { alive = false; clearInterval(timer); clearTimeout(lease); document.removeEventListener("visibilitychange", onVisibility); };
  }, [getRaw, tick]);

  const trusted = raw.phase === "ready" && raw.current && raw.leaseOk && isGated(raw.view);
  const snap = useMemo<SnapState>(() => {
    if (raw.phase !== "ready") return raw;
    // Not trusted (prefix-only, unanchored, or lease expired): no decision or eligibility reaches any view.
    return { phase: "ready", snap: trusted ? raw.snap : { ...raw.snap, decisions: {}, eligibility: undefined, comparison: undefined } };
  }, [raw, trusted]);
  const gate = useMemo<Gate>(() => {
    if (raw.phase === "loading") return { decisionsAllowed: false, state: "LOADING", label: "Loading", detail: "Reading the backend." };
    if (raw.phase === "error") return { decisionsAllowed: false, state: raw.state ?? "UNAVAILABLE", label: "Backend unavailable or unverified", detail: "Everything is withdrawn: nothing from an earlier snapshot is shown and no fallback is used." };
    if (trusted) return { decisionsAllowed: true, state: "ANCHORED_CURRENT", label: "Anchored current", detail: "Verified by the original strict gate; the verification lease is live and refreshes every 2 s." };
    if (raw.current) return { decisionsAllowed: false, state: "LEASE_EXPIRED", label: "Verification lease expired", detail: "Decisions and release eligibility are withdrawn until a new verified snapshot arrives. Recorded facts remain, marked not current." };
    return { decisionsAllowed: false, state: raw.cause === "PREFIX_ONLY" ? "ANCHORED_PREFIX_ONLY" : "UNANCHORED", label: raw.cause === "PREFIX_ONLY" ? "Anchored prefix only" : "Unanchored", detail: SEGREGATED_REASON[raw.cause as "PREFIX_ONLY" | "UNANCHORED"] };
  }, [raw, trusted]);
  const view = raw.phase === "ready" ? raw.view : null;
  const mode: "current" | "noncurrent" = trusted ? "current" : "noncurrent";
  const gateReason = raw.phase === "ready" ? raw.reason : raw.phase === "error" ? raw.error : "";
  return <DataCtx.Provider value={{ snap, gate, timings, reload, verifyNow, get, getRaw, view, mode, gateReason }}>{children}</DataCtx.Provider>;
}

export type MotorResource<T> = { res: Fetched<T> | null; consistency: Consistency | "PENDING"; reason: string };

/**
 * Lazy per-motor resource bound to the verified snapshot. The request epoch is the snapshot's archive, audit sequence, head hash and checkpoint:
 * when it changes (new evidence, another archive, prefix-only, withdrawal) the cached resource is dropped and refetched, and a response that
 * belongs to an earlier epoch is discarded. A resource is shown as CURRENT only when its own metadata matches the snapshot (see consistency.ts);
 * one that cannot be compared is UNVERIFIED, and one that contradicts the snapshot is withheld (MISMATCH).
 */
export function useMotorResourceChecked<T>(kind: "lifecycle" | "provenance" | "decisions", motor: string | null): MotorResource<T> {
  const { get, snap, mode } = useData();
  const s = snap.phase === "ready" ? snap.snap : null;
  const epoch = epochOf(s);
  const key = motor && epoch ? `${epoch}#${kind}:${motor}` : "";
  const [state, setState] = useState<{ key: string; res: Fetched<T> | null }>({ key: "", res: null });
  useEffect(() => {
    if (!key || !motor) { setState((p) => (p.key ? { key: "", res: null } : p)); return; }
    let live = true;
    get<T>(`${kind[0].toUpperCase()}${kind.slice(1)} ${motor}`, `/api/motors/${encodeURIComponent(motor)}/${kind}`).then((r) => { if (live) setState({ key, res: r }); });
    return () => { live = false; };
  }, [get, kind, motor, key]);
  const res = key && state.key === key ? state.res : null;
  if (!res || !s || !motor) return { res: null, consistency: "PENDING", reason: "" };
  if (!res.ok) return { res, consistency: "UNVERIFIED", reason: "the backend returned an error" };
  const v = assess(kind, res.body, s, motor, mode === "current");
  return v.consistency === "MISMATCH" ? { res: null, consistency: "MISMATCH", reason: v.reason } : { res, consistency: v.consistency, reason: v.reason };
}

/** Same resource without the label: null while loading, withdrawn or inconsistent with the snapshot. */
export function useMotorResource<T>(kind: "lifecycle" | "provenance" | "decisions", motor: string | null) {
  return useMotorResourceChecked<T>(kind, motor).res;
}
