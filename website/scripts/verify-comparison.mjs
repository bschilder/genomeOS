/** Real-artifact browser proof for Atlas design §11. No fixtures or data rewriting. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const [baseUrl, output] = process.argv.slice(2);
if (!baseUrl || !output)
  throw new Error('Supply base URL and PNG output path.');
const browser = await chromium.launch({ headless: true });
let page;
try {
  page = await browser.newPage({
    viewport: { width: 2560, height: 1440 },
    reducedMotion: 'reduce',
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const query = (entity) =>
    new URLSearchParams({
      entity,
      version: 'v3/map-2026-08',
      layers: 'surface,support,observations',
      view: 'globe',
      elevation: 'false',
      edges: 'false',
      geometry: 'hexagons',
      lon: '15',
      lat: '10',
      height: '18000000',
      heading: '0',
      pitch: '-90',
    }).toString();
  const url = new URL('/app/compare/', baseUrl);
  url.search = new URLSearchParams({
    left: query('hbs-rs334'),
    right: query('g6pd-deficiency'),
  });
  await page.goto(url.href);
  console.log('Loaded comparison route; waiting for both real artifacts.');
  const progress = setInterval(async () => {
    console.log(
      await page
        .locator(
          '[role=alert], [data-atlas-status-slot], .cesium-widget-errorPanel',
        )
        .allTextContents()
        .catch(() => []),
    );
  }, 10000);
  progress.unref();
  await page
    .locator('#comparison-left [data-atlas-ready="true"]')
    .waitFor({ timeout: 120000 });
  await page
    .locator('#comparison-right [data-atlas-ready="true"]')
    .waitFor({ timeout: 120000 });
  clearInterval(progress);
  console.log('Both real artifacts rendered.');
  await page.screenshot({
    path: output,
    fullPage: true,
    animations: 'disabled',
  });
  const read = () =>
    page.evaluate(() => {
      const params = new URLSearchParams(location.search);
      return Object.fromEntries(
        ['left', 'right'].map((side) => [
          side,
          Object.fromEntries(new URLSearchParams(params.get(side))),
        ]),
      );
    });
  for (const side of ['left', 'right'])
    assert.equal(
      await page
        .locator(`#comparison-${side}`)
        .getByRole('radio', { name: 'Posterior estimate', exact: true })
        .isChecked(),
      true,
    );
  const before = await read();
  await page
    .locator('#comparison-left')
    .getByRole('button', { name: 'Zoom in', exact: true })
    .click({ noWaitAfter: true, timeout: 60000 });
  await page.waitForFunction(
    () => {
      const params = new URLSearchParams(location.search);
      const a = new URLSearchParams(params.get('left')),
        b = new URLSearchParams(params.get('right'));
      return (
        Number(a.get('height')) < 18000000 &&
        Math.abs(Number(a.get('height')) - Number(b.get('height'))) < 2
      );
    },
    { timeout: 30000 },
  );
  const after = await read();
  for (const side of ['left', 'right']) {
    assert.equal(after[side].entity, before[side].entity);
    assert.equal(after[side].version, before[side].version);
    assert.equal(after[side].layers, before[side].layers);
  }
  await page
    .locator('#comparison-right')
    .getByRole('button', { name: 'Zoom out', exact: true })
    .click({ noWaitAfter: true, timeout: 60000 });
  await page.waitForFunction(
    (previousHeight) => {
      const params = new URLSearchParams(location.search);
      const a = new URLSearchParams(params.get('left')),
        b = new URLSearchParams(params.get('right'));
      return (
        Number(b.get('height')) > previousHeight &&
        Math.abs(Number(a.get('height')) - Number(b.get('height'))) < 2
      );
    },
    Number(after.right.height),
    { timeout: 30000 },
  );
  const duplicateIds = await page.evaluate(() => {
    const ids = [...document.querySelectorAll('[id]')].map((node) => node.id);
    return ids.filter((id, index) => ids.indexOf(id) !== index);
  });
  assert.deepEqual(duplicateIds, []);
  assert.deepEqual(errors, []);
  console.log(
    'PASS: zoom and independent panel identities/layers. Reloading shared URL.',
  );
  const sharedUrl = page.url();
  await page.reload();
  await page
    .locator('#comparison-left [data-atlas-ready="true"]')
    .waitFor({ timeout: 120000 });
  await page
    .locator('#comparison-right [data-atlas-ready="true"]')
    .waitFor({ timeout: 120000 });
  const restored = await read();
  assert.equal(restored.left.entity, 'hbs-rs334');
  assert.equal(restored.right.entity, 'g6pd-deficiency');
  assert.ok(sharedUrl.includes('version'));
  const invalid = new URL('/app/compare/', baseUrl);
  invalid.search = new URLSearchParams({
    left: query('missing-map'),
    right: query('g6pd-deficiency'),
  });
  await page.goto(invalid.href);
  await page.getByRole('alert').filter({ hasText: 'unavailable' }).waitFor();
  assert.equal(await page.locator('[data-atlas-explorer]').count(), 0);
  console.log(
    'PASS: real-data render, bidirectional zoom, independent identities/layers, unique controls, URL restore, unavailable-map refusal.',
  );
} catch (error) {
  if (page) {
    console.error(
      await page
        .locator('[role=alert], .cesium-widget-errorPanel')
        .allTextContents(),
    );
    await page
      .screenshot({ path: '/tmp/genomeos-comparison-failure.png' })
      .catch(() => {});
  }
  throw error;
} finally {
  await browser.close();
}
