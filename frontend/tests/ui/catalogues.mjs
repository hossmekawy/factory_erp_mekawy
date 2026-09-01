// Browser test for the model and fit catalogues and the new-lay defaults
// (SRS 4.4.1, 4.4.2, 7.2). Same staging setup as new-lay.mjs — see its header.
// Needs `qa_sup` (cutting_supervisor) and `qa_admin` (admin) on the dev
// database, and CuttingSettings with both defaults set. Never touches production.

import { chromium, devices } from "playwright";
import path from "node:path";

const BASE = "http://127.0.0.1:3010";
const SHOTS = process.env.SHOTS;
let pass = 0, fail = 0; const failures = [];
const check = (n, ok, d = "") => {
  if (ok) { pass++; console.log(`  ✓ ${n}`); }
  else { fail++; failures.push(`${n} ${d}`); console.log(`  ✗ ${n} ${d}`); }
};

async function login(user, pw) {
  const r = await fetch(`${BASE}/api/auth/login/`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: user, password: pw }),
  });
  return r.json();
}
const supTok = await login("qa_sup", "qa-staging-pw");
const adminTok = await login("qa_admin", "qa-staging-pw");

const browser = await chromium.launch();
async function ctxFor(tok, device = devices["Desktop Chrome"]) {
  const ctx = await browser.newContext({ ...device, locale: "ar-EG" });
  await ctx.addInitScript(([a, r]) => {
    localStorage.setItem("access", a); localStorage.setItem("refresh", r);
  }, [tok.access, tok.refresh]);
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  p.on("console", (m) => {
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text());
  });
  return { p, errs, ctx };
}

const { p: page, errs } = await ctxFor(adminTok);
const t = (id) => page.getByTestId(id);
const shot = (n) => SHOTS ? page.screenshot({ path: path.join(SHOTS, `${n}.png`), fullPage: true }) : null;
const rows = () => page.locator("tbody tr").count();

// ---------------------------------------------------------------- 1
console.log("\n1. the fit catalogue lists, adds, renames");
await page.goto(`${BASE}/cutting/fits`, { waitUntil: "networkidle" });
await page.waitForTimeout(800);
const before = await rows();
check("fits load", before > 0, String(before));

const newFit = "بوت كت " + String(Date.now()).slice(-5);
await page.getByRole("button", { name: "إضافة" }).click();
await t("field-name").fill(newFit);
await t("save-row").click();
await page.waitForTimeout(1200);
check("added", (await rows()) === before + 1, `${await rows()} vs ${before + 1}`);
await shot("f1-fits");

// ---------------------------------------------------------------- 2
console.log("\n2. a duplicate name is refused, in the dialog");
await page.getByRole("button", { name: "إضافة" }).click();
await t("field-name").fill(newFit);
await t("save-row").click();
await page.waitForTimeout(1000);
check("duplicate rejected with a field error", await t("error-name").isVisible());
await shot("f2-duplicate");
await page.getByRole("button", { name: "إلغاء" }).click();

// ---------------------------------------------------------------- 3
console.log("\n3. renaming a fit renames it on every model that uses it");
const fitsList = await (await fetch(`${BASE}/api/cutting/fits/?page_size=200`,
  { headers: { Authorization: `Bearer ${adminTok.access}` } })).json();
