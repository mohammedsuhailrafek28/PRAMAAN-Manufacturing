// Page-level behaviour of the branded views: per-motor clearance (T7), historical views, previews.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { InvestigationApp } from "../../src/investigation/InvestigationApp";
import type { InvestigationLoad, InvestigationSource } from "../../src/investigation/investigationSource";
import { PassportApp } from "../../src/passport/PassportApp";
import type { PassportLoad, PassportSource } from "../../src/passport/passportSource";
import { gatedForTest, historicalForTest, previewForTest } from "../../src/contract/testing";
import { freshStage, stage } from "./investigationHelpers";
import { freshSnapshot, previewSnapshot } from "./passportHelpers";

const PAGE = "http://127.0.0.1:4173/passport.html";
const go = (h: string) => { window.location.hash = h; };
afterEach(cleanup);

const passportSource = (load: PassportLoad, live = true): PassportSource => ({ label: "scripted", live, load: async () => load });
const invSource = (load: InvestigationLoad, live = true): InvestigationSource => ({ label: "scripted", live, load: async () => load });

describe("passport: a motor whose own eligibility is withheld", () => {
  beforeEach(() => go("#/passport/MTR-26003/recall"));
  it("keeps the recorded finding but never states clearance or 'no hold recorded'", async () => {
    const snap = freshSnapshot();
    render(<PassportApp source={passportSource({ view: gatedForTest(snap, { "MTR-26003": false }), reason: "", leaseMs: 4000 })} pageUrl={PAGE} pollMs={100000} />);
    const card = await screen.findByTestId("recall-current");
    expect(card).toHaveTextContent("Current clearance withheld for this motor");
    expect(card).toHaveTextContent(/Excluded|Affected|Unresolved|evidence/i);                    // finding preserved
    expect(document.body.textContent).not.toMatch(/No recall hold recorded|Release eligible/);
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
  });
  it("another motor in the same snapshot is unaffected", async () => {
    go("#/passport/MTR-26001/recall");
    const snap = freshSnapshot();
    render(<PassportApp source={passportSource({ view: gatedForTest(snap, { "MTR-26003": false }), reason: "", leaseMs: 4000 })} pageUrl={PAGE} pollMs={100000} />);
    const card = await screen.findByTestId("recall-current");
    expect(card).toHaveTextContent("Held under the recall policy");
  });
  it("the cleared motor keeps the original wording when its eligibility is honest", async () => {
    render(<PassportApp source={passportSource({ view: gatedForTest(freshSnapshot()), reason: "", leaseMs: 4000 })} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByTestId("recall-current")).toHaveTextContent("No recall hold recorded under this policy");
  });
  it("a historical view and a preview never show current recall status", async () => {
    for (const [view, live] of [[historicalForTest(previewSnapshot(), "PREFIX_ONLY"), true], [previewForTest(previewSnapshot()), false]] as const) {
      const { unmount } = render(<PassportApp source={passportSource({ view, reason: "Not current.", leaseMs: 0 }, live)} pageUrl={PAGE} pollMs={100000} />);
      expect(await screen.findByTestId("recall-unavailable")).toBeInTheDocument();
      expect(screen.queryByTestId("recall-current")).toBeNull();
      expect(document.body.textContent).not.toMatch(/Release eligible|No recall hold recorded/);
      unmount();
    }
  });
});

describe("investigation", () => {
  beforeEach(() => go("#/"));
  it("a historical view shows no tasks and no decision content", async () => {
    render(<InvestigationApp source={invSource({ view: historicalForTest(stage("before"), "PREFIX_ONLY"), reason: "Historical evidence only.", leaseMs: 0 })} />);
    expect(await screen.findByTestId("withdrawn")).toBeInTheDocument();
    expect(screen.queryAllByTestId("cluster-card")).toHaveLength(0);
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
  });
  it("a preview shows labelled synthetic evaluator output and never a clearance chip", async () => {
    render(<InvestigationApp source={invSource({ view: previewForTest(stage("before")), reason: "preview", leaseMs: 0 }, false)} />);
    await screen.findAllByTestId("cluster-card");
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Current clearance|authorized for release/i);
  });
  it("a live gated view with one motor's eligibility withheld still lists its tasks, without a clearance for it", async () => {
    const snap = freshStage("before", Date.now(), 100);
    render(<InvestigationApp source={invSource({ view: gatedForTest(snap, Object.fromEntries(snap.units.map((u) => [u.unitId, false]))), reason: "", leaseMs: 5000 })} />);
    await screen.findAllByTestId("cluster-card");
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
  });
});
