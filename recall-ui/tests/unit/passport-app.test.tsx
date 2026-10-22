import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PassportApp } from "../../src/passport/PassportApp";
import { LivePassportSource, PreviewPassportSource, type PassportLoad, type PassportSource } from "../../src/passport/passportSource";
import { FORBIDDEN, freshSnapshot, previewSnapshot } from "./passportHelpers";

const PAGE = "http://127.0.0.1:4173/passport.html";

function scripted(loads: Array<PassportLoad | Error>, live = true): PassportSource & { calls: number } {
  const src = {
    label: "scripted source", live, calls: 0,
    async load() {
      const next = loads[Math.min(src.calls, loads.length - 1)];
      src.calls++;
      if (next instanceof Error) throw next;
      return next;
    },
  };
  return src;
}
const verified = (): PassportLoad => ({ snap: freshSnapshot(), verified: true, reason: "", leaseMs: 4000 });
const unverified = (reason = "Current verification unavailable: trusted external anchor required."): PassportLoad => ({ snap: previewSnapshot(), verified: false, reason, leaseMs: 0 });
const go = (hash: string) => { window.location.hash = hash; };

beforeEach(() => { go("#/passport/MTR-26004"); });
afterEach(() => { cleanup(); Object.defineProperty(document, "hidden", { value: false, configurable: true }); vi.restoreAllMocks(); });

