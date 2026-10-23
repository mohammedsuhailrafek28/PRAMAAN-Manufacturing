// Owned per-test stack: own database, own custody directory, own root checkpoint, own port. Nothing is shared between tests.
// A capture moves the ledger past the active checkpoint (ANCHORED_PREFIX_ONLY). `cycle()` performs the explicit TEST-ONLY custodian
// steps (propose -> accept with typed digest) through application.checkpoint_ops and restarts the server with the successor and its
// predecessor. Local test custody: this is NOT independent custody and the helper never activates a checkpoint on a running server.
import { ChildProcess, spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const ROOT = resolve("..");
const PY = resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python");

export class OwnedStack {
  readonly dir = mkdtempSync(join(tmpdir(), "pramaan-owned-"));
  readonly database = join(this.dir, "ledger.sqlite");
  readonly custody = join(this.dir, "custody");
  current = join(this.dir, "custody", "root.json");
  previous: string | undefined;
  generations = 0;
  unanchored = false;   // real server started WITHOUT --trusted-anchor (UNANCHORED historical records only)
  private server?: ChildProcess;
  constructor(readonly port: number) {}
  get base() { return `http://127.0.0.1:${this.port}`; }

  static async start(port: number, opts: { empty?: boolean; unanchored?: boolean } = {}): Promise<OwnedStack> {
    const s = new OwnedStack(port); s.unanchored = !!opts.unanchored;
    mkdirSync(s.custody, { recursive: true });
    const boot = spawnSync(PY, ["recall-ui/tests/owned_bootstrap.py", s.database, s.current, ...(opts.empty ? ["--empty"] : [])], { cwd: ROOT, encoding: "utf8", windowsHide: true });
    if (boot.status !== 0) throw new Error(`bootstrap failed: ${boot.stderr}`);
    await s.launch();
    return s;
  }

  private async launch() {
    const args = ["app.py", "--database", this.database, "--port", String(this.port)];
    if (!this.unanchored) args.push("--trusted-anchor", this.current);
    if (this.previous) args.push("--previous-anchor", this.previous);
    this.server = spawn(PY, args, { cwd: ROOT, stdio: "ignore", windowsHide: true });
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(`${this.base}/api/session`)).ok) return; } catch { /* not up yet */ }
      await new Promise((r) => setTimeout(r, 150));
    }
    throw new Error(`owned server on ${this.port} did not start`);
  }

  private async halt() {
    const s = this.server; this.server = undefined;
    if (!s) return;
    await new Promise<void>((done) => { s.once("exit", () => done()); s.kill(); setTimeout(done, 3000); });
  }

  private ops(op: string, extra: string[] = []) {
    const base = ["-m", "application.checkpoint_ops", op, "--database", this.database, "--current", this.current, "--custody-dir", this.custody];
    if (this.previous) base.push("--current-previous", this.previous);
    const r = spawnSync(PY, [...base, ...extra], { cwd: ROOT, encoding: "utf8", windowsHide: true });
    if (r.status !== 0) throw new Error(`checkpoint_ops ${op} failed: ${r.stderr}`);
    return JSON.parse(r.stdout);
  }

  /** TEST-ONLY custodian steps: propose a successor, accept it by typing its digest back, restart with it activated. */
  async cycle(custodian = "Test Custodian (test-only)") {
    await this.halt();
    const proposed = this.ops("propose");
    if (proposed.status !== "CANDIDATE_PROPOSED_NOT_ACTIVATED") { await this.launch(); return proposed.status; }
    const accepted = this.ops("accept", ["--candidate", proposed.candidate, "--custodian", custodian, "--confirm-sha256", proposed.candidateSha256]);
    this.previous = this.current; this.current = accepted.accepted; this.generations++;
    await this.launch();
    return accepted.status;
  }

  /** Move the ledger past the active checkpoint without any HTTP command (an external writer). */
  async post(path: string, body: unknown) {
    const r = await fetch(`${this.base}/api/${path}`, { method: "POST", headers: { "content-type": "application/json", origin: this.base, "x-pramaan-token": (await (await fetch(`${this.base}/api/session`)).json()).token }, body: JSON.stringify(body) });
    return { status: r.status, body: await r.json().catch(() => null) };
  }

  async stop() { await this.halt(); try { rmSync(this.dir, { recursive: true, force: true }); } catch { /* best effort */ } }
}
