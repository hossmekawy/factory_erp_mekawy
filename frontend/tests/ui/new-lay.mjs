// Browser test for the new-lay screen (SRS 7.2).
// Playwright is NOT a dependency of this project; the browsers were already on
// the VPS. To run it, start the staging stack against the DEV database:
//
//   cd backend && DB_NAME=factory_erp_dev ALLOWED_HOSTS=127.0.0.1,localhost \
//     DEBUG=True venv/bin/python manage.py runserver 127.0.0.1:8011
//   cd frontend && BACKEND_URL=http://127.0.0.1:8011 npx next dev -p 3010 \
//     --hostname 127.0.0.1
//   node tests/ui/new-lay.mjs          # SHOTS=/some/dir for screenshots
//
// Needs a `qa_sup` user in the cutting_supervisor group on the dev database,
// at least one bank, and the model 1749. It never touches production.

import { chromium, devices } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = "http://localhost:3010";
const SHOTS = process.env.SHOTS;
const SHEET = "/root/factory_erp/reference/notebook-page-1749.jpeg";

let pass = 0, fail = 0;
const failures = [];
function check(name, ok, detail = "") {
  if (ok) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; failures.push(`${name} ${detail}`); console.log(`  ✗ ${name} ${detail}`); }
}

const token = await (await fetch(`${BASE}/api/auth/login/`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "qa_sup", password: "qa-staging-pw" }),
})).json();

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [token.access, token.refresh]);

const page = await ctx.newPage();
// A rejected close is a 400 by design, so record what actually failed rather
// than counting console noise. Anything that is not a deliberate validation
// rejection on /close/ is a real bug.
const consoleErrors = [];
const badResponses = [];
page.on("console", (m) => {
  if (m.type() === "error" && !/Failed to load resource/.test(m.text())) {
    consoleErrors.push(m.text());
  }
});
page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));
page.on("response", (r) => {
  if (r.status() >= 400) badResponses.push(`${r.status()} ${new URL(r.url()).pathname}`);
});

const t = (id) => page.getByTestId(id);

async function fresh() {
  await page.goto(`${BASE}/cutting/new`, { waitUntil: "networkidle" });
  await t("sizes-input").waitFor({ timeout: 15000 });
}

async function pickModel(code) {
  await t("model-search").fill(code);
  const option = page.locator(`button:has-text("${code}")`).first();
  await option.waitFor({ timeout: 8000 });
  await option.click();
}

async function setSizes(text) {
  await t("sizes-input").fill(text);
  await page.waitForTimeout(700); // debounce + server parse
}

async function fillHeader({ model = "1749", sizes = "30 32 32 34 34 36",
                            width = "1.62", length = "6.55", end = null }) {
  await pickModel(model);
  await setSizes(sizes);
  await t("width-input").fill(width);
  await t("length-input").fill(length);
  if (end) await page.locator('input[type="date"]').nth(1).fill(end);
  await t("bank-select").selectOption({ index: 1 });
  await t("leader-select").selectOption({ index: 1 });
}

async function fillRows(rows) {
  for (let i = 0; i < rows.length; i++) {
    if (i > 0) await t("add-line").click();
    const r = rows[i];
    await t("line-length").nth(i).fill(String(r.len));
    await t("line-plies").nth(i).fill(String(r.plies));
    await t("line-remnant").nth(i).fill(String(r.rem ?? "0"));
    if (r.shade) await t("line-shade").nth(i).fill(r.shade);
    if (r.action) await t(`roll-end-${r.action}`).nth(i).click();
  }
  await page.waitForTimeout(200);
}

async function attachSheet() {
  await t("sheet-input").setInputFiles(SHEET);
  await page.locator('img[alt="ورقة الدفتر"]').waitFor({ timeout: 20000 });
}

// Close, supplying a reason if the backend asks for one. Whether it asks
// depends on the data — V7 warns when the team leader has no punch inside the
// lay's dates, and the attendance history only runs so far — so a test that
// assumes a clean close breaks every time the calendar moves past it.
async function closeLay(reason = "اختبار") {
  await t("close-btn").click();
  const closed = await Promise.race([
    page.getByText("الفرشة اتقفلت").waitFor({ timeout: 20000 }).then(() => true),
    t("issue").first().waitFor({ timeout: 20000 }).then(() => false),
  ]);
  if (closed) return { closed: true, viaReason: false };
  if (await t("reason-input").isVisible()) {
    await t("reason-input").fill(reason);
    await t("close-with-reason").click();
    await page.getByText("الفرشة اتقفلت").waitFor({ timeout: 20000 });
    return { closed: true, viaReason: true };
  }
  return { closed: false, viaReason: false };
}

