// Headless render check: serves nothing itself — expects `vite preview` on PORT.
// Fails if (a) any request leaves localhost, (b) any console error / page error, (c) #loading never hides.
// Writes a screenshot for visual confirmation.
import puppeteer from "puppeteer-core";

const PORT = process.env.PORT ?? "4173";
const OUT = process.env.OUT ?? "../docs/screenshots/latest.png";
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const url = `http://localhost:${PORT}/${process.env.QUERY ?? ""}`;

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--use-angle=metal", "--enable-webgl", "--ignore-gpu-blocklist", "--window-size=1600,900"],
  defaultViewport: { width: 1600, height: 900 },
});
const page = await browser.newPage();
const problems = [];
await page.setRequestInterception(true);
page.on("request", (req) => {
  const u = new URL(req.url());
  if (u.protocol === "data:" || u.protocol === "blob:" || u.hostname === "localhost" || u.hostname === "127.0.0.1") return req.continue();
  problems.push(`EXTERNAL REQUEST: ${req.url()}`);
  req.abort();
});
page.on("console", (m) => { if (m.type() === "error") problems.push(`console.error: ${m.text()}`); });
page.on("response", (r) => { if (r.status() >= 400) problems.push(`HTTP ${r.status()}: ${r.url()}`); });
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => { if (!problems.some((p) => p.includes(r.url()))) problems.push(`request failed: ${r.url()}`); });

await page.goto(url, { waitUntil: "networkidle0", timeout: 60000 });
try {
  await page.waitForSelector("#loading.hidden", { timeout: 30000 });
} catch {
  problems.push("loading overlay never hid");
}
await new Promise((r) => setTimeout(r, 1500));
await page.screenshot({ path: OUT });
await browser.close();

if (problems.length) {
  console.error("CHECK FAILED\n" + problems.join("\n"));
  process.exit(1);
}
console.log(`CHECK OK — no external requests, no errors. Screenshot: ${OUT}`);
