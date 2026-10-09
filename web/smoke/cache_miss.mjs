// Cache-miss / slow-model UX check. Needs the web dev server on :3000 and the stub API on
// :8001 started with STUB_MODE=unavailable (every model call answers 503, like a cache
// miss in cache-only mode). Run from web/:  node smoke/cache_miss.mjs
// Playwright is the existing install in the npx cache; set PLAYWRIGHT_DIR to override.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import path from "node:path";
import os from "node:os";

const pwDir =
  process.env.PLAYWRIGHT_DIR ||
  path.join(os.homedir(), "AppData/Local/npm-cache/_npx/381cec31605a419a/node_modules/playwright");
const { chromium } = createRequire(import.meta.url)(pwDir);

const BASE = process.env.WEB_URL || "http://localhost:3000";
const PASSWORD = "Demo!Gateway2026";
const EQUIPMENT = "Show me the equipment currently awaiting maintenance.";
const NOTICE =
  "This demonstration runs on recorded answers for its scripted questions. " +
  "Live model access is disabled in this environment.";
const shots = path.resolve("smoke/screenshots");
mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const page = await (await browser.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
page.setDefaultTimeout(60000);

function check(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  console.log(`ok   ${msg}`);
}
async function shot(name) {
  await page.screenshot({ path: path.join(shots, `${name}.png`) });
}
async function send(q) {
  await page.fill("#question", q);
  await page.press("#question", "Enter");
}
async function assertCalm() {
  const body = await page.textContent("body");
  for (const raw of ["503", "Service Unavailable", "Traceback", "unavailable; retry", "Internal Server Error"]) {
    check(!body.includes(raw), `no raw error text on screen ("${raw}")`);
  }
  check((await page.locator('[data-testid^="msg-"] [role="alert"]').count()) === 0, "no red error alert on screen");
  check((await page.locator('[data-testid="pending"]').count()) === 0, "no pending spinner left");
  check(await page.locator("#question").isEnabled(), "the question box is usable again");
}

try {
  await page.goto(BASE);
  await page.fill("#username", "owner");
  await page.fill("#password", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL("**/home");
  await page.click('a[href="/chat"]');
  await page.waitForURL("**/chat");
  await page.waitForSelector('[data-testid="user-name"]');

  // 1. the API answers 503 (cache miss): calm panel, nothing raw
  await send(EQUIPMENT);
  await page.waitForSelector('[data-testid="demo-notice"]');
  const text = (await page.textContent('[data-testid="demo-notice"]')).replace(/\s+/g, " ");
  check(text.includes(NOTICE), "503 shows the recorded-answers panel with the exact wording");
  await assertCalm();
  await shot("10-cache-miss-notice");

  // 2. no answer within 30 s: the wait ends with the same panel, not an endless spinner
  await page.route("**/api/v1/assistant/query", () => {
    /* never answered */
  });
  const before = await page.locator('[data-testid="demo-notice"]').count();
  const started = Date.now();
  await send(EQUIPMENT);
  await page.waitForSelector('[data-testid="pending"]');
  await page.waitForFunction(
    (n) => document.querySelectorAll('[data-testid="demo-notice"]').length > n,
    before,
    { timeout: 45000 },
  );
  const waited = (Date.now() - started) / 1000;
  check(waited >= 29 && waited < 40, `a silent model ends after ~30 s (${waited.toFixed(1)} s)`);
  await assertCalm();
  await shot("11-slow-model-notice");
} catch (err) {
  await shot("zz-failure-cache-miss").catch(() => {});
  console.error(String(err));
  await browser.close();
  process.exit(1);
}
console.log("cache_miss: OK");
await browser.close();
