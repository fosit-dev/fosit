import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Static, relative-path build so the app can be hosted anywhere or embedded via iframe.
export default defineConfig({
  base: "./",
  plugins: [react()],
  worker: { format: "es" },
  build: { target: "es2022", sourcemap: true },
  test: { include: ["tests/**/*.test.ts"], environment: "node" },
});
