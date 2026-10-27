import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { advisoryNote, loadModel, predict } from "../src/ml/forest";
import { MAX_ROWS, parseCsv, validateRecord } from "../src/ml/input";

// Real model and real genuine records only: the held-out CSV and samples are rows of the UCI dataset; nothing is invented.
const base = resolve(process.cwd());
const model = loadModel(JSON.parse(readFileSync(resolve(base, "public/ml/model.json"), "utf8")));
const held = readFileSync(resolve(base, "ml/data/heldout.csv"), "utf8");
const samples = JSON.parse(readFileSync(resolve(base, "public/ml/samples.json"), "utf8")) as { samples: Array<{ id: string; recordedLabel: string; values: Record<string, number> }> };
const F = model.features, C = model.classes;
const heldRows = held.trim().split("\n").slice(1).map((l) => l.split(","));
const header = held.split("\n")[0];
const good = (n: number) => [header, ...held.trim().split("\n").slice(1, 1 + n)].join("\n");
const oneRow = (edit: (r: string[]) => void, cols = header.split(",")) => { const r = held.trim().split("\n")[1].split(","); edit(r); return [cols.join(","), r.join(",")].join("\n"); };
const idx = (name: string) => header.split(",").indexOf(name);

test("model file passes structural validation and records its provenance", () => {
  assert.equal(F.length, 27); assert.equal(C.length, 7); assert.equal(model.kind, "ADVISORY_ML_NOT_EVIDENCE");
  assert.match(model.meta.modelSha256 ?? "", /^[0-9a-f]{64}$/);
  assert.equal(model.meta.dataset.licence, "CC BY 4.0"); assert.equal(model.meta.dataset.rows, 1941); assert.equal(model.meta.dataset.sourceFileSha256, "08994f5b0185a8e6cc22afe9910fd36834990fb1ca30852ed79012a832fbff55");
});

test("malformed or tampered models are rejected, never partly used", () => {
  const raw = JSON.parse(readFileSync(resolve(base, "public/ml/model.json"), "utf8"));
  const clone = () => JSON.parse(JSON.stringify(raw));
  assert.throws(() => loadModel(null)); assert.throws(() => loadModel({}));
  const a = clone(); a.classes.pop(); assert.throws(() => loadModel(a), /27 features and 7 classes/);
  const b = clone(); b.trees = []; assert.throws(() => loadModel(b), /no trees/);
  const c = clone(); const i = c.trees[0].f.findIndex((v: number) => v >= 0); c.trees[0].l[i] = 0; assert.throws(() => loadModel(c), /invalid/);
  const d = clone(); const j = d.trees[0].f.findIndex((v: number) => v === -1); d.trees[0].v[j] = [0, 0, 0, 0, 0, 0, 0]; assert.throws(() => loadModel(d), /leaf/);
  const e = clone(); e.trees[0].t.pop(); assert.throws(() => loadModel(e), /inconsistent/);
  const f = clone(); f.kind = "EVIDENCE"; assert.throws(() => loadModel(f), /Unrecognised/);
});

test("real inference on every held-out genuine record reproduces the recorded accuracy and confusion matrix exactly", () => {
  const conf = C.map(() => C.map(() => 0)); let hit = 0;
  for (const r of heldRows) {
    const pr = predict(model, r.slice(0, 27).map(Number));
    const truth = C.indexOf(r[27]); assert.ok(truth >= 0);
    conf[truth][pr.index]++; if (pr.index === truth) hit++;
    assert.ok(Math.abs(pr.probabilities.reduce((s, p) => s + p.p, 0) - 1) < 1e-9);
    assert.equal(pr.confidence, Math.max(...pr.probabilities.map((p) => p.p)));
    assert.ok(pr.confidence > 0 && pr.confidence <= 1);
  }
  assert.equal(heldRows.length, model.meta.split.heldOut);
  assert.equal(Math.round((hit / heldRows.length) * 1e6) / 1e6, model.meta.heldOut.accuracy);
  assert.deepEqual(conf, model.meta.heldOut.confusion.matrix);
  assert.ok(model.meta.heldOut.accuracy > 0.7, "advisory model must beat the majority-class baseline of about 0.35 by a wide margin");
});

