import type { Consistency } from "./consistency";

/** Says whether a per-motor resource is established as consistent with the verified snapshot. Reuses existing note, tag and muted-text styles. */
export function ResourceNote({ c, what, seq }: { c: { consistency: Consistency | "PENDING"; reason: string }; what: string; seq?: number }) {
  if (c.consistency === "PENDING") return null;
  if (c.consistency === "CURRENT") return <span className="na" data-testid="resource-current">{what} matches the verified snapshot{seq !== undefined ? ` (checkpoint ${seq})` : ""}.</span>;
  if (c.consistency === "MISMATCH") return <p className="note warn-t" role="status" data-testid="resource-mismatch"><span className="tag bad">[WITHHELD]</span> {what} does not match the verified snapshot ({c.reason}). It is read again when the next verified snapshot arrives.</p>;
  return <p className="note" data-testid="resource-unverified"><span className="tag warn">[UNVERIFIED]</span> {what} is shown as recorded fact. It is not established as consistent with the current snapshot: {c.reason}.</p>;
}
