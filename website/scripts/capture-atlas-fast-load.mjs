/**
 * Fast-load visual parity figures (fast-load design §B.1 "Visual parity").
 *
 *   ATLAS_CAPTURE_BASE_URL=<pre-change build> node scripts/capture-atlas-fast-load.mjs --phase before --commit <sha>
 *   node scripts/capture-atlas-fast-load.mjs --phase after          # serves ./dist (production build)
 *
 * Each phase captures HbS and G6PD at the default camera in four geometry
 * modes after the sky box has loaded, with time frozen and neutral imagery,
 * twice: at the default URL (every layer; the committed figures) and with the
 * Natural Earth countries overlay off (GATE_LAYERS). The after phase compares
 * every pair with the before captures and writes
 * docs/figures/atlas-fast-load-parity.receipt.json. The gate is the
 * countries-off comparison: it exits non-zero when any pair differs on more
 * than 0.5% of pixels. §B.6.9 redraws the borders with a
 * BufferPolylineCollection instead of GeoJsonDataSource entity polylines, whose
 * 1-px anti-aliasing differs, so the every-layer comparison is recorded as
 * informational, with magnified before/after border crops in
 * docs/figures/atlas-fast-load-border-crops.png.
 */
import { execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import { chromium } from 'playwright';

import { countPixelDifferences, decodePng } from './pixel-diff.mjs';

const websiteRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const figuresDir = path.resolve(websiteRoot, '..', 'docs', 'figures');
const ENTITIES = [
  ['hbs', 'hbs-rs334'],
  ['g6pd', 'g6pd-deficiency'],
];
const GEOMETRIES = ['triangles', 'hexagons', 'extruded', 'honmoon'];
const FIGURE_GEOMETRY = 'triangles';
const VIEWPORT = { height: 900, width: 1440 };
const FIXED_TIME = new Date('2026-10-07T12:00:00Z');
const CHANNEL_TOLERANCE = 2;
const MAX_DIFFERENT_FRACTION = 0.005;
/** Every layer but the Natural Earth countries overlay: the §B.1 screenshot gate. */
const GATE_LAYERS = 'surface,observations,support,context';
const VIEWS = [
  // The default URL, every layer on: the committed figures and the informational delta.
  { figure: true, kind: 'globe', params: {} },
  { figure: false, kind: 'gate', params: { layers: GATE_LAYERS } },
];
/** Border windows of the every-layer HbS triangles globe, magnified CROP_SCALE times. */
const BORDER_CROPS = [
  { name: 'Europe', x: 620, y: 190, width: 180, height: 100 },
  { name: 'Egypt', x: 700, y: 330, width: 180, height: 100 },
  { name: 'West Africa', x: 520, y: 460, width: 180, height: 100 },
];
const CROP_SCALE = 3;
const OVERLAYS = [
  '.site-header',
  '.atlas-top-slot',
  '.atlas-controls',
  '.atlas-legend',
  '.atlas-right-rail',
  '.atlas-status-stack',
  '.atlas-warning-banner',
  '.atlas-data-credit',
  '.atlas-hover-preview',
  '.cesium-viewer-bottom',
].join(', ');
const neutralTile = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAFAgIAvPp7WQAAAABJRU5ErkJggg==',
  'base64',
);

const { values } = parseArgs({
  options: {
    commit: { type: 'string' },
    out: {
      default: path.join(
        websiteRoot,
        'test-results',
        'atlas-fast-load-figures',
      ),
      type: 'string',
    },
    phase: { type: 'string' },
  },
});
const phase = values.phase;
if (phase !== 'before' && phase !== 'after')
  throw new Error('Pass --phase before|after.');
if (phase === 'before' && !values.commit)
  throw new Error('Pass --commit <sha of the pre-change build>.');
const commit =
  values.commit ??
  execFileSync('git', ['rev-parse', 'HEAD'], {
    cwd: websiteRoot,
    encoding: 'utf8',
  }).trim();