const issues = async () =>
  Promise.all((await t("issue").all()).map(async (e) => ({
    code: await e.getAttribute("data-code"),
    level: await e.getAttribute("data-level"),
  })));

const shot = (n) => SHOTS ? page.screenshot({ path: path.join(SHOTS, `${n}.png`), fullPage: true }) : null;

// ---------------------------------------------------------------- 1
console.log("\n1. simple lay, three rows, closes clean");
await fresh();
await fillHeader({});
await fillRows([
  { len: "105.30", plies: 16, rem: "0.50", shade: "كحلي" },
  { len: "105.30", plies: 16, rem: "0.50", shade: "كحلي" },
  { len: "98.75",  plies: 15, rem: "0.50", shade: "كحلي" },
]);
check("pieces per ply parsed as 6", (await t("pieces-per-ply").innerText()).includes("6"));
check("live plies = 47", (await t("stat-plies").innerText()) === "47");
check("live pieces = 282", (await t("stat-pieces").innerText()) === "282");
await shot("01-filled");
await attachSheet();
check("closed", (await closeLay()).closed);
await shot("01-closed");

// ---------------------------------------------------------------- 2
console.log("\n2. bracket sizes and metres width, as the notebook writes them");
await fresh();
await fillHeader({ sizes: "(30)(32)(32)(34)(34)(36)", width: "1.62" });
check("brackets parsed to 6", (await t("pieces-per-ply").innerText()).includes("6"));
check("1.62 reads as 162 cm", (await t("width-hint").innerText()).includes("162"));
await fillRows([{ len: "105.30", plies: 16, rem: "0.50", shade: "أسود" }]);
await attachSheet();
check("closed", (await closeLay()).closed);

// ---------------------------------------------------------------- 3
console.log("\n3. width typed in centimetres instead");
await fresh();
await fillHeader({ width: "162" });
check("162 also reads as 162 cm", (await t("width-hint").innerText()).includes("162"));

// ---------------------------------------------------------------- 4
console.log("\n4. Arabic-Indic digits in the size box");
await fresh();
await pickModel("1749");
await setSizes("٣٠ ٣٢ ٣٢ ٣٤ ٣٤ ٣٦");
check("٣٠ ٣٢ … parsed to 6", (await t("pieces-per-ply").innerText()).includes("6"));

// ---------------------------------------------------------------- 5
console.log("\n5. a splice takes one ply off the total");
await fresh();
await fillHeader({});
await fillRows([
  { len: "50.00", plies: 10, rem: "0", shade: "أسود", action: "splice" },
  { len: "55.30", plies: 10, rem: "0.50", shade: "أسود" },
]);
check("20 plies minus 1 splice = 19", (await t("stat-plies").innerText()) === "19");
check("pieces follow the corrected count", (await t("stat-pieces").innerText()) === "114");
check("splice note shown", await page.getByText("الراق الموصول اتحسب مرة واحدة").isVisible());
await shot("05-splice");

// ---------------------------------------------------------------- 6
console.log("\n6. remnant colour: waste under a metre, usable at or over");
await fresh();
await fillHeader({});
await fillRows([{ len: "105.30", plies: 16, rem: "0.50" }]);
const waste = await t("line-remnant").first().getAttribute("class");
await t("line-remnant").first().fill("1.50");
await page.waitForTimeout(150);
const usable = await t("line-remnant").first().getAttribute("class");
check("under 1 m is red", waste.includes("rose"));
check("over 1 m is green", usable.includes("emerald"));
await shot("06-remnant");

