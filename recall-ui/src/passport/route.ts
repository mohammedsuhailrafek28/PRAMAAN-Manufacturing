import { UNIT_ID_PATTERN } from "./projection";

export type PassportTab = "overview" | "components" | "evidence" | "timeline" | "recall" | "qr";
export const PASSPORT_TABS: Array<[PassportTab, string]> = [
  ["overview", "Overview"],
  ["components", "Components"],
  ["evidence", "Evidence"],
  ["timeline", "Timeline"],
  ["recall", "Recall context"],
  ["qr", "QR label"],
];

export type PassportRoute =
  | { page: "index" }
  | { page: "invalid"; raw: string }
  | { page: "passport"; unitId: string; tab: PassportTab; evidenceId: string | null };

export function parsePassportRoute(hash: string): PassportRoute {
  let parts: string[];
  try {
    parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return { page: "invalid", raw: hash };
  }
  if (parts[0] !== "passport" || parts.length < 2) return { page: "index" };
  const unitId = parts[1];
  if (!UNIT_ID_PATTERN.test(unitId)) return { page: "invalid", raw: unitId };
  const tab = PASSPORT_TABS.some(([t]) => t === parts[2]) ? (parts[2] as PassportTab) : "overview";
  return { page: "passport", unitId, tab, evidenceId: tab === "evidence" && parts[3] ? parts[3] : null };
}

export const tabHref = (unitId: string, tab: PassportTab, evidenceId?: string) =>
  `#/passport/${encodeURIComponent(unitId)}/${tab}${evidenceId ? `/${encodeURIComponent(evidenceId)}` : ""}`;
