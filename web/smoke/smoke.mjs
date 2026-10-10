// UI smoke test. Needs the web dev server on :3000 and the stub API on :8001.
// It also logs in as the archived restricted accounts (coo, group.audit), so seed the dev DB with
// `python -m app.seed --include-archived` first (see README).
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
const REPORT = "Prepare a summary of training activity for this command over the last quarter.";
const EQUIPMENT = "Show me the equipment currently awaiting maintenance.";
const shots = path.resolve("smoke/screenshots");
mkdirSync(shots, { recursive: true });
const saved = [];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const page = await (await browser.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
page.setDefaultTimeout(60000);
// Air-gap: record every request that leaves this machine (the basemap included).
const external = [];
const local = new Set(["localhost", "127.0.0.1"]);
page.on("request", (r) => {
  const u = new URL(r.url());
  if (/^https?:$/.test(u.protocol) && !local.has(u.hostname)) external.push(r.url());
});
const basemapLoaded = page.waitForResponse((r) => r.url().endsWith("/basemap/demo-area.pmtiles") && r.ok());

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
  await login("owner", "wrong-password");
  await page.waitForSelector("text=Invalid credentials");
  check(true, "bad password shows inline 'Invalid credentials'");
  await shot("02-login-invalid");

  // owner: policy question -> cited answer -> open citation
  await login("owner");
  await page.waitForURL("**/home");
  await page.waitForSelector('[data-testid="user-name"]');
  check((await page.textContent('[data-testid="clearance-badge"]')).includes("GOVERNMENT-SENSITIVE"), "owner clearance badge is GOVERNMENT-SENSITIVE");
  check((await page.locator("text=UAS-OPS").count()) > 0, "compartment tags shown");
  check((await page.locator('a[href="/audit"]').count()) === 0, "audit nav hidden without read_audit");

  // group home: login lands here; five cards, alerts only where something needs attention
  await page.waitForSelector('[data-testid="division-briech"]');
  for (const key of ["briech", "stratoc", "giga", "poctova", "field-ops"]) {
    check((await page.locator(`[data-testid="division-${key}"]`).count()) === 1, `owner home has the ${key} card`);
  }
  check(Number(await page.getAttribute('[data-testid="division-poctova"]', "data-alert")) > 0, "poctova card carries an alert count");
  await shot("12-home-owner");
  await page.click('[data-testid="division-poctova"]');
  await page.waitForSelector('[data-testid="division-title"]');
  check((await page.textContent('[data-testid="division-title"]')) === "Poctova", "a card opens that business");
  await page.waitForSelector('[data-testid="section-qc-holds"]');
  check((await page.locator('[data-testid="section-runs"] [data-testid="row-link"]').count()) === 2, "poctova lists its two production runs");
  await page.fill('[aria-label="Serial number"]', "PCT-ARM-0007");
  await page.click('[data-testid="serial-lookup"] button[type="submit"]');
  await page.waitForSelector('[data-testid="trace-row"]');
  check(true, "a serial number traces to its run and delivery");
  await shot("12b-division-poctova");
  await page.click('[data-testid="section-qc-holds"] [data-testid="row-link"]');
  await page.waitForURL("**/records/REC-086");
  check(true, "a section row opens its record");
  await page.goBack();
  await page.waitForSelector('[data-testid="division-title"]');
  await page.goto(BASE + "/d/briech");
  await page.waitForSelector('[data-testid="section-fleet"]');
  check((await page.locator('[data-testid="service-gauge"]').count()) >= 1, "briech fleet shows a service gauge");
  check((await page.locator('[data-testid="open-map"]').count()) === 1, "briech links to the map");
  await shot("12d-division-briech");
  await page.goto(BASE + "/d/field-ops");
  await page.waitForSelector('[data-testid="section-personnel"]');
  check((await page.textContent('[data-testid="division-facts"]')).includes("Stratoc Site Team 4"), "field operations names its site and who it supports");
  check((await page.locator('[data-testid="section-personnel"] [data-testid="row-link"]').count()) === 5, "field operations lists its five people");
  await shot("12f-division-field-ops");
  await page.goto(BASE + "/d/stratoc");
  await page.waitForSelector('[data-testid="section-findings"]');
  await page.click('[data-testid="run-correlation"]');
  await page.waitForSelector('[data-testid="section-findings"] [data-testid="row-link"]');
  check((await page.locator('[data-testid="section-detections"] [data-testid="row-link"]').count()) >= 1, "stratoc lists detections");
  check((await page.locator('[data-testid="open-field-ops"]').count()) === 1, "stratoc links to field operations");
  await shot("12e-division-stratoc");
  await page.click('[data-testid="section-findings"] [data-testid="row-link"]');
  await page.waitForURL("**/findings/**");
  check(true, "a finding row opens the finding and its evidence");
  await page.goto(BASE + "/home");
  await page.waitForSelector('[data-testid="division-briech"]');
  await page.click('[data-testid="division-poctova"]');
  await page.waitForSelector('[data-testid="division-title"]');
  await page.click('[data-testid="back-to-group"]');
  await page.waitForSelector('[data-testid="division-briech"]');
  check(true, "back to the group home works");

  // group compliance and the forensic case workspace
  await page.goto(BASE + "/compliance");
  await page.waitForSelector('[data-testid="compliance-tally"]');
  check((await page.locator('[data-testid="section-maintenance"] [data-testid="row-link"]').count()) > 0, "compliance lists maintenance rows");
  await page.goto(BASE + "/d/giga");
  await page.waitForSelector('[data-testid="section-custody-breaks"]');
  await page.click('[data-testid="section-custody-breaks"] [data-testid="row-link"]');
  await page.waitForSelector('[data-testid="case-title"]');
  check((await page.locator('[data-testid="custody-break"]').count()) === 1, "the case page marks the one custody break");
  await shot("12g-case-workspace");

  // phone width: the shell collapses (menu + bottom tabs) and nothing scrolls sideways
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of ["/home", "/d/poctova", "/compliance", "/cases/FR-2026-017", "/dashboard", "/chat", "/map"]) {
    await page.goto(BASE + route);
    await page.waitForSelector('nav[aria-label="Main"]');
    const [scrollW, innerW] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    check(scrollW <= innerW, `${route} does not scroll sideways on a phone (${scrollW} <= ${innerW})`);
  }
  await page.goto(BASE + "/home");
  await page.waitForSelector('[data-testid="division-briech"]');
  check(await page.locator("text=Menu").isVisible(), "phone shows a Menu button for the identity strip");
  await shot("12c-home-phone");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(BASE + "/home");
  await page.waitForSelector('[data-testid="division-briech"]');

  // overview: every stub tile is tagged; the Secret finding is shown
  await page.click('a[href="/dashboard"]');
  await page.waitForSelector('[data-testid="tile-recent_findings"]');
  check((await page.locator('[data-testid="placeholder-tag"]').count()) === 0, "no tile is tagged placeholder: every tile is counted from typed tools");
  // the finding exists once a commander runs the correlation job
  await page.click('[data-testid="run-correlation"]');
  await page.waitForSelector('[data-testid="finding-link"]');
  check((await page.locator('[data-testid="item-FND-RISING-FAULTS-SITE-4"]').count()) === 1, "owner sees the Secret finding after running correlation");
  const ownerItems = await page.locator('[data-testid^="item-"]').count();
  await shot("13-dashboard-owner");
  await page.click('[data-testid="finding-link"]');
  await page.waitForSelector('[data-testid="finding-detail"]');
  const evidence = await page.locator('[data-testid="evidence-link"]').count();
  check(evidence === 10, `finding detail lists its evidence (${evidence} records)`);
  check((await page.textContent('[data-testid="finding-detail"]')).includes("GOVERNMENT-SENSITIVE"), "finding detail shows the derived GOVERNMENT-SENSITIVE label");
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
  const ownerCites = await page.locator('[data-testid="citation-badge"]').count();
  check(ownerCites > 0, `policy answer carries citations (${ownerCites})`);
  await shot("04-owner-policy-answer");
  await page.locator('[data-testid="citation-badge"]').first().click();
  await page.waitForSelector('[data-testid="passage-panel"] blockquote');
  check(true, "citation opens the passage in the side panel");
  await shot("05-owner-citation-panel");

  // reporting: a draft over records and documents, marked and labelled
  await ask(REPORT);
  await page.waitForSelector('[data-testid="draft-banner"]');
  check((await page.textContent('[data-testid="draft-banner"]')).includes("UAS-OPS"), "owner draft carries the derived UAS-OPS label");
  check((await page.locator('[data-testid="msg-assistant"]').last().textContent()).includes("REC-044"), "owner draft covers the UAS training event");
  await shot("20-report-owner");
  // owner: equipment question -> table
  await ask(EQUIPMENT);
  await page.waitForSelector('[data-testid="result-table"]');
  const ownerRows = await page.locator('[data-testid="result-table"] tbody tr').count();
  check(ownerRows > 0, `equipment answer renders a result table (${ownerRows} rows)`);
  await shot("06-owner-equipment-table");
  await page.locator('[data-testid="record-link"]').first().click();
  await page.waitForSelector('[data-testid="record-detail"]');
  check(true, "a result-table row link opens the record detail");
  await shot("15-record-detail");

  // map: sensors, detections and missions from the connected-data endpoint
  await page.click('a[href="/map"]');
  await page.waitForSelector('[data-testid="map-canvas"][data-ready="true"]');
  check((await page.textContent('[data-testid="count-sensor"]')) === "2", "owner map shows 2 sensors");
  check((await page.textContent('[data-testid="count-detection"]')) === "6", "owner map shows 6 detections");
  check((await page.textContent('[data-testid="count-mission"]')) === "5", "owner map shows 5 missions");
  await basemapLoaded;
  check(true, "offline basemap archive is served by this app");
  await page.click('[data-testid="map-item-REC-060"]');
  await page.waitForSelector('[data-testid="map-detail"]');
  check((await page.textContent('[data-testid="map-detail"]')).includes("GOVERNMENT-SENSITIVE"), "Secret mission detail carries its classification badge");
  await shot("17-map-owner");
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

  // coo: same questions -> fewer results
  await login("coo");
  await page.waitForURL("**/d/field-ops");
  await page.waitForSelector('[data-testid="division-title"]');
  check((await page.locator('[data-testid="division-title"]').count()) === 1, "coo sees one business, so lands in it directly");
  await shot("14a-division-coo");
  await page.goto(BASE + "/d/briech");
  await page.waitForSelector('[data-testid="division-not-found"]');
  check(true, "coo gets 'not found' for a business outside their unit");
  await page.click('a[href="/dashboard"]');
  await page.waitForSelector('[data-testid="tile-recent_findings"]');
  check((await page.locator('[data-testid="finding-link"]').count()) === 0, "coo does not see the Secret finding");
  check((await page.locator('[data-testid="run-correlation"]').count()) === 0, "coo has no run-correlation button");
  const cooItems = await page.locator('[data-testid^="item-"]').count();
  check(cooItems < ownerItems, `coo dashboard is smaller (${cooItems} < ${ownerItems} items)`);
  await shot("14-dashboard-coo");
  await page.click('a[href="/chat"]');
  await page.waitForURL("**/chat");
  await page.waitForSelector('[data-testid="user-name"]');
  await ask(POLICY);
  const cooCites = await page.locator('[data-testid="citation-badge"]').count();
  await ask(REPORT);
  await page.waitForSelector('[data-testid="draft-banner"]');
  const draftText = await page.locator('[data-testid="msg-assistant"]').last().textContent();
  check(!draftText.includes("REC-044") && !draftText.includes("UAS-OPS"), "coo draft has no UAS record and no UAS-OPS label");
  await shot("21-report-coo");
  await ask(EQUIPMENT);
  await page.waitForSelector('[data-testid="result-table"]');
  const cooRows = await page.locator('[data-testid="result-table"] tbody tr').count();
  check(cooRows < ownerRows, `coo sees fewer equipment rows (${cooRows} < ${ownerRows})`);
  check(cooCites <= ownerCites, `coo citations ${cooCites} <= owner ${ownerCites}`);
  await shot("07-coo-fewer-results");
  await page.goto(BASE + "/findings/FND-RISING-FAULTS-SITE-4");
  await page.waitForSelector('[data-testid="finding-error"]');
  check(true, "coo gets 'not found' for the Secret finding page");
  await page.goto(BASE + "/records/REC-023");
  await page.waitForSelector('[data-testid="record-error"]');
  check(true, "coo gets 'not found' for a Secret UAS record, same as a missing one");
  await shot("16-record-hidden-coo");
  await page.goto(BASE + "/map");
  await page.waitForSelector('[data-testid="map-canvas"][data-ready="true"]');
  check((await page.textContent('[data-testid="count-mission"]')) === "0", "coo map shows no missions");
  check((await page.locator('[data-testid="map-item-REC-060"]').count()) === 0, "coo map never lists the Secret mission");
  await shot("18-map-coo");
  await logout();

  // group.audit: audit -> verify chain
  await login("group.audit");
  await page.waitForURL("**/audit");
  check((await page.locator('a[href="/dashboard"]').count()) === 0, "auditor has no dashboard nav");
  await page.waitForSelector('[data-testid="audit-row"]');
  check((await page.locator('[data-testid="audit-row"]').count()) > 0, "audit table lists events");
  await shot("08-audit-table");
  await page.getByRole("button", { name: "Verify chain", exact: true }).click();
  await page.waitForSelector('[data-testid="verify-modal"]');
  check((await page.textContent('[data-testid="verify-valid"]')) === "true", "Verify chain reports valid");
  await shot("09-audit-verify-modal");
  check(external.length === 0, `no request left the machine${external.length ? ": " + external.join(" ") : ""}`);
} catch (err) {
  await shot("zz-failure").catch(() => {});
  console.error(String(err));
  console.log("\nScreenshots:\n" + saved.join("\n"));
  await browser.close();
  process.exit(1);
}
console.log("\nScreenshots:\n" + saved.join("\n"));
await browser.close();
