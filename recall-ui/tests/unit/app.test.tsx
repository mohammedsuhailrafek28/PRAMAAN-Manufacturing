import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../src/App";
import type { RecallDataSource } from "../../src/data/RecallDataSource";
import { ActionChip, FindingChip, ReviewChip } from "../../src/components/StatusChips";
import { realSnapshot, sourceOf } from "./helpers";

const go = (hash: string) => { window.location.hash = hash; };
beforeEach(() => go(""));

describe("status chips", () => {
  it("shows finding, action and review as three separate text-labelled chips", () => {
    render(<><FindingChip finding="UNRESOLVED" /><ActionChip action="RECALL_HOLD" /><ReviewChip required /></>);
    expect(screen.getByTestId("chip-finding")).toHaveTextContent("Unresolved");
    expect(screen.getByTestId("chip-action")).toHaveTextContent("Recall hold");
    expect(screen.getByTestId("chip-review")).toHaveTextContent("Review required");
  });
});

describe("App states", () => {
  it("shows a loading state, then the fleet board", async () => {
    render(<App source={sourceOf(realSnapshot())} />);
    expect(screen.getByTestId("loading")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();
    expect(screen.getByText(/Synthetic fixtures/)).toBeInTheDocument();
  });

  it("refuses an invalid fixture and lists the problems instead of showing decisions", async () => {
    const bad: any = realSnapshot();
    bad.decisions["case-06"]["RC-009/P1"].current.operationalAction = "RELEASE_ELIGIBLE";
    render(<App source={sourceOf(bad)} />);
    const alert = await screen.findByTestId("load-error");
    expect(alert).toHaveTextContent("failed validation");
    expect(alert).toHaveTextContent(/contradict/);
    expect(screen.queryByRole("heading", { name: "Motor decisions" })).toBeNull();
  });

  it("shows a load error when the source fails", async () => {
    const failing: RecallDataSource = { label: "x", load: async () => { throw new Error("HTTP 500"); } };
    render(<App source={failing} />);
    expect(await screen.findByTestId("load-error")).toHaveTextContent("HTTP 500");
  });

  it("filters motors by evidence finding and switches policy", async () => {
    const user = userEvent.setup();
    render(<App source={sourceOf(realSnapshot())} />);
    await screen.findByRole("heading", { name: "Motor decisions" });
    await user.selectOptions(screen.getByLabelText("Evidence finding"), "UNRESOLVED");
    const rows = screen.getAllByTestId("chip-finding").filter((c) => c.closest("tbody"));
    expect(rows.length).toBeGreaterThan(0);
    rows.forEach((r) => expect(r).toHaveTextContent("Unresolved"));
    await user.selectOptions(screen.getByLabelText("Recall policy"), "RC-009/P2");
    expect(screen.getByLabelText("Recall policy")).toHaveValue("RC-009/P2");
  });
});

describe("investigation views", () => {
  it("explains a decision with reasons, ambiguity and capture gaps", async () => {
    go("#/unit/case-06/decision");
    render(<App source={sourceOf(realSnapshot())} />);
    expect(await screen.findByRole("heading", { name: /Slot attribution and ambiguity/ })).toBeInTheDocument();
    expect(screen.getByText(/Ambiguous: not cleared/)).toBeInTheDocument();
    expect(screen.getByText("Ambiguous slot attribution")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Slot evidence and capture gaps/ })).toBeInTheDocument();
  });

  it("shows supersession and the notification obligation in decision history", async () => {
    go("#/unit/case-05/history");
    render(<App source={sourceOf(realSnapshot())} />);
    expect(await screen.findByText(/Superseded by v2/)).toBeInTheDocument();
    const note = screen.getByText(/Notification obligation/).closest("div")!;
    expect(note).toHaveTextContent(/no longer stands/);
  });

  it("warns when a decision cites events missing from the log", async () => {
    const s: any = realSnapshot();
    s.decisions["case-01"]["RC-009/P1"].current.evidenceEventIds.push("GHOST-1");
    go("#/unit/case-01/decision");
    render(<App source={sourceOf(s)} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Incomplete evidence.*GHOST-1/);
  });

  it("reports an unknown unit instead of crashing", async () => {
    go("#/unit/case-99");
    render(<App source={sourceOf(realSnapshot())} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("case-99 is not in the snapshot");
  });

  it("renders the genealogy graph with a table alternative", async () => {
    go("#/unit/case-06/genealogy");
    render(<App source={sourceOf(realSnapshot())} />);
    const svg = await screen.findByRole("img", { name: /Genealogy of case-06/ });
    expect(svg).toBeInTheDocument();
    expect(screen.getByText("Genealogy as a table")).toBeInTheDocument();
  });

  it("lot investigation lists motors holding the recalled lot", async () => {
    go("#/lot/BR-204");
    render(<App source={sourceOf(realSnapshot())} />);
    expect(await screen.findByText("This lot is named by the recall.")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("link").length).toBeGreaterThan(0);
  });

  it("case 06 comparison reads original EXCLUDED versus current UNRESOLVED from the data", async () => {
    go("#/case06/case-06");
    render(<App source={sourceOf(realSnapshot())} />);
    const before = await screen.findByRole("region", { name: "Before: original engine" });
    const after = screen.getByRole("region", { name: "After: current engine" });
    expect(within(before).getByTestId("chip-finding")).toHaveTextContent("Excluded with evidence");
    expect(within(before).getByTestId("safety")).toHaveTextContent("False release");
    expect(within(after).getByTestId("chip-finding")).toHaveTextContent("Unresolved");
    expect(within(after).getByTestId("chip-action")).toHaveTextContent("Recall hold");
    await waitFor(() => expect(screen.getByTestId("false-release-summary")).toHaveTextContent(/with the current engine/));
    expect(screen.getByTestId("attribution")).toHaveTextContent(/also matches/);
  });
});
