import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionExplanation } from "../../src/views/DecisionExplanation";
import { ProvenanceBar } from "../../src/components/ProvenanceBar";
import { realSnapshot } from "./helpers";

describe("v1.1 guards display", () => {
  it("shows an interrupted operation as its own integrity hold, not as a lot-identity problem", () => {
    const s = realSnapshot();
    const unit = s.units[0];
    const d = structuredClone(Object.values(s.decisions[unit.unitId])[0].current);
    d.evaluatorOperationalAction = "RELEASE_ELIGIBLE";
    d.operationalAction = "RECALL_HOLD";
    d.integrityGuard = {
      status: "OPERATION_INTERRUPTED", evaluatorOperationalAction: "RELEASE_ELIGIBLE", guardChangedAction: true,
      findings: [{ eventId: "e1", workOrderId: "BUILD-MTR-1", orderType: "BUILD", source: "OPERATION", reason: "OPERATION_INTERRUPTED", detail: "x" }],
    };
    render(<DecisionExplanation d={d} unit={unit} />);
    const box = screen.getByTestId("integrity-guard");
    expect(box).toHaveTextContent("Operation interrupted: held");
    expect(box).toHaveTextContent("not a lot-identity problem");
    expect(box).toHaveTextContent("retrying is refused on purpose");
    expect(box).toHaveTextContent("BUILD-MTR-1");
    expect(screen.queryByTestId("identity-guard")).toBeNull();
  });

  it("shows quarantine as never implying clearance, with remediation options", () => {
    const s = realSnapshot();
    const unit = s.units[0];
    const d = structuredClone(Object.values(s.decisions[unit.unitId])[0].current);
    d.quarantine = {
      status: "QUARANTINED_NOT_CLEARED", clearance: "NEVER_IMPLIED", note: "Derived from recorded events; writes nothing.", blockedPaths: "Investigation records do not clear a motor.",
      steps: [{ slot: "NDE", reason: "SENTINEL", option: "CONTROLLED_REPLACEMENT", instruction: "Replace the bearing in this slot." }],
    };
    render(<DecisionExplanation d={d} unit={unit} />);
    const box = screen.getByTestId("quarantine");
    expect(box).toHaveTextContent("Quarantined, not cleared");
    expect(box).toHaveTextContent("never implies clearance");
    expect(box).toHaveTextContent("Controlled replacement");
  });

  it("warns that the registry is not bound to the accepted checkpoint and says it is a same-host check", () => {
    const s = realSnapshot();
    const reg = { registryId: "R", version: 1, digest: "d", entryCount: 1 };
    s.lotIdentity = {
      registry: { ...reg, provenance: "LOCALLY_AUTHORED_SYNTHETIC", administeredBy: "m", trustStatement: "t" }, motors: {}, recallPolicyFindings: [],
      registryBinding: { status: "DISCREPANCY", detail: "the live registry differs", custodyNote: "n", live: reg, bound: reg, changes: [{ change: "ENTRY_ADDED", lot: "LEG-777" }] },
    };
    render(<ProvenanceBar snap={s} policyId={s.policies[0].policyId} onPolicy={() => {}} sourceLabel="test" />);
    const w = screen.getByTestId("registry-binding-warning");
    expect(w).toHaveTextContent("Registry not bound to the accepted checkpoint");
    expect(w).toHaveTextContent("No motor is release eligible");
    expect(w).toHaveTextContent("not independent verification");
  });
});
