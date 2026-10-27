// Static architecture guards for the branded-view contract. They are developer-misuse protection:
// they keep the construction and unwrapping of views, and every read of decision/clearance fields, inside
// a short allow-list, so a new page cannot quietly go around the gate. They are not a security boundary.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");
const walk = (d: string): string[] => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : /\.(ts|tsx)$/.test(n) ? [p] : []; });
const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").split(/\r?\n/).map((l) => l.replace(/(^|\s)\/\/.*$/, "")).join("\n");
const FILES = walk(SRC).map((p) => ({ rel: relative(SRC, p).replace(/\\/g, "/"), text: strip(readFileSync(p, "utf8")) }));
const usersOf = (re: RegExp) => FILES.filter((f) => re.test(f.text)).map((f) => f.rel).sort();

const CORES = ["passport/projection.ts", "investigation/projection.ts", "impact/projection.ts"];
const PREVIEW_ADAPTERS = ["passport/passportSource.ts", "investigation/investigationSource.ts", "impact/impactSource.ts"];

describe("architecture: who may build, unwrap or read clearance", () => {
  it("makeGated / makeHistorical are called only by the gate (and defined in gated.ts)", () => {
    expect(usersOf(/\bmakeGated\s*\(/)).toEqual(["contract/gate.ts", "contract/gated.ts", "contract/testing.ts"]);
    expect(usersOf(/\bmakeHistorical\s*\(/)).toEqual(["contract/gate.ts", "contract/gated.ts", "contract/testing.ts"]);
  });
  it("makePreview is called only by the explicit preview adapters", () => {
    expect(usersOf(/\bmakePreview\s*\(/)).toEqual(["contract/gated.ts", "contract/testing.ts", ...PREVIEW_ADAPTERS].sort());
  });
  it("only gated.ts mints a clearance", () => {
    expect(usersOf(/\bmintCurrentClearance\s*\(/)).toEqual(["contract/clearance.ts", "contract/gated.ts"]);
  });
  it("only views.ts unwraps a view into a raw snapshot", () => {
    expect(usersOf(/\brawSnapshotOf\s*\(/)).toEqual(["contract/gated.ts", "contract/views.ts"]);
  });
  it("test-only constructors are never imported by production code", () => {
    expect(FILES.filter((f) => /from\s+"[^"]*\/testing"/.test(f.text)).map((f) => f.rel)).toEqual([]);
  });
  it("pages and components never read the raw decision, eligibility or release fields", () => {
    const allowed = new Set(["contract/gate.ts", "contract/gated.ts", "contract/clearance.ts", "contract/ClearanceChip.tsx", "contract/testing.ts", "impact/syntheticScale.ts", ...CORES]);   // syntheticScale only clones preview decisions under new ids
    const re = /\boperationalAction\b|\.eligibility\b|\bcurrentReleaseEligible\b|["']RELEASE_ELIGIBLE["']|\bACTION_TEXT\b|\bsnap\.decisions\b/;
    const offenders = FILES.filter((f) => re.test(f.text) && !allowed.has(f.rel)).map((f) => f.rel);
    // domain/* is the validated data model and the established console, which this task does not change.
    expect(offenders.filter((r) => /^(passport|investigation|impact)\//.test(r))).toEqual([]);
  });
  it("standalone pages do not import a projection core or read a raw snapshot from a load", () => {
    const pages = FILES.filter((f) => /^(passport|investigation|impact)\/.*(App|Explorer|Workspace|NodeDetails|ImpactList|ImpactGraphView)\.tsx$/.test(f.rel));
    expect(pages.length).toBeGreaterThanOrEqual(7);
    for (const p of pages) {
      expect(p.text, p.rel).not.toMatch(/\b(buildPassport|buildInvestigation|buildImpactGraph|lotChoices)\s*[(,]/);
      expect(p.text, p.rel).not.toMatch(/\blast\??\.snap\b|\bload\.snap\b|\.verified\b/);
    }
  });
  it("a load carries a branded view, never a raw snapshot or a boolean `verified`", () => {
    for (const rel of PREVIEW_ADAPTERS) {
      const t = FILES.find((f) => f.rel === rel)!.text;
      expect(t, rel).not.toMatch(/\bverified\s*:/);
      expect(t, rel).not.toMatch(/\bsnap:\s*(r\.snap|validateSnapshot)/);
    }
  });
  it("?mode=preview is read only from location.search in the page entry points, never from fetched data", () => {
    const users = usersOf(/mode=preview|get\(["']mode["']\)/);
    for (const rel of users) expect(rel, rel).toMatch(/\/main\.tsx$|^App\.tsx$|^main\.tsx$|contract\//);
    for (const rel of PREVIEW_ADAPTERS) expect(FILES.find((f) => f.rel === rel)!.text).not.toMatch(/location\.search|URLSearchParams/);
  });
  it("only the contract module may render the release wording", () => {
    const offenders = FILES.filter((f) => /Release eligible/.test(f.text) && !f.rel.startsWith("contract/") && !f.rel.startsWith("domain/") && !f.rel.startsWith("components/")).map((f) => f.rel);
    expect(offenders.filter((r) => /^(passport|investigation|impact)\//.test(r))).toEqual([]);
  });
});