test("inference is deterministic and independent of CSV column order", () => {
  const rows = heldRows.slice(0, 20);
  for (const r of rows) assert.deepEqual(predict(model, r.slice(0, 27).map(Number)), predict(model, r.slice(0, 27).map(Number)));
  const cols = header.split(","); const order = [...cols.keys()].reverse();
  const shuffled = [order.map((i) => cols[i]).join(","), ...rows.map((r) => order.map((i) => r[i]).join(","))].join("\n");
  const a = parseCsv(good(20), F, C), b = parseCsv(shuffled, F, C);
  assert.ok(a.ok && b.ok);
  if (a.ok && b.ok) for (let i = 0; i < 20; i++) { assert.deepEqual(a.rows[i].values, b.rows[i].values); assert.equal(predict(model, a.rows[i].values).label, predict(model, b.rows[i].values).label); }
});

test("a valid CSV with a recorded label parses; BOM, CRLF and a trailing blank line are accepted", () => {
  const p = parseCsv("﻿" + good(3).replace(/\n/g, "\r\n") + "\r\n\r\n", F, C);
  assert.ok(p.ok); if (p.ok) { assert.equal(p.rows.length, 3); assert.ok(C.includes(p.rows[0].recordedLabel!)); assert.equal(p.rows[0].line, 2); }
  const noLabel = parseCsv([F.join(","), held.trim().split("\n")[1].split(",").slice(0, 27).join(",")].join("\n"), F, C);
  assert.ok(noLabel.ok); if (noLabel.ok) assert.equal(noLabel.rows[0].recordedLabel, undefined);
});

test("structural input problems reject the whole file with a clear reason", () => {
  const fail = (text: string, re: RegExp) => { const p = parseCsv(text, F, C); assert.equal(p.ok, false, text.slice(0, 60)); if (!p.ok) assert.match(p.errors.join("\n"), re); };
  fail("", /empty/); fail("\n\n", /empty/);
  fail(header, /no records/);
  fail(header.replace("X_Minimum,", "") + "\n" + held.trim().split("\n")[1], /Missing column X_Minimum/);
  fail(header.replace("X_Maximum", "X_Minimum") + "\n1", /Duplicate column X_Minimum/);
  fail(header + ",Extra\n" + held.trim().split("\n")[1] + ",1", /Unknown column Extra/);
  fail(oneRow((r) => r.pop()), /expected 28 values, found 27/);
  fail('"a",b\n1,2', /Quoted fields/);
  fail(good(1) + "\n" + "x".repeat(1_000_001), /larger than/);
  fail([header, ...Array(MAX_ROWS + 1).fill(held.trim().split("\n")[1])].join("\n"), /More than 500/);
});

test("cell-level problems are rejected: non-numbers, blanks, NaN/Infinity, hex, units, injection text, bad label", () => {
  const fail = (text: string, re: RegExp) => { const p = parseCsv(text, F, C); assert.equal(p.ok, false); if (!p.ok) assert.match(p.errors.join("\n"), re); };
  const set = (name: string, v: string) => oneRow((r) => { r[idx(name)] = v; });
  for (const v of ["abc", "", "NaN", "Infinity", "-Infinity", "0x10", "1,5", "12mm", "=1+1", "1e999", "--1"]) fail(set("Pixels_Areas", v), /Pixels_Areas|expected 28 values|out of range/);
  fail(set("Recorded_Label", "Bent"), /not one of the seven classes/);
});

