// Hash routes for the standalone investigation page. Identifiers are only ever looked up by exact
// match in the loaded snapshot and rendered as text.
export const UNIT_ID = /^MTR-[A-Z0-9-]{3,30}$/;
export const CLUSTER_ID = /^g-[0-9a-f]{14}x*$/;

export type Route =
  | { page: "overview" }
  | { page: "cluster"; clusterId: string }
  | { page: "evidence"; unitId: string; eventId: string }
  | { page: "invalid"; raw: string };

const safe = (s: string) => s.length > 0 && s.length <= 200 && !/[\u0000-\u001f\u007f]/.test(s);

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  let parts: string[];
  try {
    parts = raw.split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return { page: "invalid", raw: raw.slice(0, 80) };
  }
  if (parts.length === 0) return { page: "overview" };
  if (parts[0] === "cluster" && parts.length === 2 && CLUSTER_ID.test(parts[1])) return { page: "cluster", clusterId: parts[1] };
  if (parts[0] === "evidence" && parts.length === 3 && UNIT_ID.test(parts[1]) && safe(parts[2])) return { page: "evidence", unitId: parts[1], eventId: parts[2] };
  return { page: "invalid", raw: raw.slice(0, 80) };
}

export const clusterHref = (id: string) => `#/cluster/${encodeURIComponent(id)}`;
export const evidenceHref = (unitId: string, eventId: string) => `#/evidence/${encodeURIComponent(unitId)}/${encodeURIComponent(eventId)}`;
/** Existing console views, where they already exist. */
export const consoleUnitHref = (unitId: string, tab: "decision" | "events" | "history" = "decision") => `./index.html#/unit/${encodeURIComponent(unitId)}/${tab}`;
