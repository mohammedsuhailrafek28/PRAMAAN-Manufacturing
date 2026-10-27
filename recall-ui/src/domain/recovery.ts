/** Shapes returned by the restricted recovery routes. They carry no decision, eligibility or clearance by construction. */
export interface RecoveryStatus {
  mode: string;
  checkpoint: { state: string; anchoredSequence: number | null; checkpointRequired: boolean; h2: string };
  allowedActions: string[];
  prohibitedActions: string[];
  custodyConfigured: boolean;
  heldMotors: {
    motor: string;
    identityFindings: { source: string; reason: string; slot: string | null; lot: string | null; resembles: string[] }[];
    integrityFindings: { reason: string; workOrderId?: string }[];
    quarantine: { status: string; steps: { instruction: string }[] } | null;
  }[];
  notice: string;
}
export interface RecoveryProposal {
  status: string; candidate: string; candidateSha256: string;
  review: { containedMotors: string[]; refusedForIdentity: string[]; requiresAcknowledgement: string[] };
}
export interface RecoveryApi {
  call(action: string | null, body?: Record<string, unknown>): Promise<{ status: number; body: { recovery?: RecoveryStatus; proposal?: RecoveryProposal; error?: string } }>;
}
