import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImpactApp } from "../../src/impact/ImpactApp";
import { DRAW_CAP, headline } from "../../src/impact/ImpactWorkspace";
import { LiveImpactSource, PreviewImpactSource, type ImpactLoad, type ImpactSource } from "../../src/impact/impactSource";
import { buildImpactGraph } from "../../src/impact/projection";
import { lotHref, parseRoute } from "../../src/impact/route";
import { scaleSnapshot } from "../../src/impact/syntheticScale";
import demo from "../../public/data/impact-demo.json";
import { dataset, freshDataset, FORBIDDEN, origin } from "./impactHelpers";

type Step = ImpactLoad | Error;
class Scripted implements ImpactSource {
  readonly label = "scripted"; calls = 0;
  constructor(readonly live: boolean, private steps: Step[]) {}
  async load(): Promise<ImpactLoad> {
    const step = this.steps[Math.min(this.calls++, this.steps.length - 1)];
    if (step instanceof Error) throw step;
    return step;
  }
}
const verified = (leaseMs = 5000, id: "de" | "nde" = "de", sequence = 100): ImpactLoad => ({ snap: freshDataset(id, Date.now(), sequence), verified: true, reason: "", leaseMs });
const unverified = (): ImpactLoad => ({ snap: dataset("de"), verified: false, reason: "Current verification unavailable: trusted external anchor required. Decisions are historical.", leaseMs: 0 });
const go = (hash: string) => { window.location.hash = hash; };
const LIST = lotHref("BEARING_LOT", "BR-204", "list");
const GRAPH = lotHref("BEARING_LOT", "BR-204", "graph");

beforeEach(() => { go("#/"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Object.defineProperty(document, "hidden", { configurable: true, value: false }); });

describe("routes", () => {
  it("accepts only the documented address forms and rejects hostile ones", () => {
    expect(parseRoute("#/")).toEqual({ page: "home" });
    expect(parseRoute("#/lot/bearing/BR-204/graph/motor%3AMTR-26001")).toEqual({ page: "lot", kind: "BEARING_LOT", lotId: "BR-204", view: "graph", nodeId: "motor:MTR-26001" });
    expect(parseRoute("#/lot/raw/RM-1")).toMatchObject({ kind: "RAW_LOT", view: null });
    for (const bad of ["#/lot/bearing/<script>", "#/lot/bearing/BR-204/sideways", "#/lot/other/BR-204", "#/lot/bearing/BR-204/list/%00", "#/%E0%A4%A", "#/x"]) expect(parseRoute(bad).page, bad).toBe("invalid");
  });
});

describe("verified live data", () => {
  it("states the lot, scope, counts and the limits of ledger records", async () => {
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    const h = await screen.findByTestId("impact-headline");
    expect(h).toHaveTextContent("Lot BR-204 is named by recall");
    expect(h).toHaveTextContent("10 motors have a ledger-recorded link to it (7 affected, 2 unresolved, 1 excluded with evidence)");
    expect(h).toHaveTextContent("9 motors have a recorded shipment record");
    expect(screen.getByText(/ledger records, not a physical verification/i)).toBeInTheDocument();
    expect(screen.getByText(/Excluded with evidence does not mean safe/)).toBeInTheDocument();
    expect(screen.queryByTestId("noncurrent-label")).toBeNull();
    expect(screen.getByText("Scope and ledger watermark")).toBeInTheDocument();
    expect(screen.getByText("VERIFIED_ANCHORED_SYNTHETIC")).toBeInTheDocument();
  });

  it("never renders customer, destination or operator identifiers", async () => {
    go(LIST);
    const { container } = render(<ImpactApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("impact-headline");
    // open a motor with shipment evidence, then a shipment
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^Select: MTR-26001 / }));
    await screen.findByTestId("impact-details");
    const text = container.textContent ?? "";
    for (const f of FORBIDDEN) expect(text, f).not.toContain(f);
  });

  it("copies the engine decision and labels exclusion as scoped, not safe", async () => {
    const excluded = buildImpactGraph(freshDataset(), { kind: "BEARING_LOT", id: "BR-204" }, { recallStatusCurrent: true }).nodes.find((n) => n.status?.finding === "EXCLUDED_WITH_EVIDENCE")!;
    go(lotHref("BEARING_LOT", "BR-204", "list", excluded.id));
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    const d = await screen.findByTestId("impact-decision");
    expect(d).toHaveTextContent("Excluded with evidence");
    expect(d).toHaveTextContent("this page does not evaluate anything");
    expect(d).toHaveTextContent("not a statement that the motor is safe");
  });

  it("renders a removed component as historical and says removal is not elimination", async () => {
    const snap = freshDataset();
    const g = buildImpactGraph(snap, { kind: "BEARING_LOT", id: "BR-204" }, { recallStatusCurrent: true });
    const hist = g.nodes.find((n) => n.kind === "COMPONENT" && n.lifecycle === "HISTORICAL")!;
    go(lotHref("BEARING_LOT", "BR-204", "list", hist.id));
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    expect(await screen.findByText(/not proof that the affected lot was eliminated/)).toBeInTheDocument();
  });

  it("explains that a shipment record is not delivery", async () => {
    const g = buildImpactGraph(freshDataset(), { kind: "BEARING_LOT", id: "BR-204" }, { recallStatusCurrent: true });
    go(lotHref("BEARING_LOT", "BR-204", "list", g.nodes.find((n) => n.kind === "SHIPMENT")!.id));
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    expect(await screen.findByText(/does not show delivery, receipt/)).toBeInTheDocument();
  });

  it("lists link-integrity problems with their cited records", async () => {
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("impact-headline");
    const kinds = screen.getAllByTestId("impact-issue").map((e) => e.getAttribute("data-issue-kind"));
    for (const k of ["MISSING_MANUFACTURE_LINK", "MISSING_MATERIAL_LINK", "LOT_MISMATCH", "DUPLICATE_REFERENCE"]) expect(kinds, k).toContain(k);
  });

  it("filters motors by engine finding and says hidden motors are not cleared", async () => {
    const user = userEvent.setup();
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("impact-headline");
    await user.click(screen.getByLabelText("Unresolved"));
    expect(screen.getByText(/hidden by the finding filter. Hidden motors are not cleared/)).toBeInTheDocument();
    const rows = within(screen.getByTestId("impact-list")).getAllByRole("row");
    const motorRows = rows.filter((r) => r.getAttribute("data-node-id")?.startsWith("motor:"));
    const expected = buildImpactGraph(freshDataset(), { kind: "BEARING_LOT", id: "BR-204" }, { recallStatusCurrent: true }).nodes.filter((n) => n.status?.finding === "UNRESOLVED").length;
    expect(expected).toBeGreaterThan(0);
    expect(motorRows).toHaveLength(expected);
  });

  it("works for a raw-material lot and an unknown lot", async () => {
    go(lotHref("RAW_LOT", "RM-NOPE", "list"));
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    expect(await screen.findByTestId("unknown-lot")).toHaveTextContent(/not evidence that no motor holds it/);
  });

  it("is deterministic: the same snapshot gives the same headline", () => {
    const a = headline(buildImpactGraph(freshDataset(), { kind: "BEARING_LOT", id: "BR-204" }, { recallStatusCurrent: true }));
    const b = headline(buildImpactGraph(freshDataset(), { kind: "BEARING_LOT", id: "BR-204" }, { recallStatusCurrent: true }));
    expect(a).toBe(b);
  });

  it("has no control that mutates anything: only view controls, filters and selection", async () => {
    go(GRAPH);
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("impact-headline");
    const labels = [...document.querySelectorAll("a, button, input, select, textarea, summary, [role=button]")].map((e) => (e.textContent ?? "") + (e.getAttribute("aria-label") ?? ""));
    for (const l of labels) expect(l).not.toMatch(/\b(assign|approve|resolve|release|delete|save|submit|notify|send|ship)\b/i);
    expect(document.querySelectorAll("textarea, input[type=file], input[type=password]")).toHaveLength(0);
  });
});

