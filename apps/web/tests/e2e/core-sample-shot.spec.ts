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
  const canvas = page.locator("canvas");
  await canvas.waitFor({ timeout: 30_000 });
  const core = page.getByTestId("core-sample");
  await core.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1200);

  // Sweep the cursor down the core to land on a stratum → side panel fills in.
  const box = await canvas.boundingBox();
  if (box) {
    const cx = box.x + box.width / 2;
    for (const f of [0.35, 0.5, 0.62, 0.45]) {
      await page.mouse.move(cx, box.y + box.height * f);
      await page.waitForTimeout(250);
    }
  }
  await page.waitForTimeout(500);
  await core.screenshot({ path: "var/atlas/core-sample.png" });
});
