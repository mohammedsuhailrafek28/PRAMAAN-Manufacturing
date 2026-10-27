"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { advisoryNote, loadModel, predict, type Model, type Prediction } from "@/ml/forest";
import { MAX_BYTES, parseCsv, validateRecord } from "@/ml/input";

type Sample = { id: string; recordedLabel: string; values: Record<string, number> };
type Result = { source: string; recordedLabel?: string; pr: Prediction };
type Load = { phase: "loading" } | { phase: "error"; message: string } | { phase: "ready"; model: Model; samples: Sample[] };

const pct = (p: number) => `${(p * 100).toFixed(1)}%`;

export default function MlInspectionPage() {
  const [load, setLoad] = useState<Load>({ phase: "loading" });
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [m, s] = await Promise.all([fetch("/ml/model.json", { cache: "no-store" }), fetch("/ml/samples.json", { cache: "no-store" })]);
        if (!m.ok || !s.ok) throw new Error(`The model files could not be read (${m.status}/${s.status}).`);
        const model = loadModel(await m.json());
        const samples = ((await s.json()) as { samples: Sample[] }).samples;
        if (live) setLoad({ phase: "ready", model, samples });
      } catch (e) { if (live) setLoad({ phase: "error", message: e instanceof Error ? e.message : "The model could not be loaded." }); }
    })();
    return () => { live = false; };
  }, []);

  return (
    <div className="pp ml" data-testid="ml-inspection">
      <h1>Quality Inspection</h1>
      <p className="lede">An advisory classifier for steel-plate surface faults, shown here to demonstrate how a machine-learning prompt could sit beside PRAMAAN&apos;s evidence workflow. It is a separate example domain: it reads no PRAMAAN record and writes nothing.</p>
      <div className="banner bad ml-advisory" role="note" data-testid="ml-advisory"><div><b>ADVISORY ML FINDING · NOT VERIFIED MANUFACTURING EVIDENCE.</b> A prediction is a statistical guess from a model trained on public data. It is not an inspection, a measurement, a ledger event or a certificate, and it cannot change a recall decision or release anything.</div></div>
      {load.phase === "loading" && <div className="skel" style={{ height: 120 }} />}
      {load.phase === "error" && <div className="banner bad" role="alert" data-testid="ml-error"><div><b>Model unavailable.</b> {load.message} No prediction is shown.</div></div>}
      {load.phase === "ready" && <Workbench model={load.model} samples={load.samples} />}
    </div>
  );
}

