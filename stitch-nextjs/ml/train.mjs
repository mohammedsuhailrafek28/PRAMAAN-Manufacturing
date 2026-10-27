// Trains the advisory Random Forest from the authentic UCI "Steel Plates Faults" files in ml/data (unchanged originals).
// Pure Node, seeded and deterministic: no serialized third-party model is loaded or executed. Writes public/ml/model.json,
// public/ml/samples.json and ml/data/heldout.csv. Run: node ml/train.mjs
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const raw = readFileSync(resolve(root, "ml/data/Faults.NNA"));
const names = readFileSync(resolve(root, "ml/data/Faults27x7_var"), "utf8").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
const FEATURES = names.slice(0, 27), CLASSES = names.slice(27);
if (FEATURES.length !== 27 || CLASSES.length !== 7) throw new Error("expected 27 features and 7 classes");

const rows = raw.toString("utf8").split(/\r?\n/).filter((l) => l.trim()).map((l) => l.trim().split(/\s+/).map(Number));
if (rows.length !== 1941 || rows.some((r) => r.length !== 34 || r.some((v) => !Number.isFinite(v)))) throw new Error("unexpected dataset shape");
const X = rows.map((r) => r.slice(0, 27));
const y = rows.map((r) => { const hot = r.slice(27).map((v, i) => (v === 1 ? i : -1)).filter((i) => i >= 0); if (hot.length !== 1 || r.slice(27).some((v) => v !== 0 && v !== 1)) throw new Error("label is not exactly one-hot"); return hot[0]; });

