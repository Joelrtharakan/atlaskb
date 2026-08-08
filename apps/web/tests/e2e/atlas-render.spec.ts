import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

// Rendering-only checks (no /chat call, so no LLM quota needed): the 3D canvas
// renders in the default mode and the 2D fallback renders under reduced motion.
const FIXTURE = path.join(__dirname, "..", "fixtures", "zubrowka.md");
const SHOTS = path.join(__dirname, "..", "..", "var", "atlas");

async function signupUploadReady(page: Page): Promise<void> {
  const email = `render-${Date.now()}-${Math.floor(Math.random() * 1e4)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: /create account/i }).click();
  await page.getByLabel("Workspace name").fill("E2E Workspace");
  await page.getByRole("button", { name: /create workspace/i }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: /^upload$/i }).click();
  await expect(page.getByRole("row", { name: /zubrowka\.md/i })).toContainText("ready", {
    timeout: 90_000,
  });
}

test("3D canvas renders on the chat page", async ({ page }) => {
  await signupUploadReady(page);
  await page.goto("/chat");
  await expect(page.locator("canvas")).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: path.join(SHOTS, "08-render-3d.png") });
});

test("2D fallback renders under reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signupUploadReady(page);
  await page.goto("/chat");
  await expect(page.locator("svg[role='img']")).toBeVisible({ timeout: 15_000 });
  expect(await page.locator("canvas").count()).toBe(0);
  await page.screenshot({ path: path.join(SHOTS, "09-render-2d.png") });
});
