import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

// Runs the EXISTING feature specs against a shared server that is the real H1/H2 backend (a separate,
// unmodified checkout given by H1H2_BACKEND) serving THIS branch's production build. Nothing from the
// H1/H2 branch is merged or copied into the repository; the build is only copied into that checkout's
// ignored dist/ for the duration of the run.
const backend = process.env.H1H2_BACKEND;
if (!backend) throw new Error("set H1H2_BACKEND to a checkout of the H1/H2 backend");
const py = resolve(backend, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const distTarget = resolve(backend, "recall-ui/dist");
const server = resolve(backend, "recall-ui/tests/browser_server.py");
const db = join(mkdtempSync(join(tmpdir(), "pramaan-h1h2-")), "ledger.sqlite");
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: /(passport|impact|workspace)\.spec\.ts/,
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:4173", channel: "chrome", headless: true, trace: "retain-on-failure" },
  webServer: {
    command: `node tests/copy-dist.mjs "${distTarget}" && "${py}" "${server}" "${db}"`,
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
