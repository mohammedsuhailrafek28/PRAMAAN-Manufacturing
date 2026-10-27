// Minimal text-based PDF 1.4 writer: A4, the four standard Type1 fonts (no embedding), real selectable text, vector rectangles and lines.
// It exists because the repo has no PDF dependency and a screenshot-style export would not be selectable text. No network, no compression, no external fonts.

export type Font = "R" | "B" | "M" | "MB";
export type Line = { t: string; f?: Font; s?: number; c?: string };
export type Cell = string | Line[];
export type Col = { head: string; w: number; align?: "l" | "r" };

export const A4 = { w: 595.28, h: 841.89 };
const BASE: Record<Font, string> = { R: "Helvetica", B: "Helvetica-Bold", M: "Courier", MB: "Courier-Bold" };
const FNUM: Record<Font, string> = { R: "F1", B: "F2", M: "F3", MB: "F4" };

// Helvetica / Helvetica-Bold advance widths (1/1000 em) for ASCII 32..126.
const HR = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584];
const HB = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584];

// Characters outside ASCII that WinAnsi can carry (code, width). Everything else is replaced by a plain equivalent.
const WIN: Record<string, [number, number]> = { "·": [0xb7, 278], "—": [0x97, 1000], "–": [0x96, 556], "’": [0x92, 222], "‘": [0x91, 222], "“": [0x93, 333], "”": [0x94, 333], "•": [0x95, 350], "…": [0x85, 1000], "×": [0xd7, 584], "°": [0xb0, 400] };
const PLAIN: Record<string, string> = { "−": "-", "⋯": "...", "→": "->", "←": "<-", "≥": ">=", "≤": "<=", " ": " ", " ": " ", " ": " ", "‑": "-" };

export const clean = (s: string) => [...s].map((ch) => (WIN[ch] || (ch >= " " && ch <= "~") ? ch : PLAIN[ch] ?? (ch === "\n" ? " " : "?"))).join("");
const cw = (ch: string, f: Font) => (f === "M" || f === "MB" ? 600 : WIN[ch] ? WIN[ch][1] : ((f === "B" ? HB : HR)[ch.charCodeAt(0) - 32] ?? 556));
export const widthOf = (s: string, f: Font, size: number) => ([...clean(s)].reduce((a, ch) => a + cw(ch, f), 0) * size) / 1000;
const esc = (s: string) => [...clean(s)].map((ch) => { const w = WIN[ch]; return w ? String.fromCharCode(w[0]) : ch === "(" || ch === ")" || ch === "\\" ? "\\" + ch : ch; }).join("");
const rgb = (hex: string) => { const n = parseInt(hex.replace("#", ""), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => (v / 255).toFixed(3)).join(" "); };
const num = (n: number) => (Math.round(n * 100) / 100).toString();

export function wrap(s: string, f: Font, size: number, maxW: number): string[] {
  const out: string[] = [];
  for (const para of clean(s).split("\n")) {
    let cur = "";
    const push = (w: string) => {
      // break a token that cannot fit on a line of its own (hashes, event ids) at character level
      while (widthOf(w, f, size) > maxW) { let i = 1; while (i < w.length && widthOf(w.slice(0, i + 1), f, size) <= maxW) i++; if (cur) { out.push(cur); cur = ""; } out.push(w.slice(0, i)); w = w.slice(i); }
      const next = cur ? `${cur} ${w}` : w;
      if (widthOf(next, f, size) <= maxW) cur = next; else { out.push(cur); cur = w; }
    };
    for (const w of para.split(/ +/).filter(Boolean)) push(w);
    out.push(cur);
  }
  return out;
}

export class Pdf {
  readonly M = { l: 42, r: 42, t: 64, b: 56 };
  readonly W = A4.w - 42 - 42;
  pages: string[][] = [];
  y = 0;
  chrome?: (pdf: Pdf, page: string[], no: number, total: number) => void;
  constructor(private meta: { title: string; subject: string; author: string }) { this.newPage(); }

  get ops() { return this.pages[this.pages.length - 1]; }
  get bottom() { return A4.h - this.M.b; }
  get pageNo() { return this.pages.length; }
  newPage() { this.pages.push([]); this.y = this.M.t; }
  ensure(h: number) { if (this.y + h > this.bottom) this.newPage(); }
  gap(h: number) { this.y += h; if (this.y > this.bottom) this.newPage(); }

  rect(x: number, y: number, w: number, h: number, fill?: string, stroke?: string, lw = 0.6, page = this.ops) {
    const p = [`q`]; if (fill) p.push(`${rgb(fill)} rg`); if (stroke) p.push(`${rgb(stroke)} RG ${lw} w`);
    p.push(`${num(x)} ${num(A4.h - y - h)} ${num(w)} ${num(h)} re ${fill && stroke ? "B" : fill ? "f" : "S"}`, `Q`); page.push(p.join(" "));
  }
  line(x1: number, y1: number, x2: number, y2: number, color = "#cfd9e3", lw = 0.6, page = this.ops) { page.push(`q ${rgb(color)} RG ${lw} w ${num(x1)} ${num(A4.h - y1)} m ${num(x2)} ${num(A4.h - y2)} l S Q`); }
  /** One line of text with its baseline at y (top-down). */
  text(x: number, y: number, s: string, f: Font = "R", size = 10, color = "#0b1620", page = this.ops) { page.push(`BT /${FNUM[f]} ${size} Tf ${rgb(color)} rg ${num(x)} ${num(A4.h - y)} Td (${esc(s)}) Tj ET`); }
  textR(xRight: number, y: number, s: string, f: Font = "R", size = 10, color = "#0b1620", page = this.ops) { this.text(xRight - widthOf(s, f, size), y, s, f, size, color, page); }

