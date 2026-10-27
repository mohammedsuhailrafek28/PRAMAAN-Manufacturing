// Composes the Daily Operations Report as a text PDF from a freshly verified snapshot. It renders the same Report model and KPI list as the page.
import { activity, evLabel, stepLabel, type Flat } from "./eda";
import { Pdf, wrap, type Cell, type Line } from "./miniPdf";
import { BASIS, actionLabel, buildReport, findingLabel, isWithdrawnRelease, kpisOf, tsOf, type Basis } from "./reportModel";
import { describe } from "./trailModel";
import type { Snapshot } from "./types";

export type ExportInput = { snap: Snapshot; allowed: boolean; state: string; label: string; detail: string; date: string; basis: Basis; generatedAt: string; mode: "current" | "noncurrent" };
export const pdfFileName = (date: string, basis: Basis) => `PRAMAAN_Daily_Report_${date}${basis === "ingest" ? "_ingestion-time" : ""}.pdf`;

const C = { ink: "#0b1620", ink2: "#3c4a58", ink3: "#6b7a89", bronze: "#ad7944", graphite: "#141c24", ivory: "#f6f1e7", ivory2: "#efe9de", line: "#d9d1c2", red: "#9b2c2c", redBg: "#f6e3e1", green: "#2f6b4a", amber: "#8a5a12" };
const hhmm = (t?: string) => (t ? t.slice(11, 19) : "unknown");
const stamp = (t: string) => t.slice(0, 19).replace("T", " ") + " UTC";
const L = (t: string, f: Line["f"] = "R", c?: string, s?: number): Line => ({ t, f, c, s });

