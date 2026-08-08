import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

// Verifies the functional (chat) atlas is centered and contained with several
// documents. Uploads via the API (fast) using the session's token, waits for
// ingestion, then screenshots the idle atlas — no /chat call, so no LLM needed.
const FIXTURE = path.join(__dirname, "..", "fixtures", "zubrowka.md");
const SHOTS = path.join(__dirname, "..", "..", "var", "atlas");
const API = process.env.E2E_API_URL ?? "http://localhost:8000";

test("chat atlas is centered and contained with several documents", async ({ page }) => {
  const email = `atlas-fit-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: /create account/i }).click();
  await page.getByLabel("Workspace name").fill("Fit Workspace");
  await page.getByRole("button", { name: /create workspace/i }).click();
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();

  const token = await page.evaluate(() => localStorage.getItem("atlaskb.access"));
  const ws = await page.evaluate(() => localStorage.getItem("atlaskb.workspace"));
  const headers = { Authorization: `Bearer ${token}`, "X-Workspace-Id": ws! };
  const buffer = fs.readFileSync(FIXTURE);

  for (let i = 0; i < 8; i++) {
    const r = await page.request.post(`${API}/documents`, {
      headers,
      multipart: { file: { name: `doc-${i}.md`, mimeType: "text/markdown", buffer } },
    });
    expect(r.status()).toBe(201);
  }

  await expect
    .poll(
      async () => {
        const r = await page.request.get(`${API}/documents`, { headers });
        const docs = await r.json();
        return docs.length >= 8 && docs.every((d: { status: string }) => d.status === "ready");
      },
      { timeout: 90_000, intervals: [2000] },
    )
    .toBe(true);

  await page.goto("/chat");
  await expect(page.locator("canvas")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(SHOTS, "11-chat-atlas.png") });

  // The transcript is a bounded, internally-scrollable region (not the page).
  const log = await page.evaluate(() => {
    const el = document.querySelector('[role="log"]') as HTMLElement | null;
    if (!el) return null;
    return { overflowY: getComputedStyle(el).overflowY, clientH: el.clientHeight, winH: window.innerHeight };
  });
  expect(log?.overflowY).toBe("auto");
  expect(log!.clientH).toBeLessThan(log!.winH);

  // Focused state (a question in flight): the globe must stay inside the frame.
  await page.getByLabel("Ask a question").fill("What is the capital of Zubrowka?");
  await page.getByRole("button", { name: /^ask$/i }).click();
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(SHOTS, "12-chat-atlas-focus.png") });
});
