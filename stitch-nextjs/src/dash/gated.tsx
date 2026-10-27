"use client";

// The impact, evidence and history views read the SAME gated view as every other route (one provider, one tracker, one lease).
import type { PageView } from "@/orig/contract/gated";
import { useData } from "./data";

export type GatedState =
  | { phase: "loading" }
  | { phase: "withheld"; reason: string }
  | { phase: "ready"; view: PageView; reason: string; leaseOk: boolean };

export function useGatedView(): GatedState & { mode: "current" | "noncurrent" } {
  const { snap, view, mode, gateReason } = useData();
  if (snap.phase === "loading") return { phase: "loading", mode };
  if (snap.phase === "error" || !view) return { phase: "withheld", reason: gateReason, mode };
  return { phase: "ready", view, reason: gateReason, leaseOk: mode === "current", mode };
}
