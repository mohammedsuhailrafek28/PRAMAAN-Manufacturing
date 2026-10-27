import { defineConfig } from "@playwright/test";

// Browser matrix for the shared checkpoint/eligibility gate. It starts its own envelope server on a
// dedicated port inside the spec, so it needs no webServer and never touches port 4173.
export default defineConfig({
  testDir: "tests/e2e",
  testMatch: /gate\.spec\.ts/,
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { channel: "chrome", headless: true },
});
