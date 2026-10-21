import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

// Uses the system Chrome (no browser download) against the production build.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:4173", channel: "chrome", headless: true, trace: "retain-on-failure" },
  webServer: {
    command: `npm run build && "${resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python")}" ../app.py --seed-demo --database "${join(mkdtempSync(join(tmpdir(), "pramaan-browser-")), "ledger.sqlite")}"`,
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
