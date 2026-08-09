import { test } from "@playwright/test";
test("landing desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "var/atlas/landing-desktop.png" });
});
test("landing mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "var/atlas/landing-mobile.png" });
});
