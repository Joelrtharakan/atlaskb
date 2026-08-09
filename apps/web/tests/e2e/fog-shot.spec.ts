import { test } from "@playwright/test";

// Screenshot driver for the Fog of War page (real content gaps from chat history).
const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";

test.skip(!TOKEN || !WS, "set E2E_ADMIN_TOKEN + E2E_WS to capture fog shots");

test("fog of war — before + after resolving", async ({ page }) => {
  await page.addInitScript(
    ([t, w, e]) => {
      localStorage.setItem("atlaskb.access", t);
      localStorage.setItem("atlaskb.refresh", t);
      localStorage.setItem("atlaskb.workspace", w);
      localStorage.setItem("atlaskb.email", e);
    },
    [TOKEN, WS, EMAIL],
  );
  await page.goto("/admin/content-gaps");
  await page.waitForSelector("canvas", { timeout: 30_000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: "var/atlas/fog-before.png" });

  // Resolve the first open gap → its fog should clear.
  const resolve = page.getByRole("button", { name: /resolve/i }).first();
  if (await resolve.isVisible()) {
    await resolve.click();
    await page.waitForTimeout(2200); // ~1.5s fog-clear ease + margin
    await page.screenshot({ path: "var/atlas/fog-after-resolve.png" });
  }
});
