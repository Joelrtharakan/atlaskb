import { expect, test } from "@playwright/test";

// Verifies the cross-cutting rules for every atlas-world treatment, using the
// Dashboard relief as the representative scene:
//   - prefers-reduced-motion → scene still renders (frozen), not removed
//   - no WebGL → 2D fallback renders instead, and page data stays usable
//   - the Settings "Atlas motion" pref feeds useCapabilities (still renders frozen)
const TOKEN = process.env.E2E_ADMIN_TOKEN!;
const WS = process.env.E2E_WS!;
const EMAIL = process.env.E2E_EMAIL ?? "admin@northwind.test";

test.skip(!TOKEN || !WS, "set E2E_ADMIN_TOKEN + E2E_WS to run");

async function seed(page: import("@playwright/test").Page, extra: () => void = () => {}) {
  await page.addInitScript(
    ([t, w, e]) => {
      localStorage.setItem("atlaskb.access", t);
      localStorage.setItem("atlaskb.refresh", t);
      localStorage.setItem("atlaskb.workspace", w);
      localStorage.setItem("atlaskb.email", e);
    },
    [TOKEN, WS, EMAIL],
  );
  await page.addInitScript(extra);
}

test("reduced-motion still renders the scene (frozen, not disabled)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await seed(page);
  await page.goto("/dashboard");
  await expect(page.locator("canvas")).toHaveCount(1, { timeout: 30_000 });
});

test("no WebGL falls back to 2D and the page data stays usable", async ({ page }) => {
  await seed(page, () => {
    // Force capability detection to report no WebGL.
    const proto = HTMLCanvasElement.prototype as unknown as {
      getContext: (type: string, ...args: unknown[]) => unknown;
    };
    const orig = proto.getContext;
    proto.getContext = function (this: HTMLCanvasElement, type: string, ...args: unknown[]) {
      if (type === "webgl" || type === "webgl2" || type === "experimental-webgl") return null;
      return orig.call(this, type, ...args);
    };
  });
  await page.goto("/dashboard");
  await page.getByRole("heading", { name: "Dashboard" }).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  // No 3D canvas...
  await expect(page.locator("canvas")).toHaveCount(0);
  // ...but the page's real data is still there (non-blocking rule).
  await expect(page.getByText("documents mapped")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent documents" })).toBeVisible();
});

test("Settings 'Atlas motion' off still renders the scene frozen", async ({ page }) => {
  await seed(page, () => localStorage.setItem("atlaskb.motion", "off"));
  await page.goto("/dashboard");
  await expect(page.locator("canvas")).toHaveCount(1, { timeout: 30_000 });
});