function Workbench({ model, samples }: { model: Model; samples: Sample[] }) {
  const [sampleId, setSampleId] = useState(samples[0]?.id ?? "");
  const [results, setResults] = useState<Result[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [picked, setPicked] = useState(0);
  const [copied, setCopied] = useState("");
  const m = model.meta, sel = results[picked];

  const runSample = () => {
    const s = samples.find((x) => x.id === sampleId); if (!s) return;
    const values = model.features.map((f) => s.values[f]);
    const bad = validateRecord(model.features, values);
    if (bad) { setResults([]); setErrors([`${s.id}: ${bad}.`]); return; }
    setErrors([]); setPicked(0); setCopied(""); setResults([{ source: s.id, recordedLabel: s.recordedLabel, pr: predict(model, values) }]);
  };
  const runFile = async (file: File | undefined) => {
    if (!file) return;
    setCopied("");
    if (file.size > MAX_BYTES) { setResults([]); setErrors([`The file is larger than ${MAX_BYTES} bytes.`]); return; }
    const parsed = parseCsv(await file.text(), model.features, model.classes);
    if (!parsed.ok) { setResults([]); setErrors(parsed.errors); return; }
    setErrors([]); setPicked(0);
    setResults(parsed.rows.map((r) => ({ source: `${file.name} line ${r.line}`, recordedLabel: r.recordedLabel, pr: predict(model, r.values) })));
  };
  const note = useMemo(() => (sel ? advisoryNote(model, sel.pr, sel.source) : ""), [model, sel]);
  const copy = async () => { try { await navigator.clipboard.writeText(note); setCopied("Copied. Nothing was sent or saved."); } catch { setCopied("Copy is not available in this browser; select the text above instead."); } };

  return (
    <>
      <h2>1 · Input</h2>
      <div className="grid g2">
        <div className="card">
          <h3>Genuine sample record</h3>
          <p className="note">Rows of the UCI dataset that were held out from training. The dataset&apos;s own label is shown beside the prediction.</p>
          <label className="ml-row">Record <select value={sampleId} onChange={(e) => setSampleId(e.target.value)} data-testid="ml-sample">{samples.map((s) => <option key={s.id} value={s.id}>{s.id} · recorded {s.recordedLabel}</option>)}</select></label>
          <button type="button" className="btn" onClick={runSample} data-testid="ml-run-sample">Run on sample</button>
        </div>
        <div className="card">
          <h3>Upload a CSV</h3>
          <p className="note">Comma-separated, one header row with the 27 feature names (any order), up to 500 records and 1 MB. An optional <code>Recorded_Label</code> column is compared, never used. One invalid cell rejects the file.</p>
          <input type="file" accept=".csv,text/csv" onChange={(e) => { void runFile(e.target.files?.[0]); e.target.value = ""; }} data-testid="ml-file" aria-label="Upload CSV of steel-plate records" />
          <details><summary>Required columns</summary><p className="mono ml-cols">{model.features.join(", ")}</p></details>
        </div>
      </div>
      {errors.length > 0 && <div className="banner bad" role="alert" data-testid="ml-errors"><div><b>The input was rejected; no prediction was made.</b><ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul></div></div>}

      {results.length > 0 && (
        <>
          <h2 style={{ marginTop: 18 }}>2 · Advisory prediction</h2>
          <div className="scroll"><table className="t" data-testid="ml-results">
            <thead><tr><th>Record</th><th>Predicted class</th><th>Tree vote share</th><th>Next most likely</th><th>Dataset label</th></tr></thead>
            <tbody>{results.map((r, i) => {
              const second = [...r.pr.probabilities].sort((a, b) => b.p - a.p)[1];
              return <tr key={i} className={i === picked ? "sel click" : "click"} onClick={() => { setPicked(i); setCopied(""); }}>
                <td className="mono">{r.source}</td><td><span className="tag warn">[ADVISORY] {r.pr.label}</span></td><td>{pct(r.pr.confidence)}</td><td>{second.label} {pct(second.p)}</td>
                <td>{r.recordedLabel ? <>{r.recordedLabel} <span className={`tag ${r.recordedLabel === r.pr.label ? "ok" : "bad"}`}>{r.recordedLabel === r.pr.label ? "agrees" : "differs"}</span></> : <span className="na">none supplied</span>}</td></tr>;
            })}</tbody></table></div>
          {sel && <div className="card ml-detail" data-testid="ml-detail" style={{ marginTop: 12 }}>
            <h3>Class shares for {sel.source}</h3>
            <ul className="ml-bars">{sel.pr.probabilities.map((p) => <li key={p.label}><span>{p.label}</span><span className="ml-bar"><i style={{ width: `${Math.max(1, p.p * 100)}%` }} /></span><b className="mono">{pct(p.p)}</b></li>)}</ul>
            <p className="note">Vote share is the average of {model.trees.length} trees&apos; leaf class shares. It is not a calibrated probability: a high share does not mean the plate is defective with that likelihood.</p>
          </div>}
        </>
      )}

      <h2 style={{ marginTop: 18 }}>3 · Advisory finding or verified evidence</h2>
      <div className="scroll"><table className="t ml-compare" data-testid="ml-compare">
        <thead><tr><th /><th>ML advisory finding (this page)</th><th>Verified manufacturing evidence (PRAMAAN)</th></tr></thead>
        <tbody>
          <tr><th>What it is</th><td>A model&apos;s statistical guess from 27 numbers.</td><td>Hash-chained ledger events with source, time and capture hash.</td></tr>
          <tr><th>Who stands behind it</th><td>Nobody has inspected the item. Trained on public data; {pct(m.heldOut.accuracy)} accurate on its own held-out split, weaker on some classes.</td><td>A named source and capture, recorded as a claim and checked by the ledger for integrity (not for truth).</td></tr>
          <tr><th>Standing in PRAMAAN</th><td><span className="tag warn">[ADVISORY]</span> No ledger event, no passport entry, no recall input.</td><td><span className="tag info">RECORDED CLAIMS</span> Inputs to the evaluator under the checkpoint gate.</td></tr>
          <tr><th>Can it change a decision?</th><td><b>No.</b> It cannot hold, clear or release a motor.</td><td>Only through the engine&apos;s published decision, while the checkpoint is anchored current.</td></tr>
        </tbody></table></div>

      <h2 style={{ marginTop: 18 }}>4 · Model and dataset provenance</h2>
      <div className="card" data-testid="ml-provenance">
        <dl className="kv">
          <dt>Dataset</dt><dd>{m.dataset.name} · {m.dataset.source} · DOI {m.dataset.doi} · {m.dataset.licence}<div className="na">{m.dataset.creators}. {m.dataset.rows} rows, {m.dataset.features} features, {m.dataset.classes} classes.</div></dd>
          <dt>Source file sha-256</dt><dd className="mono">{m.dataset.sourceFileSha256}</dd>
          <dt>Model</dt><dd>{m.algorithm}</dd>
          <dt>Training</dt><dd>{m.trainedWith}. {m.split.method}: {m.split.train} train, {m.split.heldOut} held out.</dd>
          <dt>Model sha-256</dt><dd className="mono">{m.modelSha256}</dd>
          <dt>Held-out accuracy</dt><dd>{pct(m.heldOut.accuracy)} · recall by class: {m.heldOut.perClass.map((c) => `${c.class} ${c.recall === null ? "n/a" : pct(c.recall)}`).join(" · ")}</dd>
          <dt>Limits</dt><dd>{m.limits}</dd>
        </dl>
      </div>

      <h2 style={{ marginTop: 18 }}>5 · Possible handoff to an investigation</h2>
      <div className="card" data-testid="ml-handoff">
        {sel ? <>
          <p>A person may copy the advisory note below into an investigation as a prompt for a real inspection. This page does not create evidence, link a steel-plate record to any motor or component, alter a recall decision, or release a product.</p>
          <pre className="ml-note mono" data-testid="ml-note">{note}</pre>
          <button type="button" className="btn ghost" onClick={() => void copy()} data-testid="ml-copy">Copy advisory note</button> <span className="na" role="status">{copied}</span>
          <p style={{ marginTop: 10 }}><Link className="btn ghost" href="/dashboard/evidence">Open Evidence investigation</Link> <Link className="btn ghost" href="/dashboard/recall">Open Recall investigation</Link></p>
        </> : <p className="na">Run a sample or upload a CSV to prepare an advisory note.</p>}
      </div>
    </>
  );
}
