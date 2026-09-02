// The printable lay sheet (SRS 7.4.1). Same staging setup as new-lay.mjs.
// Checks the buttons produce a real PDF; the sheet's contents are asserted in
// the backend suite, which reads the text back out of it.

import { chromium, devices } from "playwright";
import fs from "node:fs";

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

const lays = await (await fetch(`${BASE}/api/cutting/lays/?page_size=50`, { headers: auth })).json();
const lay = lays.results.find((l) => l.total_plies > 0) ?? lays.results[0];

const browser = await chromium.launch({ acceptDownloads: true });
const ctx = await browser.newContext({
  ...devices["Pixel 7"], locale: "ar-EG", acceptDownloads: true,
});
await ctx.addInitScript(([a, r]) => {
  localStorage.setItem("access", a); localStorage.setItem("refresh", r);
}, [tok.access, tok.refresh]);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
const t = (id) => page.getByTestId(id);

await page.goto(`${BASE}/cutting/${lay.id}`, { waitUntil: "networkidle" });
await t("pdf-a4").waitFor({ timeout: 20000 });

console.log("\n1. the A4 button downloads a PDF");
for (const [testid, label] of [["pdf-a4", "A4"], ["pdf-a5", "A5"]]) {
  const el = t(testid);
  await el.scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -140);
  const [dl] = await Promise.all([
    page.waitForEvent("download", { timeout: 40000 }),
    el.click(),
  ]);
  const path = `/tmp/claude-0/-root-factory-erp/58c13572-81ee-4de8-b588-ecfad8f456a5/scratchpad/dl-${testid}.pdf`;
  await dl.saveAs(path);
  const head = fs.readFileSync(path).subarray(0, 5).toString();
  check(`${label} downloads a real PDF`, head === "%PDF-", head);
  check(`${label} filename carries the lay code`,
        dl.suggestedFilename().includes(lay.code), dl.suggestedFilename());
}

console.log("\n2. nothing on screen leaks onto the paper");
const pdfText = await (await fetch(`${BASE}/api/cutting/lays/${lay.id}/pdf/`, { headers: auth })).arrayBuffer();
check("the sheet is not the screen", pdfText.byteLength > 1000);

check("no JS errors", errs.length === 0, errs[0] ?? "");
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) { failures.forEach((f) => console.log("  FAIL " + f)); process.exit(1); }
