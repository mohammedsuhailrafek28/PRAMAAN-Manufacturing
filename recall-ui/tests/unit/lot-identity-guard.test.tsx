import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionExplanation } from "../../src/views/DecisionExplanation";
import { ProvenanceBar } from "../../src/components/ProvenanceBar";
import { realSnapshot } from "./helpers";

describe("lot-identity guard display", () => {
  it("shows evaluator output and the guarded action separately and never as release", () => {
    const s = realSnapshot();
    const unit = s.units[0];
    const d = structuredClone(Object.values(s.decisions[unit.unitId])[0].current);
    d.evaluatorOperationalAction = "RELEASE_ELIGIBLE";
    d.operationalAction = "RECALL_HOLD";
    d.identityGuard = {
      status: "IDENTITY_NOT_ESTABLISHED", evaluatorOperationalAction: "RELEASE_ELIGIBLE", evaluatorEvidenceFinding: "EXCLUDED_WITH_EVIDENCE", guardChangedAction: true,
      findings: [{ eventId: "e1", slot: "DE", lot: "BR-2O4", source: "INSTALL", reason: "UNREGISTERED", detail: "not in the registry", resembles: ["BR-204"] }],
    };
    render(<DecisionExplanation d={d} unit={unit} />);
    const box = screen.getByTestId("identity-guard");
    expect(box).toHaveTextContent("Lot identity not established");
    expect(box).toHaveTextContent("changed the operational action to Recall hold");
    expect(box).toHaveTextContent("BR-2O4");
    expect(box).toHaveTextContent("resembles registered lot BR-204");
    expect(screen.queryByText(/Release eligible/i, { selector: "[data-testid=chip-action]" })).toBeNull();
  });

  it("states the registry is locally authored and proves nothing about physical identity", () => {
    const s = realSnapshot();
    s.lotIdentity = { registry: { registryId: "R", version: 1, digest: "d", provenance: "LOCALLY_AUTHORED_SYNTHETIC", administeredBy: "m", trustStatement: "t", entryCount: 1 }, motors: {}, recallPolicyFindings: [] };
    render(<ProvenanceBar snap={s} policyId={s.policies[0].policyId} onPolicy={() => {}} sourceLabel="test" />);
    expect(screen.getByTestId("lot-registry-note")).toHaveTextContent("locally authored synthetic");
    expect(screen.getByTestId("lot-registry-note")).toHaveTextContent("does not prove");
  });
});
