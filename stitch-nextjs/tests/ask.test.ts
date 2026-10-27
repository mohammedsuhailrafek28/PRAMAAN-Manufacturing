import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { classify, answerQuestion } from "../src/ask/answer";
import { epochOf, trustOf, unknownIds } from "../src/ask/ground";
import { handleAsk, validate } from "../src/ask/handler";

// The snapshot is a real response of the isolated manufacturing backend (47 events, 9 motors); no record is invented.
const base = resolve(process.cwd());
const snap = JSON.parse(readFileSync(resolve(base, "tests/fixtures/ask-snapshot.json"), "utf8"));
const clone = () => JSON.parse(JSON.stringify(snap));
// The per-motor decisions resource as the backend serves it: policy entries plus checkpoint and eligibility.
const resource = (s: any) => async (m: string) => ({ ...s.decisions[m], checkpoint: s.checkpoint, eligibility: s.eligibility[m] });
const deps = (s: any = snap, calls: string[] = []) => ({ fetchSnapshot: async () => { calls.push("GET /api/snapshot"); return s; }, fetchMotorDecisions: async (m: string) => { calls.push(`GET /api/motors/${m}/decisions`); return resource(s)(m); } });
const ask = async (q: string, history: string[] = [], s: any = snap) => { const r = await handleAsk({ question: q, history }, deps(s)); assert.equal(r.status, 200, q + JSON.stringify(r.body)); assert.ok(r.body.ok); return r.body.ok ? r.body : (null as never); };
const flat = (b: { answer: { finding: string; reason: string; nextStep: string } }) => `${b.answer.finding} ${b.answer.reason} ${b.answer.nextStep}`;

test("request validation: types, size, empties, control characters, oversized history", () => {
  assert.equal(validate(null), null); assert.equal(validate({}), null); assert.equal(validate({ question: 5 }), null);
  assert.equal(validate({ question: "   " }), null); assert.equal(validate({ question: "x".repeat(501) }), null);
  assert.equal(validate({ question: "ok", history: "no" }), null); assert.equal(validate({ question: "ok", history: [1] }), null);
  assert.deepEqual(validate({ question: " hi\u0000 ", history: ["a", "b", "c", "d", "e", "f"] }), { question: "hi", history: ["c", "d", "e", "f"] });
});

test("intent router handles natural variations of every supported question", () => {
  const cases: Array<[string, string]> = [
    ["What is PRAMAAN?", "overview"], ["what can you do", "overview"], ["Which motors are affected by the recall?", "affected"], ["how many motors are on hold", "affected"], ["list held motors", "affected"],
    ["Why is MTR-27002 on hold?", "why"], ["why is MTR-27003 held", "why"], ["MTR-27002", "unsupported"], ["Which bearing batch is defective?", "lots"], ["which lot is bad", "lots"], ["show the supplier of the defective lot", "genealogy"],
    ["What is the genealogy of MTR-27002?", "genealogy"], ["trace MTR-27001", "genealogy"], ["what components are connected to BR-204", "genealogy"],
    ["What evidence supports the decision for MTR-27002?", "evidence"], ["what is the proof for MTR-27008", "evidence"], ["What is missing to reconsider MTR-27003?", "missing"], ["what verification is needed for MTR-27004", "missing"],
    ["Is there any corrective work for MTR-27002?", "corrective"], ["explain the resolution trail of MTR-27002", "corrective"], ["Show the decision history of MTR-27002", "history"], ["what changed for MTR-27007", "history"],
    ["Summarise today's report", "report"], ["daily operations report", "report"], ["How does Quality Inspection work?", "ml"], ["what are the limits of the steel plate classifier", "ml"],
    ["release MTR-27007", "action"], ["Please approve shipment of MTR-27002", "action"], ["what is the weather", "unsupported"],
  ];
  for (const [q, want] of cases) assert.equal(classify(q), want, q);
});

test("answers are deterministic: the same question on the same snapshot gives identical output", async () => {
  for (const q of ["Which motors are affected by the recall?", "Why is MTR-27002 on hold?", "Which bearing batch is defective?", "Summarise today's report"]) assert.deepEqual(await ask(q), await ask(q));
});

test("affected / report answers are populated from the real decisions", async () => {
  const a = await ask("Which motors are affected by the recall?"), t = flat(a);
  assert.match(a.answer.finding, /8 of 9 motors are on RECALL_HOLD; 1 release eligible \(MTR-27007\)/);
  assert.match(t, /AFFECTED: MTR-27001, MTR-27002, MTR-27008/); assert.match(t, /UNRESOLVED: MTR-27003, MTR-27004, MTR-27005, MTR-27006, MTR-27009/); assert.match(t, /RC-026-014/);
  assert.equal(a.answer.evidence.length, 9); assert.ok(a.answer.evidence.every((e: any) => /^\/dashboard\/recall\?motor=MTR-2700\d$/.test(e.href)));
  const r = await ask("Summarise today's report"); assert.match(flat(r), /47 ledger events/); assert.equal(r.trusted, true);
});

