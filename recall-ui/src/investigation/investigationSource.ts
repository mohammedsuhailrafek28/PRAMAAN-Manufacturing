// Read-only data adapters. They only ever issue GET requests and never construct a mutation. The live
// adapter classifies every response with the shared typed gate (src/contract/gate.ts); unrecognised input is WITHHELD.
import { GateTracker } from "../contract/gate";
import { liveLoad } from "../contract/liveLoad";
import { makePreview, type PageView, type PreviewView } from "../contract/gated";
import { validateSnapshot } from "../domain/validate";

export interface InvestigationLoad {
  view: PageView;
  reason: string;
  /** Remaining server lease in ms when verified, otherwise 0. */
  leaseMs: number;
  /** Preview only: which authored stage this is, and the stage before it. */
  stage?: { id: string; label: string; origin: Record<string, string>; authoredNote: string };
  previous?: PreviewView;
}

export interface InvestigationSource {
  readonly label: string;
  readonly live: boolean;
  load(signal?: AbortSignal): Promise<InvestigationLoad>;
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
export class LiveInvestigationSource implements InvestigationSource {
  readonly label = "Live SQLite ledger (synthetic manufacturing demo)";
  readonly live = true;
  private tracker = new GateTracker();
  constructor(private timeoutMs = 4000) {}

  async load(signal?: AbortSignal): Promise<InvestigationLoad> {
    // Classification lives in the shared typed gate; this adapter never inspects error text.
    const r = await liveLoad(this.tracker, "/api/snapshot", this.timeoutMs, signal);
    return { view: r.view, reason: r.reason, leaseMs: r.leaseMs };
  }
}

interface DemoDocument {
  kind: string;
  label: string;
  origin: Record<string, string>;
  stages: Array<{ id: string; label: string; snapshot: unknown }>;
}

/** Explicit, labelled preview of the authored synthetic scenario. Never used implicitly, never verified. */
export class PreviewInvestigationSource implements InvestigationSource {
  readonly label = "Preview: authored synthetic scenario (not a live ledger)";
  readonly live = false;
  constructor(private stageId = "before", private url = "./data/investigation-demo.json") {}

  async load(signal?: AbortSignal): Promise<InvestigationLoad> {
    const res = await getJson(this.url, 6000, signal);
    if (!res.ok) throw new Error(`Could not load preview data: HTTP ${res.status}`);
    const doc = res.body as DemoDocument;
    if (!doc || doc.kind !== "SYNTHETIC_INVESTIGATION_DEMONSTRATION" || !Array.isArray(doc.stages)) throw new Error("Preview data is not the investigation demonstration scenario.");
    const index = doc.stages.findIndex((s) => s.id === this.stageId);
    if (index < 0) throw new Error(`Unknown preview stage “${this.stageId}”.`);
    return {
      view: makePreview(validateSnapshot(doc.stages[index].snapshot), this.label),
      previous: index > 0 ? makePreview(validateSnapshot(doc.stages[index - 1].snapshot), this.label) : undefined,
      reason: "Preview data is a captured synthetic scenario, not a verified live ledger.",
      leaseMs: 0,
      stage: { id: doc.stages[index].id, label: doc.stages[index].label, origin: doc.origin, authoredNote: doc.label },
    };
  }
}
