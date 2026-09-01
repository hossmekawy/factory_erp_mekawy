// Saved size runs: the buttons on the new-lay screen and the page that manages
// them. Same staging setup as new-lay.mjs.
import { chromium, devices } from "playwright";

const BASE = "http://127.0.0.1:3010";
let pass = 0, fail = 0; const failures = [];
const check = (n, ok, d = "") => {
  if (ok) { pass++; console.log(`  ✓ ${n}`); }
  else { fail++; failures.push(`${n} ${d}`); console.log(`  ✗ ${n} ${d}`); }
};

const tok = await (await fetch(`${BASE}/api/auth/login/`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "qa_sup", password: "qa-staging-pw" }),
})).json();
const admin = await (await fetch(`${BASE}/api/auth/login/`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "qa_admin", password: "qa-staging-pw" }),
})).json();

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [admin.access, admin.refresh]);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
const t = (id) => page.getByTestId(id);
const tap = async (id, i = 0) => {
  const el = t(id).nth(i);
  await el.scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -140);
  await el.click({ timeout: 20000 });
};

// ---------------------------------------------------------------- 1
console.log("\n1. the presets page lists, adds and edits");
await page.goto(`${BASE}/cutting/size-sets`, { waitUntil: "networkidle" });
await page.waitForTimeout(900);
const before = await page.locator("tbody tr").count();
check("presets load", before > 0, String(before));

const newName = "طقم اختبار " + String(Date.now()).slice(-5);
await page.getByRole("button", { name: "إضافة" }).click();
await t("field-name").fill(newName);
await t("field-sizes_raw").fill("40 42 44");
await t("save-row").click();
await page.waitForTimeout(1400);
check("added", (await page.locator("tbody tr").count()) === before + 1);
check("pieces counted from the sizes",
      (await page.locator("tbody").innerText()).includes("40 42 44"));

// ---------------------------------------------------------------- 2
console.log("\n2. hand-typed lay sizes never show up here");
const all = await (await fetch(`${BASE}/api/cutting/size-sets/?page_size=200`,
  { headers: { Authorization: `Bearer ${admin.access}` } })).json();
const presets = await (await fetch(
  `${BASE}/api/cutting/size-sets/?is_preset=true&page_size=200`,
  { headers: { Authorization: `Bearer ${admin.access}` } })).json();
check("there are more size sets than presets", all.count > presets.count,
      `${presets.count} presets of ${all.count} sets`);

// ---------------------------------------------------------------- 3
console.log("\n3. the buttons appear on the new-lay screen");
await page.goto(`${BASE}/cutting/new`, { waitUntil: "networkidle" });
await t("sizes-input").waitFor({ timeout: 20000 });
await page.waitForTimeout(1500);
const shown = await t("size-preset").count();
check("preset buttons rendered", shown > 0, String(shown));

// ---------------------------------------------------------------- 4
console.log("\n4. tapping one fills the sizes, and it stays editable");
const target = t("size-preset").filter({ hasText: "رجالي عادي" }).first();
await target.scrollIntoViewIfNeeded();
await page.mouse.wheel(0, -140);
await target.click();
await page.waitForTimeout(1200);
const chips = async () =>
  Promise.all((await t("size-chip").all()).map((c) => c.getAttribute("data-size")));
check("five sizes filled", (await chips()).join(",") === "30,32,34,36,38",
      JSON.stringify(await chips()));
check("pieces per ply is 5", (await t("pieces-per-ply").innerText()).includes("5"));
check("focus went back to the box",
      (await page.evaluate(() => document.activeElement?.getAttribute("data-testid")))
        === "sizes-input");

// still editable afterwards
await t("sizes-input").fill("40");
await tap("add-size");
await page.waitForTimeout(900);
check("still editable after applying", (await chips()).includes("40"),
      JSON.stringify(await chips()));
await t("size-chip").filter({ hasText: "30" }).first().click();
await page.waitForTimeout(900);
check("and a chip can still be removed", !(await chips()).includes("30"),
      JSON.stringify(await chips()));

// ---------------------------------------------------------------- 5
console.log("\n5. tapping another replaces rather than appends");
const other = t("size-preset").filter({ hasText: "حريمي" }).first();
await other.scrollIntoViewIfNeeded();
await page.mouse.wheel(0, -140);
await other.click();
await page.waitForTimeout(1200);
check("replaced, not appended", (await chips()).join(",") === "36,38,40,42",
      JSON.stringify(await chips()));

// ---------------------------------------------------------------- 6
console.log("\n6. the model's own section sorts first");
await page.goto(`${BASE}/cutting/new`, { waitUntil: "networkidle" });
await t("model-search").waitFor({ timeout: 20000 });
await t("model-search").fill("كارل رجالي");
const option = page.locator('button:has-text("كارل رجالي")').first();
await option.waitFor({ timeout: 15000 });
await option.click();
await page.waitForTimeout(1200);
const order = await Promise.all(
  (await t("size-preset").all()).map((b) => b.getAttribute("data-preset"))
);
console.log("   " + order.join(" · "));
const firstIsMens = order[0]?.includes("رجالي");
check("a رجالي preset comes first for a رجالي model", Boolean(firstIsMens),
      JSON.stringify(order));

check("no JS errors", errs.length === 0, errs[0] ?? "");
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
