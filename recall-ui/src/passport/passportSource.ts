// Read-only data adapters for the passport. They only ever issue GET requests and never
// construct a mutation. The live adapter reuses the application's own snapshot validation and
// shared typed checkpoint/eligibility gate (src/contract/gate.ts); it never re-implements backend verification.
import { GateTracker } from "../contract/gate";
import { liveLoad } from "../contract/liveLoad";
import { makePreview, type PageView } from "../contract/gated";
import { validateSnapshot } from "../domain/validate";

export interface PassportLoad {
  /** GatedSnapshot (live CURRENT), HistoricalView (live SEGREGATED) or PreviewView (explicit preview). */
  view: PageView;
  reason: string;
  /** Remaining server lease in ms when verified, otherwise 0. */
  leaseMs: number;
}

export interface PassportSource {
  readonly label: string;
  readonly live: boolean;
  load(signal?: AbortSignal): Promise<PassportLoad>;
}

async function getJson(url: string, timeoutMs: number, signal?: AbortSignal): Promise<{ ok: boolean; status: number; body: unknown }> {
  const ctl = new AbortController();
  const abort = () => ctl.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) ctl.abort();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      fetch(url, { method: "GET", cache: "no-store", signal: ctl.signal }).then(async (res) => ({ ok: res.ok, status: res.status, body: res.ok ? await res.json() : null })),
      new Promise<never>((_, reject) => { timer = setTimeout(() => { ctl.abort(); reject(new Error("Backend request timed out.")); }, timeoutMs); }),
    ]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

/** Live backend. No fixture fallback: any failure is an error the page must show. */
export class LivePassportSource implements PassportSource {
  readonly label = "Live SQLite ledger (synthetic manufacturing demo)";
  readonly live = true;
  private tracker = new GateTracker();
  constructor(private timeoutMs = 4000) {}

  async load(signal?: AbortSignal): Promise<PassportLoad> {
    // Classification lives in the shared typed gate; this adapter never inspects error text.
    const r = await liveLoad(this.tracker, "/api/snapshot", this.timeoutMs, signal);
    return { view: r.view, reason: r.reason, leaseMs: r.leaseMs };
  }
}

/** Explicit, labelled preview from a captured synthetic snapshot. Never used implicitly. */
export class PreviewPassportSource implements PassportSource {
  readonly label = "Preview: captured synthetic snapshot (not a live ledger)";
  readonly live = false;
  constructor(private url = "./data/passport-preview.json") {}

  async load(signal?: AbortSignal): Promise<PassportLoad> {
    const res = await getJson(this.url, 4000, signal);
    if (!res.ok) throw new Error(`Could not load preview data: HTTP ${res.status}`);
    return { view: makePreview(validateSnapshot(res.body), this.label), reason: "Preview data is a captured synthetic snapshot, not a verified live ledger.", leaseMs: 0 };
  }
}
