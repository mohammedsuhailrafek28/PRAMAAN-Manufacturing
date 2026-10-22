import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isGated } from "../../src/contract/gated";
import { gatedForTest, historicalForTest } from "../../src/contract/testing";
import { InvestigationApp } from "../../src/investigation/InvestigationApp";
import { LiveInvestigationSource, PreviewInvestigationSource, type InvestigationLoad, type InvestigationSource } from "../../src/investigation/investigationSource";
import { buildInvestigation } from "../../src/investigation/projection";
import { clusterHref, evidenceHref } from "../../src/investigation/route";
import { freshStage, stage } from "./investigationHelpers";

type Step = InvestigationLoad | Error;
class Scripted implements InvestigationSource {
  readonly label = "scripted"; calls = 0;
  constructor(readonly live: boolean, private steps: Step[]) {}
  async load(): Promise<InvestigationLoad> {
    const step = this.steps[Math.min(this.calls++, this.steps.length - 1)];
    if (step instanceof Error) throw step;
    return step;
  }
}
const verified = (id: "before" | "after" = "before", sequence = 100, leaseMs = 5000): InvestigationLoad => ({ view: gatedForTest(freshStage(id, Date.now(), sequence)), reason: "", leaseMs });
const unverified = (): InvestigationLoad => ({ view: historicalForTest(stage("before")), reason: "Current verification unavailable: trusted external anchor required. Decisions are historical.", leaseMs: 0 });

