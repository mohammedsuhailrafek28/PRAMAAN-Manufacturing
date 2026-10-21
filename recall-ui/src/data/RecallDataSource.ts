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