test("domain rules: steel type flags, index ranges, geometry and luminosity ordering", () => {
  const fail = (name: string, v: string, re: RegExp) => { const p = parseCsv(oneRow((r) => { r[idx(name)] = v; }), F, C); assert.equal(p.ok, false, name + "=" + v); if (!p.ok) assert.match(p.errors.join("\n"), re); };
  fail("TypeOfSteel_A300", "2", /must be 0 or 1/);
  fail("Edges_Index", "1.5", /between 0 and 1/); fail("Empty_Index", "-0.1", /between 0 and 1/);
  fail("Orientation_Index", "2", /between -1 and 1/); fail("Luminosity_Index", "-1.2", /between -1 and 1/);
  fail("Pixels_Areas", "0", /greater than 0/); fail("Steel_Plate_Thickness", "-5", /greater than 0/);
  fail("X_Maximum", "-1", /X_Maximum is smaller/); fail("Y_Maximum", "-1", /Y_Maximum is smaller/);
  fail("Minimum_of_Luminosity", "255", /exceeds|between 0 and 255/); fail("Maximum_of_Luminosity", "300", /between 0 and 255/);
  const both = oneRow((r) => { r[idx("TypeOfSteel_A300")] = "1"; r[idx("TypeOfSteel_A400")] = "1"; }); assert.equal(parseCsv(both, F, C).ok, false);
  const none = oneRow((r) => { r[idx("TypeOfSteel_A300")] = "0"; r[idx("TypeOfSteel_A400")] = "0"; }); assert.equal(parseCsv(none, F, C).ok, false);
});

test("one bad row rejects the file: no partial inference; errors are capped and name the line", () => {
  const lines = held.trim().split("\n"); lines[3] = lines[3].replace(/^[^,]+/, "oops");
  const p = parseCsv(lines.slice(0, 6).join("\n"), F, C); assert.equal(p.ok, false); if (!p.ok) assert.match(p.errors[0], /^Line 4: X_Minimum "oops"/);
  const many = [header, ...Array(100).fill("a,b")].join("\n"); const q = parseCsv(many, F, C); assert.equal(q.ok, false); if (!q.ok) assert.ok(q.errors.length <= 20);
});

test("every one of the 1941 genuine UCI rows satisfies the validation rules (rules do not reject real data)", () => {
  const rows = readFileSync(resolve(base, "ml/data/Faults.NNA"), "utf8").trim().split(/\r?\n/).map((l) => l.trim().split(/\s+/).map(Number));
  assert.equal(rows.length, 1941);
  const bad = rows.map((r, i) => [i + 1, validateRecord(F, r.slice(0, 27))] as const).filter(([, why]) => why);
  assert.deepEqual(bad.slice(0, 5), []);
});

test("sample records are exact held-out rows of the dataset with their own recorded labels", () => {
  assert.equal(samples.samples.length, 14);
  for (const s of samples.samples) {
    const values = F.map((f) => s.values[f]); assert.equal(validateRecord(F, values), null);
    const row = heldRows.find((r) => r.slice(0, 27).map(Number).every((v, i) => v === values[i]) && r[27] === s.recordedLabel);
    assert.ok(row, s.id + " is not a held-out dataset row");
    assert.match(s.id, /^UCI-198 row \d+$/);
  }
  assert.deepEqual([...new Set(samples.samples.map((s) => s.recordedLabel))].sort(), [...C].sort());
});

test("the advisory note says what the finding is not and names no motor, component or ledger event", () => {
  const pr = predict(model, heldRows[0].slice(0, 27).map(Number)); const note = advisoryNote(model, pr, "UCI-198 row 1");
  assert.match(note, /ADVISORY ML FINDING - NOT VERIFIED MANUFACTURING EVIDENCE/); assert.match(note, /creates no evidence, changes no recall decision and releases nothing/);
  assert.match(note, new RegExp(model.meta.modelSha256!)); assert.match(note, /not linked to any motor/);
  assert.doesNotMatch(note, /MTR-\d|RECALL HOLD|RELEASE ELIGIBLE|urn:pramaan/);
});