// ---------------------------------------------------------------- 6b
console.log("\n6b. RTL: numbers and Latin codes must not be reordered");
await fresh();
await fillHeader({});
// A negative shortage: the minus belongs on the left, not trailing.
await fillRows([{ len: "50.00", plies: 16, rem: "0.50" }]);
const shortage = (await t("stat-shortage").innerText()).trim();
check("negative shortage reads -x, not x-", shortage.startsWith("-"), `got "${shortage}"`);
const typed = await t("sizes-input").inputValue();
check("size text stays as typed", typed === "30 32 32 34 34 36", `got "${typed}"`);
const chipOrder = await page.locator('[data-testid="sizes-input"] ~ div span').allInnerTexts();
check("chips keep the written order (30 first)", chipOrder[0]?.startsWith("30"),
      JSON.stringify(chipOrder));
await shot("06b-rtl");

// ---------------------------------------------------------------- 7
console.log("\n7. two shades on one lay -> V8, informational only");
await fresh();
await fillHeader({});
await fillRows([
  { len: "105.30", plies: 16, rem: "0.50", shade: "كحلي" },
  { len: "105.30", plies: 16, rem: "0.50", shade: "أسود" },
]);
await attachSheet();
check("V8 did not block the close", (await closeLay()).closed);

// ---------------------------------------------------------------- 8
console.log("\n8. roll length that does not add up -> V4 warning, reason, then close");
await fresh();
await fillHeader({});
await fillRows([{ len: "90.00", plies: 16, rem: "0.50", shade: "أسود" }]);
await attachSheet();
await t("close-btn").click();
await t("issue").first().waitFor({ timeout: 20000 });
const i8 = await issues();
check("V4 raised", i8.some((i) => i.code === "V4"), JSON.stringify(i8));
check("V4 is a warning, not an error", i8.every((i) => i.level !== "error"), JSON.stringify(i8));
check("reason box appeared", await t("reason-input").isVisible());
await shot("08-v4-warning");
await t("reason-input").fill("التوب اتقاس بالتقريب");
await t("close-with-reason").click();
await page.getByText("الفرشة اتقفلت").waitFor({ timeout: 20000 });
check("closes once a reason is given", true);

// ---------------------------------------------------------------- 9
console.log("\n9. no notebook photo -> refused");
await fresh();
await fillHeader({});
await fillRows([{ len: "105.30", plies: 16, rem: "0.50" }]);
await t("close-btn").click();
await page.getByText("صوّر ورقة الدفتر قبل القفل").waitFor({ timeout: 10000 });
check("close refused without the photo", true);
await shot("09-no-photo");

// ---------------------------------------------------------------- 10
console.log("\n10. quick mode");
await fresh();
await fillHeader({});
await t("mode-quick").click();
await t("quick-metres").fill("1250.00");
await t("quick-plies").fill("125");
await page.waitForTimeout(200);
check("quick plies = 125", (await t("stat-plies").innerText()) === "125");
check("quick pieces = 750", (await t("stat-pieces").innerText()) === "750");
await shot("10-quick");
await attachSheet();
check("quick mode closed", (await closeLay("إدخال سريع")).closed);

// ---------------------------------------------------------------- 11
console.log("\n11. multi-day lay");
await fresh();
await fillHeader({ end: "2026-09-02" });
await fillRows([{ len: "105.30", plies: 16, rem: "0.50", shade: "أسود" }]);
await attachSheet();
check("multi-day lay closed", (await closeLay("فرشة يومين")).closed);

// ---------------------------------------------------------------- 12
console.log("\n12. quick-add a model that is not in the catalogue");
await fresh();
// A code that cannot already be in the catalogue, so the run repeats cleanly.
const newCode = "9" + String(Date.now()).slice(-6);
await t("model-search").fill(newCode);
await t("quick-add-model").waitFor({ timeout: 8000 });
await t("quick-add-model").click();
await page.getByText(newCode).first().waitFor({ timeout: 10000 });
check("model added from the screen", true);
await shot("12-quick-add");

console.log("\nfailed responses seen:", badResponses.length ? badResponses.join(", ") : "none");
consoleErrors.slice(0, 5).forEach((e) => console.log("   " + e.slice(0, 130)));
const unexpected = badResponses.filter((r) => !r.endsWith("/close/"));
check("no uncaught JS errors", consoleErrors.length === 0, consoleErrors[0] ?? "");
check("the only 4xx are the deliberate close rejections", unexpected.length === 0,
      unexpected.join(", "));

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
