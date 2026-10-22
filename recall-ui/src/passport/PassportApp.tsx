import { useEffect, useMemo, useRef, useState } from "react";
import { PassportExplorer, type PassportBanner } from "./PassportExplorer";
import type { PassportLoad, PassportSource } from "./passportSource";
import { buildPassport } from "./projection";
import { passportUrl } from "./qr";
import { parsePassportRoute } from "./route";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready" };

/**
 * Standalone passport page. It only reads. Recall context is shown solely while the source
 * reports a freshly verified snapshot whose lease has not expired; the tab being hidden
 * withdraws it until a new verified snapshot is accepted.
 */
export function PassportApp({ source, pageUrl = window.location.href, pollMs = 2000 }: { source: PassportSource; pageUrl?: string; pollMs?: number }) {
  const [hash, setHash] = useState(() => window.location.hash);
  const [state, setState] = useState<State>({ status: "loading" });
  const [last, setLast] = useState<PassportLoad | null>(null);
  const [recallOk, setRecallOk] = useState(false);
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
    const withdraw = () => { clearTimeout(lease.current); setRecallOk(false); };
    const refresh = () => {
      if (inFlight) return;
      inFlight = true;
      const gen = ++generation.current;
      source.load(ctl.signal).then((load) => {
        if (ctl.signal.aborted || gen !== generation.current) return;
        setState({ status: "ready" }); setLast(load); setLastError("");
        clearTimeout(lease.current);
        if (source.live && load.verified && !document.hidden) {
          setRecallOk(true);
          lease.current = setTimeout(() => setRecallOk(false), Math.max(0, load.leaseMs));
        } else setRecallOk(false);
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

  const route = parsePassportRoute(hash);
  const unitId = route.page === "passport" ? route.unitId : "";
  const verifiedNow = recallOk && last?.verified === true && !lastError;
  const reason = lastError
    ? `The backend could not be reached or verified (${lastError}). Current recall status is withheld.`
    : last && !last.verified ? last.reason || "Current verification unavailable." : "Verification lease expired; waiting for a new verified snapshot.";
  const passport = useMemo(
    () => (last && unitId ? buildPassport(last.snap, unitId, { recallVerified: verifiedNow, unavailableReason: `Current recall status unavailable. ${reason}` }) : null),
    [last, unitId, verifiedNow, reason],
  );

  let banner: PassportBanner | null = null;
  if (lastError && last) banner = { kind: "stale", text: `Last loaded from the backend; refresh failed (${lastError}). Nothing shown here is current.` };
  else if (last && !last.verified) banner = { kind: "unverified", text: last.reason };

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="top">
        <h1>Digital product passport</h1>
        <nav aria-label="Primary"><a href="./index.html">Recall investigation console</a><a href="#/">All passports</a></nav>
      </header>
      <main id="main" tabIndex={-1}>
        {state.status === "loading" && <p role="status">Loading passport data…</p>}
        {state.status === "error" && (
          <div role="alert" className="error-panel" data-testid="load-error">
            <h2>Passport data could not be loaded</h2>
            <p>{state.message}. No passport content is shown, and no fixture data is substituted.</p>
          </div>
        )}
        {last && route.page === "index" && (
          <div>
            {banner && <div className="callout callout-warn" role="status" data-testid="passport-banner">{banner.text}</div>}
            <h2>Motor passports</h2>
            <ul className="plain">{last.snap.units.map((u) => <li key={u.unitId}><a href={`#/passport/${encodeURIComponent(u.unitId)}`}>{u.unitId}</a> <span className="muted">{u.title}</span></li>)}</ul>
          </div>
        )}
        {route.page === "invalid" && <p className="warn" role="alert" data-testid="invalid-id">“{route.raw}” is not a valid motor identifier. No passport or QR code is generated. <a href="#/">All passports</a></p>}
        {last && route.page === "passport" && passport && (passport.found
          ? <PassportExplorer passport={passport} tab={route.tab} evidenceId={route.evidenceId} banner={banner} sourceLabel={source.label} qrUrl={passportUrl(route.unitId, pageUrl)} />
          : <p className="warn" role="alert" data-testid="unknown-unit">No motor {route.unitId} is recorded in this ledger. <a href="#/">All passports</a></p>)}
      </main>
    </>
  );
}