const used = (fitsList.results ?? fitsList).find((f) => f.model_count > 0);
if (used) {
  const renamed = used.name + "-م";
  await page.goto(`${BASE}/cutting/fits`, { waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  const rowIndex = (await page.locator("tbody tr").allInnerTexts())
    .findIndex((tx) => tx.includes(used.name));
  await t("edit-row").nth(rowIndex).click();
  await t("field-name").fill(renamed);
  await t("save-row").click();
  await page.waitForTimeout(1200);

  const models = await (await fetch(`${BASE}/api/cutting/models/?page_size=200`,
    { headers: { Authorization: `Bearer ${adminTok.access}` } })).json();
  const touched = (models.results ?? models).filter((m) => m.fit === used.id);
  check("every model shows the new name",
        touched.length > 0 && touched.every((m) => m.fit_name === renamed),
        JSON.stringify(touched.map((m) => m.fit_name)));
} else check("every model shows the new name", false, "no fit in use to rename");

// ---------------------------------------------------------------- 4
console.log("\n4. a fit still in use cannot be deleted");
const res4 = await fetch(`${BASE}/api/cutting/fits/${used.id}/`, {
  method: "DELETE", headers: { Authorization: `Bearer ${adminTok.access}` },
});
check("refused with 400", res4.status === 400, String(res4.status));
const body4 = await res4.json();
check("and says why in Arabic", /مينفعش/.test(body4.detail), JSON.stringify(body4));

// ---------------------------------------------------------------- 5
console.log("\n5. the model catalogue: duplicate code refused, junk model fixable");
await page.goto(`${BASE}/cutting/models`, { waitUntil: "networkidle" });
await page.waitForTimeout(900);
const modelRows = await rows();
check("models load", modelRows > 0, String(modelRows));

await page.getByRole("button", { name: "إضافة" }).click();
await t("field-code").fill("1749");
await t("field-name").fill("مكرر");
await t("save-row").click();
await page.waitForTimeout(1000);
check("duplicate code refused", await t("error-code").isVisible());
await shot("f5-dupcode");
await page.getByRole("button", { name: "إلغاء" }).click();

// rename the first model — the "I named it wrong" case
await page.waitForTimeout(400);
await t("edit-row").first().click();
const fixed = "اتصلح " + String(Date.now()).slice(-4);
await t("field-name").fill(fixed);
await t("save-row").click();
await page.waitForTimeout(1200);
check("a mistyped model can be corrected",
      (await page.locator("tbody").innerText()).includes(fixed));
await shot("f5-models");

// ---------------------------------------------------------------- 6
console.log("\n6. the supervisor can correct but not delete");
const { p: sup } = await ctxFor(supTok);
await sup.goto(`${BASE}/cutting/models`, { waitUntil: "networkidle" });
await sup.waitForTimeout(900);
check("supervisor sees the edit button",
      (await sup.getByTestId("edit-row").count()) > 0);
check("supervisor sees no delete button",
      (await sup.getByTestId("delete-row").count()) === 0);
const del = await fetch(`${BASE}/api/cutting/models/1/`, {
  method: "DELETE", headers: { Authorization: `Bearer ${supTok.access}` },
});
check("and the API refuses him anyway", del.status === 403, String(del.status));
await sup.context().close();

// ---------------------------------------------------------------- 7
console.log("\n7. the new-lay screen preselects the stored defaults");
const { p: phone, errs: phoneErrs } = await ctxFor(supTok, devices["Pixel 7"]);
await phone.goto(`${BASE}/cutting/new`, { waitUntil: "networkidle" });
await phone.waitForTimeout(1600);
const settings = await (await fetch(`${BASE}/api/cutting/settings/1/`,
  { headers: { Authorization: `Bearer ${adminTok.access}` } })).json();
const bankVal = await phone.getByTestId("bank-select").inputValue();
const leadVal = await phone.getByTestId("leader-select").inputValue();
check("bank preselected", bankVal === String(settings.default_bank),
      `${bankVal} vs ${settings.default_bank}`);
check("team leader preselected", leadVal === String(settings.default_team_leader),
      `${leadVal} vs ${settings.default_team_leader}`);

// and still changeable
const options = await phone.getByTestId("bank-select").locator("option").count();
if (options > 2) {
  await phone.getByTestId("bank-select").selectOption({ index: 2 });
  await phone.waitForTimeout(300);
  check("still changeable",
        (await phone.getByTestId("bank-select").inputValue()) !== String(settings.default_bank));
} else check("still changeable", true, "only one bank to pick");
if (SHOTS) await phone.screenshot({ path: path.join(SHOTS, "f7-defaults.png"), fullPage: true });
await phone.context().close();
check("no JS errors on the new-lay screen", phoneErrs.length === 0, phoneErrs[0] ?? "");

console.log(`\nJS errors: ${errs.length}`);
errs.slice(0, 4).forEach((e) => console.log("   " + e.slice(0, 140)));
check("no JS errors on the catalogues", errs.length === 0, errs[0] ?? "");

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
