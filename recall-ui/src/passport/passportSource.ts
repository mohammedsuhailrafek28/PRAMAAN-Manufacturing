// Read-only data adapters for the passport. They only ever issue GET requests and never
// construct a mutation. The live adapter reuses the application's own snapshot validation and
// verifyFreshness boundary (unchanged); it neither weakens nor re-implements it.
import { verifyFreshness } from "../data/freshness";
import type { RecallSnapshot } from "../domain/types";
import { validateSnapshot } from "../domain/validate";

export interface PassportLoad {
  snap: RecallSnapshot;
  /** True only when verifyFreshness accepted this snapshot just now. */
  verified: boolean;
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
  private previous: RecallSnapshot | null = null;
  constructor(private timeoutMs = 4000) {}

  async load(signal?: AbortSignal): Promise<PassportLoad> {
    const res = await getJson("/api/snapshot", this.timeoutMs, signal);
    if (!res.ok) throw new Error(`Ledger unavailable: HTTP ${res.status}`);
    const snap = validateSnapshot(res.body);
    try {
      const leaseMs = verifyFreshness(snap, this.previous);
      this.previous = snap;
      return { snap, verified: true, reason: "", leaseMs };
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      // A regression means the ledger went backwards: show nothing rather than older records.
      if (/regression/i.test(message)) throw new Error("Snapshot regression detected; the passport is withheld.");
      return { snap, verified: false, reason: message, leaseMs: 0 };
    }
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
    return { snap: validateSnapshot(res.body), verified: false, reason: "Preview data is a captured synthetic snapshot, not a verified live ledger.", leaseMs: 0 };
  }
}
