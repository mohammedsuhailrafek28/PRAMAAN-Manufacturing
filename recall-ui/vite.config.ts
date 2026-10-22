import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// One HTML entry per standalone page. Each page owns its own source folder, styles and tests; none imports another.
const page = (file: string) => fileURLToPath(new URL(`./${file}`, import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      input: {
        main: page("index.html"),
        passport: page("passport.html"),
        investigation: page("investigation.html"),
        impact: page("impact.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/unit/**/*.test.{ts,tsx}"],
  },
});