const go = (hash: string) => { window.location.hash = hash; };
beforeEach(() => { go("#/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Object.defineProperty(document, "hidden", { configurable: true, value: false }); });

describe("verified live data", () => {
  it("shows the watermark, ordered groups and the read-only boundary", async () => {
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    expect(await screen.findByTestId("watermark")).toHaveTextContent(/journal sequence\s*100/i);
    const cards = screen.getAllByTestId("cluster-card");
    expect(cards[0]).toHaveAttribute("data-cluster-class", "UNTRUSTED_AFFECTED_OBSERVATION");
    expect(cards[0]).toHaveTextContent("3 motors share this exact key");
    expect(screen.getByText("Not a release authorization")).toBeInTheDocument();
    expect(screen.getByText("Synthetic demonstration data")).toBeInTheDocument();
  });
  it("has no assignment, completion, approval or resolution control anywhere", async () => {
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("watermark");
    for (const hash of ["#/", clusterHref(buildInvestigation(stage("before")).clusters[0].clusterId)]) {
      act(() => go(hash));
      await waitFor(() => expect(screen.getByTestId("watermark")).toBeInTheDocument());
      expect(screen.queryAllByRole("button")).toHaveLength(0);
      // Prose may say what the page cannot do; no interactive control may offer to do it.
      const controls = [...document.querySelectorAll("a, button, input, select, textarea, summary, [role=button]")].map((e) => e.textContent ?? "");
      for (const label of controls) expect(label).not.toMatch(/\b(assign|mark (as )?(done|complete|resolved)|approve|resolve|complete|close|release)\b/i);
      expect(document.querySelectorAll("form, input, textarea")).toHaveLength(0);
    }
  });
  it("separates notification obligations from the evidence groups", async () => {
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    const panel = await screen.findByTestId("obligations");
    expect(panel).toHaveTextContent(/not evidence-gathering tasks/i);
    expect(panel).toHaveTextContent("MTR-26005");
    expect(within(screen.getAllByTestId("cluster-card")[0]).queryByText(/PRIOR_EXCLUSION_WITHDRAWN/)).toBeNull();
  });
  it("filters groups by class using a native select", async () => {
    const user = userEvent.setup();
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("watermark");
    await user.selectOptions(screen.getByLabelText("Show"), "CAPTURE_GAP");
    const cards = screen.getAllByTestId("cluster-card");
    expect(cards.length).toBeGreaterThan(0);
    for (const c of cards) expect(c).toHaveAttribute("data-cluster-class", "CAPTURE_GAP");
  });
});

describe("a cluster page explains the four required parts for each motor", () => {
  it("shows the decision, the evidence class, the supporting records and the investigation guidance", async () => {
    const v = buildInvestigation(stage("before"));
    const cluster = v.clusters.find((c) => c.key.includes(`sourceId=ASSY:SHARED-DEMO-STATION`))!;
    go(clusterHref(cluster.clusterId));
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    const t = await screen.findByTestId("task-MTR-26015");
    expect(within(t).getByText("What the existing recall decision says")).toBeInTheDocument();
    expect(within(t).getByText("What evidence is missing, conflicting or untrusted")).toBeInTheDocument();
    expect(within(t).getByText("Ledger records that support this")).toBeInTheDocument();
    expect(within(t).getByText("What a quality engineer should independently investigate")).toBeInTheDocument();
    expect(t).toHaveTextContent("ASSY:SHARED-DEMO-STATION");
    expect(t).toHaveTextContent("2026-10-02T00:00:00Z");
    expect(screen.getByTestId("task-MTR-26016")).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/Absence from the ledger is not evidence/);
  });
  it("links a supporting record to its evidence page with hashes and the limits of hashes", async () => {
    const v = buildInvestigation(stage("before"));
    const task = v.tasks.find((t) => t.unitId === "MTR-26005")!;
    go(evidenceHref(task.unitId, task.evidenceEventIds[0]));
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    const page = await screen.findByTestId("evidence-page");
    expect(page).toHaveTextContent("OP-OBSERVATION-21");
    expect(page).toHaveTextContent(/HANDHELD_LABEL_READ/i);
    expect(page).toHaveTextContent(/[0-9a-f]{64}/);
    expect(page).toHaveTextContent(/do not show that what the record says is true/);
  });
  it("handles unknown groups, unknown records and malformed addresses without throwing", async () => {
    go("#/cluster/g-00000000000000");
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    expect(await screen.findByTestId("unknown-cluster")).toBeInTheDocument();
    act(() => go("#/evidence/MTR-26005/nope"));
    expect(await screen.findByTestId("unknown-evidence")).toBeInTheDocument();
    act(() => go("#/%E0%A4%A"));
    expect(await screen.findByTestId("invalid-route")).toBeInTheDocument();
    act(() => go("#/cluster/<script>"));
    expect(await screen.findByTestId("invalid-route")).toBeInTheDocument();
  });
});

describe("verification failure withdraws current claims", () => {
  it("shows no tasks for an unverified (historical) snapshot", async () => {
    render(<InvestigationApp source={new Scripted(true, [unverified()])} />);
    const panel = await screen.findByTestId("withdrawn");
    expect(panel).toHaveTextContent(/trusted external anchor required/);
    expect(screen.queryAllByTestId("cluster-card")).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/MTR-26005/);
  });
  it("withdraws tasks after a failed refresh but keeps only the last watermark, labelled not current", async () => {
    const source = new Scripted(true, [verified("before", 100), new Error("Backend request timed out.")]);
    render(<InvestigationApp source={source} pollMs={20} />);
    await screen.findByTestId("watermark");
    const panel = await screen.findByTestId("withdrawn");
    expect(panel).toHaveTextContent(/timed out/);
    expect(panel).toHaveTextContent(/journal sequence 100/);
    expect(panel).toHaveTextContent(/not current/);
    expect(screen.queryAllByTestId("cluster-card")).toHaveLength(0);
  });
  it("shows an error and no fixture data when the first load fails", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("connection refused"));
    vi.stubGlobal("fetch", fetch);
    render(<InvestigationApp source={new LiveInvestigationSource(50)} />);
    expect(await screen.findByTestId("load-error")).toHaveTextContent(/no fixture data is substituted/);
    for (const call of fetch.mock.calls) expect(String(call[0])).toBe("/api/snapshot");
  });
  it("withdraws tasks when the verification lease expires", async () => {
    render(<InvestigationApp source={new Scripted(true, [verified("before", 100, 60)])} pollMs={10_000} />);
    await screen.findByTestId("watermark");
    expect(await screen.findByTestId("withdrawn")).toHaveTextContent(/lease expired/);
  });
  it("withdraws tasks while the tab is hidden and restores them after a new verified load", async () => {
    render(<InvestigationApp source={new Scripted(true, [verified("before", 100), verified("before", 101)])} pollMs={10_000} />);
    await screen.findByTestId("watermark");
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(await screen.findByTestId("withdrawn")).toBeInTheDocument();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    await waitFor(() => expect(screen.getByTestId("watermark")).toHaveTextContent(/sequence\s*101/));
  });
});

