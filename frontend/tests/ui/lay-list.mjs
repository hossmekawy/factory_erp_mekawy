// Browser test for the lay list and detail screens (SRS 7.1, 7.1.1, 7.1.2, 7.4).
// Playwright is NOT a dependency of this project; the browsers were already on
// the VPS. To run it, start the staging stack against the DEV database:
//
//   cd backend && DB_NAME=factory_erp_dev ALLOWED_HOSTS=127.0.0.1,localhost \
//     DEBUG=True venv/bin/python manage.py runserver 127.0.0.1:8011
//   cd frontend && BACKEND_URL=http://127.0.0.1:8011 npx next dev -p 3010 \
//     --hostname 127.0.0.1
//   node tests/ui/lay-list.mjs          # SHOTS=/some/dir for screenshots
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

const browser = await chromium.launch();

async function makePage(device) {
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
  return { p, errs };
}

const { p: page, errs } = await makePage(devices["Desktop Chrome"]);
const shot = (n) => SHOTS ? page.screenshot({ path: path.join(SHOTS, `${n}.png`), fullPage: true }) : null;
const rowCount = async () => (await page.locator("tbody tr").count());
const countFromApi = async (qs) => {
  const r = await fetch(`${BASE}/api/cutting/lays/?${qs}`, {
    headers: { Authorization: `Bearer ${tok.access}` },
  });
  return (await r.json()).count;
};

