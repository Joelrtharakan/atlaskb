import { test } from "@playwright/test";
test.skip(!process.env.E2E_ADMIN_TOKEN, "");
test("search soundings", async ({ page }) => {
  const t=process.env.E2E_ADMIN_TOKEN!, w=process.env.E2E_WS!;
  await page.addInitScript(([t,w])=>{localStorage.setItem("atlaskb.access",t);localStorage.setItem("atlaskb.refresh",t);localStorage.setItem("atlaskb.workspace",w);localStorage.setItem("atlaskb.email","admin@northwind.test");},[t,w]);
  await page.goto("/search");
  await page.getByLabel("Search query").fill("collision detection safety standard");
  await page.getByRole("button", { name: /plot/i }).click();
  await page.waitForSelector(".doc-plate", { timeout: 30000 });
  await page.waitForTimeout(900);
  await page.screenshot({ path: "var/atlas/dark-search.png" });
});
