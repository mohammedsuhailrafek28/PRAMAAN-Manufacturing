import { NextRequest, NextResponse } from "next/server";

const upstream = process.env.PRAMAAN_API_URL ?? "http://127.0.0.1:4411";
const allowed = [
  /^snapshot$/,
  /^motors$/,
  /^motors\/[^/]+\/(genealogy|decisions|lifecycle|provenance)$/,
  /^trace\/(bearingLot|rawMaterialLot|machineId|componentId)\/[^/]+$/,
  /^lots\/[^/]+\/investigation$/,
];

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const resource = path.join("/");
  if (!allowed.some((pattern) => pattern.test(resource))) {
    return NextResponse.json({ error: "Proxy route is not approved" }, { status: 404 });
  }

  try {
    const response = await fetch(`${upstream}/api/${resource}`, {
      cache: "no-store",
      headers: {
        Host: new URL(upstream).host,
        "Sec-Fetch-Site": "same-origin",
        Accept: "application/json",
      },
    });
    const body = await response.arrayBuffer();
    return new NextResponse(body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "UPSTREAM_UNAVAILABLE", decisionsUnavailable: true }, { status: 503 });
  }
}
