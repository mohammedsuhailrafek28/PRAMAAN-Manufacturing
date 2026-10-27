// Deterministic, rule-based answer engine for Ask PRAMAAN. No language model, no network access of its own:
// every answer is a template filled with values read from the verified snapshot (and the per-motor decisions resource).
import { assessDecisions } from "../dash/consistency";
import { epochOf, motorsIn, trustOf, unknownIds, type Snap } from "./ground";

export type Ref = { id: string; label: string; href: string };
export type Answer = { finding: string; reason: string; evidence: Ref[]; nextStep: string };
export type Intent = "overview" | "affected" | "why" | "lots" | "genealogy" | "evidence" | "missing" | "corrective" | "history" | "report" | "ml" | "action" | "unsupported";
export type Result = { answer: Answer; caution?: string; intent: Intent };
export type MotorDecisions = (motor: string) => Promise<Record<string, unknown>>;

export const SUGGESTIONS = [
  "Which motors are affected by the recall?", "Why is MTR-27002 on hold?", "Which bearing batch is defective?",
  "What is the genealogy of MTR-27002?", "What evidence supports the decision for MTR-27002?", "What is missing to reconsider MTR-27003?",
  "Show the decision history of MTR-27002", "Summarise today's report", "How does Quality Inspection work?",
];
const NEEDS_MOTOR: Intent[] = ["why", "evidence", "missing", "corrective", "history"];

/** Natural-language variations are matched by keyword rules in a fixed order; the first rule that matches wins. */
export function classify(question: string): Intent {
  const q = question.toLowerCase();
  if (/^\s*(please\s+)?(release|clear|approve|authori[sz]e|ship|unhold|remove|lift|override|delete|edit|modify|update|reopen)\b/.test(q)) return "action";
  if (/\bml\b|machine.?learning|steel|classifier|quality inspection|random forest/.test(q)) return "ml";
  if (/what (is|does) (pramaan|this)|what can you|what can i ask|capabilit|overview|about (the |this )?(project|app|dashboard)|\bhelp\b|\bhow does (this|pramaan)/.test(q)) return "overview";
  if (/histor|what changed|\bchange[sd]?\b|version|previous decision|between decisions|supersed|earlier decision/.test(q)) return "history";
  if (/missing|reconsider|unverified|what (do we|is) need|needed|baseline|\bgaps?\b|what.*(lift|clear|resolve)|how.*(resolve|lift)/.test(q)) return "missing";
  if (/corrective|resolution|trail|rework|\bfix\b|work order|what should|next action/.test(q)) return "corrective";
  if (/\bwhy\b|reason|held|on hold|hold\b/.test(q) && (motorsIn(question).length || /\b(it|that one|this one|the same|this motor|that motor)\b/.test(q))) return "why";
  if (/evidence|proof|support|justif|basis/.test(q)) return "evidence";
  if (/genealog|traceab|\btrace\b|connected|component|supplier|raw material|upstream|downstream|installed/.test(q)) return "genealogy";
  if (/batch|\blots?\b|bearing|defect/.test(q)) return "lots";
  if (/report|today|daily|summar/.test(q)) return "report";
  if (/affected|which motors|how many|\bheld\b|\bhold|recall|released|eligible/.test(q)) return "affected";
  if (/\bwhy\b/.test(q)) return "why";
  return "unsupported";
}

const policyOf = (s: Snap, m: string) => { const d = s.decisions?.[m]; const k = d && Object.keys(d)[0]; return k ? d[k] : null; };
const cur = (s: Snap, m: string) => policyOf(s, m)?.current;
const eventIndex = (s: Snap) => { const x = new Map<string, { unit: string; type: string }>(); for (const u of s.units ?? []) for (const e of u.events ?? []) x.set(e.eventId, { unit: u.unitId, type: e.eventType }); return x; };
const motorRef = (m: string): Ref => ({ id: m, label: `Motor ${m}`, href: `/dashboard/recall?motor=${m}` });
const list = (a: string[]) => (a.length ? a.join(", ") : "none");
const CODES: Record<string, string> = {
  AFFECTED_LOT_INSTALLED: "an affected bearing lot is recorded as installed", NO_TRUSTED_BASELINE: "there is no trusted as-built baseline for its slots",
  CURRENT_STATE_UNVERIFIED: "its current installed state has not been verified", AS_BUILT_UNAFFECTED_LOT: "the recorded as-built lot is not an affected lot",
};
const codes = (c: string[] = []) => c.map((x) => CODES[x] ?? x.toLowerCase().replace(/_/g, " "));

