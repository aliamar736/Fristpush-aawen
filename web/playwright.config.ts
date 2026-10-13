import { defineConfig } from "@playwright/test";

/* E2E against a running stack: Django API on :8000 (with `seed_demo`) and `vite preview` on :4173.
   See ../scripts/e2e.sh. */
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  workers: 2,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE ?? "http://127.0.0.1:4173",
    locale: "ar-LY",
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