async function go(url) {
  await page.goto(BASE + url, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
}

// ---------------------------------------------------------------- 1
console.log("\n1. the list loads with its summary cards");
await go("/cutting");
await page.getByText("الفرشات").first().waitFor({ timeout: 15000 });
const total = await rowCount();
check("rows render", total > 0, `got ${total}`);
check("summary card shows a count", /\d/.test(await page.getByText("فرشات الفترة").locator("..").innerText()));
await shot("d1-list");

// ---------------------------------------------------------------- 2
console.log("\n2. shorthand search narrows the list and explains itself");
await go("/cutting");
const unfiltered = await countFromApi("");
await page.locator('input[placeholder*="ابحث"]').fill("عجز:نعم");
// Wait for the URL rather than a sleep — the box is debounced.
const landed = await page
  .waitForURL(/[?&]q=/, { timeout: 8000 })
  .then(() => true)
  .catch(() => false);
check("URL carries the query", landed, page.url());
await page.waitForTimeout(600);
const chip = await page.getByText("فيها عجز").first().isVisible();
check("the parsed token shows as a chip", chip);
// Compare totals, not rendered rows: a full page caps at the page size.
const filtered = await countFromApi("has_shortage=true");
check("fewer results than unfiltered", filtered < unfiltered,
      `${filtered} of ${unfiltered}`);
await shot("d2-search");

// ---------------------------------------------------------------- 3
console.log("\n3. a threshold token filters");
await go("/cutting?q=" + encodeURIComponent("ميتراج>0"));
const withMetrage = await rowCount();
await go("/cutting?q=" + encodeURIComponent("ميتراج>99"));
const none = await rowCount();
check("ميتراج>0 finds counted lays", withMetrage > 0, String(withMetrage));
check("ميتراج>99 finds none", none === 0, String(none));

// ---------------------------------------------------------------- 4
console.log("\n4. the filter drawer writes to the URL");
await go("/cutting");
await page.getByRole("button", { name: /فلاتر/ }).click();
// scope to the drawer: "الحالة" is also a table column header
await page.locator("aside").getByRole("button", { name: "الحالة" }).click();
await page.locator("aside select").first().selectOption("closed");
await page.waitForTimeout(800);
check("status landed in the URL", page.url().includes("status=closed"), page.url());
await shot("d4-drawer");
await page.getByRole("button", { name: "عرض النتائج" }).click();
await page.waitForTimeout(600);
check("chip for the applied filter", await page.getByText(/حالة الفرشة/).first().isVisible());

// ---------------------------------------------------------------- 5
console.log("\n5. the link alone reproduces the result");
const shared = page.url();
const { p: other } = await makePage(devices["Desktop Chrome"]);
await other.goto(shared, { waitUntil: "networkidle" });
await other.waitForTimeout(800);
const mine = await rowCount();
const theirs = await other.locator("tbody tr").count();
check("same rows from the same link", mine === theirs, `${mine} vs ${theirs}`);
await other.context().close();

// ---------------------------------------------------------------- 6
console.log("\n6. clearing removes the filters but keeps the search text");
await go("/cutting?status=closed&q=" + encodeURIComponent("كارل"));
await page.getByText("مسح الكل").click();
await page.waitForTimeout(700);
check("filter gone", !page.url().includes("status="), page.url());
check("search text kept", page.url().includes("q="), page.url());

// ---------------------------------------------------------------- 7
console.log("\n7. sorting by a column toggles direction in the URL");
await go("/cutting");
// Wait for the URL itself rather than a fixed sleep: router.replace lands
// asynchronously and a timeout here just makes the test flaky.
await page.locator("thead").getByText("الحقيقي", { exact: true }).click();
const ascending = await page
  .waitForURL(/ordering=real_metrage/, { timeout: 8000 })
  .then(() => true)
  .catch(() => false);
check("ordering set", ascending, page.url());
await page.locator("thead").getByText("الحقيقي", { exact: true }).click();
const descending = await page
  .waitForURL(/ordering=-real_metrage/, { timeout: 8000 })
  .then(() => true)
  .catch(() => false);
check("ordering flipped", descending, page.url());

// ---------------------------------------------------------------- 8
console.log("\n8. opening a lay shows every section of 7.4");
await go("/cutting");
await page.locator("tbody tr").first().click();
await page.waitForURL(/\/cutting\/\d+$/, { timeout: 15000 });
await page.waitForTimeout(900);
for (const heading of ["المقاسات", "سطور الأتواب", "الاستهلاك والعجز", "المرجع", "سجل النشاط"]) {
  check(`section "${heading}"`, await page.getByText(heading, { exact: true }).first().isVisible());
}
check("the six numbers are there", (await page.getByText("الميتراج الحقيقي").count()) > 0);
await shot("d8-detail");

// ---------------------------------------------------------------- 9
console.log("\n9. the notebook photo opens full size");
const photo = page.locator('img[alt="ورقة الدفتر"]');
if (await photo.count()) {
  await photo.click();
  await page.waitForTimeout(500);
  check("zoom overlay opened", await page.locator(".fixed.z-50 img").isVisible());
  await page.locator(".fixed.z-50").click({ position: { x: 10, y: 10 } });
} else check("zoom overlay opened", false, "no sheet image on this lay");

// ---------------------------------------------------------------- 10
console.log("\n10. the list works on a phone");
const { p: phone, errs: phoneErrs } = await makePage(devices["Pixel 7"]);
await phone.goto(BASE + "/cutting", { waitUntil: "networkidle" });
await phone.waitForTimeout(900);
const cards = await phone.locator('a[href^="/cutting/"]').count();
check("cards render on mobile", cards > 0, String(cards));
const wide = await phone.evaluate(
  () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
);
check("no horizontal overflow", !wide);
if (SHOTS) await phone.screenshot({ path: path.join(SHOTS, "d10-mobile.png"), fullPage: true });
await phone.context().close();
check("no JS errors on mobile", phoneErrs.length === 0, phoneErrs[0] ?? "");

// ---------------------------------------------------------------- 11
console.log("\n11. saved searches");
page.on("dialog", (d) => d.accept("فرشات فيها عجز"));
await go("/cutting?has_shortage=true");
await page.getByText("احفظ البحث").click();
await page.waitForTimeout(1000);
await go("/cutting");
check("saved search appears as a button", await page.getByText("فرشات فيها عجز").first().isVisible());
await page.getByText("فرشات فيها عجز").first().click();
await page.waitForTimeout(800);
check("clicking it restores the filters", page.url().includes("has_shortage=true"), page.url());

console.log(`\nJS errors: ${errs.length}`);
errs.slice(0, 4).forEach((e) => console.log("   " + e.slice(0, 130)));
check("no JS errors on desktop", errs.length === 0, errs[0] ?? "");

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