  /** Wrapped paragraph at the cursor, page-breaking between lines. */
  para(s: string, o: { f?: Font; size?: number; color?: string; x?: number; w?: number; lead?: number } = {}) {
    const f = o.f ?? "R", size = o.size ?? 10, lead = o.lead ?? size * 1.45, x = o.x ?? this.M.l, w = o.w ?? this.W - (x - this.M.l);
    for (const ln of wrap(s, f, size, w)) { this.ensure(lead); this.text(x, this.y + size, ln, f, size, o.color); this.y += lead; }
  }
  /** Height a block of Line[] needs when wrapped to w. */
  measure(lines: Line[], w: number, dflt = 9) { return lines.reduce((a, l) => a + wrap(l.t, l.f ?? "R", l.s ?? dflt, w).length * (l.s ?? dflt) * 1.4, 0); }
  drawLines(lines: Line[], x: number, y: number, w: number, page: string[], dflt = 9, align: "l" | "r" = "l") {
    let cy = y;
    for (const l of lines) { const f = l.f ?? "R", s = l.s ?? dflt; for (const ln of wrap(l.t, f, s, w)) { align === "r" ? this.textR(x + w, cy + s, ln, f, s, l.c, page) : this.text(x, cy + s, ln, f, s, l.c, page); cy += s * 1.4; } }
    return cy - y;
  }

  /** A table whose rows never split across pages; the header repeats on every page. */
  table(cols: Col[], rows: Cell[][], o: { size?: number; pad?: number } = {}) {
    const size = o.size ?? 8.5, pad = o.pad ?? 5, total = cols.reduce((a, c) => a + c.w, 0), xs: number[] = [], ws: number[] = [];
    let ax = this.M.l; for (const c of cols) { const w = (c.w / total) * this.W; xs.push(ax); ws.push(w); ax += w; }
    const heads = cols.map((c, i) => wrap(c.head, "B", 8, ws[i] - pad * 2)), hh = Math.max(...heads.map((h) => h.length)) * 10 + 10;
    const head = () => {
      this.ensure(hh + 2); this.rect(this.M.l, this.y, this.W, hh, "#efe9de");
      cols.forEach((c, i) => heads[i].forEach((ln, k) => c.align === "r" ? this.textR(xs[i] + ws[i] - pad, this.y + 13 + k * 10, ln, "B", 8, "#3c4a58") : this.text(xs[i] + pad, this.y + 13 + k * 10, ln, "B", 8, "#3c4a58")));
      this.y += hh;
    };
    head();
    for (const row of rows) {
      const cells = row.map((c) => (typeof c === "string" ? [{ t: c }] : c));
      const h = Math.max(...cells.map((c, i) => this.measure(c, ws[i] - pad * 2, size))) + pad * 2 - 2;
      if (this.y + h > this.bottom) { this.newPage(); head(); }
      cells.forEach((c, i) => this.drawLines(c, xs[i] + pad, this.y + pad - 1, ws[i] - pad * 2, this.ops, size, cols[i].align));
      this.y += h; this.line(this.M.l, this.y, this.M.l + this.W, this.y, "#e3dccf", 0.5);
    }
  }

  build(): Uint8Array {
    const total = this.pages.length;
    this.pages.forEach((ops, i) => this.chrome?.(this, ops, i + 1, total));
    const objs: string[] = [];
    const n = this.pages.length, first = 7, info = first + n * 2;
    objs[1] = `<< /Type /Catalog /Pages 2 0 R /Lang (en) >>`;
    objs[2] = `<< /Type /Pages /Count ${n} /Kids [${this.pages.map((_, i) => `${first + i * 2} 0 R`).join(" ")}] >>`;
    (Object.keys(BASE) as Font[]).forEach((f, i) => { objs[3 + i] = `<< /Type /Font /Subtype /Type1 /BaseFont /${BASE[f]} /Encoding /WinAnsiEncoding >>`; });
    this.pages.forEach((ops, i) => {
      const body = ops.join("\n");
      objs[first + i * 2] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${A4.w} ${A4.h}] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >> /Contents ${first + i * 2 + 1} 0 R >>`;
      objs[first + i * 2 + 1] = `<< /Length ${body.length} >>\nstream\n${body}\nendstream`;
    });
    objs[info] = `<< /Title (${esc(this.meta.title)}) /Subject (${esc(this.meta.subject)}) /Author (${esc(this.meta.author)}) /Creator (PRAMAAN dashboard, in-browser text export) >>`;
    let out = "%PDF-1.4\n%âãÏÓ\n"; const off: number[] = [];
    for (let i = 1; i < objs.length; i++) { off[i] = out.length; out += `${i} 0 obj\n${objs[i]}\nendobj\n`; }
    const xref = out.length;
    out += `xref\n0 ${objs.length}\n0000000000 65535 f \n` + off.slice(1).map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
    out += `trailer\n<< /Size ${objs.length} /Root 1 0 R /Info ${info} 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
    const bytes = new Uint8Array(out.length); for (let i = 0; i < out.length; i++) bytes[i] = out.charCodeAt(i) & 255;
    return bytes;
  }
}
