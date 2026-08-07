import path from "node:path";

import { expect, test } from "@playwright/test";

// Full product loop against the real backend:
// signup -> upload a document -> wait until ready -> ask a question ->
// see a cited answer on screen.
//
// Prerequisites (see README): API + worker + Postgres + Redis running, and the
// backend configured with OPENROUTER_API_KEY so /chat can answer.

const FIXTURE = path.join(__dirname, "..", "fixtures", "zubrowka.md");

test("signup, upload, ask, and get a cited answer", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "password123";

  // --- Sign up ---
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /create account/i }).click();

  // Lands on the documents register.
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();

  // --- Upload a document ---
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: /^upload$/i }).click();

  // The row appears and settles to "ready" once the worker finishes ingesting.
  const row = page.getByRole("row", { name: /zubrowka\.md/i });
  await expect(row).toBeVisible();
  await expect(row).toContainText("ready", { timeout: 90_000 });

  // --- Ask a question ---
  await page.getByRole("link", { name: "Chat" }).click();
  await expect(page.getByRole("heading", { name: /ask your atlas/i })).toBeVisible();

  await page.getByLabel("Ask a question").fill("What is the capital of Zubrowka?");
  await page.getByRole("button", { name: /^ask$/i }).click();

  // --- See a cited answer ---
  // An answerable response carries at least one inline citation marker.
  const citation = page.getByRole("button", { name: /citation 1/i }).first();
  await expect(citation).toBeVisible({ timeout: 60_000 });

  // The visible answer paragraph (the one holding the marker) states the fact.
  const answerPara = page.locator("p", { has: citation });
  await expect(answerPara).toBeVisible();
  await expect(answerPara).toContainText(/Lutz/i);

  // Activating the citation reveals its source chunk (with page/section + text).
  await citation.click();
  await expect(page.getByRole("tooltip").first()).toBeVisible();
});
