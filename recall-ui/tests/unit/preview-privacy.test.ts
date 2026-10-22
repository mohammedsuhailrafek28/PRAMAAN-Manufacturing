// FE-PRV-2/3: publicly served preview JSON carries no customer, destination or operator identifiers (owner decision O2).
// This is minimisation of a static preview, not an access-control claim about the live API.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { validateSnapshot } from "../../src/domain/validate";

const ROOT = join(__dirname, "../..");
const dirs = [join(ROOT, "public/data"), ...(existsSync(join(ROOT, "dist/data")) ? [join(ROOT, "dist/data")] : [])];
const FILES = ["passport-preview.json", "investigation-demo.json", "impact-demo.json", "snapshot.json"];
const SENSITIVE = /Aster Pump|Coimbatore|Customer [A-E] \(synthetic\)|Site [1-5] \(synthetic\)|\b(?:OP|QA|EMP|SYS|SUPPLIER|DISPATCH|MES)-[A-Z0-9]/;

describe("preview JSON privacy", () => {
  for (const dir of dirs) for (const f of FILES) {
    it(`${dir.endsWith("dist/data") ? "dist" : "public"}/${f} has no customer, destination or operator identifier`, () => {
      const raw = readFileSync(join(dir, f), "utf8");
      expect(raw.match(SENSITIVE)?.[0] ?? null).toBeNull();
      const doc = JSON.parse(raw, (k, v) => { if ((k === "customer" || k === "destination") && typeof v === "string") expect(v).toBe("[not included in preview]"); return v; });
      expect(doc).toBeTruthy();
    });
  }
  it("sanitised previews still validate as snapshots (and never as a live/verified source)", () => {
    const snap = JSON.parse(readFileSync(join(ROOT, "public/data/passport-preview.json"), "utf8"));
    expect(() => validateSnapshot(snap)).not.toThrow();
    expect(snap.checkpoint).toBeUndefined();            // a preview can never satisfy the strict gate
    expect(snap.freshness?.status).not.toBe("VERIFIED_ANCHORED_SYNTHETIC");
  });
  it("no served file under public/ contains a sensitive identifier", () => {
    const walk = (d: string): string[] => readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]);
    for (const f of walk(join(ROOT, "public")).filter((p) => /\.(json|txt|csv|html)$/.test(p))) expect(readFileSync(f, "utf8").match(SENSITIVE)?.[0] ?? null, f).toBeNull();
  });
});
