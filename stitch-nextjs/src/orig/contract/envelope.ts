// One read-only GET of /api/snapshot that keeps the HTTP status and the structured error body, so
// the gate can classify by `status`/`state` instead of by message text. GET only, never a mutation.
export async function getEnvelope(url: string, timeoutMs: number, signal?: AbortSignal): Promise<{ status: number; body: unknown }> {
  const ctl = new AbortController();
  const abort = () => ctl.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) ctl.abort();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      fetch(url, { method: "GET", cache: "no-store", signal: ctl.signal }).then(async (res) => {
        let body: unknown = null;
        try { body = await res.json(); } catch { body = null; }
        return { status: res.status, body };
      }),
      new Promise<never>((_, reject) => { timer = setTimeout(() => { ctl.abort(); reject(new TimeoutError()); }, timeoutMs); }),
    ]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export class TimeoutError extends Error { constructor() { super("Backend request timed out."); this.name = "TimeoutError"; } }
