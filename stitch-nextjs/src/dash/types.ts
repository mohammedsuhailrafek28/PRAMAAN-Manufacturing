// Shapes of the backend responses this UI reads. Only fields the UI displays are listed; anything else is ignored, never invented.
export type Checkpoint = { state?: string; anchoredSequence?: number; checkpointRequired?: boolean; h2?: string };
export type Freshness = { verifiedAt?: string; status?: string; maxAgeSeconds?: number; archiveId?: string; sequence?: number; headHash?: string };
export type Shipment = { shipmentId: string; customer?: string; destination?: string; assemblyEventId?: string; shippedAt?: string; evidenceEventId?: string; backedByLedger?: boolean; provenanceAssurance?: string };
export type LedgerEvent = { eventId: string; eventType: string; occurredAt?: string; recordedAt?: string; sourceId?: string; sourceSeq?: number; actorId?: string; timeSource?: string; payload?: Record<string, unknown>; workOrderId?: string | null; evidenceRefs?: string[]; supersedesEventId?: string | null; repository?: { captureSha256?: string; eventChainHash?: string; recordTime?: string; localReceivedAt?: string } };
export type Unit = { unitId: string; motorSerial: string; title?: string; description?: string; family?: string; fixtureSet?: string; shipment?: Shipment | null; eventCount?: number; events?: LedgerEvent[]; captureSessions?: Array<{ sourceId: string; from: string; to: string }> };
export type Component = { componentId: string; unitId: string; slot: string; part?: string; lot?: string; serial?: string; installedAt?: string; sourceId?: string; removedAt?: string | null; removalEventId?: string | null; supersededBy?: string | null; claimedBy?: string; registry?: { status?: string; canonical?: string; viaAlias?: boolean; supplierId?: string; issuer?: string; provenance?: string } };
export type Lineage = { unitId: string; rawMaterialLot?: string; supplierId?: string; supplierName?: string; part?: string; lot?: string; serial?: string; materialEventId?: string; manufacturingEventId?: string; backedByLedger?: boolean; provenanceAssurance?: string };
export type Lot = { lotId: string; part?: string; affected?: boolean; supplier?: string; rawMaterialLot?: string; evidenceEventId?: string; backedByLedger?: boolean; provenanceAssurance?: string; registry?: { status?: string } };
export type DecisionCurrent = {
  decisionId?: string; evidenceFinding?: string; operationalAction?: string; reviewRequired?: boolean; reasonCodes?: string[]; flags?: string[];
  evidenceEventIds?: string[]; slotVerdicts?: Record<string, { finding?: string; reasons?: string[] }>; version?: number; policyId?: string; recallId?: string;
  engineVersion?: string; semanticsProfile?: string; triggerEventId?: string | null; supersedesDecisionId?: string | null; notificationObligation?: { required?: boolean; reason?: string; appliesIfDecisionCommunicated?: string; communicated?: boolean | null; deliveryStatus?: string }; watermark?: Record<string, number>; identityGuard?: Record<string, unknown>; integrityGuard?: Record<string, unknown>; integrityIssues?: unknown[];
};
export type DecisionBundle = { current: DecisionCurrent; history?: unknown[] };
export type Recall = { recallId: string; policyId?: string; announcedAt?: string; affectedPart?: string; affectedLots?: string[]; affectedSlots?: string[]; exposureBasis?: string; scopeDeclaration?: string };
export type Snapshot = {
  provenance?: { dataKind?: string; engine?: { version?: string; semanticsProfile?: string } };
  recall: Recall; units: Unit[]; decisions: Record<string, Record<string, DecisionBundle>>;
  components: Component[]; lots: Lot[]; lineage: Lineage[];
  comparison?: Array<{ unitId: string; policyId?: string; legacy: DecisionCurrent; current?: DecisionCurrent }>;
  freshness?: Freshness; checkpoint?: Checkpoint; eligibility?: Record<string, { currentReleaseEligible?: boolean }>;
};
export type LifecycleEvent = { eventId: string; eventType: string; category?: string; occurredAt?: string; recordedAt?: string; sourceId?: string; sourceSeq?: number; actorId?: string; timeSource?: string; summary?: string; ledger?: Record<string, unknown> };
export type Lifecycle = { chronology: LifecycleEvent[]; violations?: unknown[]; eventCount?: number; checkpoint?: Checkpoint };
export type ProvenanceRow = { hash: string; received?: string; id: string; source?: string; seq?: number; event_chain_hash?: string };
