"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useData } from "@/dash/data";
import { epochOf } from "@/dash/consistency";

type Ref = { id: string; label: string; href: string };
type Answer = { finding: string; reason: string; evidence: Ref[]; nextStep: string };
type Msg =
  | { role: "user"; text: string }
  | { role: "assistant"; answer: Answer; epoch: string; trusted: boolean; caution?: string }
  | { role: "error"; text: string };

const CHIPS = [
  "Which motors are affected by the recall?",
  "Why is MTR-27002 on hold?",
  "Which bearing batch is defective and what is connected to it?",
  "What is missing to reconsider MTR-27003?",
  "Summarise today's report",
  "How does Quality Inspection work?",
];
const MAX = 500;

export function AskWidget() {
  const { snap } = useData();
  const current = epochOf(snap.phase === "ready" ? snap.snap : null);
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const live = useRef(current);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  live.current = current;

  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [msgs, busy, open]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);

  const send = async (raw: string) => {
    const question = raw.trim();
    if (!question || busy) return;
    if (question.length > MAX) { setMsgs((m) => [...m, { role: "error", text: `Please keep the question under ${MAX} characters.` }]); return; }
    const history = msgs.filter((m): m is Extract<Msg, { role: "user" }> => m.role === "user").map((m) => m.text).slice(-4);
    setMsgs((m) => [...m, { role: "user", text: question }]); setText(""); setBusy(true);
    try {
      const res = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question, history }) });
      const body = await res.json();
      if (body?.ok) setMsgs((m) => [...m, { role: "assistant", answer: body.answer, epoch: body.epoch, trusted: body.trusted, caution: body.caution }]);
      else setMsgs((m) => [...m, { role: "error", text: typeof body?.message === "string" ? body.message : "The assistant could not answer right now." }]);
    } catch { setMsgs((m) => [...m, { role: "error", text: "The assistant could not be reached. Check your connection and try again." }]); }
    finally { setBusy(false); }
  };

  return (
    <div className="ask" data-testid="ask-root">
      {open && (
        <section className="ask-win" role="dialog" aria-label="Ask PRAMAAN" data-testid="ask-window">
          <header className="ask-head">
            <div><b>Ask PRAMAAN</b><span>Investigation Assistant</span></div>
            <button type="button" className="ask-x" onClick={() => setMsgs([])} disabled={!msgs.length} aria-label="Clear conversation" data-testid="ask-clear">Clear</button>
            <button type="button" className="ask-x" onClick={() => setOpen(false)} aria-label="Minimise assistant" data-testid="ask-close">✕</button>
          </header>
          <div className="ask-log" role="log" aria-live="polite" data-testid="ask-log">
            {!msgs.length && (
              <div className="ask-intro">
                <p>Ask about motors, bearing batches, recall decisions or evidence. Answers are filled in from the verified records; I cannot release, clear or change anything.</p>
                <div className="ask-chips">{CHIPS.map((c) => <button type="button" key={c} className="ask-chip" onClick={() => void send(c)} disabled={busy}>{c}</button>)}</div>
              </div>
            )}
            {msgs.map((m, i) => m.role === "user" ? <div key={i} className="ask-b me">{m.text}</div>
              : m.role === "error" ? <div key={i} className="ask-b err" role="alert" data-testid="ask-error">{m.text}</div>
              : <AnswerCard key={i} m={m} stale={m.epoch !== current} />)}
            {busy && <div className="ask-b bot ask-typing" data-testid="ask-typing" aria-label="Assistant is typing"><i /><i /><i /></div>}
            <div ref={end} />
          </div>
          <form className="ask-in" onSubmit={(e) => { e.preventDefault(); void send(text); }}>
            <textarea ref={input} value={text} rows={1} maxLength={MAX + 50} placeholder="Ask about a motor, batch or decision…" aria-label="Your question" data-testid="ask-input"
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(text); } }} />
            <button type="submit" className="btn" disabled={busy || !text.trim()} data-testid="ask-send">Send</button>
          </form>
          <p className="ask-foot">Rule-based answers from verified records, read-only. The deterministic evaluator alone decides recall and release.</p>
        </section>
      )}
      <button type="button" className="ask-fab" onClick={() => setOpen((o) => !o)} aria-label={open ? "Minimise Ask PRAMAAN" : "Open Ask PRAMAAN assistant"} aria-expanded={open} data-testid="ask-fab">{open ? "✕" : "?"}</button>
    </div>
  );
}

function AnswerCard({ m, stale }: { m: Extract<Msg, { role: "assistant" }>; stale: boolean }) {
  const a = m.answer;
  return (
    <div className={`ask-b bot${stale ? " stale" : ""}`} data-testid="ask-answer" data-historical={stale ? "true" : "false"}>
      {stale && <div className="ask-hist" role="note" data-testid="ask-historical"><b>HISTORICAL</b> — the evidence or its verification changed after this answer. Ask again for a current one.</div>}
      {m.caution && <div className="ask-hist" role="note" data-testid="ask-caution"><b>NOT VERIFIED CURRENT.</b> {m.caution}</div>}
      <dl>
        <dt>Finding</dt><dd>{a.finding}</dd>
        <dt>Reason</dt><dd>{a.reason}</dd>
        <dt>Evidence</dt>
        <dd>{a.evidence.length ? <ul>{a.evidence.map((e) => <li key={e.id}><Link href={e.href}>{e.label}</Link> <code>{e.id.length > 44 ? `${e.id.slice(0, 44)}…` : e.id}</code></li>)}</ul> : <span className="na">No specific record cited.</span>}</dd>
        <dt>Next step</dt><dd>{a.nextStep}</dd>
      </dl>
    </div>
  );
}
