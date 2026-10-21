// Hash routes for the standalone impact-graph page: #/lot/<bearing|raw>/<lot>[/<graph|list>[/<node id>]].
// Identifiers are only ever matched exactly against the loaded snapshot and rendered as text.
import type { SelectionKind } from "./projection";

export type ViewMode = "graph" | "list";
export type Route =
  | { page: "home" }
  | { page: "lot"; kind: SelectionKind; lotId: string; view: ViewMode | null; nodeId: string | null }
  | { page: "invalid"; raw: string };

const LOT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const safe = (s: string) => s.length > 0 && s.length <= 300 && !/[\u0000-\u001f\u007f]/.test(s);

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  let parts: string[];
  try {
    parts = raw.split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return { page: "invalid", raw: raw.slice(0, 80) };
  }
  if (parts.length === 0) return { page: "home" };
  if (parts[0] === "lot" && parts.length >= 3 && parts.length <= 5 && (parts[1] === "bearing" || parts[1] === "raw") && LOT.test(parts[2])) {
    const view = parts[3] === undefined ? null : parts[3] === "graph" || parts[3] === "list" ? parts[3] : "bad";
    if (view === "bad") return { page: "invalid", raw: raw.slice(0, 80) };
    const nodeId = parts[4] ?? null;
    if (nodeId !== null && !safe(nodeId)) return { page: "invalid", raw: raw.slice(0, 80) };
    return { page: "lot", kind: parts[1] === "raw" ? "RAW_LOT" : "BEARING_LOT", lotId: parts[2], view, nodeId };
  }
  return { page: "invalid", raw: raw.slice(0, 80) };
}

export const lotHref = (kind: SelectionKind, lotId: string, view?: ViewMode | null, nodeId?: string | null) =>
  `#/lot/${kind === "RAW_LOT" ? "raw" : "bearing"}/${encodeURIComponent(lotId)}${view ? `/${view}` : ""}${view && nodeId ? `/${encodeURIComponent(nodeId)}` : ""}`;

/** Existing console views, where they already exist. */
export const consoleUnitHref = (unitId: string, tab: "decision" | "genealogy" | "events" = "decision") => `./index.html#/unit/${encodeURIComponent(unitId)}/${tab}`;
