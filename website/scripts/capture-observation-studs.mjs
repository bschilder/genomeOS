import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { chromium } from 'playwright';

import { installAtlasBrowserFixture } from '../tests/atlas-browser-fixture.ts';

const websiteRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const outputPath = path.resolve(
  websiteRoot,
  '..',
  'docs',
  'figures',
  'observation-studs.png',
);
const baseUrl = 'http://127.0.0.1:4323';

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

const server = spawn(
  process.execPath,
  [
    path.join(websiteRoot, 'node_modules', 'serve', 'build', 'main.js'),
    'dist',
    '-l',
    'tcp://127.0.0.1:4323',
    '--no-clipboard',
  ],
  { cwd: websiteRoot, stdio: 'ignore' },
);
await waitForServer(`${baseUrl}/app/`);

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    deviceScaleFactor: 1,
    viewport: { height: 1100, width: 1800 },
  });
  await installAtlasBrowserFixture(page, {
    focus: { lat: 8, lon: 0 },
    observationBudget: 48,
    surfaceBudget: 320,
    surfaceScope: 'regional',
  });
  const query = new URLSearchParams({
    elevation: 'true',
    entity: 'hbs-rs334',
    exaggeration: '2.4',
    geometry: 'triangles',
    heading: '12',
    height: '1400000',
    lat: '8',
    layers: 'surface,observations,support,context,countries',
    lon: '0',
    metric: 'post_mean',
    obsShape: 'hemisphere',
    obsSize: 'frequency',
    pointMax: '54',
    pointMin: '24',
    pitch: '-75',
    samplingAreas: 'false',
    version: 'v3/map-2026-08',
    view: 'globe',
  });
  await page.goto(`${baseUrl}/app/?${query}`);
  await page.locator('[data-atlas-ready="true"]').waitFor({
    timeout: 60_000,
  });
  await page.locator('summary', { hasText: 'Measured points' }).click();
  await page
    .getByLabel('Marker shape', { exact: true })
    .scrollIntoViewIfNeeded();
  await page.waitForTimeout(1_000);
  await page.screenshot({ path: outputPath });
  process.stdout.write(`Captured 1800×1100: ${outputPath}\n`);
} finally {
  await browser?.close();
  if (server.exitCode === null) {
    server.kill('SIGTERM');
    await Promise.race([
      once(server, 'exit'),
      new Promise((resolve) => setTimeout(resolve, 2_000)),
    ]);
  }
}
