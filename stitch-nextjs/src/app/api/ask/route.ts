import { NextRequest, NextResponse } from "next/server";
import { handleAsk, MESSAGES } from "@/ask/handler";

// Fully local and deterministic: no language model, no provider, no key. The only backend access is read-only GETs of the
// verified snapshot and a motor's decisions; this route writes nothing.
const upstream = process.env.PRAMAAN_API_URL ?? "http://127.0.0.1:4411";
const MAX_BYTES = 8 * 1024;

async function get(path: string) {
  const res = await fetch(`${upstream}${path}`, { cache: "no-store", signal: AbortSignal.timeout(8000), headers: { Host: new URL(upstream).host, "Sec-Fetch-Site": "same-origin", Accept: "application/json" } });
  if (!res.ok) throw new Error("upstream");
  return res.json();
}

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== request.headers.get("host")) return NextResponse.json({ ok: false, code: "INVALID_REQUEST", message: MESSAGES.INVALID_REQUEST }, { status: 403 });
  const text = await request.text();
  let body: unknown = null;
  if (text.length <= MAX_BYTES) { try { body = JSON.parse(text); } catch { body = null; } }
  const { status, body: out } = await handleAsk(body, { fetchSnapshot: () => get("/api/snapshot"), fetchMotorDecisions: (m) => get(`/api/motors/${encodeURIComponent(m)}/decisions`) });
  return NextResponse.json(out, { status, headers: { "Cache-Control": "no-store" } });
}
