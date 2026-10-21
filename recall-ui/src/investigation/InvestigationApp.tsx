import { useEffect, useMemo, useRef, useState } from "react";
import { diffViews, hasChanges, type ViewChanges } from "./diff";
import { InvestigationWorkspace, type Banner } from "./InvestigationWorkspace";
import type { InvestigationLoad, InvestigationSource } from "./investigationSource";
import { buildInvestigation, type InvestigationView } from "./projection";
import { parseRoute } from "./route";

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready" };

/**
 * Standalone, read-only investigation page. Current investigation claims are shown only while the
 * source reports a freshly verified snapshot whose lease has not expired. A failed refresh, an
 * unverified snapshot, a hidden tab or an expired lease withdraws every task. Nothing is cached
 * across a withdrawal and no fixture is substituted in live mode.
 */
export function InvestigationApp({ source, pollMs = 2000, stageLinks }: { source: InvestigationSource; pollMs?: number; stageLinks?: Array<{ id: string; label: string; href: string }> }) {
  const [hash, setHash] = useState(() => window.location.hash);
  const [state, setState] = useState<State>({ status: "loading" });
  const [last, setLast] = useState<InvestigationLoad | null>(null);
  const [leaseOk, setLeaseOk] = useState(false);
  const [lastError, setLastError] = useState("");
  const [changes, setChanges] = useState<ViewChanges | null>(null);
  const lease = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0);
  const lastVerified = useRef<InvestigationView | null>(null);

  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    let inFlight = false;
    const withdraw = () => { clearTimeout(lease.current); setLeaseOk(false); };
    const refresh = () => {
      if (inFlight) return;
      inFlight = true;
      const gen = ++generation.current;
      source.load(ctl.signal).then((load) => {
        if (ctl.signal.aborted || gen !== generation.current) return;
        setState({ status: "ready" }); setLast(load); setLastError("");
        clearTimeout(lease.current);
        if (source.live && load.verified && !document.hidden) {
          setLeaseOk(true);
          lease.current = setTimeout(() => setLeaseOk(false), Math.max(0, load.leaseMs));
        } else setLeaseOk(false);
      }).catch((e: unknown) => {
        if (ctl.signal.aborted || gen !== generation.current) return;
        withdraw();
        const message = e instanceof Error ? e.message : String(e);
        setLastError(message);
        setState((s) => (s.status === "ready" ? s : { status: "error", message }));
      }).finally(() => { inFlight = false; });
    };
    const onVisibility = () => { withdraw(); if (!document.hidden) refresh(); };
    refresh();
    const timer = source.live ? setInterval(refresh, pollMs) : undefined;
    document.addEventListener("visibilitychange", onVisibility);
    return () => { ctl.abort(); clearInterval(timer); clearTimeout(lease.current); document.removeEventListener("visibilitychange", onVisibility); };
  }, [source, pollMs]);

  const view = useMemo(() => (last ? buildInvestigation(last.snap) : null), [last]);
  const previewBase = useMemo(() => (last?.previous ? buildInvestigation(last.previous) : null), [last]);
  const live = source.live;
  const showCurrent = live && leaseOk && last?.verified === true && !lastError && view !== null;
  const showPreview = !live && view !== null && !lastError;

  // Record what changed between verified projections; only a verified, shown view counts.
  useEffect(() => {
    if (!view) return;
    if (showCurrent) {
      const prev = lastVerified.current;
      if (prev && prev !== view) {
        const d = diffViews(prev, view);
        if (hasChanges(d)) setChanges(d);
      }
      lastVerified.current = view;
    } else if (showPreview && previewBase) {
      setChanges(diffViews(previewBase, view));
    }
  }, [view, previewBase, showCurrent, showPreview]);

  const route = parseRoute(hash);
  const reason = lastError
    ? `The backend could not be reached or verified (${lastError}).`
    : last && !last.verified ? last.reason || "Current verification unavailable." : "The verification lease expired; waiting for a new verified snapshot.";
  const w = lastVerified.current?.watermark;

  let banner: Banner | null = null;
  if (!live && last) banner = { kind: "preview", text: `${last.stage?.authoredNote ?? ""} This is not a live ledger and nothing here is current.`.trim() };

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="top">
        <h1>Evidence-guided investigation</h1>
        <nav aria-label="Primary"><a href="./index.html">Recall investigation console</a><a href="#/">Investigation workspace</a></nav>
      </header>
      <main id="main" tabIndex={-1}>
        {state.status === "loading" && <p role="status">Loading ledger data…</p>}
        {state.status === "error" && (
          <div role="alert" className="error-panel" data-testid="load-error">
            <h2>Investigation tasks are unavailable</h2>
            <p>{state.message}. No tasks are shown, and no fixture data is substituted.</p>
          </div>
        )}
        {state.status === "ready" && last && view && route.page === "invalid" && <p className="warn" role="alert" data-testid="invalid-route">“{route.raw}” is not a valid investigation address. <a href="#/">Back to all groups</a></p>}
        {state.status === "ready" && last && view && route.page !== "invalid" && (showCurrent || showPreview) && (
          <InvestigationWorkspace
            view={view} snap={last.snap} route={route} banner={banner} changes={changes} mode={showCurrent ? "current" : "preview"}
            stageNote={!live && last.stage ? (
              <div className="callout" data-testid="stage-note">
                <strong>Preview stage:</strong>{" "}
                {stageLinks?.map((s, i) => <span key={s.id}>{i > 0 && " · "}{s.id === last.stage?.id ? <strong>{s.label}</strong> : <a href={s.href}>{s.label}</a>}</span>)}
                <p className="muted">Units are tagged by origin: {Object.entries(last.stage.origin).map(([u, o]) => `${u} ${o.toLowerCase().replace(/_/g, " ")}`).join("; ")}.</p>
              </div>
            ) : undefined}
          />
        )}
        {state.status === "ready" && last && route.page !== "invalid" && !showCurrent && !showPreview && (
          <div role="alert" className="error-panel" data-testid="withdrawn">
            <h2>Current investigation tasks unavailable</h2>
            <p>{reason} Investigation tasks are withheld because they are claims about the current decision, and the decision cannot be verified now. No earlier task list is shown as current.</p>
            {w && <p className="muted">Last verified watermark this page accepted: journal sequence {w.sequence ?? "unknown"}, verified {w.verifiedAt ?? "unknown"}. It is not current.</p>}
          </div>
        )}
      </main>
    </>
  );
}