export function buildDailyPdf(inp: ExportInput): Uint8Array {
  const { snap: s, allowed, date, basis, label } = inp, r = buildReport(s, date, basis, allowed), b = BASIS[basis];
  const pdf = new Pdf({ title: `PRAMAAN Daily Operations Report ${date}`, subject: `${b.label}${allowed ? "" : " · NOT CURRENT, decisions withheld"}`, author: "PRAMAAN dashboard (synthetic demonstration data)" });
  const { l, W } = { l: pdf.M.l, W: pdf.W };
  const gateLine = `Gate: ${inp.state} (${label})`;

  pdf.chrome = (p, ops, no, total) => {
    if (no > 1) { p.text(l, 38, "PRAMAAN  ·  Daily Operations Report", "B", 8, C.ink2, ops); p.textR(l + W, 38, `${date}  ·  ${b.label}`, "R", 8, C.ink3, ops); p.line(l, 46, l + W, 46, C.line, 0.6, ops); }
    p.line(l, 800, l + W, 800, C.line, 0.6, ops);
    p.text(l, 812, `Generated ${stamp(inp.generatedAt)}  ·  ${gateLine}${allowed ? "" : "  ·  NOT CURRENT"}`, "R", 7, C.ink3, ops);
    p.text(l, 822, "Synthetic demonstration data. Recorded claims; not independent custody; not a safety certification.", "R", 7, C.ink3, ops);
    p.textR(l + W, 812, `Page ${no} of ${total}`, "B", 8, C.ink2, ops);
  };

  // ---- masthead
  pdf.rect(0, 0, 595.28, 128, C.graphite); pdf.rect(0, 128, 595.28, 3, C.bronze);
  pdf.text(l, 42, "P R A M A A N", "B", 10, C.bronze);
  pdf.text(l, 78, "Daily Operations Report", "B", 25, C.ivory);
  pdf.text(l, 102, `${date}  ·  ${b.label}`, "R", 12, "#d8cfbd");
  pdf.text(l, 118, `Manufacturing  ·  ${s.units.length}-motor synthetic ledger demonstration`, "R", 8.5, "#9db0c2");
  pdf.y = 150;
  const meta: [string, string][] = [["Report date", `${date} (UTC day, 00:00:00Z to 24:00:00Z)`], ["Time basis", `${b.label} (${b.field})`], ["Generated", stamp(inp.generatedAt)]];
  meta.forEach(([k, v], i) => { const x = l + i * (W / 3); pdf.text(x, pdf.y + 9, k, "R", 8, C.ink3); wrapTo(pdf, v, x, pdf.y + 22, W / 3 - 12, "B", 9, C.ink); });
  pdf.y += 54;
  pdf.para(b.help, { size: 8.5, color: C.ink2 });
  pdf.gap(6);
  if (!allowed) banner(pdf, `NOT CURRENT · ${label}`, `Findings, actions, holds and decision changes are withheld from this document. Recorded event claims are included as historical records with the limits in section 07. ${inp.detail}`);
  else pdf.para(`Gate state at export: ${inp.state} (${label}). Decision sections were computed from a snapshot fetched and verified at export time.`, { size: 8.5, color: C.ink2 });

  // ---- 01 executive overview
  section(pdf, "01", "Executive overview", 120);
  const kp = kpisOf(r, allowed, s.units.length, label), bw = (W - 20) / 3, bh = 66;
  pdf.ensure(bh * 2 + 10);
  kp.forEach((k, i) => {
    const x = l + (i % 3) * (bw + 10), y = pdf.y + Math.floor(i / 3) * (bh + 10);
    pdf.rect(x, y, bw, bh, C.ivory); pdf.rect(x, y, 3, bh, C.bronze);
    pdf.text(x + 12, y + 16, k.label, "R", 8.5, C.ink2); pdf.text(x + 12, y + 44, k.value, "B", 24, C.ink);
    wrapTo(pdf, k.sub, x + 12, y + 50, bw - 20, "R", 7.5, C.ink3, 1);
  });
  pdf.y += bh * 2 + 10 + 14;

  // ---- 02 manufacturing activity
  section(pdf, "02", "Manufacturing activity", 150, "Recorded claims");
  if (r.day.length === 0) pdf.para(`No manufacturing events recorded for ${date} on the ${b.label.toLowerCase()} basis.`, { color: C.ink2 });
  else {
    const flat: Flat[] = r.day.map((x) => ({ unitId: x.unitId, e: x.e, t: x.ts ? Date.parse(x.ts) : null })), act = activity(flat, new Set());
    const ch = 70; pdf.ensure(ch + 36); const y0 = pdf.y + 6, base = y0 + ch;
    const total = act.bursts.length, gap = 26, pw = (W - 18 - gap * (total - 1)) / total;
    act.bursts.forEach((u, bi) => {
      const x0 = l + 18 + bi * (pw + gap), bwid = pw / u.bins.length;
      pdf.line(x0, base, x0 + pw, base, C.ink3, 0.7);
      u.bins.forEach((bn, i) => { const h = (bn.count / act.max) * (ch - 8); pdf.rect(x0 + bwid * i + 0.5, base - h, Math.max(0.8, bwid - 1), h, C.bronze); });
      pdf.text(x0, base + 11, new Date(u.a).toISOString().slice(11, 16), "M", 7, C.ink2); pdf.textR(x0 + pw, base + 11, new Date(u.b).toISOString().slice(11, 16), "M", 7, C.ink2);
      if (bi > 0) pdf.text(x0 - gap / 2 - 4, base - ch / 2, "...", "B", 9, C.bronze);
    });
    pdf.text(l, y0 + 8, String(act.max), "M", 7, C.ink2);
    pdf.y = base + 16;
    pdf.para(`Events per ${stepLabel(act.step)} (UTC), ${b.label.toLowerCase()}. Gaps are not interpolated.`, { size: 7.5, color: C.ink3 });
    pdf.gap(6);
    const max = Math.max(1, ...r.byType.map((t) => t[1]));
    for (const [t, n] of r.byType) { pdf.ensure(16); pdf.text(l, pdf.y + 10, evLabel(t), "R", 9, C.ink); pdf.textR(l + 250, pdf.y + 10, String(n), "M", 9, C.ink); pdf.rect(l + 262, pdf.y + 3, Math.max(2, (n / max) * (W - 262)), 7, C.bronze); pdf.y += 16; }
  }

  // ---- 03 quality inspection
  section(pdf, "03", "Quality inspection", 110, "Recorded claims");
  const q = r.qc, qw = (W - 30) / 4;
  pdf.ensure(54);
  ([[q.pass, "Recorded PASS"], [q.fail, "Recorded FAIL"], [q.noOutcome, "Inspection, no explicit outcome"], [q.motorsWithoutRecord.length, "Motors with no inspection record"]] as [number, string][]).forEach(([v, k], i) => {
    const x = l + i * (qw + 10); pdf.rect(x, pdf.y, qw, 48, C.ivory); pdf.text(x + 9, pdf.y + 26, String(v), "B", 20, C.ink); wrapTo(pdf, k, x + 9, pdf.y + 31, qw - 14, "R", 7.5, C.ink2, 2);
  });
  pdf.y += 58;
  if (q.total === 0) pdf.para("No inspection records on this date. Missing records are not read as PASS.", { color: C.ink2 });
  pdf.para("A recorded PASS is an inspector's claim. It does not clear a recall and does not authorize shipment.", { size: 9, f: "B", color: C.ink });

  // ---- 04 defects and corrective actions
  section(pdf, "04", "Defects and corrective actions", 150, "Recorded claims");
  if (r.motorRows.length === 0) pdf.para(`No corrective, inspection, verification or decision activity recorded for ${date}.`, { color: C.ink2 });
  for (const m of r.motorRows) {
    const superseded = !!(m.initial && m.current && m.initial.decisionId !== m.current.decisionId);
    const withheld = [L(`WITHHELD · ${label}`, "B", C.red, 8)];
    const lw = pdf.W * 0.44 - 10, rw = pdf.W * 0.56 - 10, rx = l + pdf.W * 0.44 + 10;
    const initial: Line[] = !allowed ? withheld : m.initial ? [L(findingLabel(m.initial.evidenceFinding), "B", superseded ? C.ink3 : C.ink, 9.5), L(actionLabel(m.initial.operationalAction), "R", superseded ? C.ink3 : C.ink, 9), L(`v${m.initial.version}${superseded ? "" : " · is the current decision"}`, "R", C.ink3, 7.5)] : [L("not available", "R", C.ink3)];
    const histNote: Line[] = allowed && superseded ? [L("SUPERSEDED · HISTORICAL", "B", C.red, 7.5), ...(isWithdrawnRelease(m.initial) ? [L("Release eligibility WITHDRAWN. Not in force.", "B", C.red, 8)] : [])] : [];
    const current: Line[] = !allowed ? withheld : m.current ? [L(findingLabel(m.current.evidenceFinding), "B", C.ink, 9.5), L(actionLabel(m.current.operationalAction), "R", C.ink, 9)] : [L("none", "R", C.ink3)];
    const gaps: Line[] = allowed && m.current && m.current.evidenceFinding !== "EXCLUDED_WITH_EVIDENCE" ? (m.current.reasonCodes ?? []).map((c) => L(c, "M", C.ink2, 7.5)) : [];
    const corr: Line[] = m.corrective.length ? m.corrective.map((e) => L(`${hhmm(tsOf(e, basis))}  ${describe(e)}`, "R", C.ink, 8.5)) : [L("none this date", "R", C.ink3, 8.5)];
    const ver: Line[] = m.verification.length ? m.verification.map((e) => L(`${describe(e)} (claim)`, "R", C.ink, 8.5)) : [L("No independent confirmation recorded", "R", C.ink2, 8.5)];
    const lab = (t: string): Line => L(t, "B", C.ink3, 7.5);
    const left: Line[] = [lab("Initial finding"), ...initial];
    const hh = histNote.length ? pdf.measure(histNote, lw - 16) + 10 : 0;
    const leftH = pdf.measure(left, lw) + (hh ? hh + 6 : 0) + 8 + pdf.measure([lab("Current finding / action"), ...current], lw) + (gaps.length ? 8 + pdf.measure([lab("Evidence gaps"), ...gaps], lw) : 0);
    const rightH = pdf.measure([lab(`Corrective events this date (${b.label.toLowerCase()})`), ...corr], rw) + 8 + pdf.measure([lab("Verification evidence"), ...ver], rw);
    const h = 30 + Math.max(leftH, rightH) + 12;
    pdf.ensure(h + 6); const y0 = pdf.y;
    pdf.rect(l, y0, pdf.W, h, "#ffffff", C.line, 0.6); pdf.rect(l, y0, pdf.W, 22, C.ivory);
    pdf.text(l + 10, y0 + 15, m.unitId, "MB", 10.5, C.ink);
    let y = y0 + 30;
    y += pdf.drawLines(left, l + 10, y, lw - 10, pdf.ops, 9);
    if (hh) { y += 6; pdf.rect(l + 10, y, lw - 10, hh, "#f6e3e1"); pdf.rect(l + 10, y, 3.5, hh, C.red); pdf.drawLines(histNote, l + 20, y + 5, lw - 26, pdf.ops, 8); y += hh; }
    y += 8; y += pdf.drawLines([lab("Current finding / action"), ...current], l + 10, y, lw - 10, pdf.ops, 9);
    if (gaps.length) { y += 8; pdf.drawLines([lab("Evidence gaps"), ...gaps], l + 10, y, lw - 10, pdf.ops, 9); }
    pdf.line(rx - 8, y0 + 30, rx - 8, y0 + h - 10, C.line, 0.5);
    let ry = y0 + 30; ry += pdf.drawLines([lab(`Corrective events this date (${b.label.toLowerCase()})`), ...corr], rx, ry, rw - 10, pdf.ops, 8.5);
    ry += 8; pdf.drawLines([lab("Verification evidence"), ...ver], rx, ry, rw - 10, pdf.ops, 8.5);
    pdf.y = y0 + h + 10;
  }
  pdf.gap(2);
  pdf.para("A corrective event or closed work order is a record, not a resolution. Where only a recall announcement exists, no defect-identification event is shown.", { size: 8.5, color: C.ink2 });

  // ---- 05 decision changes
  section(pdf, "05", "Decision changes", 150, allowed ? "Current decision history" : "Withheld");
  if (!allowed) banner(pdf, `WITHHELD · ${label}`, "Decision history is withheld while the checkpoint is not anchored current.");
  else {
    const card = (c: (typeof r.changesDay)[number]) => {
      const bw2 = (pdf.W - 36) / 2, lab = (t: string): Line => L(t, "B", C.ink3, 7.5);
      const before: Line[] = [L("SUPERSEDED · HISTORICAL", "B", C.red, 7.5), L(findingLabel(c.from.evidenceFinding), "B", C.ink3, 10), L(actionLabel(c.from.operationalAction), "R", C.ink3, 9), L(`v${c.from.version}`, "R", C.ink3, 7.5), ...(isWithdrawnRelease(c.from) ? [L("Release eligibility WITHDRAWN. Not in force.", "B", C.red, 8)] : [])];
      const after: Line[] = [L(c.toCurrent ? "CURRENT DECISION" : "LATER SUPERSEDED", "B", c.toCurrent ? C.green : C.red, 7.5), L(findingLabel(c.to.evidenceFinding), "B", C.ink, 10), L(actionLabel(c.to.operationalAction), "R", C.ink, 9), L(`v${c.to.version}`, "R", C.ink3, 7.5)];
      const trig: Line[] = c.trigger ? [L(describe(c.trigger), "R", C.ink, 8.5), L(`${b.label}: ${c.triggerTs ? stamp(c.triggerTs) : "unknown"}`, "R", C.ink3, 7.5)] : [L("trigger event not recorded", "R", C.ink3, 8.5)];
      const why = c.addedReasons.length || c.removedReasons.length ? [c.addedReasons.length ? `+ ${c.addedReasons.join(", ")}` : "", c.removedReasons.length ? `- ${c.removedReasons.join(", ")}` : ""].filter(Boolean).join("   ") : "reasons unchanged";
      const bh = Math.max(pdf.measure(before, bw2 - 22), pdf.measure(after, bw2 - 22)) + 16, th = pdf.measure(trig, pdf.W - 120), wh = wrap(why, "M", 7.5, pdf.W - 120).length * 10.5;
      const h = 26 + bh + 12 + th + 8 + wh + 12;
      pdf.ensure(h + 8); const y0 = pdf.y;
      pdf.rect(l, y0, pdf.W, h, "#ffffff", C.line, 0.6); pdf.rect(l, y0, pdf.W, 22, C.ivory);
      pdf.text(l + 10, y0 + 15, c.unitId, "MB", 10.5, C.ink); pdf.textR(l + pdf.W - 10, y0 + 15, `v${c.from.version} -> v${c.to.version}`, "M", 8.5, C.ink2);
      const by = y0 + 30;
      pdf.rect(l + 10, by, bw2, bh, "#f6e3e1"); pdf.rect(l + 10, by, 3.5, bh, C.red); pdf.drawLines(before, l + 22, by + 8, bw2 - 22, pdf.ops, 9);
      pdf.text(l + 10 + bw2 + 8, by + bh / 2 + 4, "->", "B", 11, C.bronze);
      const ax = l + 10 + bw2 + 26; pdf.rect(ax, by, bw2 - 10, bh, C.ivory); pdf.rect(ax, by, 3.5, bh, c.toCurrent ? C.green : C.red); pdf.drawLines(after, ax + 12, by + 8, bw2 - 32, pdf.ops, 9);
      let y = by + bh + 12;
      pdf.text(l + 10, y + 8, "Triggering event", "B", 7.5, C.ink3); y += pdf.drawLines(trig, l + 110, y, pdf.W - 120, pdf.ops, 8.5) + 8;
      pdf.text(l + 10, y + 8, "Reason change", "B", 7.5, C.ink3); wrap(why, "M", 7.5, pdf.W - 120).forEach((ln, i) => pdf.text(l + 110, y + 8 + i * 10.5, ln, "M", 7.5, C.ink2));
      pdf.y = y0 + h + 10;
    };
    if (r.changesDay.length === 0) pdf.para(`No decision change is attributable to ${date}.`, { color: C.ink2 }); else r.changesDay.forEach(card);
    if (r.undated.length) { pdf.gap(4); pdf.para("Undated changes: timing not established, not counted above.", { f: "B", size: 9, color: C.amber }); r.undated.forEach(card); }
    pdf.gap(2);
    pdf.para(`The backend gives a decision version no timestamp. A change is placed on a date only through its trigger event's ${b.label.toLowerCase()}; that is the cause's time, not when the decision was issued.`, { size: 8.5, color: C.ink2 });
  }

  // ---- 06 outstanding risks
  section(pdf, "06", "Outstanding operational risks", 120);
  pdf.rect(l, pdf.y, W, 22, C.graphite); pdf.text(l + 10, pdf.y + 14.5, "CURRENT STATE AT REPORT GENERATION. This is not the state on the report date.", "B", 8.5, C.ivory); pdf.y += 30;
  if (!allowed) pdf.para(`WITHHELD · ${label}. Active holds, findings and eligibility are withheld.`, { f: "B", color: C.red });
  else {
    pdf.para(`Active recall holds: ${r.risks.holds}`, { f: "B", size: 11 }); pdf.gap(4);
    const grp = (title: string, list: typeof r.risks.affected, note?: string) => {
      pdf.ensure(34); pdf.text(l, pdf.y + 10, `${title}  (${list.length})`, "B", 10, C.ink); pdf.y += 16;
      if (!list.length) pdf.para("none", { color: C.ink3, x: l + 10 });
      for (const x of list) { pdf.ensure(14); pdf.text(l + 10, pdf.y + 9, x.unitId, "MB", 9, C.ink); pdf.text(l + 86, pdf.y + 9, actionLabel(x.d?.operationalAction), "R", 9, C.ink); pdf.y += 13; if ((x.d?.reasonCodes ?? []).length) pdf.para((x.d?.reasonCodes ?? []).join("  ·  "), { f: "M", size: 7.5, color: C.ink2, x: l + 86 }); }
      if (note) pdf.para(note, { size: 8, color: C.ink3, x: l + 10 }); pdf.gap(6);
    };
    grp("Affected", r.risks.affected); grp("Unresolved", r.risks.unresolved); grp("Excluded with evidence", r.risks.excluded, "Not a certification of safety and not an authorization to ship.");
  }

  // ---- 07 evidence and provenance
  section(pdf, "07", "Evidence and provenance", 120);
  const kv: [string, string][] = [
    ["Report", `${date} · ${b.label} · UTC · generated ${stamp(inp.generatedAt)}`],
    ["Checkpoint", `sequence ${s.checkpoint?.anchoredSequence ?? "?"} · ledger sequence ${s.freshness?.sequence ?? "?"} · ${s.freshness?.status ?? "freshness unknown"}`],
    ["Head hash", s.freshness?.headHash ?? "not available"],
    ["Gate at export", `${inp.state} · ${label} · ${inp.mode === "current" ? "current" : "not current"} · verified ${stamp(inp.generatedAt)}`],
    ["Data", `Synthetic ledger demonstration (${s.units.length} motors; ${r.rows.length} ledger events). ${r.unknown > 0 ? `${r.unknown} events have no timestamp on this basis and are in no date.` : "Every event has a timestamp on this basis."}`],
  ];
  for (const [k, v] of kv) { const lines = wrap(v, "R", 9, W - 92).length; pdf.ensure(lines * 11.5 + 6); pdf.text(l, pdf.y + 9, k, "B", 8.5, C.ink2); pdf.para(v, { f: k === "Head hash" ? "M" : "R", size: k === "Head hash" ? 7.5 : 9, x: l + 92, lead: k === "Head hash" ? 10 : 12 }); pdf.gap(2); }
  pdf.gap(4);
  for (const t of ["The checkpoint is a self-exported anchor held on the same machine. It shows the ledger was not altered since export; it is not independent custody.", "Event times and actors are source claims from a simulated clock. Ingestion time is when this ledger received the event, not when the work happened.", "Hashes show a stored record is unchanged. They do not show who issued it or that it is true.", "A repair record or a recorded QC PASS does not clear a recall. Release is decided only by the live decision engine and the shipment gate, never by this report."]) { pdf.ensure(14); pdf.text(l + 2, pdf.y + 9, "•", "B", 9, C.bronze); pdf.para(t, { size: 8.5, x: l + 14, color: C.ink2 }); }
  pdf.gap(8);
  pdf.ensure(40); pdf.text(l, pdf.y + 10, `Source event references (${r.day.length})`, "B", 10.5, C.ink); pdf.y += 18;
  if (r.day.length === 0) pdf.para("No events on this date.", { color: C.ink3 });
  else pdf.table([{ head: b.label, w: 12 }, { head: "Motor", w: 11 }, { head: "Type", w: 16 }, { head: "Event id", w: 21 }, { head: "Source #", w: 20 }, { head: "Ingested (UTC)", w: 20 }],
    r.day.map((x) => [[L(x.ts ? hhmm(x.ts) : "unknown", "M", C.ink, 7)], [L(x.unitId, "M", C.ink, 7)], [L(evLabel(x.e.eventType), "R", C.ink, 7.5)], [L(x.e.eventId.replace("urn:pramaan:", ""), "M", C.ink, 6.5)], [L(`${x.e.sourceId}#${x.e.sourceSeq}`, "M", C.ink, 6.5)], [L(x.e.repository?.localReceivedAt?.slice(0, 19).replace("T", " ") ?? "unknown", "M", C.ink, 6.5)]]), { size: 7, pad: 4 });
  return pdf.build();
}

