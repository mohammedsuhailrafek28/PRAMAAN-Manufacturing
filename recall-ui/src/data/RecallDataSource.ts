import type { RecallSnapshot } from "../domain/types";
import { validateSnapshot } from "../domain/validate";
import { verifyFreshness } from './freshness';

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
  private previous: RecallSnapshot | null = null;
  private generation = 0;
  private accept(body: unknown, generation: number) {
    const snap = validateSnapshot(body);
    if (!snap.checkpoint || !snap.eligibility) throw new Error('Strict checkpoint state and eligibility projection required');
    if (generation !== this.generation) throw new Error('Superseded backend response');
    verifyFreshness(snap, this.previous);
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
    if (!res.ok) throw new Error(`Ledger unavailable: HTTP ${res.status}`);
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