export async function answerQuestion(s: Snap, question: string, history: string[], motorDecisions: MotorDecisions): Promise<Result> {
  const { trusted, reason: whyNot } = trustOf(s);
  let intent = classify(question);
  const ev = eventIndex(s);
  const evRef = (id: string): Ref => { const e = ev.get(id); return e ? { id, label: `${e.type.replace(/_/g, " ").toLowerCase()} · ${e.unit}`, href: `/dashboard/passport?motor=${e.unit}` } : { id, label: id, href: "/dashboard" }; };
  const motors = (s.units ?? []).map((u: Snap) => u.unitId as string);
  const asked = motorsIn(question).filter((m) => motors.includes(m));
  let motor: string | null = asked.length === 1 ? asked[0] : null;
  const A = (finding: string, reason: string, evidence: Ref[], nextStep: string, caution?: string): Result => ({ answer: { finding, reason, evidence, nextStep }, caution, intent });
  const notCurrent = `Verification is not current (${whyNot})`;

  if (intent === "action") return A("I can't do that. Ask PRAMAAN is read-only.", "Only the deterministic evaluator decides holds and release eligibility, and nothing here can release, ship, clear or change evidence.", [], "Open the Recall investigation to see the current decision and what evidence it rests on.");
  if (asked.length > 1 && NEEDS_MOTOR.includes(intent)) return A(`That question names ${asked.length} motors (${asked.join(", ")}).`, "I answer one motor at a time so nothing is mixed up.", asked.map(motorRef), "Ask again about a single motor, for example: " + `"${intent === "why" ? "Why is" : "Tell me about"} ${asked[0]}…"`);
  // A follow-up may reuse the most recent question that named exactly one motor; a question that named several is ambiguous and is never guessed.
  if (!motor && !asked.length && NEEDS_MOTOR.includes(intent)) {
    const prior = [...history].reverse().map((h) => motorsIn(h).filter((m) => motors.includes(m))).find((f) => f.length);
    if (prior && prior.length === 1) motor = prior[0];
    else return A(prior ? "Which motor do you mean?" : "Which motor do you mean? Please name one, for example MTR-27002.", prior ? `Your last question named several motors (${prior.join(", ")}).` : `The archive has ${motors.length} motors: ${list(motors)}.`, motors.slice(0, 9).map(motorRef), "Repeat the question with one motor id.");
  }
  if (intent === "unsupported" && motor) intent = "why"; // a bare motor id: explain its decision

  if (intent === "overview") return A("Ask PRAMAAN answers questions about this manufacturing archive from its verified records.", "It is a fixed rule-based assistant, not an AI model: every answer is filled in from the snapshot and per-motor resources, and it can only read.", [{ id: "/dashboard/recall", label: "Recall investigation", href: "/dashboard/recall" }, { id: "/dashboard/genealogy", label: "Genealogy", href: "/dashboard/genealogy" }, { id: "/dashboard/report", label: "Daily report", href: "/dashboard/report" }], `Try: ${SUGGESTIONS.slice(0, 4).map((x) => `"${x}"`).join("; ")}.`);
  if (intent === "ml") return A("Quality Inspection is an advisory steel-plate fault classifier, separate from recall decisions.", "It is a Random Forest trained on the public UCI Steel Plates Faults dataset (7 surface fault classes). It reads no PRAMAAN record, writes nothing, is not a motor or bearing defect model, and its predictions are not evidence and cannot change a recall decision or release anything.", [{ id: "/dashboard/ml-inspection", label: "ML quality inspection page", href: "/dashboard/ml-inspection" }], "Open the page to run a sample or upload a CSV of 27 steel-plate features; vote share shown there is not a calibrated probability.");
  if (intent === "unsupported") return A("I can't answer that from the archive.", "I can explain affected and held motors, why a motor is held, defective bearing lots, genealogy, supporting evidence, what is missing, corrective work, decision history, the daily report and Quality Inspection.", [], `Try: ${SUGGESTIONS.slice(0, 5).map((x) => `"${x}"`).join("; ")}.`);

  if (intent === "genealogy" || intent === "lots") {
    const lotAsked: string[] = (question.toUpperCase().match(/\b(?:BR-\d{3}|STEEL-\d{2}-\d{3})\b/g) ?? []);
    const comps = (s.components ?? []).filter((c: Snap) => !c.removedAt && (motor ? c.unitId === motor : lotAsked.length ? lotAsked.includes(c.lot) : (s.lots ?? []).some((l: Snap) => l.affected && l.lotId === c.lot)));
    const lots = (s.lots ?? []).filter((l: Snap) => lotAsked.length ? lotAsked.includes(l.lotId) : motor ? comps.some((c: Snap) => c.lot === l.lotId) : l.affected);
    const sup = lots.map((l: Snap) => `${l.lotId} (${l.part}, raw material ${l.rawMaterialLot ?? "unrecorded"}, ${l.supplier ?? "supplier unrecorded"})`);
    const refs: Ref[] = [...lots.slice(0, 4).map((l: Snap) => ({ id: l.lotId, label: `Lot ${l.lotId}`, href: "/dashboard/genealogy" })), ...lots.map((l: Snap) => l.evidenceEventId).filter(Boolean).slice(0, 3).map(evRef), ...comps.slice(0, 6).map((c: Snap) => evRef(c.componentId))];
    if (!lots.length && !comps.length) return A("No matching batch or component is recorded.", motor ? `${motor} has no installed components in the snapshot.` : "The snapshot lists no affected lot.", [], "Open Genealogy to browse the records.");
    const where = comps.map((c: Snap) => `${c.unitId} ${c.slot} (${c.serial})`);
    const rec = lots.some((l: Snap) => l.affected) ? `Recall ${s.recall?.recallId} names ${list(s.recall?.affectedLots ?? [])} as the affected lot.` : "";
    return A(`${motor ? `${motor} has ${comps.length} installed component(s)` : `${lots.length} batch(es) in scope`}: ${list(sup)}.`, `${rec} Installed: ${list(where)}. Supplier, lot and serial are recorded claims; the ledger checks their integrity, not their truth.`.trim(), refs, "Open Genealogy for the full upstream and downstream chain.", trusted ? undefined : `${notCurrent}; this is recorded history, not a current finding.`);
  }

  if (intent === "report" || intent === "affected") {
    const verified = `ledger sequence ${s.freshness?.sequence}, checkpoint ${s.checkpoint?.state} at ${s.checkpoint?.anchoredSequence}`;
    if (!trusted) return A("Current recall decisions cannot be shown.", `${notCurrent}. The archive holds ${motors.length} motors and ${(s.units ?? []).reduce((n: number, u: Snap) => n + (u.eventCount ?? 0), 0)} recorded events; holds and eligibility are withheld until verification is current.`, [{ id: "/dashboard/report", label: "Daily report", href: "/dashboard/report" }], "Wait for a verified, anchored-current checkpoint, then ask again.", `${notCurrent}.`);
    const rows = Object.keys(s.decisions).map((m) => ({ m, c: cur(s, m), ok: s.eligibility?.[m]?.currentReleaseEligible === true }));
    const hold = rows.filter((r) => r.c?.operationalAction === "RECALL_HOLD"), elig = rows.filter((r) => r.ok);
    const by = (f: string) => hold.filter((r) => r.c?.evidenceFinding === f).map((r) => r.m);
    return A(`${hold.length} of ${rows.length} motors are on RECALL_HOLD; ${elig.length} release eligible${elig.length ? ` (${elig.map((r) => r.m).join(", ")})` : ""}.`,
      `Recall ${s.recall?.recallId} (${s.recall?.affectedPart}, lot ${list(s.recall?.affectedLots ?? [])}, slot ${list(s.recall?.affectedSlots ?? [])}). AFFECTED: ${list(by("AFFECTED"))}. UNRESOLVED: ${list(by("UNRESOLVED"))}. Verified at ${verified}; ${(s.units ?? []).reduce((n: number, u: Snap) => n + (u.eventCount ?? 0), 0)} ledger events.`,
      rows.map((r) => motorRef(r.m)), intent === "report" ? "Open the Daily report for the printable summary." : "Ask why a specific motor is held, e.g. \"Why is MTR-27002 on hold?\".");
  }

  // Motor-specific intents. The per-motor decisions resource must agree with the snapshot before any decision is stated.
  const m = motor as string;
  if (!trusted) return A(`The current decision for ${m} cannot be shown.`, `${notCurrent}. Only recorded history is available, and it is not a current finding.`, [motorRef(m)], "Wait for a verified, anchored-current checkpoint, then ask again.", `${notCurrent}.`);
  let verdict: { consistency: string; reason: string };
  try { verdict = assessDecisions(await motorDecisions(m) as never, s as never, m, true); } catch { verdict = { consistency: "MISMATCH", reason: "the decisions for this motor could not be read" }; }
  if (verdict.consistency !== "CURRENT") return A(`The decision for ${m} is withheld.`, `Its decisions resource does not match the verified snapshot (${verdict.reason}).`, [motorRef(m)], "Ask again in a moment; a decision is shown only when both agree.", "Decision withheld: history is not consistent with the snapshot.");

  const p = policyOf(s, m), c = p.current, elig = s.eligibility?.[m]?.currentReleaseEligible === true;
  const slotBits = Object.entries(c.slots ?? {}).map(([k, v]) => `${k}: ${(v as Snap).state}${(v as Snap).currentLotPerRecords ? ` lot ${(v as Snap).currentLotPerRecords}` : ""}`);
  const base = [motorRef(m)];
  if (intent === "why") return A(`${m} is ${c.evidenceFinding} and its operational action is ${c.operationalAction}${elig ? " (release eligible)" : ""}.`, `Because ${list(codes(c.reasonCodes))}. Slots: ${list(slotBits)}.`, [...base, ...(c.evidenceEventIds ?? []).slice(0, 6).map(evRef)], c.operationalAction === "RECALL_HOLD" ? "A hold changes only when the evaluator publishes a new decision from new verified evidence. See the Resolution Trail." : "Eligibility is decided by the evaluator, not by this assistant.");
  if (intent === "evidence") return A(`Decision ${c.version} for ${m} (${c.evidenceFinding} / ${c.operationalAction}) rests on ${(c.evidenceEventIds ?? []).length} recorded event(s).`, `Events: ${list((c.evidenceEventIds ?? []).map((e: string) => `${ev.get(e)?.type ?? "event"} ${e.split(":").slice(-2).join(":")}`))}. They are recorded claims; the ledger proves integrity, not truth.`, [...base, ...(c.evidenceEventIds ?? []).slice(0, 8).map(evRef)], "Open the Passport for the full event list and hashes.");
  if (intent === "history") {
    const h: Snap[] = (p.history ?? []).slice(-5);
    return A(h.length > 1 ? `${m} has ${(p.history ?? []).length} decision versions.` : `${m} has a single decision version; nothing has changed.`, h.map((x) => `v${x.version}: ${x.evidenceFinding} / ${x.operationalAction}${x.triggerEventId ? ` (triggered by ${x.triggerEventId.split(":").slice(-2).join(":")})` : ""}`).join("; "), [...base, ...h.map((x) => x.triggerEventId).filter(Boolean).map(evRef)], "Open the Recall investigation to compare versions.");
  }
  const gaps = Object.entries(c.slots ?? {}).flatMap(([k, v]) => [...((v as Snap).gaps ?? []), ...((v as Snap).conflicts ?? [])].map((g: unknown) => `${k}: ${typeof g === "string" ? g : JSON.stringify(g)}`));
  const unmet = Object.entries(c.workOrders ?? {}).flatMap(([k, w]) => ((w as Snap).obligations ?? []).filter((o: Snap) => o.status !== "MET").map((o: Snap) => `${k} ${o.slot} ${o.action}: ${o.status}`));
  const guards = [...(c.identityGuard?.findings ?? []), ...(c.integrityGuard?.findings ?? []), ...(c.integrityIssues ?? [])].map((x: unknown) => (typeof x === "string" ? x : JSON.stringify(x)).slice(0, 120));
  if (intent === "missing") {
    const none = !gaps.length && !unmet.length && !guards.length && !(c.reasonCodes ?? []).includes("NO_TRUSTED_BASELINE") && !(c.reasonCodes ?? []).includes("CURRENT_STATE_UNVERIFIED");
    return A(none ? `No missing verification is recorded for ${m}; its action is ${c.operationalAction}${c.operationalAction === "RECALL_HOLD" ? ` because ${list(codes(c.reasonCodes))}` : ""}.` : `${m} remains ${c.operationalAction} with verification missing.`, none ? "No slot gaps, unmet work-order obligations or guard findings are recorded." : `Missing or unresolved: ${list([...codes((c.reasonCodes ?? []).filter((x: string) => x !== "AFFECTED_LOT_INSTALLED")), ...gaps, ...unmet, ...guards])}.`, base, "Reconsideration needs new verified evidence recorded in the ledger; this assistant cannot add or accept it.");
  }
  // corrective
  return A(unmet.length ? `${m} has unmet work-order obligations.` : `No corrective work is recorded as outstanding for ${m}.`, unmet.length ? `Unmet: ${list(unmet)}.` : `Work orders: ${list(Object.entries(c.workOrders ?? {}).map(([k, w]) => `${k} ${(w as Snap).status}`))}. A hold is not lifted by recorded work alone; the evaluator must publish a new decision.`, base, "The Resolution Trail on the Recall page shows the steps from evidence to outcome.");
}

export { epochOf, unknownIds };
