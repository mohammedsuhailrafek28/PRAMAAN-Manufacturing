import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", sourcemap: true, rollupOptions: { input: { main: fileURLToPath(new URL("./index.html", import.meta.url)), passport: fileURLToPath(new URL("./passport.html", import.meta.url)) } } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/unit/**/*.test.{ts,tsx}"],
  },
});
