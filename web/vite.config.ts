import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";

// VITE_ROBOTS (optional, build time): a robots rule for the app's own page. A site that embeds the app in a page
// of its own sets "noindex, indexifembedded": search engines then index the tool as part of that page, and not
// as a second, thinner page at the app's own address. Unset (the default): no robots tag at all.
const robots = (): Plugin => {
  let content = "";
  return {
    name: "fosit-robots",
    configResolved(config) {
      content = String(config.env.VITE_ROBOTS ?? "").trim();
    },
    transformIndexHtml() {
      return content ? [{ tag: "meta", attrs: { name: "robots", content }, injectTo: "head" }] : [];
    },
  };
};

// Static, relative-path build so the app can be hosted anywhere or embedded via iframe.
export default defineConfig({
  base: "./",
  plugins: [react(), robots()],
  worker: { format: "es" },
  build: { target: "es2022", sourcemap: true },
  test: { include: ["tests/**/*.test.ts"], environment: "node" },
});
