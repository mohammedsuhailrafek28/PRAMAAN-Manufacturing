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
}

/** No automatic fixture fallback: a failed backend never supplies stale release decisions. */
export class BackendRecallDataSource implements RecallDataSource {
  readonly label = "Live SQLite ledger (synthetic manufacturing demo)";
  async load(signal?: AbortSignal): Promise<RecallSnapshot> {
    const res = await fetch("/api/snapshot", { signal, cache: "no-store" });
    if (!res.ok) throw new Error(`Ledger unavailable: HTTP ${res.status}`);
    return validateSnapshot(await res.json());
  }
  async command(path: string, body: Record<string, unknown>) {
    const session = await fetch("/api/session").then(r => r.json());
    const res = await fetch(`/api/${path}`, { method: "POST", headers: {
      "Content-Type": "application/json", "X-Pramaan-Token": session.token,
    }, body: JSON.stringify(body) });
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
