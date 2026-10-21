import { createContext, useContext } from "react";

export interface StaleInfo { since: string; reason: string; lastVerifiedAt: string | null; dataGeneratedAt: string | null }

/** Non-null while the live ledger cannot be reached: everything on screen is then a historical record. */
export const StaleContext = createContext<StaleInfo | null>(null);
export const useStale = () => useContext(StaleContext);

export function StaleBanner({ info }: { info: StaleInfo }) {
  return (
    <div role="alert" className="stale-banner" data-testid="stale-banner">
      <h2>Live ledger unreachable: this is not current operational status</h2>
      <p>
        Contact was lost at {info.since} ({info.reason}). Decisions below are <b>historical records</b>
        {info.dataGeneratedAt ? <> as of {info.dataGeneratedAt}</> : null}
        {info.lastVerifiedAt ? <>; last verified against the ledger at {info.lastVerifiedAt}</> : null}.
        New evidence may exist. Do not release, ship or clear any motor from this screen until the ledger is reachable again.
      </p>
    </div>
  );
}