// seeded PRNG (mulberry32)
let state = 42;
const rnd = () => { state = (state + 0x6d2b79f5) | 0; let t = Math.imul(state ^ (state >>> 15), 1 | state); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

// stratified 80/20 split
const train = [], test = [];
for (let c = 0; c < 7; c++) { const idx = shuffle(y.map((v, i) => (v === c ? i : -1)).filter((i) => i >= 0)); const k = Math.round(idx.length * 0.2); test.push(...idx.slice(0, k)); train.push(...idx.slice(k)); }
test.sort((a, b) => a - b);

const N_TREES = 60, MAX_DEPTH = 12, MIN_SPLIT = 4, MTRY = Math.floor(Math.sqrt(27));
const r6 = (v) => Math.round(v * 1e6) / 1e6;

function gini(counts, n) { let s = 0; for (const c of counts) s += (c / n) * (c / n); return 1 - s; }
function buildTree(sample) {
  const t = { f: [], t: [], l: [], r: [], v: [] };
  const node = (idx, depth) => {
    const id = t.f.length; t.f.push(-1); t.t.push(0); t.l.push(-1); t.r.push(-1); t.v.push([]);
    const counts = new Array(7).fill(0); for (const i of idx) counts[y[i]]++;
    const pure = counts.filter((c) => c > 0).length === 1;
    if (pure || depth >= MAX_DEPTH || idx.length < MIN_SPLIT) { t.v[id] = counts; return id; }
    const feats = shuffle([...Array(27).keys()]).slice(0, MTRY);
    let best = null; const parent = gini(counts, idx.length);
    for (const f of feats) {
      const order = [...idx].sort((a, b) => X[a][f] - X[b][f]); const left = new Array(7).fill(0), right = counts.slice();
      for (let k = 0; k < order.length - 1; k++) {
        const i = order[k]; left[y[i]]++; right[y[i]]--;
        const a = X[i][f], b = X[order[k + 1]][f]; if (a === b) continue;
        const nl = k + 1, nr = order.length - nl, g = (nl * gini(left, nl) + nr * gini(right, nr)) / order.length;
        if (!best || g < best.g) best = { g, f, thr: r6((a + b) / 2) };
      }
    }
    if (!best || best.g >= parent - 1e-12) { t.v[id] = counts; return id; }
    const L = idx.filter((i) => X[i][best.f] <= best.thr), Rr = idx.filter((i) => X[i][best.f] > best.thr);
    if (!L.length || !Rr.length) { t.v[id] = counts; return id; }
    t.f[id] = best.f; t.t[id] = best.thr; t.l[id] = node(L, depth + 1); t.r[id] = node(Rr, depth + 1);
    return id;
  };
  node(sample, 0); return t;
}
const trees = [];
for (let k = 0; k < N_TREES; k++) { const boot = train.map(() => train[Math.floor(rnd() * train.length)]); trees.push(buildTree(boot)); }

// evaluation with the serialized model's own arithmetic (the app's TypeScript inference is tested against these numbers)
function proba(x) { const p = new Array(7).fill(0); for (const t of trees) { let n = 0; while (t.f[n] >= 0) n = x[t.f[n]] <= t.t[n] ? t.l[n] : t.r[n]; const c = t.v[n], s = c.reduce((a, b) => a + b, 0); for (let j = 0; j < 7; j++) p[j] += c[j] / s / trees.length; } return p; }
const argmax = (p) => p.reduce((b, v, i) => (v > p[b] ? i : b), 0);
const conf = Array.from({ length: 7 }, () => new Array(7).fill(0)); let hit = 0;
for (const i of test) { const pr = argmax(proba(X[i])); conf[y[i]][pr]++; if (pr === y[i]) hit++; }
const perClass = CLASSES.map((c, i) => { const n = conf[i].reduce((a, b) => a + b, 0); return { class: c, support: n, recall: n ? r6(conf[i][i] / n) : null }; });

const sha = (b) => createHash("sha256").update(b).digest("hex");
const model = {
  format: "pramaan-advisory-random-forest/1",
  kind: "ADVISORY_ML_NOT_EVIDENCE",
  features: FEATURES, classes: CLASSES,
  trees,
  meta: {
    algorithm: `Random forest (CART, Gini), ${N_TREES} trees, max depth ${MAX_DEPTH}, ${MTRY} features per split, bootstrap samples, probability = mean of leaf class shares`,
    trainedWith: "ml/train.mjs (own seeded implementation, seed 42); no scikit-learn model or third-party serialized file is used",
    dataset: { name: "Steel Plates Faults", source: "UCI Machine Learning Repository, dataset 198", doi: "10.24432/C5J88N", licence: "CC BY 4.0", creators: "M. Buscema, S. Terzi, W. Tastle (Semeion), 2010", rows: X.length, features: 27, classes: 7, sourceFileSha256: sha(raw), classCounts: CLASSES.map((c, i) => ({ class: c, rows: y.filter((v) => v === i).length })) },
    split: { method: "stratified 80/20 by class, seed 42", train: train.length, heldOut: test.length },
    heldOut: { accuracy: r6(hit / test.length), perClass, confusion: { rowsAreRecordedLabel: CLASSES, columnsArePredicted: CLASSES, matrix: conf } },
    limits: "Trained on steel-plate surface images of one industrial domain. It says nothing about electric motors, bearings or any PRAMAAN record.",
  },
};
const json = JSON.stringify(model);
model.meta.modelSha256 = sha(Buffer.from(json));
writeFileSync(resolve(root, "public/ml/model.json"), JSON.stringify(model));
// held-out genuine records (never used for training): CSV for tests and the sample picker
const csv = [[...FEATURES, "Recorded_Label"].join(","), ...test.map((i) => [...X[i], CLASSES[y[i]]].join(","))].join("\n") + "\n";
writeFileSync(resolve(root, "ml/data/heldout.csv"), csv);
const samples = []; for (let c = 0; c < 7; c++) for (const i of test.filter((i) => y[i] === c).slice(0, 2)) samples.push({ id: `UCI-198 row ${i + 1}`, recordedLabel: CLASSES[c], values: Object.fromEntries(FEATURES.map((f, k) => [f, X[i][k]])) });
writeFileSync(resolve(root, "public/ml/samples.json"), JSON.stringify({ source: "Held-out genuine rows of the UCI Steel Plates Faults dataset (not used for training). The recorded label is the dataset's own label.", samples }));
console.log(JSON.stringify({ trainRows: train.length, heldOut: test.length, accuracy: model.meta.heldOut.accuracy, perClass, modelBytes: Buffer.byteLength(JSON.stringify(model)), sha: model.meta.modelSha256, sourceSha: sha(raw) }, null, 1));
