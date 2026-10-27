// Advisory Random Forest inference. Pure and deterministic; the model is plain JSON produced by ml/train.mjs (no serialized third-party model).
export type Tree = { f: number[]; t: number[]; l: number[]; r: number[]; v: number[][] };
export type Meta = {
  algorithm: string; trainedWith: string; limits: string; modelSha256?: string;
  dataset: { name: string; source: string; doi: string; licence: string; creators: string; rows: number; features: number; classes: number; sourceFileSha256: string; classCounts: Array<{ class: string; rows: number }> };
  split: { method: string; train: number; heldOut: number };
  heldOut: { accuracy: number; perClass: Array<{ class: string; support: number; recall: number | null }>; confusion: { matrix: number[][] } };
};
export type Model = { format: string; kind: string; features: string[]; classes: string[]; trees: Tree[]; meta: Meta };
export type Prediction = { index: number; label: string; confidence: number; probabilities: Array<{ label: string; p: number }> };

const isInt = (n: unknown): n is number => Number.isInteger(n);

/** Validates the shape of a model file before it is used; a malformed model is rejected, never partly used. */
export function loadModel(json: unknown): Model {
  const m = json as Model;
  if (!m || m.format !== "pramaan-advisory-random-forest/1" || m.kind !== "ADVISORY_ML_NOT_EVIDENCE") throw new Error("Unrecognised model format.");
  if (!Array.isArray(m.features) || m.features.length !== 27 || !Array.isArray(m.classes) || m.classes.length !== 7) throw new Error("The model must have 27 features and 7 classes.");
  if (!Array.isArray(m.trees) || m.trees.length < 1) throw new Error("The model has no trees.");
  for (const [k, t] of m.trees.entries()) {
    const n = t?.f?.length;
    if (!isInt(n) || n < 1 || t.t.length !== n || t.l.length !== n || t.r.length !== n || t.v.length !== n) throw new Error(`Tree ${k} has inconsistent arrays.`);
    for (let i = 0; i < n; i++) {
      if (t.f[i] === -1) {
        if (!Array.isArray(t.v[i]) || t.v[i].length !== m.classes.length || t.v[i].some((c) => !Number.isFinite(c) || c < 0) || t.v[i].reduce((a, b) => a + b, 0) <= 0) throw new Error(`Tree ${k} leaf ${i} is invalid.`);
      } else if (!(isInt(t.f[i]) && t.f[i] >= 0 && t.f[i] < m.features.length && Number.isFinite(t.t[i]) && isInt(t.l[i]) && isInt(t.r[i]) && t.l[i] > i && t.r[i] > i && t.l[i] < n && t.r[i] < n)) throw new Error(`Tree ${k} node ${i} is invalid.`);
    }
  }
  return m;
}

export function predict(model: Model, x: number[]): Prediction {
  if (x.length !== model.features.length || x.some((v) => !Number.isFinite(v))) throw new Error("Input must be 27 finite numbers.");
  const p = new Array<number>(model.classes.length).fill(0);
  for (const t of model.trees) {
    let n = 0;
    while (t.f[n] >= 0) n = x[t.f[n]] <= t.t[n] ? t.l[n] : t.r[n];
    const c = t.v[n], s = c.reduce((a, b) => a + b, 0);
    for (let j = 0; j < p.length; j++) p[j] += c[j] / s / model.trees.length;
  }
  for (let j = 0; j < p.length; j++) p[j] = Math.min(1, p[j]); // float summation can overshoot 1 by 1e-16 when every tree agrees
  const index = p.reduce((b, v, i) => (v > p[b] ? i : b), 0);
  return { index, label: model.classes[index], confidence: p[index], probabilities: model.classes.map((label, i) => ({ label, p: p[i] })) };
}

/** Text a person may copy into an investigation by hand. It states what the finding is not, and names no motor or component. */
export function advisoryNote(model: Model, pr: Prediction, source: string): string {
  return [
    "ADVISORY ML FINDING - NOT VERIFIED MANUFACTURING EVIDENCE",
    `Input record: ${source} (steel-plate surface features; not linked to any motor, component, lot or ledger event)`,
    `Predicted class: ${pr.label} - tree vote share ${(pr.confidence * 100).toFixed(1)}% (not a calibrated probability)`,
    `Model: ${model.meta.algorithm}`,
    `Model sha256: ${model.meta.modelSha256 ?? "unrecorded"} - dataset: ${model.meta.dataset.name}, UCI ${model.meta.dataset.doi}, ${model.meta.dataset.licence}`,
    `Held-out accuracy on the training dataset's own split: ${(model.meta.heldOut.accuracy * 100).toFixed(1)}%`,
    "Use: a prompt for human inspection only. It creates no evidence, changes no recall decision and releases nothing.",
  ].join("\n");
}
