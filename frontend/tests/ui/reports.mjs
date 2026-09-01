// Browser test for the reports screen, the alerts and the exports
// (SRS section 9, 11.1). Same staging setup as new-lay.mjs — see its header.
// Needs `qa_sup` and `qa_admin` on the dev database and some closed lays.
// Never touches production.

import { chromium, devices } from "playwright";
import path from "node:path";

const BASE = "http://127.0.0.1:3010";
const SHOTS = process.env.SHOTS;
let pass = 0, fail = 0; const failures = [];
const check = (n, ok, d = "") => {
  if (ok) { pass++; console.log(`  ✓ ${n}`); }
  else { fail++; failures.push(`${n} ${d}`); console.log(`  ✗ ${n} ${d}`); }
};

const tok = await (await fetch(`${BASE}/api/auth/login/`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "qa_sup", password: "qa-staging-pw" }),
})).json();
const auth = { Authorization: `Bearer ${tok.access}` };

const browser = await chromium.launch({ acceptDownloads: true });
const ctx = await browser.newContext({
  ...devices["Desktop Chrome"], locale: "ar-EG", acceptDownloads: true,
});
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
page.on("console", (m) => {
  if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text());
});
const t = (id) => page.getByTestId(id);
const shot = (n) => SHOTS ? page.screenshot({ path: path.join(SHOTS, `${n}.png`), fullPage: true }) : null;

// ---------------------------------------------------------------- 1
console.log("\n1. every report renders");
await page.goto(`${BASE}/cutting/reports`, { waitUntil: "networkidle" });
await page.waitForTimeout(900);
for (const key of ["metrage", "shortage", "productivity", "remnants", "banks", "quality"]) {
  await t(`report-${key}`).click();
  await page.waitForTimeout(900);
  const hasTable = await t("report-table").isVisible().catch(() => false);
  const empty = await page.getByText("مفيش بيانات في الفترة دي").isVisible().catch(() => false);
  check(`${key} renders`, hasTable || empty, hasTable ? "table" : "empty");
}
await t("report-shortage").click();
await page.waitForTimeout(900);
await shot("g1-reports");

// ---------------------------------------------------------------- 2
console.log("\n2. the report choice and dates live in the URL");
check("report in the URL", page.url().includes("r=shortage"), page.url());
await t("date-from").fill("2026-08-01");
await page.waitForTimeout(900);
check("date in the URL", page.url().includes("date_from=2026-08-01"), page.url());

// ---------------------------------------------------------------- 3
console.log("\n3. backfilled lays are out unless asked for");
const plain = await (await fetch(`${BASE}/api/cutting/reports/metrage/`, { headers: auth })).json();
const withOld = await (await fetch(
  `${BASE}/api/cutting/reports/metrage/?include_backfill=true`, { headers: auth })).json();
const sum = (r) => r.rows.reduce((s, x) => s + x.lays, 0);
check("including them can only add lays", sum(withOld) >= sum(plain),
      `${sum(plain)} -> ${sum(withOld)}`);

// ---------------------------------------------------------------- 4
console.log("\n4. Excel and PDF download");
for (const [testid, ext] of [["export-xlsx", "xlsx"], ["export-pdf", "pdf"]]) {
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 25000 }),
    t(testid).click(),
  ]);
  const name = download.suggestedFilename();
  check(`${ext} downloads`, name.endsWith(`.${ext}`), name);
}

// ---------------------------------------------------------------- 5
console.log("\n5. the lay list exports under its filters");
await page.goto(`${BASE}/cutting?has_shortage=true`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
const [dl] = await Promise.all([
  page.waitForEvent("download", { timeout: 25000 }),
  t("export-xlsx").click(),
]);
check("list exports to Excel", dl.suggestedFilename().endsWith(".xlsx"),
      dl.suggestedFilename());

// ---------------------------------------------------------------- 6
console.log("\n6. the bell shows unread alerts and the page clears them");
const unreadBefore = (await (await fetch(
  `${BASE}/api/cutting/notifications/unread_count/`, { headers: auth })).json()).unread;
check("there are alerts to see", unreadBefore > 0, String(unreadBefore));

await page.goto(`${BASE}/cutting`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
check("badge visible", await t("unread-badge").first().isVisible());
await shot("g6-bell");

await t("notification-bell").first().click();
await page.waitForURL(/notifications/, { timeout: 15000 });
await page.waitForTimeout(1000);
const cards = await t("notification").count();
check("alerts listed", cards > 0, String(cards));
await shot("g6-notifications");

await t("mark-all-read").click();
await page.waitForTimeout(1500);
const after = (await (await fetch(
  `${BASE}/api/cutting/notifications/unread_count/`, { headers: auth })).json()).unread;
check("marking read clears the count", after === 0, String(after));

// ---------------------------------------------------------------- 7
console.log("\n7. each person only sees their own alerts");
const other = await (await fetch(`${BASE}/api/auth/login/`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "qa_admin", password: "qa-staging-pw" }),
})).json();
const theirs = await (await fetch(`${BASE}/api/cutting/notifications/unread_count/`,
  { headers: { Authorization: `Bearer ${other.access}` } })).json();
check("the other user still has theirs unread", theirs.unread > 0, String(theirs.unread));

// ---------------------------------------------------------------- 8
console.log("\n8. mobile");
const phone = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await phone.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
const mob = await phone.newPage();
await mob.goto(`${BASE}/cutting/reports`, { waitUntil: "networkidle" });
await mob.waitForTimeout(1200);
const wide = await mob.evaluate(
  () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
);
check("reports fit the phone", !wide);
if (SHOTS) await mob.screenshot({ path: path.join(SHOTS, "g8-mobile.png"), fullPage: true });
await phone.close();

console.log(`\nJS errors: ${errs.length}`);
errs.slice(0, 4).forEach((e) => console.log("   " + e.slice(0, 140)));
check("no JS errors", errs.length === 0, errs[0] ?? "");

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