describe("keyboard and list fallback", () => {
  it("selects a graph node with Enter and shows its ledger records", async () => {
    const user = userEvent.setup();
    go(GRAPH);
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("impact-svg");
    const node = screen.getAllByTestId("impact-node").find((n) => n.getAttribute("data-node-id") === "motor:MTR-26001")!;
    expect(node).toHaveAttribute("tabindex", "0");
    expect(node.getAttribute("aria-label")).toMatch(/^MTR-26001 .*, Motor, Affected/);
    node.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(window.location.hash).toContain("motor%3AMTR-26001"));
    const details = await screen.findByTestId("impact-details");
    expect(within(details).getByText("Ledger records behind this item")).toBeInTheDocument();
  });

  it("the list shows every node with its recorded links and opens details", async () => {
    const user = userEvent.setup();
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    const table = await screen.findByTestId("impact-list");
    expect(within(table).getByText("Recorded links")).toBeInTheDocument();
    await user.click(within(table).getByRole("button", { name: /Select: MTR-26001 / }));
    expect(await screen.findByTestId("impact-details")).toHaveTextContent("MTR-26001");
  });

  it("traces back to the source and highlights only recorded links", async () => {
    const user = userEvent.setup();
    go(lotHref("BEARING_LOT", "BR-204", "graph", "motor:MTR-26001"));
    render(<ImpactApp source={new Scripted(true, [verified()])} />);
    await screen.findByTestId("impact-details");
    const total = screen.getAllByTestId("impact-node").length;
    await user.click(screen.getByRole("button", { name: "Trace back to source" }));
    expect(screen.getByText(/Showing the backward trace of MTR-26001 along recorded links only/)).toBeInTheDocument();
    expect(screen.getAllByTestId("impact-node").length).toBeLessThan(total);
  });
});

