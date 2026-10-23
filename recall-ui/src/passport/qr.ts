// Route-only QR for a passport. The encoded text is the passport page address plus a
// fragment route that carries the unit identifier and nothing else: no query string, no
// customer, destination, evidence, hash, signature claim or recall verdict.
//
// A QR code is a link. It is not proof of authenticity and cannot prevent cloning.
import { encode } from "uqr";
import { UNIT_ID_PATTERN } from "./projection";

export const PASSPORT_PAGE = "passport.html";

export function passportRoute(unitId: string): string {
  if (!UNIT_ID_PATTERN.test(unitId)) throw new Error("Invalid motor identifier; no QR is generated.");
  return `#/passport/${encodeURIComponent(unitId)}`;
}

/** `pageUrl` is the address the passport page is served from; its query and fragment are discarded. */
export function passportUrl(unitId: string, pageUrl: string): string {
  const u = new URL(pageUrl);
  u.username = "";
  u.password = "";
  u.search = "";
  u.hash = "";
  return `${u.toString()}${passportRoute(unitId)}`;
}

export interface QrMatrix {
  size: number;
  /** true = dark module, without quiet zone */
  modules: boolean[][];
  version: number;
}

export function qrMatrix(text: string): QrMatrix {
  const r = encode(text, { ecc: "M", border: 0 });
  return { size: r.size, modules: r.data, version: r.version };
}

export const QUIET_ZONE = 4;

/** One SVG path of dark modules, in module units, including the standard 4-module quiet zone. */
export function qrSvgPath(m: QrMatrix): { path: string; viewBox: string; size: number } {
  const parts: string[] = [];
  for (let y = 0; y < m.size; y++) {
    let x = 0;
    while (x < m.size) {
      if (!m.modules[y][x]) { x++; continue; }
      const start = x;
      while (x < m.size && m.modules[y][x]) x++;
      parts.push(`M${start + QUIET_ZONE} ${y + QUIET_ZONE}h${x - start}v1h-${x - start}z`);
    }
  }
  const size = m.size + QUIET_ZONE * 2;
  return { path: parts.join(""), viewBox: `0 0 ${size} ${size}`, size };
}
