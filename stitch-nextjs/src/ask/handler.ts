// Orchestration of one question: validate -> read verified snapshot (GET only) -> deterministic answer -> re-read and compare the epoch.
// Entirely local: no language model, no provider, no key. Dependencies are injected so the whole path is testable.
import { answerQuestion, type Answer, type MotorDecisions } from "./answer";
import { epochOf, MAX_HISTORY, MAX_QUESTION, trustOf, unknownIds, type Snap } from "./ground";

export type ErrorCode = "INVALID_REQUEST" | "BACKEND_UNAVAILABLE" | "UNKNOWN_IDENTIFIER" | "EVIDENCE_CHANGED";
export type AskBody =
  | { ok: true; answer: Answer; epoch: string; trusted: boolean; caution?: string; scope: { archiveId?: string; sequence?: number; checkpoint?: string } }
  | { ok: false; code: ErrorCode; message: string };
export type Deps = { fetchSnapshot: () => Promise<Snap>; fetchMotorDecisions: MotorDecisions };

export const MESSAGES: Record<ErrorCode, string> = {
  INVALID_REQUEST: `Please ask a question of up to ${MAX_QUESTION} characters.`,
  BACKEND_UNAVAILABLE: "The verified evidence could not be read right now, so no answer was produced. Try again shortly.",
  UNKNOWN_IDENTIFIER: "That identifier is not in the verified evidence, so there is nothing to explain about it.",
  EVIDENCE_CHANGED: "The ledger or its verification changed while the answer was being prepared, so the answer was withheld. Please ask again.",
};
const fail = (status: number, code: ErrorCode, message = MESSAGES[code]): { status: number; body: AskBody } => ({ status, body: { ok: false, code, message } });

export function validate(raw: unknown): { question: string; history: string[] } | null {
  const b = raw as { question?: unknown; history?: unknown } | null;
  if (!b || typeof b !== "object" || typeof b.question !== "string") return null;
  const question = b.question.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ").trim();
  if (!question || question.length > MAX_QUESTION) return null;
  let history: string[] = [];
  if (b.history !== undefined) {
    if (!Array.isArray(b.history) || b.history.some((h) => typeof h !== "string" || h.length > MAX_QUESTION)) return null;
    history = (b.history as string[]).slice(-MAX_HISTORY);
  }
  return { question, history };
}

export async function handleAsk(raw: unknown, deps: Deps): Promise<{ status: number; body: AskBody }> {
  const req = validate(raw);
  if (!req) return fail(400, "INVALID_REQUEST");
  let snap: Snap;
  try { snap = await deps.fetchSnapshot(); } catch { return fail(503, "BACKEND_UNAVAILABLE"); }
  if (!snap || typeof snap !== "object" || !snap.freshness) return fail(503, "BACKEND_UNAVAILABLE");

  const unknown = unknownIds(req.question, snap);
  if (unknown.length) return fail(404, "UNKNOWN_IDENTIFIER", `${unknown.slice(0, 3).join(", ")} is not in the verified evidence, so there is nothing to explain about it. Check the identifier and try again.`);

  const epoch = epochOf(snap) as string, { trusted, reason } = trustOf(snap);
  const result = await answerQuestion(snap, req.question, req.history, deps.fetchMotorDecisions);

  // The answer is only as current as the evidence it was built on: re-read and compare before releasing it.
  let after: Snap;
  try { after = await deps.fetchSnapshot(); } catch { return fail(503, "BACKEND_UNAVAILABLE"); }
  if (epochOf(after) !== epoch) return fail(409, "EVIDENCE_CHANGED");

  return { status: 200, body: { ok: true, answer: result.answer, epoch, trusted, caution: result.caution ?? (trusted ? undefined : `Verification is not current (${reason}) Current recall decisions are not shown; anything below is recorded history only.`), scope: { archiveId: snap.freshness?.archiveId, sequence: snap.freshness?.sequence, checkpoint: snap.checkpoint?.state } } };
}
