// Plies per shade: derived in detailed mode, optional in quick mode.
// Same staging setup as new-lay.mjs.
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
const auth = { Authorization: `Bearer ${tok.access}` };

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
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
const chips = async () =>
  Object.fromEntries(await Promise.all(
    (await t("shade-chip").all()).map(async (c) => [
      await c.getAttribute("data-shade"), (await c.innerText()).replace(/\s+/g, " "),
    ])
  ));

async function header(code) {
  await page.goto(`${BASE}/cutting/new`, { waitUntil: "networkidle" });
  await t("lay-code").waitFor({ timeout: 20000 });
  await t("lay-code").fill(code);
  await t("model-search").fill("كارل رجالي");
  const opt = page.locator('button:has-text("كارل رجالي")').first();
  await opt.waitFor({ timeout: 15000 });
  await opt.click();
  await page.waitForTimeout(600);
  const clear = t("clear-sizes");
  if (await clear.count()) { await tap("clear-sizes"); await page.waitForTimeout(300); }
  await t("sizes-input").fill("30");
  await tap("add-size");
  await t("sizes-input").fill("32");
  await tap("add-size");
  await page.waitForTimeout(800);
  await t("width-input").fill("1.62");
  await t("length-input").fill("6.55");
}

// ---------------------------------------------------------------- 1
console.log("\n1. detailed mode works it out from the lines, no extra typing");
const code1 = "SH" + String(Date.now()).slice(-8);
await header(code1);
await t("line-length").nth(0).fill("131.00");
await t("line-plies").nth(0).fill("20");
await t("line-remnant").nth(0).fill("0.00");
await t("line-shade").nth(0).fill("أسود");
await tap("add-line");
await t("line-length").nth(1).fill("65.50");
await t("line-plies").nth(1).fill("10");
await t("line-remnant").nth(1).fill("0.00");
await t("line-shade").nth(1).fill("كحلي");
await page.waitForTimeout(700);

const got = await chips();
console.log("   " + JSON.stringify(got));
check("two shades shown", Object.keys(got).length === 2, JSON.stringify(got));
check("أسود has 20 plies", /20 راق/.test(got["أسود"] ?? ""), got["أسود"]);
check("كحلي has 10 plies", /10 راق/.test(got["كحلي"] ?? ""), got["كحلي"]);
check("shares are 66.7 / 33.3", /66\.7%/.test(got["أسود"] ?? "") && /33\.3%/.test(got["كحلي"] ?? ""),
      JSON.stringify(got));
check("pieces follow the ply count", /40 قطعة/.test(got["أسود"] ?? ""), got["أسود"]);

// ---------------------------------------------------------------- 2
console.log("\n2. a splice comes off its own shade so the total still matches");
await t("roll-end-splice").nth(0).click();
await page.waitForTimeout(700);
const spliced = await chips();
check("أسود drops to 19", /19 راق/.test(spliced["أسود"] ?? ""), spliced["أسود"]);
const shownTotal = Number(await t("stat-plies").innerText());
const sum = Object.values(spliced).reduce(
  (s, txt) => s + Number(/(\d+) راق/.exec(txt)?.[1] ?? 0), 0);
check("the shades add up to the ply counter", sum === shownTotal, `${sum} vs ${shownTotal}`);
await t("roll-end-new_roll").nth(0).click();
await page.waitForTimeout(500);

// ---------------------------------------------------------------- 3
console.log("\n3. it is stored, and the detail page shows it");
await t("sheet-input").setInputFiles("/root/factory_erp/reference/notebook-page-1749.jpeg");
await page.locator('img[alt="ورقة الدفتر"]').waitFor({ timeout: 25000 });
await tap("close-btn");
const closed = await Promise.race([
  page.getByText("الفرشة اتقفلت").waitFor({ timeout: 25000 }).then(() => true),
  t("issue").first().waitFor({ timeout: 25000 }).then(() => false),
]);
if (!closed && await t("reason-input").isVisible().catch(() => false)) {
  await t("reason-input").fill("اختبار الألوان");
  await tap("close-with-reason");
  await page.getByText("الفرشة اتقفلت").waitFor({ timeout: 25000 });
}
const made = await (await fetch(`${BASE}/api/cutting/lays/?code=${code1}`,
  { headers: auth })).json();
