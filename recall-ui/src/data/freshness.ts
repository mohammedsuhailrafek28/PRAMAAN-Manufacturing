import type { RecallSnapshot } from "../domain/types";
import {evaluateEnvelope, GateWithheldError} from "../contract/gate";

/** Compatibility seam: only CURRENT earns a lease. PREFIX is historical and must be
 * handled explicitly by callers of the typed gate, never by a freshness boolean. */
export function verifyFreshness(snap: RecallSnapshot, previous?: RecallSnapshot | null, now=Date.now()): number {
 const gate=evaluateEnvelope({status:200,body:snap},previous ?? null,now);
 if(gate.kind === "WITHHELD") throw new GateWithheldError(gate);
 if(gate.kind !== "CURRENT") throw new Error("Historical evidence only; current verification withheld");
 return gate.leaseMs;
}
