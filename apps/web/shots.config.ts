import { defineConfig, devices } from "@playwright/test";

// Isolated config for ad-hoc screenshot runs: reuses the already-running dev
// server (E2E_BASE_URL) and does NOT spawn its own `npm run dev`, so it can't
// collide with the running server over the shared .next directory.
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    trace: "off",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
