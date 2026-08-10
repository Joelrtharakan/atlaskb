import { test } from "@playwright/test";

// Screenshot driver for the Document Detail Core Sample (real chunk data).
const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";
const DOC = process.env.E2E_DOC!;

test.skip(!TOKEN || !WS || !DOC, "set E2E_ADMIN_TOKEN + E2E_WS + E2E_DOC to capture");

test("core sample — with hovered stratum", async ({ page }) => {
  await page.addInitScript(
    ([t, w, e]) => {
      localStorage.setItem("atlaskb.access", t);
      localStorage.setItem("atlaskb.refresh", t);
      localStorage.setItem("atlaskb.workspace", w);
      localStorage.setItem("atlaskb.email", e);
    },
    [TOKEN, WS, EMAIL],
  );
  await page.goto(`/documents/${DOC}`);
  const core = page.getByTestId("core-sample");
  await core.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);

  // Hover a stratum in the (now plain DOM, no canvas) 2D core → side panel fills in.
  const firstBand = core.locator("button").first();
  await firstBand.hover();
  await page.waitForTimeout(300);
  await core.screenshot({ path: "var/atlas/core-sample.png" });
});
