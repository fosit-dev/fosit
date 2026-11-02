import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run the production build (vite build + vite preview) in a real browser.
export default defineConfig({
  testDir: "e2e",
  timeout: 12 * 60_000,
  expect: { timeout: 30_000 },
  reporter: [["list"]],
  use: { baseURL: "http://localhost:4173/", trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: {
    command: "pnpm build && pnpm preview",
    url: "http://localhost:4173/",
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
  },
});