describe("withdrawal", () => {
  it("withholds recall status and labels the genealogy not current when not verified", async () => {
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [unverified()])} />);
    const label = await screen.findByTestId("noncurrent-label");
    expect(label).toHaveTextContent(/Not current/);
    expect(screen.getByTestId("impact-headline")).toHaveTextContent("Current recall status is withheld");
    expect(screen.queryByTestId("impact-decision")).toBeNull();
    expect(screen.queryByText(/named by the recall/)).toBeNull();
    expect(screen.queryByText(/Engine finding/i, { selector: ".chip-cap" })).toBeNull();
    expect(screen.getByText(/Withheld, because it is a claim about the current recall/)).toBeInTheDocument();
  });

  it("withholds status again when the lease expires", async () => {
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified(80), unverified()])} pollMs={10_000} />);
    await screen.findByTestId("impact-headline");
    expect(screen.queryByTestId("noncurrent-label")).toBeNull();
    expect(await screen.findByTestId("noncurrent-label", undefined, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.queryByTestId("impact-decision")).toBeNull();
  });

  it("withdraws everything on an outage and substitutes no fixture", async () => {
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified(), new Error("Backend request timed out.")])} pollMs={30} />);
    await screen.findByTestId("impact-headline");
    expect(await screen.findByTestId("withdrawn", undefined, { timeout: 2000 })).toHaveTextContent(/Backend request timed out/);
    expect(screen.queryByTestId("impact-workspace")).toBeNull();
    expect(screen.queryByTestId("impact-svg")).toBeNull();
  });

  it("shows an error, not data, when the first load fails", async () => {
    render(<ImpactApp source={new Scripted(true, [new Error("Ledger unavailable: HTTP 500")])} />);
    expect(await screen.findByTestId("load-error")).toHaveTextContent(/no fixture data is substituted/);
  });

  it("withholds status while the tab is hidden", async () => {
    go(LIST);
    render(<ImpactApp source={new Scripted(true, [verified(60_000)])} pollMs={60_000} />);
    await screen.findByTestId("impact-headline");
    expect(screen.queryByTestId("noncurrent-label")).toBeNull();
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    act(() => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(await screen.findByTestId("noncurrent-label")).toBeInTheDocument();
  });
});

describe("adapters", () => {
  it("live adapter sends only GET to the snapshot endpoint and verifies freshness", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => freshDataset("de", Date.now(), 100) }));
    vi.stubGlobal("fetch", fetchMock);
    const src = new LiveImpactSource();
    const load = await src.load();
    expect(load.verified).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/snapshot");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("live adapter marks an unverified snapshot and refuses a regression", async () => {
    const bad = dataset("de");
    const seq = [freshDataset("de", Date.now(), 100), freshDataset("de", Date.now(), 50)];
    let i = 0;
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => seq[i++] })));
    const src = new LiveImpactSource();
    expect((await src.load()).verified).toBe(true);
    await expect(src.load()).rejects.toThrow(/regression/i);
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => bad })));
    expect((await new LiveImpactSource().load()).verified).toBe(false);
  });

  it("live adapter turns HTTP failure into an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
    await expect(new LiveImpactSource().load()).rejects.toThrow(/HTTP 503/);
  });

  it("preview adapter is labelled, never verified, and tags the authored origin", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => demo })));
    const load = await new PreviewImpactSource("de").load();
    expect(load.verified).toBe(false);
    expect(load.dataset?.origin["MTR-26031"].kind).toBe(origin("de")["MTR-26031"].kind);
    go(LIST);
    render(<ImpactApp source={new PreviewImpactSource("de")} />);
    expect(await screen.findByTestId("impact-banner")).toHaveTextContent(/not a live ledger and nothing here is current/);
    expect(screen.getByTestId("dataset-note")).toHaveTextContent(/MTR-26031 authored link edit/i);
  });

  it("preview adapter refuses unknown datasets and foreign documents", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => demo })));
    await expect(new PreviewImpactSource("nope").load()).rejects.toThrow(/Unknown preview dataset/);
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ kind: "x" }) })));
    await expect(new PreviewImpactSource("de").load()).rejects.toThrow(/not the impact-graph/);
  });
});

describe("large graph", () => {
  it("draws a window of motors and keeps every record in the list", async () => {
    const big = scaleSnapshot(freshDataset(), 1500).snap;
    const load: ImpactLoad = { snap: big, verified: true, reason: "", leaseMs: 60_000 };
    go(GRAPH);
    render(<ImpactApp source={new Scripted(true, [load])} />);
    const note = await screen.findByTestId("impact-window");
    expect(note).toHaveTextContent(/too many to draw at once/);
    expect(screen.getAllByTestId("impact-node").length).toBeLessThan(DRAW_CAP);
    expect(screen.getAllByTestId("impact-node").length).toBeGreaterThan(0);
    act(() => go(LIST));
    const table = await screen.findByTestId("impact-list");
    expect(within(table).getAllByRole("row").length).toBeLessThanOrEqual(101);
    expect(screen.getByRole("button", { name: /more of \d+ remaining/ })).toBeInTheDocument();
  }, 60_000);
});