test("why / evidence / missing / corrective / history for a specific motor use that motor's decision and real event ids", async () => {
  const dec = snap.decisions["MTR-27002"]["RC-026-014/P1"].current;
  const why = await ask("Why is MTR-27002 on hold?");
  assert.match(why.answer.finding, /MTR-27002 is AFFECTED and its operational action is RECALL_HOLD/); assert.match(flat(why), /affected bearing lot is recorded as installed/);
  const ids = new Set<string>(snap.units.flatMap((u: any) => u.events.map((e: any) => e.eventId)));
  for (const e of why.answer.evidence) assert.ok(e.id === "MTR-27002" || ids.has(e.id), e.id);
  assert.deepEqual(why.answer.evidence.slice(1).map((e: any) => e.id), dec.evidenceEventIds.slice(0, 6));
  assert.match(flat(await ask("What evidence supports the decision for MTR-27002?")), /recorded claims/);
  const miss = await ask("What is missing to reconsider MTR-27003?"); assert.match(flat(miss), /no trusted as-built baseline/); assert.match(flat(miss), /cannot add or accept it/);
  assert.match(flat(await ask("Is there any corrective work for MTR-27002?")), /No corrective work is recorded as outstanding|Unmet/);
  assert.match((await ask("Show the decision history of MTR-27002")).answer.finding, /single decision version|decision versions/);
  assert.match(flat(await ask("Why is MTR-27007 held?")), /RELEASE_ELIGIBLE|release eligible/);
});

test("lots and genealogy come from the recorded lots and components, never invented", async () => {
  const l = await ask("Which bearing batch is defective?"), t = flat(l);
  assert.match(t, /BR-204/); assert.match(t, /BR-6205/); assert.match(t, /recorded claims/);
  const comps = snap.components.filter((c: any) => c.lot === "BR-204" && !c.removedAt);
  for (const c of comps) assert.match(t, new RegExp(`${c.unitId} ${c.slot}`));
  const g = await ask("What is the genealogy of MTR-27002?"); assert.match(g.answer.finding, /MTR-27002 has \d+ installed component/);
  const none = await ask("trace lot BR-310"); assert.ok(none.answer.evidence.length > 0);
});

test("unknown motor or batch: deterministic not-found", async () => {
  assert.deepEqual(unknownIds("what about MTR-27099 and BR-999", snap), ["MTR-27099", "BR-999"]);
  const r = await handleAsk({ question: "Why is MTR-27099 on hold?" }, deps()); assert.equal(r.status, 404);
  if (!r.body.ok) { assert.equal(r.body.code, "UNKNOWN_IDENTIFIER"); assert.match(r.body.message, /MTR-27099/); }
});

