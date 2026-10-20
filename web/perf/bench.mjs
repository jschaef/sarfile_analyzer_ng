#!/usr/bin/env node
// ECharts vs BokehJS: time from "data available in the page" to "chart painted".
//
//   node perf/bench.mjs [payload dir] [runs]
//
// The payload dir comes from perf/export_payloads.py. Both libraries run in the
// same headless Chromium (Playwright), in a fresh page per run, alternating.
// Set PLAYWRIGHT_CHROMIUM_EXECUTABLE to use a preinstalled Chromium.
//
// Timed span per run (t0 -> t2):
//   ECharts: t0 before toColumns(API rows) -> echarts.init -> setOption ->
//            'finished' event -> two animation frames
//   Bokeh:   t0 before Bokeh.embed.embed_item(json_item) -> all views
//            finished -> two animation frames
// Fetching and JSON.parse of the payload happen before t0 for both.

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, "..");
const payloadDir = path.resolve(process.argv[2] ?? path.join(here, "out"));
const runs = Number(process.argv[3] ?? 11);
const require = createRequire(import.meta.url);
const ts = require("typescript");

// The app's own option builder and data conversion, types stripped.
async function transpile(file) {
  const source = await readFile(path.join(webRoot, file), "utf8");
  return ts
    .transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    })
    .outputText.replace(/from "@\/lib\/sar"/g, 'from "/lib/sar.js"');
}

const files = {
  "/lib/sar.js": ["text/javascript", await transpile("lib/sar.ts")],
  "/lib/echarts-option.js": ["text/javascript", await transpile("lib/echarts-option.ts")],
  "/echarts.min.js": [
    "text/javascript",
    await readFile(path.join(webRoot, "node_modules/echarts/dist/echarts.min.js")),
  ],
  "/echarts.html": [
    "text/html",
    `<!doctype html><meta charset="utf-8"><body style="margin:0">
<div id="chart" style="width:1200px;height:400px"></div>
<script src="/echarts.min.js"></script>
<script type="module">
import { toColumns } from "/lib/sar.js";
import { buildLineOption } from "/lib/echarts-option.js";
const frame = () => new Promise((r) => requestAnimationFrame(() => r()));
window.bench = async (url) => {
  const payload = await (await fetch(url)).json();
  await frame();
  const el = document.getElementById("chart");
  const t0 = performance.now();
  const columns = toColumns(payload.data);
  const t_conv = performance.now();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  const finished = new Promise((r) => chart.on("finished", r));
  chart.setOption(buildLineOption({ columns }));
  await finished;
  const t1 = performance.now();
  await frame(); await frame();
  const t2 = performance.now();
  return { convert: t_conv - t0, library: t1 - t0, painted: t2 - t0 };
};
window.benchReady = true;
</script>`,
  ],
  "/bokeh.html": [
    "text/html",
    `<!doctype html><meta charset="utf-8"><body style="margin:0">
<div id="chart" style="width:1200px;height:400px"></div>
<script src="/bokeh.min.js"></script>
<script>
const frame = () => new Promise((r) => requestAnimationFrame(() => r()));
window.bench = async (url) => {
  const item = await (await fetch(url)).json();
  await frame();
  const t0 = performance.now();
  const manager = await Bokeh.embed.embed_item(item, "chart");
  const roots = manager.roots ?? Array.from(manager);
  window.benchHasFinished = roots.length > 0 && roots.every((v) => typeof v.has_finished === "function");
  while (!roots.every((v) => (typeof v.has_finished === "function" ? v.has_finished() : true))) {
    await frame();
  }
  const t1 = performance.now();
  await frame(); await frame();
  const t2 = performance.now();
  return { convert: 0, library: t1 - t0, painted: t2 - t0 };
};
window.benchReady = true;
</script>`,
  ],
};

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://x").pathname;
  try {
    if (files[url]) {
      res.writeHead(200, { "content-type": files[url][0] });
      return res.end(files[url][1]);
    }
    const name = path.basename(url);
    const type = name.endsWith(".js") ? "text/javascript" : "application/json";
    const body = await readFile(path.join(payloadDir, name));
    res.writeHead(200, { "content-type": type });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
});
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });

const cases = [
  { scenario: "cpu-overview", lib: "bokeh", payload: "cpu-overview.bokeh.json" },
  { scenario: "cpu-overview", lib: "echarts (full rows)", payload: "cpu-overview.echarts.json" },
  { scenario: "cpu-overview", lib: "echarts (Bokeh's rows)", payload: "cpu-overview.echarts-same.json" },
  { scenario: "cpu-per-core", lib: "bokeh", payload: "cpu-per-core.bokeh.json" },
  { scenario: "cpu-per-core", lib: "echarts (full rows)", payload: "cpu-per-core.echarts.json" },
  { scenario: "cpu-per-core", lib: "echarts (Bokeh's rows)", payload: "cpu-per-core.echarts-same.json" },
];

// BENCH_SCREENSHOTS=<dir>: keep one screenshot per case to check what was drawn
const shotDir = process.env.BENCH_SCREENSHOTS;
const shot = new Set();

async function once(c) {
  const page = await context.newPage();
  const html = c.lib === "bokeh" ? "/bokeh.html" : "/echarts.html";
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(base + html);
  await page.waitForFunction(() => window.benchReady === true);
  const result = await page.evaluate((u) => window.bench(u), `/${c.payload}`);
  const canvases = await page.locator("#chart canvas").count();
  if (c.lib === "bokeh" && !(await page.evaluate(() => window.benchHasFinished))) {
    errors.push("Bokeh views expose no has_finished() - completion not observable");
  }
  if (shotDir && !shot.has(c)) {
    shot.add(c);
    const name = `${c.scenario}-${c.lib.replace(/[^a-z]+/gi, "_")}.png`;
    await page.locator("#chart").screenshot({ path: path.join(shotDir, name) });
  }
  await page.close();
  if (errors.length || canvases === 0) throw new Error(`${c.lib}: ${errors.join("; ") || "no canvas"}`);
  return result;
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

const samples = new Map(cases.map((c) => [c, []]));
for (let run = 0; run < runs; run++) {
  // alternate the order every run so neither library always goes first
  const order = run % 2 ? [...cases].reverse() : cases;
  for (const c of order) samples.get(c).push(await once(c));
}

const meta = JSON.parse(await readFile(path.join(payloadDir, "meta.json"), "utf8"));
const echartsVersion = require("echarts/package.json").version;
const results = {
  runs,
  browser: `Chromium ${browser.version()}`,
  echarts: echartsVersion,
  bokeh: meta.versions.bokeh,
  cases: cases.map((c) => {
    const xs = samples.get(c);
    const painted = xs.map((x) => x.painted);
    return {
      scenario: c.scenario,
      lib: c.lib,
      payload_bytes: meta.scenarios[c.scenario].bytes[c.payload.split(".")[1]],
      median_painted_ms: +median(painted).toFixed(1),
      min_ms: +Math.min(...painted).toFixed(1),
      max_ms: +Math.max(...painted).toFixed(1),
      median_convert_ms: +median(xs.map((x) => x.convert)).toFixed(1),
    };
  }),
};
console.log(JSON.stringify(results, null, 2));
await browser.close();
server.close();
