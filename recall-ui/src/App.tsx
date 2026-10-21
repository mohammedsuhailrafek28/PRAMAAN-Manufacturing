import { useEffect, useState, useRef } from "react";
import { ProvenanceBar } from "./components/ProvenanceBar";
import type { RecallDataSource } from "./data/RecallDataSource";
import type { RecallSnapshot } from "./domain/types";
import { SnapshotValidationError, type ValidationIssue } from "./domain/validate";
import { Case06Comparison } from "./views/Case06Comparison";
import { FleetBoard } from "./views/FleetBoard";
import { LotInvestigationView } from "./views/LotInvestigation";
import { UnitDetail, type UnitTab } from "./views/UnitDetail";
import { ManufacturingWorkbench } from "./views/ManufacturingWorkbench";
import { verifyFreshness } from './data/freshness';

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
  const [verifiedAt, setVerifiedAt] = useState("");
  const [leaseValid, setLeaseValid] = useState(false);
  const busyRef = useRef(false);
  const generation = useRef(0);
  const leaseTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [lastSnap, setLastSnap] = useState<RecallSnapshot | null>(null);
  const previous = useRef<RecallSnapshot | null>(null);
  const renewLease = (snap: RecallSnapshot) => {
    const remaining = source.command ? verifyFreshness(snap, previous.current) : 5000;
    previous.current = snap;
    clearTimeout(leaseTimer.current);
    setLeaseValid(true); setVerifiedAt(snap.freshness?.verifiedAt ?? new Date().toISOString());
    if (source.command) leaseTimer.current=setTimeout(()=>{generation.current++;setLeaseValid(false);setState({status:'error',message:'Verification lease expired; historical release decisions are not currently verified'});},remaining);
  };

  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    let inFlight = false;
    const refresh = () => {
      if (inFlight || busyRef.current || (source.command && document.hidden)) return;
      inFlight = true;
      const gen = ++generation.current;
      source
      .load(ctl.signal)
      .then((snap) => {
        if (ctl.signal.aborted || gen !== generation.current) return;
        renewLease(snap);
        setPolicyId(p => snap.policies.some(s => s.policyId === p) ? p : snap.policies[0]?.policyId ?? "");
        setState({ status: "ready", snap }); setLastSnap(snap);
      })
      .catch((e: unknown) => {
        if (ctl.signal.aborted || gen !== generation.current) return;
        setLeaseValid(false);
        if (e instanceof SnapshotValidationError) setState({ status: "error", message: e.message, issues: e.issues });
        else setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
      }).finally(() => { inFlight=false; });
    };
    const resume = () => { generation.current++; setLeaseValid(false); if (!document.hidden) refresh(); };
    refresh();
    const interval = source.command ? setInterval(refresh, 2000) : undefined;
    if (source.command) document.addEventListener('visibilitychange', resume);
    return () => { ctl.abort(); clearInterval(interval); clearTimeout(leaseTimer.current); document.removeEventListener('visibilitychange', resume); };
  }, [source]);

  const route = parseRoute(hash);
  const run = async (path: string, body: Record<string, unknown>) => {
    if (!source.command || busy || !leaseValid) return;
    const gen = ++generation.current; busyRef.current=true; setLeaseValid(false);
    setBusy(true);
    const started = performance.now();
    try {
      const result = await source.command(path, body);
      if (gen !== generation.current) throw new Error('Capture response superseded; verify current evidence again');
      renewLease(result.snapshot);
      setPolicyId(result.snapshot.policies[0]?.policyId ?? "");
      setState({ status: "ready", snap: result.snapshot });
      setLastSnap(result.snapshot);
      requestAnimationFrame(() => setCaptureStatus(`Evidence captured. Backend capture-to-decision ${result.captureToDecisionMs.toFixed(1)} ms; browser request-to-render scheduled ${(performance.now()-started).toFixed(1)} ms.`));
    } catch (e) {
      // An interrupted capture can have durable partial evidence. Remove stale decisions.
      setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(false); busyRef.current=false; }
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
            {source.command && verifiedAt && <p>Last successful local verification: {verifiedAt}. Earlier decisions are historical evidence, not currently verified operational clearance.</p>}
            {source.command && lastSnap && <details><summary>Last recorded decisions — historical, not operational clearance</summary><ul>{Object.entries(lastSnap.decisions).flatMap(([motor,policies])=>Object.entries(policies).map(([policy,bundle])=><li key={`${motor}:${policy}`}>{motor}: recorded {bundle.current.evidenceFinding} / {bundle.current.operationalAction}. Historical only; current eligibility unavailable.</li>))}</ul></details>}
            <p><a href="/">Reload verified ledger</a></p>
            {state.issues && (
              <ul>{state.issues.slice(0, 20).map((i, k) => <li key={k}><code>{i.path}</code>: {i.message}</li>)}</ul>
            )}
          </div>
        )}
        {source.command && lastSnap && <ManufacturingWorkbench snap={lastSnap} run={run} busy={busy || state.status !== 'ready' || !leaseValid} />}
        {state.status === "ready" && (
          <>
            <ProvenanceBar snap={state.snap} policyId={policyId} onPolicy={setPolicyId} sourceLabel={source.label} />
            {source.command && <p role="status">{leaseValid ? `Verified with local synthetic backend at ${verifiedAt}; lease 5 seconds, refresh every 2 seconds.` : "Current decisions unavailable while evidence is being refreshed or captured."}</p>}
            {captureStatus && <p role="status" data-testid="capture-status">{captureStatus}</p>}
            {state.snap.notifications && state.snap.notifications.length > 0 && <section className="callout" aria-label="Notification obligations"><h2>Notification obligations</h2><p>PENDING. Resolution is disabled until an authenticated workflow is approved. Displaying a decision does not mark it communicated; no notifications are sent by this application.</p><ul>{state.snap.notifications.map(n => <li key={n.decisionId}><a href={`#/unit/${n.unitId}/history`}>{n.unitId}</a>: {n.reason}; if {n.appliesIfDecisionCommunicated} was communicated. Delivery: {n.deliveryStatus}. Acknowledgment: unknown.</li>)}</ul></section>}
            {(!source.command || leaseValid) && <>
              {route.page === "fleet" && <FleetBoard snap={state.snap} policyId={policyId} />}
              {route.page === "unit" && <UnitDetail snap={state.snap} unitId={route.unitId} policyId={policyId} tab={route.tab} />}
              {route.page === "lot" && <LotInvestigationView snap={state.snap} policyId={policyId} lotId={route.lotId} />}
              {route.page === "case06" && <Case06Comparison snap={state.snap} policyId={policyId} unitId={route.unitId} />}
            </>}
          </>
        )}
      </main>
    </>
  );
}
