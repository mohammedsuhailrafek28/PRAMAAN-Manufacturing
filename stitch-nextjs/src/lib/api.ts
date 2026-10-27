export type EvidenceFinding = "AFFECTED" | "UNRESOLVED" | "EXCLUDED_WITH_EVIDENCE" | string;

export type DecisionCurrent = {
  evidenceFinding?: EvidenceFinding;
  operationalAction?: string;
  reasonCodes?: string[];
  reviewRequired?: boolean;
  [key: string]: unknown;
};

export type Motor = {
  unitId: string;
  motorSerial?: string;
  title?: string;
  family?: string;
  eventCount?: number;
  events?: Array<Record<string, unknown>>;
  shipment?: Record<string, unknown> | null;
  fixtureSet?: string;
  manifest?: Record<string, unknown>;
};

export type Decision = {
  current?: DecisionCurrent;
  history?: Array<Record<string, unknown>>;
};

export type Checkpoint = {
  state?: string;
  verifiedAt?: string;
  checksum?: string;
  [key: string]: unknown;
};

export type DecisionsResponse = Record<string, Decision> & {
  checkpoint?: Checkpoint;
  eligibility?: Record<string, unknown>;
};

export type Snapshot = {
  schemaVersion?: number;
  provenance?: Record<string, unknown>;
  recall?: Record<string, unknown>;
  units: Motor[];
  decisions: Record<string, Record<string, Decision>>;
  components: Array<Record<string, unknown>>;
  lineage: Array<Record<string, unknown>>;
  lots: Array<Record<string, unknown>>;
  checkpoint?: Checkpoint;
  eligibility?: Record<string, Record<string, unknown>>;
  freshness?: { status?: string; verifiedAt?: string; maxAgeSeconds?: number };
};

export type Genealogy = {
  unit: Motor;
  relationships: Array<Record<string, unknown>>;
  lineage: Array<Record<string, unknown>>;
  checkpoint?: Checkpoint;
};

export class ApiError extends Error {
  readonly kind: "unavailable" | "http";
  readonly status?: number;
  constructor(message: string, kind: "unavailable" | "http" = "http", status?: number) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

const baseUrl = "";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { signal, cache: "no-store" });
  } catch {
    throw new ApiError("Manufacturing backend is unavailable. Start the authorized local backend and retry.", "unavailable");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { error?: string; state?: string };
    const detail = body.error ?? `HTTP ${response.status}`;
    const state = body.state ? ` (${body.state})` : "";
    throw new ApiError(`Backend returned ${detail}${state} for ${path}. No fallback data was used.`, "http", response.status);
  }
  return response.json() as Promise<T>;
}

export function getSnapshot(signal?: AbortSignal) {
  return get<Snapshot>("/api/snapshot", signal);
}

export function getGenealogy(motor: string, signal?: AbortSignal) {
  return get<Genealogy>(`/api/motors/${encodeURIComponent(motor)}/genealogy`, signal);
}

export function getDecisions(motor: string, signal?: AbortSignal) {
  return get<DecisionsResponse>(`/api/motors/${encodeURIComponent(motor)}/decisions`, signal);
}