function wrapTo(pdf: Pdf, s: string, x: number, y: number, w: number, f: "R" | "B" | "M", size: number, color: string, maxLines = 3) {
  wrap(s, f, size, w).slice(0, maxLines).forEach((ln, i) => pdf.text(x, y + i * size * 1.3 + size * 0.9, ln, f, size, color));
}
function section(pdf: Pdf, n: string, title: string, need: number, tag?: string) {
  pdf.gap(16); pdf.ensure(need);
  pdf.text(pdf.M.l, pdf.y + 16, n, "M", 10, C.bronze); pdf.text(pdf.M.l + 24, pdf.y + 17, title, "B", 16, C.ink);
  if (tag) pdf.textR(pdf.M.l + pdf.W, pdf.y + 16, tag.toUpperCase(), "B", 7.5, C.ink3);
  pdf.line(pdf.M.l, pdf.y + 26, pdf.M.l + pdf.W, pdf.y + 26, C.bronze, 1); pdf.y += 38;
}
function banner(pdf: Pdf, head: string, body: string) {
  const lines = wrap(body, "R", 8.5, pdf.W - 24), h = 24 + lines.length * 12;
  pdf.ensure(h + 6); pdf.rect(pdf.M.l, pdf.y, pdf.W, h, C.redBg); pdf.rect(pdf.M.l, pdf.y, 4, h, C.red);
  pdf.text(pdf.M.l + 14, pdf.y + 15, head, "B", 10, C.red); lines.forEach((ln, i) => pdf.text(pdf.M.l + 14, pdf.y + 29 + i * 12, ln, "R", 8.5, C.ink));
  pdf.y += h + 8;
}
