import { test } from "@playwright/test";

const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";

test.skip(!TOKEN || !WS, "set E2E_ADMIN_TOKEN + E2E_WS to capture");

test("settings instrument panel", async ({ page }) => {
  await page.addInitScript(
    ([t, w, e]) => {
      localStorage.setItem("atlaskb.access", t);
      localStorage.setItem("atlaskb.refresh", t);
      localStorage.setItem("atlaskb.workspace", w);
      localStorage.setItem("atlaskb.email", e);
    },
    [TOKEN, WS, EMAIL],
  );
  await page.goto("/settings");
  await page.getByRole("heading", { name: "Settings" }).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: "var/atlas/settings.png" });
});
