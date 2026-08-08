import path from "node:path";

import { expect, test } from "@playwright/test";

const SHOTS = path.join(__dirname, "..", "..", "var", "atlas");

test("landing: ambient atlas is centered", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2500); // let the field render + rotate a touch
  await page.screenshot({ path: path.join(SHOTS, "10-landing.png") });
});
