import { test } from "@playwright/test";

// Screenshot driver (not an assertion test): injects an existing session and
// captures the Dashboard Relief Map against the real Northwind corpus. Token +
// workspace come from env so no password is needed.
const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";

// This is an on-demand screenshot driver, not part of the assertion suite. It
// only runs when an existing session is supplied via env; otherwise skip so it
// never breaks a normal `playwright test` run.
test.skip(!TOKEN || !WS, "set E2E_ADMIN_TOKEN + E2E_WS to capture dashboard shots");

async function seedSession(page: import("@playwright/test").Page) {
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

test("dashboard relief — default motion", async ({ page }) => {
  await seedSession(page);
  await page.goto("/dashboard");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3500); // terrain forms + orbit settles
  const url = page.url();
  const canvases = await page.locator("canvas").count();
  const heading = await page.locator("h1").first().textContent();
  console.log(`[diag] url=${url} canvases=${canvases} heading=${heading}`);
  await page.screenshot({ path: "var/atlas/dashboard-relief.png", fullPage: true });
});

test("dashboard relief — reduced motion (frozen frame)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await seedSession(page);
  await page.goto("/dashboard");
  await page.waitForSelector("canvas", { timeout: 30_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "var/atlas/dashboard-relief-reduced.png" });
});
