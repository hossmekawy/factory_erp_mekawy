// Editing and deleting roll lines from the detail page.
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

async function makeLay(code, close) {
  const models = await (await fetch(`${BASE}/api/cutting/models/?search=${encodeURIComponent("كارل")}`, { headers: auth })).json();
  const leaders = await (await fetch(`${BASE}/api/cutting/team-leaders/`, { headers: auth })).json();
  const banks = await (await fetch(`${BASE}/api/cutting/banks/`, { headers: auth })).json();
  const lay = await (await fetch(`${BASE}/api/cutting/lays/`, {
    method: "POST", headers: auth,
    body: JSON.stringify({
      code, start_date: "2026-09-01", bank: banks.results[0].id,
      garment_model: models.results[0].id, team_leader: leaders[0].id,
      lay_width_cm: "162", lay_length_m: "6.55", sizes_raw: "30 32",
      lines: [
        { roll_length_m: "131.00", plies: 20, remnant_m: "0.00", shade_note: "أسود" },
        { roll_length_m: "65.50", plies: 10, remnant_m: "0.00", shade_note: "كحلي" },
      ],
    }),
  })).json();
  if (close) {
    const fd = new FormData();
    fd.append("sheet_image", new Blob([Uint8Array.from(
      atob("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"),
      (c) => c.charCodeAt(0))], { type: "image/gif" }), "s.gif");
    await fetch(`${BASE}/api/cutting/lays/${lay.id}/attachments/`, {
      method: "POST", headers: { Authorization: auth.Authorization }, body: fd });
    await fetch(`${BASE}/api/cutting/lays/${lay.id}/close/`, {
      method: "POST", headers: auth, body: JSON.stringify({ reason: "اختبار" }) });
  }
  return lay;
}
const get = async (id) => (await fetch(`${BASE}/api/cutting/lays/${id}/`, { headers: auth })).json();

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
page.on("dialog", (d) => d.accept());
const t = (id) => page.getByTestId(id);
const tap = async (id, i = 0) => {
  const el = t(id).nth(i);
  await el.scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -140);
  await el.click({ timeout: 20000 });
};

const stamp = String(Date.now()).slice(-7);
const openLay = await makeLay("LE" + stamp, false);
const shutLay = await makeLay("LS" + stamp, true);

// ---------------------------------------------------------------- 1
console.log("\n1. an open lay: a line edits straight away");
await page.goto(`${BASE}/cutting/${openLay.id}`, { waitUntil: "networkidle" });
await t("edit-line").first().waitFor({ timeout: 20000 });
await tap("edit-line");
await t("line-plies-edit").waitFor({ timeout: 10000 });
check("no reason asked", (await t("line-reason").count()) === 0);
await t("line-plies-edit").fill("25");
await tap("save-line");
await page.waitForTimeout(2500);
const a1 = await get(openLay.id);
check("the ply count moved", a1.total_plies === 35, String(a1.total_plies));
check("pieces followed", a1.theoretical_pieces === 70, String(a1.theoretical_pieces));
check("consumption followed", Number(a1.consumed_m) !== Number(openLay.consumed_m));
const sh1 = Object.fromEntries(a1.shade_breakdown.map((r) => [r.shade, r.plies]));
check("the shade split followed", sh1["أسود"] === 25, JSON.stringify(sh1));

// ---------------------------------------------------------------- 2
console.log("\n2. a line can be deleted, and everything recalculates");
await page.goto(`${BASE}/cutting/${openLay.id}`, { waitUntil: "networkidle" });
await t("edit-line").first().waitFor({ timeout: 20000 });
await tap("edit-line", 1);
await t("line-plies-edit").waitFor({ timeout: 10000 });
await tap("delete-line");
await page.waitForTimeout(2500);
const a2 = await get(openLay.id);
check("the line is gone", a2.lines.length === 1, String(a2.lines.length));
check("plies recalculated", a2.total_plies === 25, String(a2.total_plies));
check("its shade went with it",
      a2.shade_breakdown.every((r) => r.shade !== "كحلي"),
      JSON.stringify(a2.shade_breakdown.map((r) => r.shade)));

// ---------------------------------------------------------------- 3
console.log("\n3. a line can be added back");
await page.goto(`${BASE}/cutting/${openLay.id}`, { waitUntil: "networkidle" });
await t("add-line").waitFor({ timeout: 20000 });
await tap("add-line");
await t("line-length-edit").waitFor({ timeout: 10000 });
await t("line-length-edit").fill("65.50");
await t("line-plies-edit").fill("10");
await t("line-shade-edit").fill("كحلي");
await tap("save-line");
await page.waitForTimeout(2500);
const a3 = await get(openLay.id);
check("the line is back", a3.lines.length === 2, String(a3.lines.length));
check("plies back to 35", a3.total_plies === 35, String(a3.total_plies));

// ---------------------------------------------------------------- 4
console.log("\n4. a closed lay: no reason, no save");
await page.goto(`${BASE}/cutting/${shutLay.id}`, { waitUntil: "networkidle" });
await t("edit-line").first().waitFor({ timeout: 20000 });
await tap("edit-line");
await t("line-plies-edit").waitFor({ timeout: 10000 });
check("the reason box appears", await t("line-reason").isVisible());
await t("line-plies-edit").fill("30");
await page.waitForTimeout(300);
check("save is blocked", await t("save-line").isDisabled());
check("delete is blocked too", await t("delete-line").isDisabled());

// ---------------------------------------------------------------- 5
console.log("\n5. with a reason it saves and the log records both values");
await t("line-reason").fill("الراق اتكتب غلط");
await page.waitForTimeout(300);
await tap("save-line");
await page.waitForTimeout(2500);
const a5 = await get(shutLay.id);
check("the ply count moved", a5.total_plies === 40, String(a5.total_plies));
const entry = a5.audit_entries.find((e) => e.action === "line_edited");
check("the log has the old value", /20 راق/.test(entry?.old_value ?? ""), entry?.old_value);
check("and the new one", /30 راق/.test(entry?.new_value ?? ""), entry?.new_value);
check("and the reason", entry?.reason === "الراق اتكتب غلط", entry?.reason);
check("the page shows it",
      (await page.locator("body").innerText()).includes("الراق اتكتب غلط"));

// ---------------------------------------------------------------- 6
console.log("\n6. the line rules still apply while editing");
await tap("edit-line");
await t("line-remnant-edit").waitFor({ timeout: 10000 });
await t("line-remnant-edit").fill("9.99");     // longer than the lay
await t("line-reason").fill("تجربة");
await tap("save-line");
await page.waitForTimeout(2200);
const codes = await Promise.all(
  (await t("line-issue").all()).map((e) => e.getAttribute("data-code"))
);
check("V3 refuses a remnant longer than the lay", codes.includes("V3"),
      JSON.stringify(codes));

check("no JS errors", errs.length === 0, errs[0] ?? "");
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