const outDir = path.resolve(values.out);
mkdirSync(outDir, { recursive: true });
const suppliedBaseUrl = process.env.ATLAS_CAPTURE_BASE_URL;
const baseUrl = suppliedBaseUrl ?? 'http://127.0.0.1:4323';

function capturePath(kind, entity, geometry, capturePhase = phase) {
  return path.join(outDir, `${capturePhase}-${entity}-${geometry}-${kind}.png`);
}

async function waitForServer(url) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function waitUntil(condition, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() > deadline)
      throw new Error(`Timed out waiting for ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

async function settledScreenshot(page) {
  const options = { animations: 'disabled', caret: 'hide' };
  let previous = await page.screenshot(options);
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    await page.waitForTimeout(750);
    const next = await page.screenshot(options);
    if (next.equals(previous)) return next;
    previous = next;
  }
  throw new Error('The globe did not settle within 30 s.');
}

async function capture(browser, entity, geometry, view) {
  const context = await browser.newContext({
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
    viewport: VIEWPORT,
  });
  await context.clock.setFixedTime(FIXED_TIME);
  await context.route('https://tile.openstreetmap.org/**', (route) =>
    route.fulfill({ body: neutralTile, contentType: 'image/png', status: 200 }),
  );
  const page = await context.newPage();
  const pageErrors = [];
  const skyBoxFaces = new Set();
  page.on('pageerror', (error) => pageErrors.push(error));
  page.on('requestfinished', (request) => {
    if (request.url().includes('/Textures/SkyBox/'))
      skyBoxFaces.add(request.url());
  });
  try {
    await page.goto(
      `${baseUrl}/app/?${new URLSearchParams({ entity, geometry, ...view.params })}`,
    );
    await page
      .locator('[data-atlas-ready="true"]')
      .waitFor({ timeout: 180_000 });
    await waitUntil(() => skyBoxFaces.size >= 6, 60_000, 'six sky box faces');
    await page.setViewportSize({
      height: VIEWPORT.height + 1,
      width: VIEWPORT.width,
    });
    await page.waitForTimeout(250);
    await page.setViewportSize(VIEWPORT);
    // Headed Chrome hovers wherever the real pointer is, and the pointer can move during a capture,
    // so a hover preview would open in some figures: leave the canvas and hide that transient panel.
    await page.mouse.move(0, 0);
    await page.addStyleTag({
      content: '.atlas-hover-preview { visibility: hidden !important; }',
    });
    const figure = view.figure ? await settledScreenshot(page) : null;
    const overlays = await page.addStyleTag({
      content: `${OVERLAYS} { visibility: hidden !important; }`,
    });
    const globe = await settledScreenshot(page);
    await overlays.evaluate((element) => element.remove());
    if (pageErrors.length > 0) throw pageErrors[0];
    if (figure) writeFileSync(capturePath('figure', entity, geometry), figure);
    writeFileSync(capturePath(view.kind, entity, geometry), globe);
    return await page.evaluate(() => {
      const gl = document.createElement('canvas').getContext('webgl');
      const debug = gl?.getExtension('WEBGL_debug_renderer_info');
      return gl && debug
        ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL))
        : 'unknown';
    });
  } finally {
    await context.close();
  }
}

async function comparePairs(page, kind) {
  const pairs = [];
  for (const [, entity] of ENTITIES)
    for (const geometry of GEOMETRIES) {
      const before = await decodePng(
        page,
        readFileSync(capturePath(kind, entity, geometry, 'before')),
      );
      const after = await decodePng(
        page,
        readFileSync(capturePath(kind, entity, geometry, 'after')),
      );
      if (before.width !== after.width || before.height !== after.height)
        throw new Error(
          `${entity} ${geometry} ${kind}: ${before.width}×${before.height} vs ${after.width}×${after.height}`,
        );
      pairs.push({
        entity,
        geometry,
        ...countPixelDifferences(before.data, after.data, CHANNEL_TOLERANCE),
      });
    }
  return pairs;
}

/** Before, after and the pixels over CHANNEL_TOLERANCE (red), one row per BORDER_CROPS window. */
async function writeBorderCrops(page) {
  const [entity, geometry] = ['hbs-rs334', FIGURE_GEOMETRY];
  const png = await page.evaluate(
    async ({ after, before, crops, scale, tolerance }) => {
      const bitmap = async (base64) =>
        createImageBitmap(
          await (await fetch(`data:image/png;base64,${base64}`)).blob(),
          { colorSpaceConversion: 'none', premultiplyAlpha: 'none' },
        );
      const images = [await bitmap(before), await bitmap(after)];
      const header = 30;
      const gap = 8;
      const cellWidth = Math.max(...crops.map((crop) => crop.width)) * scale;
      const cellHeight = Math.max(...crops.map((crop) => crop.height)) * scale;
      const canvas = new OffscreenCanvas(
        3 * cellWidth + 2 * gap,
        crops.length * (header + cellHeight + gap) - gap,
      );
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No 2D context for the border crops.');
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.imageSmoothingEnabled = false;
      context.font = '600 16px system-ui, sans-serif';
      crops.forEach((crop, row) => {
        const top = row * (header + cellHeight + gap);
        const pixels = images.map((image) => {
          const source = new OffscreenCanvas(crop.width, crop.height);
          const sourceContext = source.getContext('2d');
          if (!sourceContext) throw new Error('No 2D context for a crop.');
          sourceContext.drawImage(image, -crop.x, -crop.y);
          return sourceContext.getImageData(0, 0, crop.width, crop.height);
        });
        const mask = new ImageData(crop.width, crop.height);
        for (let index = 0; index < mask.data.length; index += 4) {
          let delta = 0;
          for (let channel = 0; channel < 4; channel += 1)
            delta = Math.max(
              delta,
              Math.abs(
                pixels[0].data[index + channel] -
                  pixels[1].data[index + channel],
              ),
            );
          const grey =
            (pixels[1].data[index] +
              pixels[1].data[index + 1] +
              pixels[1].data[index + 2]) /
            9;
          mask.data.set(
            delta > tolerance ? [255, 48, 32, 255] : [grey, grey, grey, 255],
            index,
          );
        }
        const titles = [
          `${crop.name}: before`,
          'after',
          `differs by more than ${tolerance}/255`,
        ];
        [...pixels, mask].forEach((data, column) => {
          const left = column * (cellWidth + gap);
          const cell = new OffscreenCanvas(crop.width, crop.height);
          cell.getContext('2d')?.putImageData(data, 0, 0);
          context.drawImage(
            cell,
            left,
            top + header,
            crop.width * scale,
            crop.height * scale,
          );
          context.fillStyle = '#111111';
          context.fillText(titles[column], left + 4, top + header - 9);
        });
      });
      const blob = await canvas.convertToBlob({ type: 'image/png' });
      const dataUrl = await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.readAsDataURL(blob);
      });
      return dataUrl.slice(dataUrl.indexOf(',') + 1);
    },
    {
      after: readFileSync(
        capturePath('globe', entity, geometry, 'after'),
      ).toString('base64'),
      before: readFileSync(
        capturePath('globe', entity, geometry, 'before'),
      ).toString('base64'),
      crops: BORDER_CROPS,
      scale: CROP_SCALE,
      tolerance: CHANNEL_TOLERANCE,
    },
  );
  writeFileSync(
    path.join(figuresDir, 'atlas-fast-load-border-crops.png'),
    Buffer.from(png, 'base64'),
  );
}

async function writeParityReceipt(browser) {
  const beforeMetaPath = path.join(outDir, 'before-meta.json');
  if (!existsSync(beforeMetaPath))
    throw new Error(`Run --phase before first (missing ${beforeMetaPath}).`);
  const page = await browser.newPage();
  let pairs;
  let everyLayerPairs;
  try {
    pairs = (await comparePairs(page, 'gate')).map((pair) => ({
      ...pair,
      pass: pair.fractionOverTolerance <= MAX_DIFFERENT_FRACTION,
    }));
    everyLayerPairs = await comparePairs(page, 'globe');
    await writeBorderCrops(page);
  } finally {
    await page.close();
  }
  const receipt = {
    generated_by: 'website/scripts/capture-atlas-fast-load.mjs',
    spec: 'docs/superpowers/specs/2026-10-07-atlas-mobile-fast-load-gcs-design.md §B.1',
    before: JSON.parse(readFileSync(beforeMetaPath, 'utf8')),
    after: JSON.parse(
      readFileSync(path.join(outDir, 'after-meta.json'), 'utf8'),
    ),
    viewport: VIEWPORT,
    fixed_time: FIXED_TIME.toISOString(),
    compared: `globe captures with page overlays hidden and the Natural Earth countries overlay off (layers=${GATE_LAYERS})`,
    channel_tolerance: CHANNEL_TOLERANCE,
    max_different_fraction: MAX_DIFFERENT_FRACTION,
    pairs,
    informational: {
      compared:
        'globe captures with page overlays hidden and every layer on (the default URL)',
      why_not_gated:
        '§B.6.9 draws the Natural Earth borders as a BufferPolylineCollection instead of GeoJsonDataSource entity polylines; their 1-px anti-aliasing differs',
      border_crops: 'docs/figures/atlas-fast-load-border-crops.png',
      pairs: everyLayerPairs,
    },
  };
  writeFileSync(
    path.join(figuresDir, 'atlas-fast-load-parity.receipt.json'),
    `${JSON.stringify(receipt, null, 2)}\n`,
  );
  const percent = (pair) => (pair.fractionOverTolerance * 100).toFixed(3);
  for (const pair of pairs)
    process.stdout.write(
      `${pair.pass ? 'ok  ' : 'FAIL'} ${pair.entity} ${pair.geometry}: ${percent(pair)}% of pixels differ by more than ${CHANNEL_TOLERANCE}/255 (countries off)\n`,
    );
  for (const pair of everyLayerPairs)
    process.stdout.write(
      `info ${pair.entity} ${pair.geometry}: ${percent(pair)}% with every layer on\n`,
    );
  return pairs.some((pair) => !pair.pass);
}

let server;
if (!suppliedBaseUrl) {
  server = spawn(
    process.execPath,
    [
      path.join(websiteRoot, 'node_modules', 'serve', 'build', 'main.js'),
      'dist',
      '-c',
      '../serve.json',
      '-l',
      'tcp://127.0.0.1:4323',
      '--no-clipboard',
    ],
    { cwd: websiteRoot, stdio: 'ignore' },
  );
  await waitForServer(`${baseUrl}/app/`);
}

let browser;
let failed = false;
try {
  browser = await chromium.launch(
    process.env.ATLAS_CAPTURE_HEADLESS === '1'
      ? { headless: true }
      : { channel: 'chrome', headless: false },
  );
  let renderer = 'unknown';
  for (const [, entity] of ENTITIES)
    for (const geometry of GEOMETRIES)
      for (const view of VIEWS)
        renderer = await capture(browser, entity, geometry, view);
  writeFileSync(
    path.join(outDir, `${phase}-meta.json`),
    `${JSON.stringify({ baseUrl, commit, renderer }, null, 2)}\n`,
  );
  for (const [short, entity] of ENTITIES)
    copyFileSync(
      capturePath('figure', entity, FIGURE_GEOMETRY),
      path.join(figuresDir, `atlas-fast-load-${phase}-${short}.png`),
    );
  if (phase === 'after') failed = await writeParityReceipt(browser);
  process.stdout.write(`Captured ${phase} figures in ${outDir}\n`);
} finally {
  await browser?.close();
  if (server && server.exitCode === null) {
    server.kill('SIGTERM');
    await Promise.race([
      once(server, 'exit'),
      new Promise((resolve) => setTimeout(resolve, 2_000)),
    ]);
  }
}
if (failed) process.exitCode = 1;
