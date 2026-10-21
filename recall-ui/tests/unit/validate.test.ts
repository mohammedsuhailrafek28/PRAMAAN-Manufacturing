import { describe, expect, it } from "vitest";
import { FixtureSnapshotSource } from "../../src/data/RecallDataSource";
import { SnapshotValidationError, validateSnapshot } from "../../src/domain/validate";
import { realSnapshot } from "./helpers";

describe("validateSnapshot", () => {
  it("accepts the real exported snapshot", () => {
    expect(validateSnapshot(realSnapshot()).units.length).toBeGreaterThan(20);
  });

  it("rejects a wrong schema version", () => {
    const s: any = realSnapshot();
    s.schemaVersion = 2;
    expect(() => validateSnapshot(s)).toThrow(SnapshotValidationError);
  });

  it("rejects a release-eligible action on an unresolved finding", () => {
    const s: any = realSnapshot();
    s.decisions["case-06"]["RC-009/P1"].current.operationalAction = "RELEASE_ELIGIBLE";
    try {
      validateSnapshot(s);
      throw new Error("should have thrown");
    } catch (e) {
      expect((e as SnapshotValidationError).issues.some((i) => /contradict/.test(i.message))).toBe(true);
    }
  });

  it("rejects an unknown finding and a missing unit decision", () => {
    const s: any = realSnapshot();
    s.decisions["case-01"]["RC-009/P1"].current.evidenceFinding = "PROBABLY_FINE";
    delete s.decisions["case-02"];
    const issues = (() => { try { validateSnapshot(s); return []; } catch (e) { return (e as SnapshotValidationError).issues; } })();
    expect(issues.map((i) => i.path)).toEqual(expect.arrayContaining(["decisions.case-01.RC-009/P1.current.evidenceFinding", "decisions.case-02"]));
  });

  it("the fixture source reports HTTP and JSON failures", async () => {
    const notFound = new FixtureSnapshotSource("/x.json", async () => new Response("", { status: 404 }));
    await expect(notFound.load()).rejects.toThrow(/HTTP 404/);
    const junk = new FixtureSnapshotSource("/x.json", async () => new Response("not json"));
    await expect(junk.load()).rejects.toThrow(/not valid JSON/);
  });
});
