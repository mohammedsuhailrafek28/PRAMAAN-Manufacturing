import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecoveryWorkspace } from "../../src/views/RecoveryWorkspace";
import type { RecoveryApi, RecoveryStatus } from "../../src/domain/recovery";

const status = (over: Partial<RecoveryStatus> = {}): RecoveryStatus => ({
  mode: "STALE_CHECKPOINT_RECOVERY",
  checkpoint: { state: "ANCHORED_PREFIX_ONLY", anchoredSequence: 5, checkpointRequired: true, h2: "VERIFIED" },
  allowedActions: ["observe", "replace", "propose"], prohibitedActions: ["ship", "announce", "accept-checkpoint", "release"],
  custodyConfigured: true, notice: "n",
  heldMotors: [{ motor: "MTR-1", identityFindings: [{ source: "OBSERVATION", reason: "UNREGISTERED", slot: "NDE", lot: "ZZ-9", resembles: [] }], integrityFindings: [], quarantine: { status: "QUARANTINED_NOT_CLEARED", steps: [{ instruction: "Identify the bearing." }] } }],
  ...over,
});

describe("stale-checkpoint recovery workspace", () => {
  it("offers only capture, reconciliation and proposal, and never a shipment, release, acceptance or activation control", async () => {
    const api: RecoveryApi = { call: vi.fn(async () => ({ status: 200, body: { recovery: status() } })) };
    render(<RecoveryWorkspace api={api} motors={["MTR-1", "MTR-2"]} />);
    await screen.findByTestId("recovery-held");
    const text = screen.getAllByRole("button").map(b => b.textContent).join("|");
    expect(text).toMatch(/Record unverified sighting/);
    expect(text).toMatch(/Capture controlled replacement/);
    expect(text).toMatch(/Propose successor checkpoint \(not activated\)/);
    expect(text).not.toMatch(/ship|announce|accept|\bactivate\b|release|clear/i);
    expect(screen.getByTestId("recovery-workspace")).toHaveTextContent("No motor is cleared here");
    expect(screen.getByTestId("recovery-held")).toHaveTextContent("MTR-1");
  });

  it("calls only the whitelisted actions and shows containment and refusal from a proposal without implying acceptance", async () => {
    const calls: [string | null, unknown][] = [];
    const api: RecoveryApi = {
      call: vi.fn(async (action, body) => {
        calls.push([action, body]);
        if (action === "propose") return { status: 200, body: { recovery: status(), proposal: { status: "CANDIDATE_PROPOSED_NOT_ACTIVATED", candidate: "c", candidateSha256: "abc", review: { containedMotors: ["MTR-1"], refusedForIdentity: [], requiresAcknowledgement: ["MTR-1"] } } } };
        return { status: 200, body: { recovery: status() } };
      }),
    };
    render(<RecoveryWorkspace api={api} motors={["MTR-1"]} />);
    await screen.findByTestId("recovery-held");
    fireEvent.click(screen.getByTestId("recovery-propose"));
    const proposal = await screen.findByTestId("recovery-proposal");
    expect(proposal).toHaveTextContent("Contained, stays held: MTR-1");
    expect(proposal).toHaveTextContent("Refused (candidate cannot be accepted): none");
    expect(proposal).toHaveTextContent("operator actions outside this page");
    expect(calls.map(c => c[0]).filter(Boolean)).toEqual(["propose"]);
  });

  it("shows a refusal and nothing else when the server declines, and disables proposal without a custody directory", async () => {
    const api: RecoveryApi = { call: vi.fn(async (action) => action === null ? { status: 200, body: { recovery: status({ custodyConfigured: false }) } } : { status: 409, body: { error: "RECOVERY_NOT_APPLICABLE" } }) };
    render(<RecoveryWorkspace api={api} motors={["MTR-1"]} />);
    await screen.findByTestId("recovery-held");
    expect(screen.getByTestId("recovery-propose")).toBeDisabled();
    fireEvent.change(screen.getByTestId("recovery-sighting"), { target: { value: "QX-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Record unverified sighting" }));
    await waitFor(() => expect(screen.getByTestId("recovery-error")).toHaveTextContent("Refused (RECOVERY_NOT_APPLICABLE). Nothing was changed."));
  });
});
