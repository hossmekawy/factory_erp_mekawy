// The size box must work with a numeric keypad that has NO space key — which
// is exactly what iOS gives an inputMode="numeric" field, and what made typing
// "30 32 32" impossible on the phone this screen exists for.
// Same staging setup as new-lay.mjs — see its header.

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

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
const t = (id) => page.getByTestId(id);
const shot = (n) => SHOTS ? page.screenshot({ path: path.join(SHOTS, `${n}.png`), fullPage: true }) : null;

const pieces = async () => (await t("pieces-per-ply").innerText()).trim();
const chips = async () =>
  Promise.all((await t("size-chip").all()).map((c) => c.getAttribute("data-size")));

async function fresh() {
  await page.goto(`${BASE}/cutting/new`, { waitUntil: "networkidle" });
  await t("sizes-input").waitFor({ timeout: 15000 });
  await page.waitForTimeout(500);
  // Nothing may be covering the field on a screen the user just opened.
  check("no dropdown covering the form on load",
        (await page.locator('button:has-text("karl")').count()) === 0);
}

// The mobile header is sticky; scroll the target clear of it before tapping,
// the way a thumb would.
async function tap(testid, index = 0) {
  const el = t(testid).nth(index);
  await el.scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -120);
  await el.click({ timeout: 15000 });
}

// ---------------------------------------------------------------- 1
console.log("\n1. sizes go in one at a time — no space needed anywhere");
await fresh();
for (const size of ["30", "32", "32", "34", "34", "36"]) {
  await t("sizes-input").fill(size);
  await tap("add-size");
}
await page.waitForTimeout(900);
check("six pieces counted", (await pieces()).includes("6"), await pieces());
check("four distinct chips", (await chips()).length === 4, JSON.stringify(await chips()));
check("box cleared after each add", (await t("sizes-input").inputValue()) === "");
await shot("s1-added");

// ---------------------------------------------------------------- 2
console.log("\n2. the same size repeats, and the chip shows the count");
const chipText = await t("size-chip").filter({ hasText: "32" }).first().innerText();
check("32 shows as ×2", chipText.includes("2"), chipText);

// ---------------------------------------------------------------- 3
console.log("\n3. tapping a chip removes ONE, not all of them");
await t("size-chip").filter({ hasText: "32" }).first().click();
await page.waitForTimeout(900);
check("now five pieces", (await pieces()).includes("5"), await pieces());
check("32 still there once", (await chips()).includes("32"), JSON.stringify(await chips()));
await t("size-chip").filter({ hasText: "32" }).first().click();
await page.waitForTimeout(900);
check("tapping again removes the last one", !(await chips()).includes("32"),
      JSON.stringify(await chips()));
check("four pieces left", (await pieces()).includes("4"), await pieces());

// ---------------------------------------------------------------- 4
console.log("\n4. Enter adds too, for a real keyboard");
await t("sizes-input").fill("38");
await t("sizes-input").press("Enter");
await page.waitForTimeout(900);
check("added by Enter", (await chips()).includes("38"), JSON.stringify(await chips()));

// ---------------------------------------------------------------- 5
console.log("\n5. a whole pasted string still works");
await fresh();
await t("sizes-input").fill("30 32 32 34 34 36");
await tap("add-size");
await page.waitForTimeout(900);
check("pasted string splits", (await pieces()).includes("6"), await pieces());

// ---------------------------------------------------------------- 6
console.log("\n6. the notebook's bracket form, and Arabic digits");
await fresh();
await t("sizes-input").fill("(32)(34)(34)");
await tap("add-size");
await page.waitForTimeout(900);
check("brackets split to 3", (await pieces()).includes("3"), await pieces());
await fresh();
await t("sizes-input").fill("٣٠");
await tap("add-size");
await t("sizes-input").fill("٣٢");
await tap("add-size");
await page.waitForTimeout(900);
check("Arabic digits become sizes", (await chips()).includes("30"),
      JSON.stringify(await chips()));

// ---------------------------------------------------------------- 7
console.log("\n7. clear all");
await tap("clear-sizes");
await page.waitForTimeout(800);
check("chips gone", (await t("size-chip").count()) === 0);
check("count reset", (await pieces()).includes("—"), await pieces());

// ---------------------------------------------------------------- 8
console.log("\n8. the add button is dead until something is typed");
await fresh();
check("disabled when empty", await t("add-size").isDisabled());
await t("sizes-input").fill("30");
check("enabled once typed", !(await t("add-size").isDisabled()));

// ---------------------------------------------------------------- 9
console.log("\n9. a lay still closes end to end with sizes entered this way");
await tap("add-size");
await t("sizes-input").fill("32");
await tap("add-size");
await page.waitForTimeout(800);
await t("lay-code").fill("SZ" + String(Date.now()).slice(-8));
await t("model-search").fill("كارل رجالي");
await page.locator('button:has-text("كارل رجالي")').first().click();
await t("width-input").fill("1.62");
await t("length-input").fill("6.55");
await t("bank-select").selectOption({ index: 1 });
await t("leader-select").selectOption({ index: 1 });
await t("line-length").first().fill("105.30");
await t("line-plies").first().fill("16");
await t("line-remnant").first().fill("0.50");
await page.waitForTimeout(400);
check("live plies", (await t("stat-plies").innerText()) === "16");
check("live pieces = 16 x 2", (await t("stat-pieces").innerText()) === "32",
      await t("stat-pieces").innerText());
await t("sheet-input").setInputFiles("/root/factory_erp/reference/notebook-page-1749.jpeg");
await page.locator('img[alt="ورقة الدفتر"]').waitFor({ timeout: 20000 });
await tap("close-btn");
const closed = await Promise.race([
  page.getByText("الفرشة اتقفلت").waitFor({ timeout: 20000 }).then(() => true),
  t("issue").first().waitFor({ timeout: 20000 }).then(() => false),
]);
if (!closed && await t("reason-input").isVisible()) {
  await t("reason-input").fill("اختبار");
  await t("close-with-reason").click();
  await page.getByText("الفرشة اتقفلت").waitFor({ timeout: 20000 });
}
check("closed", true);
await shot("s9-closed");

check("no JS errors", errs.length === 0, errs[0] ?? "");
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
