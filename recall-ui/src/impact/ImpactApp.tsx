import { useEffect, useRef, useState } from "react";
import { ImpactWorkspace, type Banner, type Mode } from "./ImpactWorkspace";
import type { ImpactLoad, ImpactSource } from "./impactSource";
import { parseRoute } from "./route";

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready" };

/**
 * Standalone, read-only impact graph. Recall status (findings, actions, scope) is a claim about the current
 * decision, so it is shown only while the live source reports a freshly verified snapshot whose lease has not
 * expired. Otherwise the recorded genealogy may still be shown, labelled not current, with all recall status
 * withheld. A failed refresh withdraws everything; no fixture is substituted in live mode.
 */
export function ImpactApp({ source, pollMs = 2000, datasetLinks }: { source: ImpactSource; pollMs?: number; datasetLinks?: Array<{ id: string; label: string; href: string }> }) {
  const [hash, setHash] = useState(() => window.location.hash);
  const [state, setState] = useState<State>({ status: "loading" });
  const [last, setLast] = useState<ImpactLoad | null>(null);
  const [leaseOk, setLeaseOk] = useState(false);
  const [lastError, setLastError] = useState("");
  const lease = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0);

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

  const live = source.live;
  const route = parseRoute(hash);
  const verifiedNow = live && leaseOk && last?.verified === true && !lastError;
  const mode: Mode = !live ? "preview" : verifiedNow ? "current" : "noncurrent";
  // After a failed refresh nothing from the earlier snapshot is shown: its genealogy is not re-presented as a result.
  const showData = last !== null && !lastError;

  const why = lastError
    ? `The backend could not be reached or verified (${lastError}).`
    : last && !last.verified ? last.reason || "Current verification is unavailable." : "The verification lease expired; waiting for a new verified snapshot.";
  let banner: Banner | null = null;
  if (!live && last) banner = { kind: "preview", text: `${last.dataset?.note ?? ""} This is not a live ledger and nothing here is current.`.trim() };
  else if (mode === "noncurrent") banner = { kind: "noncurrent", text: `${why} Recall status is withheld.` };

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="top">
        <h1>Recall impact graph</h1>
        <nav aria-label="Primary"><a href="./index.html">Recall investigation console</a><a href="#/">Impact graph</a></nav>
      </header>
      <main id="main" tabIndex={-1}>
        {state.status === "loading" && <p role="status">Loading ledger data…</p>}
        {state.status === "error" && (
          <div role="alert" className="error-panel" data-testid="load-error">
            <h2>The impact graph is unavailable</h2>
            <p>{state.message}. Nothing is drawn, and no fixture data is substituted.</p>
          </div>
        )}
        {state.status === "ready" && lastError && (
          <div role="alert" className="error-panel" data-testid="withdrawn">
            <h2>The impact graph is withdrawn</h2>
            <p>{why} The earlier graph and recall status are not shown, because they can no longer be tied to a verified ledger.</p>
          </div>
        )}
        {state.status === "ready" && showData && route.page === "invalid" && (
          <p className="warn" role="alert" data-testid="invalid-route">“{route.raw}” is not a valid impact-graph address. <a href="#/">Back to the lot list</a></p>
        )}
        {state.status === "ready" && showData && last && route.page !== "invalid" && (
          <ImpactWorkspace
            key={`${mode}`} snap={last.snap} route={route} mode={mode} banner={banner}
            datasetNote={!live && last.dataset ? (
              <div className="callout" data-testid="dataset-note">
                <strong>Preview dataset:</strong>{" "}
                {datasetLinks?.map((s, i) => <span key={s.id}>{i > 0 && " · "}{s.id === last.dataset?.id ? <strong>{s.label}</strong> : <a href={s.href}>{s.label}</a>}</span>)}
                {last.dataset.authoredScale ? <p className="muted">{last.dataset.note}</p> : (
                  <p className="muted">Units are tagged by origin: {Object.entries(last.dataset.origin).map(([u, o]) => `${u} ${o.kind.toLowerCase().replace(/_/g, " ")}`).join("; ")}.</p>
                )}
              </div>
            ) : undefined}
          />
        )}
      </main>
    </>
  );
}
