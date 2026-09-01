// Browser test for the counting screen (SRS 7.3, 4.9).
// Playwright is NOT a dependency of this project; the browsers were already on
// the VPS. To run it, start the staging stack against the DEV database:
//
//   cd backend && DB_NAME=factory_erp_dev ALLOWED_HOSTS=127.0.0.1,localhost \
//     DEBUG=True venv/bin/python manage.py runserver 127.0.0.1:8011
//   cd frontend && BACKEND_URL=http://127.0.0.1:8011 npx next dev -p 3010 \
//     --hostname 127.0.0.1
//   node tests/ui/counting.mjs          # SHOTS=/some/dir for screenshots
//
// Needs a `qa_sup` user in the cutting_supervisor group on the dev database,
// at least one bank, and the model 1749. It never touches production.

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

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices["Pixel 7"], locale: "ar-EG" });
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

async function waiting() {
  const r = await fetch(`${BASE}/api/cutting/lays/?awaiting_count=true&ordering=end_date`, { headers: auth });
  return (await r.json()).results;
}

async function openFirst() {
  await page.goto(`${BASE}/cutting/count`, { waitUntil: "networkidle" });
  await t("count-card").first().waitFor({ timeout: 15000 });
  await t("count-card").first().click();
  await t("good-pieces").waitFor({ timeout: 8000 });
}

// ---------------------------------------------------------------- 1
console.log("\n1. the worklist shows only lays awaiting a count");
const before = await waiting();
await page.goto(`${BASE}/cutting/count`, { waitUntil: "networkidle" });
await page.waitForTimeout(700);
const cards = await t("count-card").count();
check("a card per waiting lay", cards === before.length, `${cards} vs ${before.length}`);
await shot("e1-worklist");

// ---------------------------------------------------------------- 2
console.log("\n2. typing a count shows the automatic split, summing exactly");
await openFirst();
const lay = before[0];
await t("good-pieces").fill(String(lay.theoretical_pieces - 3));
await page.waitForTimeout(900);
const cells = await page.locator("tbody tr td:nth-child(4)").allInnerTexts();
const sum = cells.reduce((s, c) => s + Number(c.trim()), 0);
check("the split adds to the number typed", sum === lay.theoretical_pieces - 3,
      `${sum} vs ${lay.theoretical_pieces - 3}`);
check("loss shown", await page.getByText(/فاقد القطع/).isVisible());
await shot("e2-split");

// ---------------------------------------------------------------- 3
console.log("\n3. an impossible count is refused with V9");
await t("good-pieces").fill(String(lay.theoretical_pieces + 50));
await page.waitForTimeout(900);
const codes = await Promise.all(
  (await t("preview-issue").all()).map((e) => e.getAttribute("data-code"))
);
check("V9 shown before saving", codes.includes("V9"), JSON.stringify(codes));
check("save is disabled", await t("save-count").isDisabled());
await shot("e3-v9");

// ---------------------------------------------------------------- 4
console.log("\n4. manual override asks first, then must add up");
await t("good-pieces").fill(String(lay.theoretical_pieces - 3));
await page.waitForTimeout(900);
let asked = false;
page.on("dialog", (d) => { asked = true; d.accept(); });
await t("unlock-manual").click();
await page.waitForTimeout(500);
check("it asked for confirmation", asked);

const sizes = (await page.locator("tbody tr td:nth-child(1)").allInnerTexts()).map((s) => s.trim());
await t(`manual-${sizes[0]}`).fill("1");
await page.waitForTimeout(400);
check("mismatched total is flagged",
      (await t("manual-total").innerText()).includes("لازم يتساووا"));
check("save blocked while it does not add up", await t("save-count").isDisabled());
await shot("e4-manual");

// ---------------------------------------------------------------- 5
console.log("\n5. a manual split that adds up saves, and is marked manual");
// put the removed pieces onto the second size so the total matches again
const firstWas = Number(
  (await page.locator("tbody tr td:nth-child(4) input").first().inputValue()) || 0
);
const target = lay.theoretical_pieces - 3;
const others = await page.locator("tbody tr td:nth-child(4) input").count();
let running = 1;
for (let i = 1; i < others; i++) {
  const v = Number(await page.locator("tbody tr td:nth-child(4) input").nth(i).inputValue());
  running += v;
}
const secondInput = page.locator("tbody tr td:nth-child(4) input").nth(1);
const secondVal = Number(await secondInput.inputValue());
await secondInput.fill(String(secondVal + (target - running)));
await page.waitForTimeout(500);
check("total matches again", !(await t("manual-total").innerText()).includes("لازم"));
await t("count-notes").fill("توزيع يدوي للاختبار");
await t("save-count").click();
await page.waitForTimeout(2500);

const after = await fetch(`${BASE}/api/cutting/lays/${lay.id}/`, { headers: auth }).then((r) => r.json());
check("lay is now counted", after.status === "counted", after.status);
check("output stored", after.output?.actual_pieces === target, String(after.output?.actual_pieces));
check("split marked manual", after.size_breakdown.every((b) => b.is_manually_adjusted));
const stored = after.size_breakdown.reduce((s, b) => s + (b.actual_pieces ?? 0), 0);
check("stored split still adds to the total", stored === target, `${stored} vs ${target}`);

// ---------------------------------------------------------------- 6
console.log("\n6. the automatic path, with rejects");
const list2 = await waiting();
check("the counted lay left the worklist", !list2.some((r) => r.id === lay.id));
const next = list2[0];
await page.goto(`${BASE}/cutting/count?lay=${next.id}`, { waitUntil: "networkidle" });
await t("good-pieces").waitFor({ timeout: 10000 });
await t("good-pieces").fill(String(next.theoretical_pieces));
await t("rejected-pieces").fill("4");
await page.waitForTimeout(900);
await t("save-count").click();
await page.waitForTimeout(2500);
const after2 = await fetch(`${BASE}/api/cutting/lays/${next.id}/`, { headers: auth }).then((r) => r.json());
check("saved with no loss", after2.output?.actual_pieces === next.theoretical_pieces);
check("rejects recorded", after2.output?.rejected_pieces === 4, String(after2.output?.rejected_pieces));
check("split not marked manual", after2.size_breakdown.every((b) => !b.is_manually_adjusted));
check("real metrage now computed", after2.real_metrage != null, String(after2.real_metrage));

// ---------------------------------------------------------------- 7
console.log("\n7. a big loss demands a reason");
const list3 = await waiting();
const third = list3[0];
await page.goto(`${BASE}/cutting/count?lay=${third.id}`, { waitUntil: "networkidle" });
await t("good-pieces").waitFor({ timeout: 10000 });
await t("good-pieces").fill(String(Math.floor(third.theoretical_pieces * 0.5)));
await page.waitForTimeout(900);
check("tolerance breach shown", await page.getByText(/تعدّى نسبة التسامح/).isVisible());
check("save blocked without a reason", await t("save-count").isDisabled());
await t("count-notes").fill("قماش بايظ");
await page.waitForTimeout(300);
check("save allowed once a reason is given", !(await t("save-count").isDisabled()));
await shot("e7-tolerance");

// ---------------------------------------------------------------- 8
console.log("\n8. no horizontal overflow on a phone");
const wide = await page.evaluate(
  () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
);
check("fits the screen", !wide);

console.log(`\nJS errors: ${errs.length}`);
errs.slice(0, 4).forEach((e) => console.log("   " + e.slice(0, 130)));
check("no JS errors", errs.length === 0, errs[0] ?? "");

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
