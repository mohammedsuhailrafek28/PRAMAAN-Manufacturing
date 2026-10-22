// Read-only data adapters. They only ever issue GET requests. The live adapter reuses the application's own
// shared typed checkpoint/eligibility gate (src/contract/gate.ts). No adapter falls back to fixture data.
import { GateTracker } from "../contract/gate";
import { liveLoad } from "../contract/liveLoad";
import { makePreview, type PageView } from "../contract/gated";
import { validateSnapshot } from "../domain/validate";
import { scaleSnapshot } from "./syntheticScale";

export interface ImpactLoad {
  view: PageView;
  reason: string;
  /** Remaining server lease in ms when verified, otherwise 0. */
  leaseMs: number;
  /** Preview only. */
  dataset?: { id: string; label: string; note: string; origin: Record<string, { kind: string; note: string }>; authoredScale: boolean };
}

export interface ImpactSource {
  readonly label: string;
  readonly live: boolean;
  load(signal?: AbortSignal): Promise<ImpactLoad>;
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

/** Live backend. A failure is an error the page must show; there is no fixture fallback. */
export class LiveImpactSource implements ImpactSource {
  readonly label = "Live SQLite ledger (synthetic manufacturing demo)";
  readonly live = true;
  private tracker = new GateTracker();
  constructor(private timeoutMs = 4000) {}

  async load(signal?: AbortSignal): Promise<ImpactLoad> {
    // Classification lives in the shared typed gate; this adapter never inspects error text.
    const r = await liveLoad(this.tracker, "/api/snapshot", this.timeoutMs, signal);
    return { view: r.view, reason: r.reason, leaseMs: r.leaseMs };
  }
}

interface DemoDocument {
  kind: string;
  label?: string;
  datasets: Array<{ id: string; label?: string; note?: string; origin: Record<string, { kind: string; note: string }>; snapshot: unknown }>;
}

export const LARGE_MOTORS = 1500;

/** Explicit, labelled preview of authored synthetic datasets. Never implicit, never verified. */
export class PreviewImpactSource implements ImpactSource {
  readonly label = "Preview: authored synthetic data (not a live ledger)";
  readonly live = false;
  constructor(private datasetId = "de", private url = "./data/impact-demo.json", private largeMotors = LARGE_MOTORS) {}

  async load(signal?: AbortSignal): Promise<ImpactLoad> {
    const res = await getJson(this.url, 6000, signal);
    if (!res.ok) throw new Error(`Could not load preview data: HTTP ${res.status}`);
    const doc = res.body as DemoDocument;
    if (!doc || doc.kind !== "SYNTHETIC_IMPACT_DEMONSTRATION" || !Array.isArray(doc.datasets)) throw new Error("Preview data is not the impact-graph demonstration dataset.");
    const large = this.datasetId === "large";
    const d = doc.datasets.find((x) => x.id === (large ? "de" : this.datasetId));
    if (!d) throw new Error(`Unknown preview dataset “${this.datasetId}”.`);
    let snap = validateSnapshot(d.snapshot);
    if (large) snap = scaleSnapshot(snap, this.largeMotors).snap;
    return {
      view: makePreview(snap, this.label), leaseMs: 0,
      reason: "Preview data is a captured synthetic dataset, not a verified live ledger.",
      dataset: {
        id: this.datasetId, label: d.label ?? d.id, authoredScale: large, origin: d.origin,
        note: large ? `Stress data: ${this.largeMotors} motors cloned from the captured dataset under new identifiers. Cloned decisions are copies, not new evaluator output.` : d.note ?? doc.label ?? "",
      },
    };
  }
}