describe("passport page", () => {
  it("shows identity, components and the recall card for a verified live snapshot", async () => {
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByRole("heading", { name: /Digital product passport · MTR-26004/ })).toBeInTheDocument();
    expect(screen.getByText("Synthetic demonstration data")).toBeInTheDocument();
    expect(await screen.findByTestId("recall-current")).toBeInTheDocument();
    expect(screen.queryByTestId("passport-banner")).toBeNull();
  });

  it("withholds recall status and labels records when verification is unavailable", async () => {
    render(<PassportApp source={scripted([unverified()])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findAllByText("Current recall status unavailable")).not.toHaveLength(0);
    expect(screen.queryByTestId("recall-current")).toBeNull();
    expect(screen.getByTestId("passport-banner")).toHaveTextContent(/not currently verified/i);
    expect(document.body.textContent).not.toMatch(/RELEASE_ELIGIBLE|RECALL_HOLD|No recall hold recorded/);
  });

  it("never presents a historical release as current: unverified exclusion shows nothing about clearance", async () => {
    go("#/passport/MTR-26003/recall");
    render(<PassportApp source={scripted([unverified("stale")])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByTestId("recall-unavailable")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/No recall hold recorded|Excluded|eligible/i);
  });

  it("wording for a verified exclusion is a recall statement, not an authorization", async () => {
    go("#/passport/MTR-26003/recall");
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    const card = await screen.findByTestId("recall-current");
    expect(card).toHaveTextContent("No recall hold recorded under this policy");
    expect(card).toHaveTextContent(/not shipment authorization/);
  });

  it("withdraws recall status and marks records stale when the backend fails after a good load", async () => {
    const src = scripted([verified(), new Error("Failed to fetch")]);
    render(<PassportApp source={src} pageUrl={PAGE} pollMs={30} />);
    expect(await screen.findByTestId("recall-current")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("recall-current")).toBeNull());
    expect(screen.getByTestId("passport-banner")).toHaveTextContent(/may be outdated/i);
    expect(screen.getAllByText("Current recall status unavailable").length).toBeGreaterThan(0);
  });

  it("shows an error and no content (no fixture substitution) when the first load fails", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(<PassportApp source={scripted([new Error("Ledger unavailable: HTTP 409")])} pageUrl={PAGE} pollMs={100000} />);
    const err = await screen.findByTestId("load-error");
    expect(err).toHaveTextContent(/no fixture data is substituted/);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: /MTR-26004/ })).toBeNull();
    vi.unstubAllGlobals();
  });

  it("withdraws recall status immediately when the tab is hidden and requires a new verified snapshot", async () => {
    const src = scripted([verified(), verified()]);
    render(<PassportApp source={src} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByTestId("recall-current")).toBeInTheDocument();
    act(() => { Object.defineProperty(document, "hidden", { value: true, configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
    await waitFor(() => expect(screen.queryByTestId("recall-current")).toBeNull());
    act(() => { Object.defineProperty(document, "hidden", { value: false, configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
    expect(await screen.findByTestId("recall-current")).toBeInTheDocument();
    expect(src.calls).toBeGreaterThanOrEqual(2);
  });

  it("lets the lease expire without a new snapshot", async () => {
    const short = { ...verified(), leaseMs: 60 };
    render(<PassportApp source={scripted([short])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByTestId("recall-current")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("recall-current")).toBeNull(), { timeout: 2000 });
    expect(screen.getAllByText("Current recall status unavailable").length).toBeGreaterThan(0);
  });

  it("never shows recall status for a preview source, even if flagged verified", async () => {
    const src = scripted([verified()], false);
    render(<PassportApp source={src} pageUrl={PAGE} pollMs={100000} />);
    expect((await screen.findAllByText("Current recall status unavailable")).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("recall-current")).toBeNull();
  });
});

describe("routes and states", () => {
  it("rejects a malformed identifier without a QR", async () => {
    go("#/passport/MTR-1%3Fx");
    render(<PassportApp source={scripted([unverified()])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByTestId("invalid-id")).toBeInTheDocument();
    expect(screen.queryByTestId("qr-svg")).toBeNull();
  });
  it("reports an unknown motor without showing another motor", async () => {
    go("#/passport/MTR-99999");
    render(<PassportApp source={scripted([unverified()])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByTestId("unknown-unit")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/MTR-26004/);
  });
  it("lists passports on the index and links to each", async () => {
    go("#/");
    render(<PassportApp source={scripted([unverified()])} pageUrl={PAGE} pollMs={100000} />);
    const link = await screen.findByRole("link", { name: "MTR-26004" });
    expect(link).toHaveAttribute("href", "#/passport/MTR-26004");
  });
});

describe("interactive views", () => {
  it("expands replacement history with keyboard and shows the removed bearing as historical", async () => {
    go("#/passport/MTR-26004/components");
    const user = userEvent.setup();
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    const btn = await screen.findByRole("button", { name: /Show replacement history \(1\)/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    btn.focus();
    await user.keyboard("{Enter}");
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("Removed (historical)")).toBeInTheDocument();
    expect(screen.getAllByText("Currently recorded claim").length).toBeGreaterThanOrEqual(2);
  });

  it("drills from a claim to its event, source claim and hashes", async () => {
    go("#/passport/MTR-26004/evidence/urn%3Apramaan%3AMTR-26004%3AREWORK%3A2");
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    const d = await screen.findByTestId("evidence-detail");
    expect(within(d).getByText("urn:pramaan:MTR-26004:REWORK:2")).toBeInTheDocument();
    expect(d).toHaveTextContent("Rework station");
    expect(d).toHaveTextContent(/Capture SHA-256/);
    expect(d.textContent).toMatch(/[0-9a-f]{64}/);
    expect(d).toHaveTextContent(/Not a trusted time source/);
    expect(d).toHaveTextContent(/do not show who issued the record/);
  });

  it("filters the timeline and keeps gaps visible", async () => {
    go("#/passport/MTR-26004/timeline");
    const user = userEvent.setup();
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    const all = (await screen.findAllByText("View evidence")).length;
    await user.click(screen.getByRole("button", { name: "Shipment" }));
    expect(screen.getAllByText("View evidence").length).toBe(1);
    expect(all).toBeGreaterThan(5);
    expect(screen.getByRole("note")).toHaveTextContent(/No capture session recorded for the Assembly station/);
  });

  it("lists not-recorded and unverified items on the overview", async () => {
    go("#/passport/MTR-26006");
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    expect(await screen.findByText("No inspection recorded")).toBeInTheDocument();
    expect(screen.getByText("Assembly completion not recorded")).toBeInTheDocument();
    expect(screen.getByText("No shipment recorded")).toBeInTheDocument();
    expect(screen.getByText("No structured product specification recorded")).toBeInTheDocument();
  });

  it("shows the QR label with route-only text and the loopback warning", async () => {
    go("#/passport/MTR-26004/qr");
    render(<PassportApp source={scripted([verified()])} pageUrl={`${PAGE}?mode=preview#/passport/other`} pollMs={100000} />);
    expect(await screen.findByTestId("qr-svg")).toBeInTheDocument();
    expect(screen.getByTestId("qr-url")).toHaveTextContent("http://127.0.0.1:4173/passport.html#/passport/MTR-26004");
    expect(screen.getByText(/Scanning from another device will not work while this application is restricted to 127\.0\.0\.1/)).toBeInTheDocument();
    expect(screen.getByText(/link, not proof of authenticity/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print QR label" })).toBeInTheDocument();
  });

  it("has landmarks, a skip link and an operable section navigation", async () => {
    const user = userEvent.setup();
    render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
    await screen.findByRole("navigation", { name: "Passport sections" });
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toBeInTheDocument();
    const current = screen.getByRole("link", { name: "Overview" });
    expect(current).toHaveAttribute("aria-current", "page");
    await user.tab(); // skip link
    expect(document.activeElement).toHaveTextContent("Skip to content");
  });

  it("exposes no customer, destination or operator identifiers anywhere in any section", async () => {
    for (const tab of ["overview", "components", "evidence", "timeline", "recall", "qr"]) {
      go(`#/passport/MTR-26004/${tab}`);
      const { unmount } = render(<PassportApp source={scripted([verified()])} pageUrl={PAGE} pollMs={100000} />);
      await screen.findByRole("heading", { name: /MTR-26004/ });
      // Values must not appear. The words "customer"/"destination" may appear in the QR disclaimer.
      for (const f of FORBIDDEN.filter((x) => x !== "customer" && x !== "destination")) expect(document.body.textContent, `${tab} leaks ${f}`).not.toContain(f);
      unmount();
    }
  });
});

describe("read-only adapters", () => {
  it("live adapter issues only GET /api/snapshot and classifies results", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => structuredClone(freshSnapshot()) });
    vi.stubGlobal("fetch", fetchMock);
    const src = new LivePassportSource(500);
    const first = await src.load();
    expect(first.verified).toBe(true);
    for (const [url, init] of fetchMock.mock.calls) { expect(url).toBe("/api/snapshot"); expect(init.method).toBe("GET"); expect(init.body).toBeUndefined(); }
    // an unanchored snapshot is accepted as records but not as current recall status
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => structuredClone(previewSnapshot()) });
    const second = await src.load();
    expect(second.verified).toBe(false);
    expect(second.reason).toMatch(/anchor|expired|unavailable/i);
    vi.unstubAllGlobals();
  });
  it("live adapter withholds everything on regression and on HTTP failure", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const src = new LivePassportSource(500);
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => structuredClone(freshSnapshot(Date.now(), 100)) });
    await src.load();
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => structuredClone(freshSnapshot(Date.now(), 90)) });
    await expect(src.load()).rejects.toThrow(/regression/i);
    fetchMock.mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({}) });
    await expect(src.load()).rejects.toThrow(/HTTP 409/);
    vi.unstubAllGlobals();
  });
  it("live adapter times out a hung request and aborts transport", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_u: string, init: RequestInit) => { signal = init.signal as AbortSignal; return new Promise(() => {}); }));
    await expect(new LivePassportSource(30).load()).rejects.toThrow(/timed out/);
    expect(signal?.aborted).toBe(true);
    vi.unstubAllGlobals();
  });
  it("preview adapter is explicit, not live, and never claims verification", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => structuredClone(previewSnapshot()) }));
    const src = new PreviewPassportSource();
    expect(src.live).toBe(false);
    const load = await src.load();
    expect(load.verified).toBe(false);
    expect(load.reason).toMatch(/not a verified live ledger/);
    vi.unstubAllGlobals();
  });
});
