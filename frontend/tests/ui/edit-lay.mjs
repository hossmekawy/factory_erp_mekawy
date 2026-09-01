// Fixing a mistyped lay — the code above all. Same staging setup as new-lay.mjs.
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
const auth = { Authorization: `Bearer ${tok.access}`, "Content-Type": "application/json" };

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
const t = (id) => page.getByTestId(id);
const tap = async (id) => {
  const el = t(id).first();
  await el.scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -140);
  await el.click({ timeout: 20000 });
};

// build two lays through the API: one open, one closed
async function makeLay(code, close) {
  const models = await (await fetch(`${BASE}/api/cutting/models/?search=${encodeURIComponent("كارل")}`,
    { headers: auth })).json();
  const leaders = await (await fetch(`${BASE}/api/cutting/team-leaders/`, { headers: auth })).json();
  const banks = await (await fetch(`${BASE}/api/cutting/banks/`, { headers: auth })).json();
  const res = await fetch(`${BASE}/api/cutting/lays/`, {
    method: "POST", headers: auth,
    body: JSON.stringify({
      code, start_date: "2026-09-01", bank: banks.results[0].id,
      garment_model: models.results[0].id, team_leader: leaders[0].id,
      lay_width_cm: "162", lay_length_m: "6.55", sizes_raw: "30 32",
      lines: [{ roll_length_m: "105.30", plies: 16, remnant_m: "0.50", shade_note: "أسود" }],
    }),
  });
  const lay = await res.json();
  if (close) {
    await fetch(`${BASE}/api/cutting/lays/${lay.id}/attachments/`, {
      method: "POST", headers: { Authorization: auth.Authorization },
      body: (() => {
        const fd = new FormData();
        fd.append("sheet_image", new Blob([Uint8Array.from(
          atob("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"),
          (c) => c.charCodeAt(0))], { type: "image/gif" }), "s.gif");
        return fd;
      })(),
    });
    await fetch(`${BASE}/api/cutting/lays/${lay.id}/close/`, {
      method: "POST", headers: auth, body: JSON.stringify({ reason: "اختبار" }),
    });
  }
  return lay;
}

const stamp = String(Date.now()).slice(-7);
const openLay = await makeLay("WRONG" + stamp, false);
const closedLay = await makeLay("SHUT" + stamp, true);

// ---------------------------------------------------------------- 1
console.log("\n1. an open lay: the code is fixable straight away");
await page.goto(`${BASE}/cutting/${openLay.id}`, { waitUntil: "networkidle" });
await t("edit-lay").waitFor({ timeout: 20000 });
await tap("edit-lay");
await t("edit-code").waitFor({ timeout: 10000 });
check("no reason asked for an open lay", (await t("edit-reason").count()) === 0);
const fixed = "RIGHT" + stamp;
await t("edit-code").fill(fixed);
await tap("edit-save");
await page.waitForTimeout(2200);
const after1 = await (await fetch(`${BASE}/api/cutting/lays/${openLay.id}/`, { headers: auth })).json();
check("the code changed", after1.code === fixed, after1.code);
check("the page shows it", (await page.locator("body").innerText()).includes(fixed));

// ---------------------------------------------------------------- 2
console.log("\n2. a closed lay: no reason, no save");
await page.goto(`${BASE}/cutting/${closedLay.id}`, { waitUntil: "networkidle" });
await t("edit-lay").waitFor({ timeout: 20000 });
await tap("edit-lay");
await t("edit-code").waitFor({ timeout: 10000 });
check("the reason box appears", await t("edit-reason").isVisible());
await t("edit-code").fill("SHUTFIX" + stamp);
await page.waitForTimeout(300);
check("save is blocked without a reason", await t("edit-save").isDisabled());

// ---------------------------------------------------------------- 3
console.log("\n3. with a reason it saves, and the log records it");
await t("edit-reason").fill("الكود اتكتب غلط");
await page.waitForTimeout(300);
check("save unlocked", !(await t("edit-save").isDisabled()));
await tap("edit-save");
await page.waitForTimeout(2500);
const after3 = await (await fetch(`${BASE}/api/cutting/lays/${closedLay.id}/`, { headers: auth })).json();
check("the code changed", after3.code === "SHUTFIX" + stamp, after3.code);
const entry = after3.audit_entries.find((a) => a.action === "edit_after_close" && a.field === "code");
check("the activity log has the old and new value",
      entry?.old_value === "SHUT" + stamp && entry?.new_value === "SHUTFIX" + stamp,
      JSON.stringify(entry));
check("and the reason", entry?.reason === "الكود اتكتب غلط", entry?.reason);
check("the log is on the page",
      (await page.locator("body").innerText()).includes("الكود اتكتب غلط"));

// ---------------------------------------------------------------- 4
console.log("\n4. a code already in use is refused, in the dialog");
await tap("edit-lay");
await t("edit-code").waitFor({ timeout: 10000 });
await t("edit-code").fill(fixed);            // the other lay's code
await t("edit-reason").fill("تجربة تكرار");
await tap("edit-save");
await page.waitForTimeout(2200);
check("the clash is shown on the field", await t("edit-code-error").isVisible());
check("and says it is taken",
      /مستخدم/.test(await t("edit-code-error").innerText()),
      await t("edit-code-error").innerText());

check("no JS errors", errs.length === 0, errs[0] ?? "");
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
