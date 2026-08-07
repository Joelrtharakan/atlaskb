import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

// Living Atlas verification against the real backend:
//  - 3D mode: canvas renders; asking a real question flies the camera to the
//    retrieved nodes and draws answer threads; the cited answer appears.
//  - reduced-motion: falls back to the 2D map (no <canvas>), citations still work.
//
// Prereqs: API + worker + Postgres + Redis running with OPENROUTER_API_KEY set.

const FIXTURE = path.join(__dirname, "..", "fixtures", "zubrowka.md");
const SHOTS = path.join(__dirname, "..", "..", "var", "atlas");

async function signupUploadReady(page: Page): Promise<void> {
  const email = `atlas-${Date.now()}-${Math.floor(Math.random() * 1e4)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();

  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: /^upload$/i }).click();
  const row = page.getByRole("row", { name: /zubrowka\.md/i });
  await expect(row).toBeVisible();
  await expect(row).toContainText("ready", { timeout: 90_000 });
}

test("3D atlas: camera + answer-thread animation for a real question", async ({ page }) => {
  await signupUploadReady(page);

  await page.goto("/chat");
  // The 3D scene lazy-loads a WebGL canvas.
  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: path.join(SHOTS, "01-idle.png") });

  await page.getByLabel("Ask a question").fill("What is the capital of Zubrowka?");
  await page.getByRole("button", { name: /^ask$/i }).click();

  // Mid-retrieval: camera easing toward the lit cluster, threads drawing.
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(SHOTS, "02-retrieving.png") });

  // Cited answer lands in the panel.
  const citation = page.getByRole("button", { name: /citation 1/i }).first();
  await expect(citation).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: path.join(SHOTS, "03-answered.png") });

  // Hovering a citation highlights its node in the scene.
  await citation.hover();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOTS, "04-hover-highlight.png") });

  // Canvas is still present (3D path was used, not the fallback).
  await expect(canvas).toBeVisible();
});

test.describe("reduced motion", () => {
  test("falls back to the 2D map; citations still work", async ({ page }) => {
    // Emulate the OS setting explicitly (the context option isn't reliably
    // reflected in window.matchMedia across Chromium builds).
    await page.emulateMedia({ reducedMotion: "reduce" });
    await signupUploadReady(page);
    await page.goto("/chat");

    // No WebGL canvas — the 2D fallback (an SVG map) is used instead.
    await expect(page.locator("svg[role='img']")).toBeVisible({ timeout: 15_000 });
    expect(await page.locator("canvas").count()).toBe(0);

    await page.getByLabel("Ask a question").fill("What is the capital of Zubrowka?");
    await page.getByRole("button", { name: /^ask$/i }).click();

    const citation = page.getByRole("button", { name: /citation 1/i }).first();
    await expect(citation).toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: path.join(SHOTS, "05-reduced-motion-2d.png") });
  });
});
