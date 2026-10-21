import type { RecallSnapshot } from "../domain/types";
import { validateSnapshot } from "../domain/validate";

/**
 * The only seam between the UI and wherever recall decisions come from.
 * Today: a fixture-backed snapshot produced by running the real engine (tools/export_snapshot.py).
 * Later: any implementation that returns the same RecallSnapshot (see README, integration contract).
 */
export interface RecallDataSource {
  readonly label: string;
  load(signal?: AbortSignal): Promise<RecallSnapshot>;
  command?(path: string, body: Record<string, unknown>): Promise<{ snapshot: RecallSnapshot; captureToDecisionMs: number }>;
  /** Cheap liveness + ledger-head probe. Absent for static fixtures, which are never "current operational status". */
  heartbeat?(signal?: AbortSignal): Promise<{ at: string; ledgerHead: { chainHead: string; links: number } }>;
}

/** Upper bound for any single backend request; a hung ledger must surface as an error, not a stale screen. */
export const REQUEST_TIMEOUT_MS = 8000;
const bounded = (signal?: AbortSignal) => {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
};

/** No automatic fixture fallback: a failed backend never supplies stale release decisions. */
export class BackendRecallDataSource implements RecallDataSource {
  readonly label = "Live SQLite ledger (synthetic manufacturing demo)";
  async load(signal?: AbortSignal): Promise<RecallSnapshot> {
    const res = await fetch("/api/snapshot", { signal: bounded(signal), cache: "no-store" });
    if (!res.ok) throw new Error(`Ledger unavailable: HTTP ${res.status}`);
    return validateSnapshot(await res.json());
  }
  async heartbeat(signal?: AbortSignal) {
    const res = await fetch("/api/heartbeat", { signal: bounded(signal), cache: "no-store" });
    if (!res.ok) throw new Error(`Ledger heartbeat failed: HTTP ${res.status}`);
    const body = await res.json();
    if (body?.status !== "OK" || typeof body.at !== "string" || typeof body.ledgerHead?.chainHead !== "string") throw new Error("Malformed ledger heartbeat");
    return { at: body.at as string, ledgerHead: body.ledgerHead as { chainHead: string; links: number } };
  }
  async command(path: string, body: Record<string, unknown>) {
    const session = await fetch("/api/session", { signal: bounded() }).then(r => r.json());
    const res = await fetch(`/api/${path}`, { method: "POST", headers: {
      "Content-Type": "application/json", "X-Pramaan-Token": session.token,
    }, body: JSON.stringify(body), signal: bounded() });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error ?? `Capture failed: HTTP ${res.status}`);
    return { snapshot: validateSnapshot(result.snapshot), captureToDecisionMs: Number(result.captureToDecisionMs) };
  }
}

export class FixtureSnapshotSource implements RecallDataSource {
  readonly label = "Fixture-backed snapshot";
  private url: string;
  private fetchImpl: typeof fetch;

  constructor(url?: string, fetchImpl?: typeof fetch) {
    this.url = url ?? `${import.meta.env.BASE_URL}data/snapshot.json`;
    this.fetchImpl = fetchImpl ?? ((...a) => fetch(...a));
  }

  async load(signal?: AbortSignal): Promise<RecallSnapshot> {
    const res = await this.fetchImpl(this.url, { signal });
    if (!res.ok) throw new Error(`Could not load ${this.url}: HTTP ${res.status}`);
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      throw new Error(`${this.url} is not valid JSON`);
    }
    return validateSnapshot(body);
  }
}
