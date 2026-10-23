import type { RecallSnapshot } from "../domain/types";
import { validateSnapshot } from "../domain/validate";
import { verifyFreshness } from './freshness';
import { GateTracker, GateWithheldError } from '../contract/gate';
import type { HistoricalView } from '../contract/gated';

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

/** The shared gate classified a well-formed non-current envelope (ANCHORED_PREFIX_ONLY / UNANCHORED).
 *  The console shows only the segregated historical facts it carries: never a decision, hold or clearance. */
export class SegregatedSnapshotError extends Error {
  constructor(readonly view: HistoricalView, readonly cause: "PREFIX_ONLY" | "UNANCHORED", reason: string) { super(reason); this.name = "SegregatedSnapshotError"; }
}

/** No automatic fixture fallback: a failed backend never supplies stale release decisions.
 *  Every live response passes the same typed gate as the standalone pages before anything is shown. */
export class BackendRecallDataSource implements RecallDataSource {
  private previous: RecallSnapshot | null = null;
  private generation = 0;
  private readonly tracker = new GateTracker();
  private accept(body: unknown, generation: number) {
    validateSnapshot(body);                                   // structural invariants first: "Invalid recall snapshot"
    if (generation !== this.generation) throw new Error('Superseded backend response');
    const gate = this.tracker.evaluate({ status: 200, body });
    if (gate.kind === "WITHHELD") throw new GateWithheldError(gate);
    if (gate.kind === "SEGREGATED") throw new SegregatedSnapshotError(gate.view, gate.cause, gate.reason);
    const snap = validateSnapshot(body);
    verifyFreshness(snap, this.previous);                     // lease length + regression bookkeeping for CURRENT only
    this.previous = snap;
    return snap;
  }
  readonly label = "Live SQLite ledger (synthetic manufacturing demo)";
  constructor(private timeoutMs = 4000) {}
  private async request(url: string, init: RequestInit = {}) {
    const ctl = new AbortController();
    const abort = () => ctl.abort();
    init.signal?.addEventListener("abort", abort, { once: true });
    if (init.signal?.aborted) ctl.abort();
    let timer: ReturnType<typeof setTimeout>;
    try {
      return await Promise.race([
        fetch(url, { ...init, signal: ctl.signal }).then(async res => ({ok:res.ok,status:res.status,body:typeof res.json === 'function' ? await res.json() : {}})),
        new Promise<{ok:boolean;status:number;body:unknown}>((_, reject) => { timer = setTimeout(() => { ctl.abort(); reject(new Error("Backend request timed out; capture outcome may be unknown. Reload verified evidence before retrying.")); }, this.timeoutMs); }),
      ]);
    } finally {
      clearTimeout(timer!);
      init.signal?.removeEventListener("abort", abort);
    }
  }
  async load(signal?: AbortSignal): Promise<RecallSnapshot> {
    const generation = ++this.generation;
    const res = await this.request("/api/snapshot", { signal, cache: "no-store" });
    if (!res.ok) {
      const gate = this.tracker.evaluate({ status: res.status, body: res.body });
      throw new Error(`Ledger unavailable: HTTP ${res.status}${gate.kind === "WITHHELD" ? `. ${gate.reason}` : ""}`);
    }
    return this.accept(res.body, generation);
  }
  async command(path: string, body: Record<string, unknown>) {
    const generation = ++this.generation;
    const session = (await this.request("/api/session")).body as {token:string};
    const res = await this.request(`/api/${path}`, { method: "POST", headers: {
      "Content-Type": "application/json", "X-Pramaan-Token": session.token,
    }, body: JSON.stringify(body) });
    const result = res.body as {error?:string;snapshot:unknown;captureToDecisionMs:number};
    if (!res.ok) throw new Error(result.error ?? `Capture failed: HTTP ${res.status}`);
    return { snapshot: this.accept(result.snapshot, generation), captureToDecisionMs: Number(result.captureToDecisionMs) };
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