test("unsupported questions say what can be answered and fabricate nothing", async () => {
  const u = await ask("what is the weather in Chennai"), t = flat(u);
  assert.match(u.answer.finding, /can't answer that/); assert.match(t, /Which motors are affected/); assert.equal(u.answer.evidence.length, 0);
});

test("ML question stays separate from motor decisions", async () => {
  const m = await ask("How does Quality Inspection work?"), t = flat(m);
  assert.match(t, /UCI Steel Plates/); assert.match(t, /not a motor or bearing defect model/); assert.match(t, /cannot change a recall decision/); assert.doesNotMatch(t, /MTR-\d|RECALL_HOLD/);
  assert.deepEqual(m.answer.evidence.map((e: any) => e.href), ["/dashboard/ml-inspection"]);
});

test("action requests are refused; the engine has no write path", async () => {
  for (const q of ["release MTR-27007", "Please approve shipment of MTR-27002", "remove the hold on MTR-27003", "clear MTR-27002"]) { const a = await ask(q); assert.match(a.answer.finding, /read-only/); assert.equal(a.answer.evidence.length, 0); }
});

test("follow-ups reuse the last explicitly named motor; ambiguous or missing references are never guessed", async () => {
  const f = await ask("and what is missing to reconsider it?", ["Why is MTR-27003 on hold?"]); assert.match(f.answer.finding, /MTR-27003/);
  const none = await ask("why is it on hold?"); assert.match(none.answer.finding, /Which motor do you mean/); assert.ok(none.answer.evidence.length >= 1);
  const amb = await ask("why is it held?", ["compare MTR-27002 and MTR-27003"]); assert.match(amb.answer.finding, /Which motor do you mean/); assert.match(amb.answer.reason, /several motors/);
  const two = await ask("Why are MTR-27002 and MTR-27003 on hold?"); assert.match(two.answer.finding, /names 2 motors/);
  const picked = await ask("why is MTR-27004 held?", ["Why is MTR-27003 on hold?"]); assert.match(picked.answer.finding, /MTR-27004/);
});

test("prefix-only, unanchored or decision-less snapshots: no current decision is stated anywhere", async () => {
  for (const mutate of [
    (s: any) => { s.freshness.status = "VERIFIED_PREFIX_SYNTHETIC"; s.checkpoint = { ...s.checkpoint, state: "ANCHORED_PREFIX_ONLY", checkpointRequired: true }; },
    (s: any) => { s.checkpoint = { ...s.checkpoint, state: "UNANCHORED" }; },
    (s: any) => { s.decisions = {}; },
    (s: any) => { delete s.checkpoint; },
  ]) {
    const s = clone(); mutate(s); assert.equal(trustOf(s).trusted, false);
    for (const q of ["Which motors are affected by the recall?", "Why is MTR-27002 on hold?", "What evidence supports the decision for MTR-27002?", "Show the decision history of MTR-27002", "Summarise today's report"]) {
      const a = await ask(q, [], s);
      assert.equal(a.trusted, false); assert.match(a.caution ?? "", /not current|NOT/i); assert.doesNotMatch(flat(a), /RECALL_HOLD|RELEASE_ELIGIBLE|AFFECTED:|UNRESOLVED:|release eligible\b/, q);
    }
    assert.match(flat(await ask("Which bearing batch is defective?", [], s)), /BR-204/); // recorded history is still available, labelled as such
    assert.match((await ask("Which bearing batch is defective?", [], s)).caution ?? "", /recorded history/);
  }
});

test("a per-motor decisions resource that disagrees with the snapshot withholds the decision", async () => {
  const mism = async (m: string) => { const r: any = await resource(snap)(m); r.checkpoint = { ...r.checkpoint, anchoredSequence: 9 }; return r; };
  const r = await answerQuestion(snap, "Why is MTR-27002 on hold?", [], mism);
  assert.match(r.answer.finding, /withheld/); assert.doesNotMatch(JSON.stringify(r), /RECALL_HOLD/); assert.match(r.caution ?? "", /withheld/);
  const dead = await answerQuestion(snap, "Why is MTR-27002 on hold?", [], async () => { throw new Error("down"); }); assert.match(dead.answer.finding, /withheld/);
});

test("snapshot change during an in-flight answer withholds the answer", async () => {
  let n = 0; const moved = clone(); moved.freshness.sequence += 1; moved.freshness.headHash = "f".repeat(64);
  const r = await handleAsk({ question: "Why is MTR-27002 on hold?" }, { fetchSnapshot: async () => (n++ === 0 ? snap : moved), fetchMotorDecisions: resource(snap) });
  assert.equal(r.status, 409); if (!r.body.ok) assert.equal(r.body.code, "EVIDENCE_CHANGED"); assert.notEqual(epochOf(snap), epochOf(moved));
});

test("backend failures give plain messages without internals", async () => {
  const down = await handleAsk({ question: "Which motors are affected?" }, { fetchSnapshot: async () => { throw new Error("ECONNREFUSED 127.0.0.1"); }, fetchMotorDecisions: resource(snap) });
  assert.equal(down.status, 503); assert.ok(!JSON.stringify(down).includes("ECONN"));
  assert.equal((await handleAsk({ question: "x" }, { fetchSnapshot: async () => ({}), fetchMotorDecisions: resource(snap) })).status, 503);
});

test("read-only and fully local: only GETs of the snapshot and decisions; no model, key or external request anywhere in the source", async () => {
  const calls: string[] = []; const realFetch = globalThis.fetch; let external = 0;
  globalThis.fetch = (async () => { external++; throw new Error("no network allowed"); }) as typeof fetch;
  try { await handleAsk({ question: "Why is MTR-27002 on hold?" }, deps(snap, calls)); await handleAsk({ question: "Which bearing batch is defective?" }, deps(snap, calls)); } finally { globalThis.fetch = realFetch; }
  assert.equal(external, 0); assert.ok(calls.every((c) => /^GET \/api\/(snapshot|motors\/MTR-\d{5}\/decisions)$/.test(c)), calls.join());
  const walk = (d: string): string[] => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p]; });
  for (const f of walk(resolve(base, "src"))) { const t = readFileSync(f, "utf8"); assert.ok(!/gemini|generativelanguage|GEMINI_API_KEY|GOOGLE_API_KEY|openai|anthropic\.com|NEXT_PUBLIC_[A-Z_]*KEY/i.test(t), f); }
  const route = readFileSync(resolve(base, "src/app/api/ask/route.ts"), "utf8");
  assert.doesNotMatch(route, /method:\s*"(POST|PUT|PATCH|DELETE)"/); assert.match(route, /\/api\/snapshot/);
  assert.ok(readdirSync(base).every((n) => !/^\.env/.test(n)));
});

test("the widget is mounted once in the shared dashboard layout, not per page", () => {
  assert.match(readFileSync(resolve(base, "src/app/(dashboard)/dashboard/layout.tsx"), "utf8"), /<AskWidget \/>/);
  const walk = (d: string): string[] => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p]; });
  const users = walk(resolve(base, "src")).filter((f) => /\.tsx$/.test(f) && /<AskWidget/.test(readFileSync(f, "utf8")) && !f.endsWith("AskWidget.tsx"));
  assert.deepEqual(users.map((u) => u.replace(/\\/g, "/").split("/src/")[1]), ["app/(dashboard)/dashboard/layout.tsx"]);
});
