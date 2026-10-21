// Types for the recall snapshot. Decision fields mirror the recall engine's output verbatim;
// the UI never computes a finding, an action or a review flag.

export type Finding = "AFFECTED" | "UNRESOLVED" | "EXCLUDED_WITH_EVIDENCE";
export type OperationalAction = "RECALL_HOLD" | "RELEASE_ELIGIBLE";

export interface Gap {
  kind: string;
  materiality?: string;
  sourceId?: string;
  from?: string;
  to?: string;
  eventId?: string;
  boundedByEventId?: string;
  [k: string]: unknown;
}
export interface Conflict {
  kind: string;
  [k: string]: unknown;
}
export interface SlotView {
  reconciliation: string;
  baseline?: string;
  identityGranularity?: string;
  policyRelevance?: string;
  currentLotPerRecords?: string;
  state?: string;
  gaps?: Gap[];
  conflicts?: Conflict[];
  verifications?: Array<Record<string, unknown>>;
  [k: string]: unknown;
}
export interface Candidate {
  slot: string;
  basis: string;
  claimed: boolean;
  supportingEventIds: string[];
}
export interface SlotAttribution {
  removalEventId: string;
  claimedSlot: string;
  observed: { part?: string; lot?: string; serial?: string | null; granularity?: string };
  assurance: "CLAIMED_SLOT" | "OBSERVED_SLOT_LABEL" | "CORROBORATED_SLOT";
  ambiguous: boolean;
  cleared: boolean;
  clearedBy: string | null;
  candidates: Candidate[];
  ruledOutSlots: string[];
  unrulableAlternatives: Array<{ slot: string; reason: string }>;
  labelScans: Array<Record<string, unknown>>;
  rejectedLabelScans: Array<{ eventId: string; reason: string }>;
  supportingEventIds: string[];
}
export interface UntrustedObservation {
  eventId: string;
  slot?: string | null;
  observed: { part?: string; lot?: string; serial?: string | null };
  status: string;
  rejectedReasons?: string[];
  staleBy?: string | null;
  resolvedBy?: string | null;
  reason?: string;
  [k: string]: unknown;
}
export interface NotificationObligation {
  required: boolean;
  reason: string;
  appliesIfDecisionCommunicated: string;
  [k: string]: unknown;
}
export interface Decision {
  decisionId: string;
  version?: number;
  policyId: string;
  recallId: string;
  caseId?: string;
  motorSerial?: string;
  evidenceFinding: Finding;
  operationalAction: OperationalAction;
  reviewRequired: boolean;
  reasonCodes: string[];
  flags: string[];
  slots: Record<string, SlotView>;
  evidenceEventIds: string[];
  supersededEventIds: string[];
  integrityIssues: Array<Record<string, unknown>>;
  watermark: Record<string, number>;
  engineVersion: string;
  semanticsProfile: string;
  coverageDigest: string;
  supersedesDecisionId?: string | null;
  triggerEventId?: string | null;
  precautionaryHold?: boolean;
  notificationObligation?: NotificationObligation | null;
  slotAttribution?: SlotAttribution[];
  untrustedObservations?: UntrustedObservation[];
  assuranceWarnings?: string[];
  [k: string]: unknown;
}
export interface PolicyDecisions {
  current: Decision;
  history: Decision[];
}
export interface EventRecord {
  repository?: { captureSha256: string; eventChainHash: string; localReceivedAt: string; recordTime: string };
  eventId: string;
  eventType: string;
  sourceId: string;
  sourceSeq: number;
  motorSerial: string;
  workOrderId: string | null;
  occurredAt: string;
  recordedAt: string;
  timeSource: string;
  actorId: string;
  evidenceRefs: string[];
  supersedesEventId: string | null;
  payload: Record<string, unknown>;
}
export interface Shipment {
  shipmentId: string;
  shippedAt: string;
  customer: string;
  destination: string;
  [k: string]: unknown;
}
export interface GroundTruth {
  trueP1Finding: "AFFECTED" | "UNAFFECTED";
  basis: string;
}
export interface Unit {
  unitId: string;
  motorSerial: string;
  title: string;
  description: string;
  family: string;
  fixtureSet: string;
  shipment: Shipment | null;
  eventCount: number;
  events: EventRecord[];
  captureSessions: Array<{ sourceId: string; from: string; to: string }>;
  syntheticGroundTruth?: GroundTruth | null;
}
export interface Component {
  componentId: string;
  unitId: string;
  slot: string;
  part: string | null;
  lot: string | null;
  serial: string | null;
  installedAt: string;
  sourceId: string;
  removedAt: string | null;
  removalEventId: string | null;
  supersededBy: string | null;
  claimedBy: string;
}
export interface Lot {
  lotId: string;
  part: string;
  affected: boolean;
  supplier: string | null;
}
export interface Comparison {
  unitId: string;
  policyId: string;
  legacy: Decision;
  current: Decision;
  syntheticGroundTruth?: GroundTruth | null;
}
export interface PolicyInfo {
  policyId: string;
  exposureBasis: string;
  damageInspection: unknown;
}
export interface Provenance {
  dataKind: string;
  adapter: string;
  engine: { semanticsProfile: string; version: string };
  comparisonEngine: { semanticsProfile: string; version: string };
  fixtureManifests: Record<string, string>;
  overlay: { file: string; sha256: string; kind: string; covers: string };
  oracleFilesRead: boolean;
}
export interface RecallSnapshot {
  freshness?: { verifiedAt: string; maxAgeSeconds: number; status: string; archiveId: string; sequence: number; headHash: string };
  schemaVersion: 1;
  provenance: Provenance;
  recall: {
    recallId: string;
    version: number;
    announcedAt: string | null;
    affectedPart: string;
    affectedLots: string[];
    affectedSlots: string[];
  };
  policies: PolicyInfo[];
  units: Unit[];
  decisions: Record<string, Record<string, PolicyDecisions>>;
  comparison: Comparison[];
  components: Component[];
  lots: Lot[];
  lineage?: Array<{ unitId: string; rawMaterialLot: string; supplierName: string; lot: string; serial?: string; materialEventId: string; manufacturingEventId: string }>;
  notifications?: Array<NotificationObligation & { unitId: string; decisionId: string; deliveryStatus: string }>;
  recallAnnounced?: boolean;
}