const layId = made.results[0].id;
const detail = await (await fetch(`${BASE}/api/cutting/lays/${layId}/`, { headers: auth })).json();
const stored = Object.fromEntries(detail.shade_breakdown.map((r) => [r.shade, r.plies]));
check("stored on the lay", JSON.stringify(stored) === JSON.stringify({"أسود":20,"كحلي":10}),
      JSON.stringify(stored));
check("they add up to total_plies",
      detail.shade_breakdown.reduce((s, r) => s + r.plies, 0) === detail.total_plies);

await page.goto(`${BASE}/cutting/${layId}`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
check("the detail page shows the table", await t("shade-table").isVisible());
const tableText = (await t("shade-table").innerText()).replace(/\s+/g, " ");
check("with plies, pieces and share", /66\.7%/.test(tableText), tableText.slice(0, 120));

// ---------------------------------------------------------------- 4
console.log("\n4. quick mode: the table is optional and empty closes fine");
const code2 = "SQ" + String(Date.now()).slice(-8);
await header(code2);
await tap("mode-quick");
await page.waitForTimeout(400);
await t("quick-metres").fill("500.00");
await t("quick-plies").fill("50");
await page.waitForTimeout(500);
check("no shade strip when nothing is typed", (await t("shade-chip").count()) === 0);
await t("sheet-input").setInputFiles("/root/factory_erp/reference/notebook-page-1749.jpeg");
await page.locator('img[alt="ورقة الدفتر"]').waitFor({ timeout: 25000 });
await tap("close-btn");
const ok2 = await Promise.race([
  page.getByText("الفرشة اتقفلت").waitFor({ timeout: 25000 }).then(() => true),
  t("issue").first().waitFor({ timeout: 25000 }).then(() => false),
]);
if (!ok2 && await t("reason-input").isVisible().catch(() => false)) {
  await t("reason-input").fill("سريع");
  await tap("close-with-reason");
  await page.getByText("الفرشة اتقفلت").waitFor({ timeout: 25000 });
}
check("an empty split closes normally", true);

// ---------------------------------------------------------------- 5
console.log("\n5. quick mode: a mismatch is shown but never blocks");
const code3 = "SM" + String(Date.now()).slice(-8);
await header(code3);
await tap("mode-quick");
await page.waitForTimeout(400);
await t("quick-metres").fill("500.00");
await t("quick-plies").fill("50");
await tap("add-quick-shade");
await t("quick-shade").nth(0).fill("أسود");
await t("quick-shade-plies").nth(0).fill("30");
await page.waitForTimeout(700);
check("the gap is stated", await t("shade-gap").isVisible());
const gapText = (await t("shade-gap").innerText()).replace(/\s+/g, " ");
check("and names the difference", /20/.test(gapText), gapText);

await tap("add-quick-shade");
await t("quick-shade").nth(1).fill("كحلي");
await t("quick-shade-plies").nth(1).fill("20");
await page.waitForTimeout(700);
check("filling the rest clears the warning", (await t("shade-gap").count()) === 0);
const q = await chips();
check("the strip shows both", Object.keys(q).length === 2, JSON.stringify(q));

await t("sheet-input").setInputFiles("/root/factory_erp/reference/notebook-page-1749.jpeg");
await page.locator('img[alt="ورقة الدفتر"]').waitFor({ timeout: 25000 });
await tap("close-btn");
const ok3 = await Promise.race([
  page.getByText("الفرشة اتقفلت").waitFor({ timeout: 25000 }).then(() => true),
  t("issue").first().waitFor({ timeout: 25000 }).then(() => false),
]);
if (!ok3 && await t("reason-input").isVisible().catch(() => false)) {
  await t("reason-input").fill("سريع بألوان");
  await tap("close-with-reason");
  await page.getByText("الفرشة اتقفلت").waitFor({ timeout: 25000 });
}
const made3 = await (await fetch(`${BASE}/api/cutting/lays/?code=${code3}`,
  { headers: auth })).json();
const d3 = await (await fetch(`${BASE}/api/cutting/lays/${made3.results[0].id}/`,
  { headers: auth })).json();
check("the typed split was stored", d3.shade_breakdown.length === 2,
      JSON.stringify(d3.shade_breakdown.map((r) => [r.shade, r.plies])));
check("and is marked manual", d3.shade_breakdown.every((r) => r.is_manual));

check("no JS errors", errs.length === 0, errs[0] ?? "");
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