describe("updates arrive from the verified snapshot, never from a manual action", () => {
  it("drops a task and notes a re-evaluation when a newer verified snapshot changes the decisions", async () => {
    const source = new Scripted(true, [verified("before", 100), verified("after", 101)]);
    render(<InvestigationApp source={source} pollMs={20} />);
    await screen.findByTestId("watermark");
    const changes = await waitFor(() => {
      const el = screen.getByTestId("changes");
      expect(el).toHaveTextContent(/Updated from a newer verified snapshot/);
      return el;
    });
    expect(changes).toHaveTextContent(/MTR-26017.*no longer listed/);
    expect(changes).toHaveTextContent(/MTR-26012.*re-evaluated \(version 2 to 3\)/);
    expect(changes).toHaveTextContent(/Nothing was closed by hand/);
    expect(screen.getByTestId("watermark")).toHaveTextContent(/sequence\s*101/);
  });
});

describe("preview mode is explicit, labelled and never current", () => {
  it("labels the data as a preview and shows no verified watermark", async () => {
    const doc = { kind: "SYNTHETIC_INVESTIGATION_DEMONSTRATION", label: "Authored scenario label.", origin: { "MTR-26004": "SEEDED", "MTR-26015": "AUTHORED_SOURCE_EDIT" }, stages: [{ id: "before", label: "Before", snapshot: stage("before") }, { id: "after", label: "After", snapshot: stage("after") }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => structuredClone(doc) }));
    render(<InvestigationApp source={new PreviewInvestigationSource("after")} stageLinks={[{ id: "before", label: "Before", href: "?mode=preview&stage=before#/" }, { id: "after", label: "After", href: "?mode=preview&stage=after#/" }]} />);
    expect(await screen.findByText("Preview: not current")).toBeInTheDocument();
    expect(screen.getByTestId("watermark")).toHaveTextContent(/Not a verified watermark/);
    expect(screen.getByTestId("watermark")).not.toHaveTextContent(/Verified ledger journal sequence/);
    expect(screen.getByTestId("iw-banner")).toHaveTextContent(/not a live ledger/);
    expect(screen.getByTestId("stage-note")).toHaveTextContent(/MTR-26015 authored source edit/);
    await waitFor(() => expect(screen.getByTestId("changes")).toHaveTextContent(/Changes compared with the previous preview stage/));
  });
});

describe("keyboard and structure", () => {
  it("reaches navigation, the filter and group links with native focusable elements in order", async () => {
    const user = userEvent.setup();
    render(<InvestigationApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("watermark");
    await user.tab();
    expect(screen.getByText("Skip to content")).toHaveFocus();
    await user.tab(); await user.tab();
    expect(screen.getByText("Investigation workspace")).toHaveFocus();
    const first = screen.getAllByTestId("cluster-card")[0].querySelector("h3 a") as HTMLElement;
    first.focus();
    await user.keyboard("{Enter}");
    expect(window.location.hash).toMatch(/^#\/cluster\/g-/);
    expect(await screen.findByLabelText("Breadcrumb")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});

describe("live adapter is GET-only and reuses the unchanged freshness boundary", () => {
  it("requests only /api/snapshot with GET and accepts a fresh anchored snapshot", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => freshStage("before", Date.now(), 7) });
    vi.stubGlobal("fetch", fetch);
    const load = await new LiveInvestigationSource().load();
    expect(isGated(load.view)).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/snapshot");
    expect(fetch.mock.calls[0][1].method).toBe("GET");
  });
  it("marks an unanchored snapshot unverified and throws on regression", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => stage("before") }));
    expect(isGated((await new LiveInvestigationSource().load()).view)).toBe(false);
    const source = new LiveInvestigationSource();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, status: 200, json: async () => freshStage("before", Date.now(), 9) }).mockResolvedValueOnce({ ok: true, status: 200, json: async () => freshStage("before", Date.now(), 8) }));
    await source.load();
    await expect(source.load()).rejects.toThrow(/regression/);
  });
  it("bounds a hung request", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    await expect(new LiveInvestigationSource(20).load()).rejects.toThrow(/timed out/);
  });
});
