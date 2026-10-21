import jsQR from "jsqr";
import { describe, expect, it } from "vitest";
import { passportRoute, passportUrl, qrMatrix } from "../../src/passport/qr";
import { FORBIDDEN, previewSnapshot } from "./passportHelpers";

function decode(modules: boolean[][]): string | null {
  const quiet = 4, scale = 6, n = modules.length, px = (n + quiet * 2) * scale;
  const rgba = new Uint8ClampedArray(px * px * 4).fill(255);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    if (!modules[y][x]) continue;
    for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) {
      const i = (((y + quiet) * scale + dy) * px + (x + quiet) * scale + dx) * 4;
      rgba[i] = rgba[i + 1] = rgba[i + 2] = 0;
    }
  }
  return jsQR(rgba, px, px)?.data ?? null;
}

const PAGE = "http://127.0.0.1:4173/passport.html";

describe("route-only QR payload", () => {
  it("encodes the passport page and the identifier only", () => {
    expect(passportUrl("MTR-26004", PAGE)).toBe("http://127.0.0.1:4173/passport.html#/passport/MTR-26004");
    expect(passportRoute("MTR-26004")).toBe("#/passport/MTR-26004");
  });
  it("discards any query or fragment on the page address, including preview mode", () => {
    expect(passportUrl("MTR-26004", `${PAGE}?mode=preview&token=x#/passport/MTR-26001/evidence/e`)).toBe("http://127.0.0.1:4173/passport.html#/passport/MTR-26004");
  });
  it("refuses to generate for malformed identifiers", () => {
    for (const bad of ["", "MTR-1", "mtr-26004", "MTR-26004?x=1", "MTR-26004#x", "MTR-26004 ", "../MTR-26004", "MTR-<script>"]) {
      expect(() => passportUrl(bad, PAGE), bad).toThrow(/Invalid motor identifier/);
    }
  });
  it("contains no customer, destination, operator, evidence, hash or verdict text", () => {
    const snap = previewSnapshot();
    for (const u of snap.units) {
      const url = passportUrl(u.unitId, PAGE);
      for (const f of [...FORBIDDEN, "RELEASE", "HOLD", "AFFECTED", "sha", "hash", "signature", "BR-"]) expect(url).not.toContain(f);
      expect(url).toMatch(/^http:\/\/127\.0\.0\.1:4173\/passport\.html#\/passport\/MTR-[A-Z0-9-]+$/);
    }
  });
});

describe("generated QR codes decode back to the exact route", () => {
  it("round-trips every unit in the snapshot", () => {
    for (const u of previewSnapshot().units) {
      const url = passportUrl(u.unitId, PAGE);
      const m = qrMatrix(url);
      expect(m.size).toBe(m.modules.length);
      expect(decode(m.modules), u.unitId).toBe(url);
    }
  });
  it("is deterministic for the same input", () => {
    const a = qrMatrix(passportUrl("MTR-26004", PAGE)), b = qrMatrix(passportUrl("MTR-26004", PAGE));
    expect(a.modules).toEqual(b.modules);
  });
  it("differs between units", () => {
    expect(qrMatrix(passportUrl("MTR-26004", PAGE)).modules).not.toEqual(qrMatrix(passportUrl("MTR-26005", PAGE)).modules);
  });
});
