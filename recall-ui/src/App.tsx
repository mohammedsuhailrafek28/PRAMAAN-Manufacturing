import { useEffect, useState } from "react";
import { ProvenanceBar } from "./components/ProvenanceBar";
import type { RecallDataSource } from "./data/RecallDataSource";
import type { RecallSnapshot } from "./domain/types";
import { SnapshotValidationError, type ValidationIssue } from "./domain/validate";
import { Case06Comparison } from "./views/Case06Comparison";
import { FleetBoard } from "./views/FleetBoard";
import { LotInvestigationView } from "./views/LotInvestigation";
import { UnitDetail, type UnitTab } from "./views/UnitDetail";
import { ManufacturingWorkbench } from "./views/ManufacturingWorkbench";

type State =
  | { status: "loading" }
  | { status: "error"; message: string; issues?: ValidationIssue[] }
  | { status: "ready"; snap: RecallSnapshot };

type Route =
  | { page: "fleet" }
  | { page: "unit"; unitId: string; tab: UnitTab }
  | { page: "lot"; lotId: string }
  | { page: "case06"; unitId: string };

const TABS: UnitTab[] = ["decision", "genealogy", "history", "events"];

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "unit" && parts[1]) {
    const tab = TABS.includes(parts[2] as UnitTab) ? (parts[2] as UnitTab) : "decision";
    return { page: "unit", unitId: parts[1], tab };
  }
  if (parts[0] === "lot") return { page: "lot", lotId: parts[1] ?? "BR-204" };
  if (parts[0] === "case06") return { page: "case06", unitId: parts[1] ?? "case-06" };
  return { page: "fleet" };
}

export function App({ source }: { source: RecallDataSource }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [policyId, setPolicyId] = useState("RC-009/P1");
  const [hash, setHash] = useState(() => window.location.hash);
  const [busy, setBusy] = useState(false);
  const [captureStatus, setCaptureStatus] = useState("");

  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    source
      .load(ctl.signal)
      .then((snap) => { setPolicyId(snap.policies[0]?.policyId ?? ""); setState({ status: "ready", snap }); })
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        if (e instanceof SnapshotValidationError) setState({ status: "error", message: e.message, issues: e.issues });
        else setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctl.abort();
  }, [source]);

  const route = parseRoute(hash);
  const run = async (path: string, body: Record<string, unknown>) => {
    if (!source.command || busy) return;
    setBusy(true);
    const started = performance.now();
    try {
      const result = await source.command(path, body);
      setPolicyId(result.snapshot.policies[0]?.policyId ?? "");
      setState({ status: "ready", snap: result.snapshot });
      requestAnimationFrame(() => setCaptureStatus(`Evidence captured. Backend capture-to-decision ${result.captureToDecisionMs.toFixed(1)} ms; browser request-to-render scheduled ${(performance.now()-started).toFixed(1)} ms.`));
    } catch (e) {
      // An interrupted capture can have durable partial evidence. Remove stale decisions.
      setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(false); }
  };
  const nav = (page: Route["page"], label: string, href: string) => (
    <a href={href} aria-current={route.page === page ? "page" : undefined}>{label}</a>
  );

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="top">
        <h1>Recall Investigation</h1>
        <nav aria-label="Primary">
          {nav("fleet", "Motors", "#/")}
          {nav("lot", "Lot investigation", "#/lot/BR-204")}
          {nav("case06", source.command ? "Case comparison" : "Case 06 before / after", "#/case06/case-06")}
          <a href={source.command ? "/?mode=fixtures" : "/"}>{source.command ? "Fixture demo mode" : "Live ledger mode"}</a>
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        {state.status === "loading" && (
          <div role="status" aria-live="polite" className="skeleton" data-testid="loading">
            <span className="sr-only">Loading recall decisions...</span>
            <div /><div /><div />
          </div>
        )}
        {state.status === "error" && (
          <div role="alert" className="error-panel" data-testid="load-error">
            <h2>{state.issues ? "The recall data failed validation" : "Recall data could not be loaded"}</h2>
            <p>{state.message}. No decisions are shown, because unvalidated data could mislead a release decision.</p>
            <p><a href="/">Reload verified ledger</a></p>
            {state.issues && (
              <ul>{state.issues.slice(0, 20).map((i, k) => <li key={k}><code>{i.path}</code>: {i.message}</li>)}</ul>
            )}
          </div>
        )}
        {state.status === "ready" && (
          <>
            <ProvenanceBar snap={state.snap} policyId={policyId} onPolicy={setPolicyId} sourceLabel={source.label} />
            {source.command && <ManufacturingWorkbench snap={state.snap} run={run} busy={busy} />}
            {captureStatus && <p role="status" data-testid="capture-status">{captureStatus}</p>}
            {state.snap.notifications && state.snap.notifications.length > 0 && <section className="callout" aria-label="Notification obligations"><h2>Notification obligations</h2><p>Conditional obligations from v3. Displaying a decision does not mark it communicated; no notifications are sent by this application.</p><ul>{state.snap.notifications.map(n => <li key={n.decisionId}><a href={`#/unit/${n.unitId}/history`}>{n.unitId}</a>: {n.reason}; if {n.appliesIfDecisionCommunicated} was communicated. Delivery: {n.deliveryStatus}.</li>)}</ul></section>}
            {route.page === "fleet" && <FleetBoard snap={state.snap} policyId={policyId} />}
            {route.page === "unit" && <UnitDetail snap={state.snap} unitId={route.unitId} policyId={policyId} tab={route.tab} />}
            {route.page === "lot" && <LotInvestigationView snap={state.snap} policyId={policyId} lotId={route.lotId} />}
            {route.page === "case06" && <Case06Comparison snap={state.snap} policyId={policyId} unitId={route.unitId} />}
          </>
        )}
      </main>
    </>
  );
}
