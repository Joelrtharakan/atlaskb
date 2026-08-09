import { test } from "@playwright/test";
test.skip(!process.env.E2E_ADMIN_TOKEN, "");
test("chat dark idle", async ({ page }) => {
  const t=process.env.E2E_ADMIN_TOKEN!, w=process.env.E2E_WS!;
  await page.addInitScript(([t,w])=>{localStorage.setItem("atlaskb.access",t);localStorage.setItem("atlaskb.refresh",t);localStorage.setItem("atlaskb.workspace",w);localStorage.setItem("atlaskb.email","admin@northwind.test");},[t,w]);
  await page.goto("/chat");
  await page.waitForTimeout(3500);
  await page.screenshot({ path: "var/atlas/dark-chat.png" });
});
