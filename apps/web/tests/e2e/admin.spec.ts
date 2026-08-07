import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const FIXTURE = path.join(__dirname, "..", "fixtures", "zubrowka.md");
const SHOTS = path.join(__dirname, "..", "..", "var", "atlas");

async function signup(page: Page): Promise<void> {
  const email = `admin-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
}

test("admin analytics + evals pages render", async ({ page }) => {
  await signup(page);
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: /^upload$/i }).click();
  await expect(page.getByRole("row", { name: /zubrowka\.md/i })).toContainText("ready", {
    timeout: 90_000,
  });

  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  await expect(page.getByText("Chunks indexed")).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "06-analytics.png") });

  await page.getByRole("link", { name: "Evals" }).click();
  await expect(page.getByRole("heading", { name: "Evaluations" })).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOTS, "07-evals.png") });
});
