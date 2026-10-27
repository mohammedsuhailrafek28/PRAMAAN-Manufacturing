// Strict parsing and validation of an uploaded CSV of steel-plate feature records. One bad cell rejects the whole file: no partial inference.
export const MAX_BYTES = 1_000_000;
export const MAX_ROWS = 500;
const MAX_ERRORS = 20;

export type Row = { line: number; values: number[]; recordedLabel?: string };
export type Parsed = { ok: true; rows: Row[] } | { ok: false; errors: string[] };

const NUM = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
const LABEL = "Recorded_Label";

/** Logical bounds taken from the dataset definitions; every genuine UCI row satisfies them (tested over all 1941 rows). */
const UNIT = ["Edges_Index", "Empty_Index", "Square_Index", "Outside_X_Index", "Edges_X_Index", "Edges_Y_Index", "Outside_Global_Index", "SigmoidOfAreas"];
const SIGNED = ["Orientation_Index", "Luminosity_Index"];

function checkRow(f: Record<string, number>): string | null {
  for (const k of ["TypeOfSteel_A300", "TypeOfSteel_A400"]) if (f[k] !== 0 && f[k] !== 1) return `${k} must be 0 or 1`;
  if (f.TypeOfSteel_A300 + f.TypeOfSteel_A400 !== 1) return "exactly one of TypeOfSteel_A300 and TypeOfSteel_A400 must be 1";
  for (const k of UNIT) if (f[k] < 0 || f[k] > 1) return `${k} must be between 0 and 1`;
  for (const k of SIGNED) if (f[k] < -1 || f[k] > 1) return `${k} must be between -1 and 1`;
  for (const k of ["Pixels_Areas", "X_Perimeter", "Y_Perimeter", "Length_of_Conveyer", "Steel_Plate_Thickness", "Sum_of_Luminosity"]) if (!(f[k] > 0)) return `${k} must be greater than 0`;
  if (f.X_Maximum < f.X_Minimum) return "X_Maximum is smaller than X_Minimum";
  if (f.Y_Maximum < f.Y_Minimum) return "Y_Maximum is smaller than Y_Minimum";
  if (f.Minimum_of_Luminosity > f.Maximum_of_Luminosity) return "Minimum_of_Luminosity exceeds Maximum_of_Luminosity";
  for (const k of ["Minimum_of_Luminosity", "Maximum_of_Luminosity"]) if (f[k] < 0 || f[k] > 255) return `${k} must be between 0 and 255`;
  return null;
}

export function validateRecord(features: string[], values: number[]): string | null {
  if (values.length !== features.length || values.some((v) => !Number.isFinite(v))) return "needs 27 finite numbers";
  return checkRow(Object.fromEntries(features.map((k, i) => [k, values[i]])));
}

export function parseCsv(text: string, features: string[], classes: string[]): Parsed {
  if (text.length > MAX_BYTES) return { ok: false, errors: [`The file is larger than ${MAX_BYTES} bytes.`] };
  if (text.includes('"')) return { ok: false, errors: ["Quoted fields are not supported. Use plain comma-separated numbers."] };
  const lines = text.replace(/^﻿/, "").split(/\r\n|\n|\r/);
  while (lines.length && lines[lines.length - 1].trim() === "") lines.pop();
  if (lines.length === 0) return { ok: false, errors: ["The file is empty."] };
  const header = lines[0].split(",").map((h) => h.trim());
  const errors: string[] = [];
  const seen = new Set<string>();
  for (const h of header) { if (seen.has(h)) errors.push(`Duplicate column ${h}.`); seen.add(h); }
  for (const h of header) if (!features.includes(h) && h !== LABEL) errors.push(`Unknown column ${h || "(empty name)"}.`);
  for (const f of features) if (!seen.has(f)) errors.push(`Missing column ${f}.`);
  if (errors.length) return { ok: false, errors: errors.slice(0, MAX_ERRORS) };
  if (lines.length === 1) return { ok: false, errors: ["The file has a header but no records."] };
  if (lines.length - 1 > MAX_ROWS) return { ok: false, errors: [`More than ${MAX_ROWS} records.`] };
  const col = header.map((h) => (h === LABEL ? -1 : features.indexOf(h)));
  const rows: Row[] = [];
  for (let n = 1; n < lines.length; n++) {
    const cells = lines[n].split(",").map((c) => c.trim());
    const line = n + 1;
    if (cells.length !== header.length) { errors.push(`Line ${line}: expected ${header.length} values, found ${cells.length}.`); continue; }
    const values = new Array<number>(features.length).fill(NaN);
    let label: string | undefined, bad = false;
    for (let c = 0; c < cells.length; c++) {
      if (col[c] === -1) {
        if (cells[c] !== "") { if (!classes.includes(cells[c])) { errors.push(`Line ${line}: ${LABEL} "${cells[c].slice(0, 30)}" is not one of the seven classes.`); bad = true; } else label = cells[c]; }
        continue;
      }
      if (!NUM.test(cells[c])) { errors.push(`Line ${line}: ${features[col[c]]} "${cells[c].slice(0, 20)}" is not a plain number.`); bad = true; continue; }
      const v = Number(cells[c]);
      if (!Number.isFinite(v)) { errors.push(`Line ${line}: ${features[col[c]]} is out of range.`); bad = true; continue; }
      values[col[c]] = v;
    }
    if (!bad) { const why = validateRecord(features, values); if (why) { errors.push(`Line ${line}: ${why}.`); bad = true; } }
    if (!bad) rows.push({ line, values, recordedLabel: label });
    if (errors.length >= MAX_ERRORS) break;
  }
  return errors.length ? { ok: false, errors: errors.slice(0, MAX_ERRORS) } : { ok: true, rows };
}
