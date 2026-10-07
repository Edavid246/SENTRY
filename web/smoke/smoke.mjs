// UI smoke test. Needs the web dev server on :3000 and the stub API on :8001.
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
const POLICY = "Find the documents relating to the vehicle maintenance policy and summarize the key requirements.";
const EQUIPMENT = "Show me the equipment currently awaiting maintenance.";
const shots = path.resolve("smoke/screenshots");
mkdirSync(shots, { recursive: true });
const saved = [];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const page = await (await browser.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
page.setDefaultTimeout(60000);

async function shot(name) {
  const file = path.join(shots, `${name}.png`);
  await page.screenshot({ path: file });
  saved.push(file);
}
function check(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  console.log(`ok   ${msg}`);
}
async function login(user, password = PASSWORD) {
  await page.goto(BASE);
  await page.fill("#username", user);
  await page.fill("#password", password);
  await page.click("button[type=submit]");
}
async function ask(q) {
  const before = await page.locator('[data-testid="msg-assistant"]').count();
  await page.fill("#question", q);
  await page.press("#question", "Enter");
  await page.waitForSelector('[data-testid="pending"]', { timeout: 5000 }).catch(() => {});
  await page.waitForFunction(
    (n) => document.querySelectorAll('[data-testid="msg-assistant"]').length > n,
    before,
  );
}
const logout = async () => {
  await page.click("text=Log out");
  await page.waitForURL(BASE + "/");
};

try {
  // login screen + failure
  await page.goto(BASE);
  await shot("01-login");
  await login("a.bello", "wrong-password");
  await page.waitForSelector("text=Invalid credentials");
  check(true, "bad password shows inline 'Invalid credentials'");
  await shot("02-login-invalid");

  // a.bello: policy question -> cited answer -> open citation
  await login("a.bello");
  await page.waitForURL("**/dashboard");
  await page.waitForSelector('[data-testid="user-name"]');
  check((await page.textContent('[data-testid="clearance-badge"]')).includes("SECRET"), "a.bello clearance badge is SECRET");
  check((await page.locator("text=UAS-OPS").count()) > 0, "compartment tags shown");
  check((await page.locator('a[href="/audit"]').count()) === 0, "audit nav hidden without read_audit");
  check((await page.locator('[data-testid="nav-not-in-demo"]').count()) === 3, "three greyed 'Not in demo' nav items");

  // dashboard: login lands here; every stub tile is tagged; the Secret finding is shown
  await page.waitForSelector('[data-testid="tile-recent_findings"]');
  check((await page.locator('[data-testid="placeholder-tag"]').count()) === 1, "only the readiness tile is tagged PLACEHOLDER DATA");
  // the finding exists once a commander runs the correlation job
  await page.click('[data-testid="run-correlation"]');
  await page.waitForSelector('[data-testid="finding-link"]');
  check((await page.locator('[data-testid="item-FND-RISING-FAULTS-BN-4"]').count()) === 1, "a.bello sees the Secret finding after running correlation");
  const belloItems = await page.locator('[data-testid^="item-"]').count();
  await shot("13-dashboard-bello");
  await page.click('[data-testid="finding-link"]');
  await page.waitForSelector('[data-testid="finding-detail"]');
  const evidence = await page.locator('[data-testid="evidence-link"]').count();
  check(evidence === 10, `finding detail lists its evidence (${evidence} records)`);
  check((await page.textContent('[data-testid="finding-detail"]')).includes("SECRET"), "finding detail shows the derived SECRET label");
  await shot("17-finding-detail");
  await page.locator('[data-testid="evidence-link"]').first().click();
  await page.waitForSelector('[data-testid="record-detail"]');
  check(true, "an evidence link opens the record");
  await page.click('a[href="/dashboard"]');
  await page.waitForSelector('[data-testid="tile-recent_findings"]');
  await page.click('a[href="/chat"]');
  await page.waitForURL("**/chat");
  await shot("03-chat-empty");
  await ask(POLICY);
  const belloCites = await page.locator('[data-testid="citation-badge"]').count();
  check(belloCites > 0, `policy answer carries citations (${belloCites})`);
  await shot("04-bello-policy-answer");
  await page.locator('[data-testid="citation-badge"]').first().click();
  await page.waitForSelector('[data-testid="passage-panel"] blockquote');
  check(true, "citation opens the passage in the side panel");
  await shot("05-bello-citation-panel");

  // a.bello: equipment question -> table
  await ask(EQUIPMENT);
  await page.waitForSelector('[data-testid="result-table"]');
  const belloRows = await page.locator('[data-testid="result-table"] tbody tr').count();
  check(belloRows > 0, `equipment answer renders a result table (${belloRows} rows)`);
  await shot("06-bello-equipment-table");
  await page.locator('[data-testid="record-link"]').first().click();
  await page.waitForSelector('[data-testid="record-detail"]');
  check(true, "a result-table row link opens the record detail");
  await shot("15-record-detail");

  // map: sensors, detections and missions from the connected-data endpoint
  await page.click('a[href="/map"]');
  await page.waitForSelector('[data-testid="map-canvas"][data-ready="true"]');
  check((await page.textContent('[data-testid="count-sensor"]')) === "2", "a.bello map shows 2 sensors");
  check((await page.textContent('[data-testid="count-detection"]')) === "6", "a.bello map shows 6 detections");
  check((await page.textContent('[data-testid="count-mission"]')) === "5", "a.bello map shows 5 missions");
  await page.click('[data-testid="map-item-REC-060"]');
  await page.waitForSelector('[data-testid="map-detail"]');
  check((await page.textContent('[data-testid="map-detail"]')).includes("SECRET"), "Secret mission detail carries its classification badge");
  await shot("17-map-bello");
  // replay: detections arrive over time as the replay clock advances (stub live feed)
  await page.click('[data-testid="replay-toggle"]');
  await page.waitForSelector('[data-testid="replay-clock"]');
  await page.waitForFunction(() => /· [1-9]/.test(document.querySelector('[data-testid="replay-clock"]')?.textContent ?? ""));
  check(true, "replay delivers detections as the clock advances");
  await shot("19-map-replay");
  await page.click('[data-testid="replay-toggle"]');
  check((await page.locator('[data-testid="replay-clock"]').count()) === 0, "stopping the replay clears the clock");
  await page.click('[data-testid="map-record-link"]');
  await page.waitForSelector('[data-testid="record-detail"]');
  check(true, "map detail links to the record page");
  await logout();

  // t.adeyemi: same questions -> fewer results
  await login("t.adeyemi");
  await page.waitForURL("**/dashboard");
  await page.waitForSelector('[data-testid="tile-recent_findings"]');
  check((await page.locator('[data-testid="finding-link"]').count()) === 0, "t.adeyemi does not see the Secret finding");
  check((await page.locator('[data-testid="run-correlation"]').count()) === 0, "t.adeyemi has no run-correlation button");
  const adeyemiItems = await page.locator('[data-testid^="item-"]').count();
  check(adeyemiItems < belloItems, `t.adeyemi dashboard is smaller (${adeyemiItems} < ${belloItems} items)`);
  await shot("14-dashboard-adeyemi");
  await page.click('a[href="/chat"]');
  await page.waitForURL("**/chat");
  await page.waitForSelector('[data-testid="user-name"]');
  await ask(POLICY);
  const adeyemiCites = await page.locator('[data-testid="citation-badge"]').count();
  await ask(EQUIPMENT);
  await page.waitForSelector('[data-testid="result-table"]');
  const adeyemiRows = await page.locator('[data-testid="result-table"] tbody tr').count();
  check(adeyemiRows < belloRows, `t.adeyemi sees fewer equipment rows (${adeyemiRows} < ${belloRows})`);
  check(adeyemiCites <= belloCites, `t.adeyemi citations ${adeyemiCites} <= a.bello ${belloCites}`);
  await shot("07-adeyemi-fewer-results");
  await page.goto(BASE + "/findings/FND-RISING-FAULTS-BN-4");
  await page.waitForSelector('[data-testid="finding-error"]');
  check(true, "t.adeyemi gets 'not found' for the Secret finding page");
  await page.goto(BASE + "/records/REC-023");
  await page.waitForSelector('[data-testid="record-error"]');
  check(true, "t.adeyemi gets 'not found' for a Secret UAS record, same as a missing one");
  await shot("16-record-hidden-adeyemi");
  await page.goto(BASE + "/map");
  await page.waitForSelector('[data-testid="map-canvas"][data-ready="true"]');
  check((await page.textContent('[data-testid="count-mission"]')) === "0", "t.adeyemi map shows no missions");
  check((await page.locator('[data-testid="map-item-REC-060"]').count()) === 0, "t.adeyemi map never lists the Secret mission");
  await shot("18-map-adeyemi");
  await logout();

  // f.danjuma: audit -> verify chain
  await login("f.danjuma");
  await page.waitForURL("**/audit");
  check((await page.locator('a[href="/dashboard"]').count()) === 0, "auditor has no dashboard nav");
  await page.waitForSelector('[data-testid="audit-row"]');
  check((await page.locator('[data-testid="audit-row"]').count()) > 0, "audit table lists events");
  await shot("08-audit-table");
  await page.getByRole("button", { name: "Verify chain", exact: true }).click();
  await page.waitForSelector('[data-testid="verify-modal"]');
  check((await page.textContent('[data-testid="verify-valid"]')) === "true", "Verify chain reports valid");
  await shot("09-audit-verify-modal");
} catch (err) {
  await shot("zz-failure").catch(() => {});
  console.error(String(err));
  console.log("\nScreenshots:\n" + saved.join("\n"));
  await browser.close();
  process.exit(1);
}
console.log("\nScreenshots:\n" + saved.join("\n"));
await browser.close();
