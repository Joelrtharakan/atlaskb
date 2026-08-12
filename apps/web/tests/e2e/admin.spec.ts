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
  // New users have no workspace yet — create one via the bootstrap screen.
  await page.getByLabel("Workspace name").fill("E2E Workspace");
  await page.getByRole("button", { name: /create workspace/i }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();
}

test("admin analytics + evals pages render", async ({ page }) => {
  await signup(page);
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: /^upload$/i }).click();
  await expect(page.getByRole("listitem").filter({ hasText: /zubrowka\.md/i })).toContainText("ready", {
    timeout: 90_000,
  });

  // Members/Analytics/Content Gaps/Evals/Feedback/Audit Log are collapsed
  // into an "Admin" dropdown (not direct nav links) since the primary nav
  // ran out of horizontal room with all of them inline.
  await page.getByRole("button", { name: /^admin/i }).click();
  await page.getByRole("menuitem", { name: "Analytics" }).click();
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  await expect(page.getByText("Chunks indexed")).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "06-analytics.png") });

  await page.getByRole("button", { name: /^admin/i }).click();
  await page.getByRole("menuitem", { name: "Evals" }).click();
  await expect(page.getByRole("heading", { name: "Evaluations" })).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOTS, "07-evals.png") });
});

test("admin connectors page renders and offers to connect Google Drive", async ({ page }) => {
  await signup(page);

  // Real OAuth (Google Drive / OIDC) needs real credentials only the
  // deployer can provide -- this only proves the page itself renders and
  // the connect form is present, not that a live connection can be made
  // (see app/connectors/README.md's rule against faking that).
  await page.getByRole("button", { name: /^admin/i }).click();
  await page.getByRole("menuitem", { name: "Connectors" }).click();
  await expect(page.getByRole("heading", { name: "Connectors" })).toBeVisible();
  await expect(page.getByRole("button", { name: /connect with google/i })).toBeVisible();
});
