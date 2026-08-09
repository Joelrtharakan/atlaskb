import { test } from "@playwright/test";

// Screenshot driver for the Search Compass Sweep (real /search hits).
const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";

test.skip(!TOKEN || !WS, "set E2E_ADMIN_TOKEN + E2E_WS to capture");

test("search compass sweep", async ({ page }) => {
  await page.addInitScript(
    ([t, w, e]) => {
      localStorage.setItem("atlaskb.access", t);
      localStorage.setItem("atlaskb.refresh", t);
      localStorage.setItem("atlaskb.workspace", w);
      localStorage.setItem("atlaskb.email", e);
    },
    [TOKEN, WS, EMAIL],
  );
  await page.goto("/search");
  await page.getByLabel("Query").fill("collision detection safety standard");
  await page.getByRole("button", { name: /^search$/i }).click();
  await page.waitForSelector("canvas", { timeout: 30_000 });
  await page.waitForTimeout(700); // mid-sweep: some nodes lit
  await page.screenshot({ path: "var/atlas/search-sweep-mid.png" });
  await page.waitForTimeout(1200); // end: sweep completed, results lit
  await page.screenshot({ path: "var/atlas/search-sweep-end.png" });
});
