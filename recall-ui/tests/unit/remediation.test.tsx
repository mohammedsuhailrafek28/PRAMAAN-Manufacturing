import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { BackendRecallDataSource, REQUEST_TIMEOUT_MS, type RecallDataSource } from "../../src/data/RecallDataSource";
import { NotificationObligations } from "../../src/views/NotificationObligations";
import { ManufacturingWorkbench } from "../../src/views/ManufacturingWorkbench";
import { realSnapshot } from "./helpers";
import { validateSnapshot } from "../../src/domain/validate";

beforeEach(() => { window.location.hash = ""; });
afterEach(() => vi.unstubAllGlobals());

const head = { chainHead: "h1", links: 1 };
const liveSource = (beat: () => Promise<{ at: string; ledgerHead: typeof head }>, snap = realSnapshot()): RecallDataSource => ({
  label: "live-ish", load: async () => validateSnapshot({ ...snap, ledgerHead: head, generatedAt: "2026-10-21T10:00:00Z" }), heartbeat: beat,
});

describe("stale data after backend failure (P1)", () => {
  it("marks decisions historical and not-current as soon as the heartbeat fails, and clears on recovery", async () => {
    let up = true;
    const source = liveSource(async () => { if (!up) throw new Error("connection refused"); return { at: "t", ledgerHead: head }; });
    render(<App source={source} heartbeatMs={20} />);
    await screen.findByRole("heading", { name: "Motor decisions" });
    expect(screen.queryByTestId("stale-banner")).toBeNull();
    expect(screen.getAllByTestId("chip-action")[0]).not.toHaveTextContent("Last recorded action");
    up = false;
    const banner = await screen.findByTestId("stale-banner");
    expect(banner).toHaveTextContent("not current operational status");
    expect(banner).toHaveTextContent("connection refused");
    expect(banner).toHaveTextContent("2026-10-21T10:00:00Z");
    expect(screen.getAllByTestId("chip-action")[0]).toHaveTextContent("Last recorded action");
    up = true;
    await waitFor(() => expect(screen.queryByTestId("stale-banner")).toBeNull());
  });

  it("reloads the snapshot when the ledger head moved instead of showing superseded decisions", async () => {
    let calls = 0;
    const source: RecallDataSource = {
      label: "x", heartbeat: async () => ({ at: "t", ledgerHead: { chainHead: "h2", links: 2 } }),
      load: async () => validateSnapshot({ ...realSnapshot(), ledgerHead: calls++ === 0 ? head : { chainHead: "h2", links: 2 } }),
    };
    render(<App source={source} heartbeatMs={20} />);
    await screen.findByRole("heading", { name: "Motor decisions" });
    await waitFor(() => expect(calls).toBeGreaterThan(1));
  });

  it("a fixture source (no heartbeat) never shows a stale banner or claims live status", async () => {
    render(<App source={{ label: "fixtures", load: async () => realSnapshot() }} heartbeatMs={10} />);
    await screen.findByRole("heading", { name: "Motor decisions" });
    await new Promise((r) => setTimeout(r, 60));
    expect(screen.queryByTestId("stale-banner")).toBeNull();
  });

  it("bounds every backend request with a timeout", async () => {
    const seen: Array<AbortSignal | undefined> = [];
    vi.stubGlobal("fetch", vi.fn((_u: string, init: RequestInit) => { seen.push(init.signal ?? undefined); return Promise.reject(new Error("net")); }));
    const src = new BackendRecallDataSource();
    await expect(src.load()).rejects.toThrow();
    await expect(src.heartbeat()).rejects.toThrow();
    expect(REQUEST_TIMEOUT_MS).toBeLessThanOrEqual(10_000);
    expect(seen.every((s) => s instanceof AbortSignal)).toBe(true);
  });

  it("rejects a malformed heartbeat", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "OK" }) }));
    await expect(new BackendRecallDataSource().heartbeat()).rejects.toThrow("Malformed");
  });
});

describe("recall scope control (P0)", () => {
  it("cannot announce until a bearing position is explicitly chosen, and sends exactly the chosen positions", async () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ManufacturingWorkbench snap={validateSnapshot(realSnapshot())} run={run} busy={false} />);
    await user.click(screen.getByText("Manufacturing capture workspace"));
    const button = screen.getByRole("button", { name: "Announce recall and evaluate" });
    expect(button).toBeDisabled();
    expect(screen.getByLabelText(/Drive end/)).not.toBeChecked();
    expect(screen.getByLabelText(/Non-drive end/)).not.toBeChecked();
    await user.click(screen.getByLabelText(/Non-drive end/));
    await user.click(button);
    expect(run).toHaveBeenCalledWith("recalls", { lot: "BR-204", slots: ["NDE"] });
    await user.click(screen.getByLabelText(/Drive end/));
    await user.click(button);
    expect(run).toHaveBeenLastCalledWith("recalls", { lot: "BR-204", slots: ["NDE", "DE"] });
  });
});

describe("notification obligations (P0)", () => {
  const snapWith = (status: "OPEN" | "RESOLVED") => ({
    ...realSnapshot(),
    notifications: [{ unitId: "MTR-1", obligationId: "OBL-1", decisionId: "D-1", required: true, reason: "PRIOR_EXCLUSION_WITHDRAWN",
      appliesIfDecisionCommunicated: "D-0", deliveryStatus: "NOT_SENT", status,
      resolution: status === "RESOLVED" ? { actor: "ROLE:QUALITY", resolution: "CORRECTION_COMMUNICATED_ATTESTED", note: "phoned", at: "2026-10-21T10:00:00Z", deliveryAcknowledged: false as const } : null }],
  });
  it("lists outstanding obligations with an explicit attestation form, never claiming delivery", async () => {
    const run = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<NotificationObligations snap={snapWith("OPEN")} run={run} busy={false} />);
    expect(screen.getByRole("heading", { name: /1 outstanding/ })).toBeInTheDocument();
    expect(screen.getByText(/no notifications are sent by this application/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Resolution note/), "Customer phoned");
    await user.click(screen.getByRole("button", { name: "Attest correction communicated" }));
    expect(run).toHaveBeenCalledWith("notifications/OBL-1/resolve", { resolution: "CORRECTION_COMMUNICATED_ATTESTED", note: "Customer phoned" });
  });
  it("shows resolved obligations as attested, not delivered", () => {
    render(<NotificationObligations snap={snapWith("RESOLVED")} run={vi.fn()} busy={false} />);
    expect(screen.getByRole("heading", { name: /0 outstanding/ })).toBeInTheDocument();
    expect(screen.getByTestId("obligation-resolved")).toHaveTextContent("not a delivery acknowledgement");
    expect(screen.queryByRole("button", { name: /Attest/ })).toBeNull();
  });
  it("offers no resolve control without a command-capable source (fixtures)", () => {
    render(<NotificationObligations snap={snapWith("OPEN")} busy={false} />);
    expect(screen.queryByRole("button", { name: /Attest/ })).toBeNull();
  });
});
