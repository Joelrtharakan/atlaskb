import { test } from "@playwright/test";

const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";

test.skip(!TOKEN || !WS, "set E2E_ADMIN_TOKEN + E2E_WS to capture");

async function seed(page: import("@playwright/test").Page) {
  await page.addInitScript(
    ([t, w, e]) => {
      localStorage.setItem("atlaskb.access", t);
      localStorage.setItem("atlaskb.refresh", t);
      localStorage.setItem("atlaskb.workspace", w);
      localStorage.setItem("atlaskb.email", e);
    },
    [TOKEN, WS, EMAIL],
  );
}

for (const [name, path, wait] of [
  ["documents", "/documents", 1500],
  ["dashboard", "/dashboard", 3000],
] as const) {
  test(`dark ${name}`, async ({ page }) => {
    await seed(page);
    await page.goto(path);
    await page.waitForTimeout(wait);
    await page.screenshot({ path: `var/atlas/dark-${name}.png` });
  });
}
