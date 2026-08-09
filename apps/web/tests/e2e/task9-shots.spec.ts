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

test("login compass (no session)", async ({ page }) => {
  await page.goto("/login");
  await page.waitForSelector("canvas", { timeout: 30_000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "var/atlas/login-compass.png" });
});

test("onboarding terrain forming", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForSelector("canvas", { timeout: 30_000 });
  await page.waitForTimeout(2500); // let terrain rise
  await page.screenshot({ path: "var/atlas/onboarding.png" });
});

test("members role flags", async ({ page }) => {
  await seed(page);
  await page.goto("/members");
  await page.getByRole("heading", { name: "Members" }).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "var/atlas/members-flags.png" });
});
