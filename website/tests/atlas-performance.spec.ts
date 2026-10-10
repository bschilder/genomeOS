import {
  expect,
  test,
  type Page,
  type Request as PlaywrightRequest,
} from '@playwright/test';
import { assertProductionBuild } from './support/production-build';

interface AtlasPerformanceMetrics {
  interactionFrameRate: number;
  longTasks: number[];
  renderer: string;
  warmArtifactMs: number;
  warmRenderMs: number;
  warmSelectMs: number;
}

/** Any map other than the default HbS and the timed G6PD. */
const SWITCH_WARM_UP_ID = 'cyt-il-10-1082-g';

async function chooseAtlasMap(page: Page, id: string): Promise<void> {
  await page
    .getByRole('button', { name: /Select dataset\. Current dataset:/ })
    .click();
  await page.locator(`[role="option"][data-map-id="${id}"]`).click();
}

test('atlas meets the warm-switch and interaction budget', async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'The performance budget is measured once in desktop Chromium.',
  );
  test.setTimeout(90_000);

  await page.addInitScript(() => {
    const atlasWindow = window as Window & { __atlasLongTasks?: number[] };
    atlasWindow.__atlasLongTasks = [];
    new PerformanceObserver((list) => {
      atlasWindow.__atlasLongTasks?.push(
        ...list.getEntries().map(({ duration }) => duration),
      );
    }).observe({ entryTypes: ['longtask'] });
  });
  await assertProductionBuild(String(testInfo.project.use.baseURL));
  // CDP blocking keeps the HTTP cache on; page.route would disable it.
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setBlockedURLs', {
    urls: ['*tile.openstreetmap.org*'],
  });
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  const prewarmed = await page.evaluate(async () => {
    const text = document.getElementById('atlas-catalog')?.textContent;
    if (!text) throw new Error('The /app/ page has no inline catalog.');
    const catalog = JSON.parse(text) as {
      artifacts: {
        id: string;
        observations_url: string | null;
        web: { render: { url: string }; detail: { url: string } };
      }[];
    };
    const selected = catalog.artifacts[0];
    const preload = [
      ...document.querySelectorAll<HTMLLinkElement>(
        'link[rel="preload"][as="fetch"]',
      ),
    ].find((link) => link.href.endsWith(`/${selected.web.render.url}`));
    if (preload === undefined)
      throw new Error('No preload link for the selected render tier.');
    const base = preload.href.slice(
      0,
      preload.href.length - selected.web.render.url.length,
    );
    const g6pd = catalog.artifacts.find(({ id }) => id === 'g6pd-deficiency');
    if (!g6pd?.observations_url)
      throw new Error('G6PD deficiency is missing from the inline catalog.');
    const urls = [
      g6pd.web.render.url,
      g6pd.web.detail.url,
      g6pd.observations_url,
    ].map((key) => new URL(key, base).href);
    const responses = await Promise.all(urls.map((url) => fetch(url)));
    const failed = responses
      .filter((response) => !response.ok)
      .map((response) => `${response.status} ${response.url}`);
    if (failed.length > 0)
      throw new Error(`Pre-warm failed: ${failed.join(', ')}`);
    await Promise.all(responses.map((response) => response.arrayBuffer()));
    return urls;
  });
  // The timed switch must be G6PD's first: the provider keeps every surface it has handed out
  // (Plan ruling R29), so a return visit makes no request and the pre-warm would not count. An
  // untimed round trip through another map keeps the timed switch the session's second, as before.
  await chooseAtlasMap(page, SWITCH_WARM_UP_ID);
  await expect(
    page.locator(
      `[data-atlas-active="${SWITCH_WARM_UP_ID}"][data-atlas-ready="true"]`,
    ),
  ).toBeVisible({ timeout: 45_000 });
  await chooseAtlasMap(page, 'hbs-rs334');
  await expect(
    page.locator('[data-atlas-active="hbs-rs334"][data-atlas-ready="true"]'),
  ).toBeVisible({ timeout: 10_000 });
  await page.evaluate(() => {
    (window as Window & { __atlasLongTasks?: number[] }).__atlasLongTasks = [];
  });

  const canvas = page.locator('.atlas-scene canvas').first();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  const startX = box!.x + box!.width * 0.58;
  const startY = box!.y + box!.height * 0.52;
  const frameRatePromise = page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        let frames = 0;
        const started = performance.now();
        const sample = () => {
          frames += 1;
          const elapsed = performance.now() - started;
          if (elapsed >= 1_200) resolve((frames * 1_000) / elapsed);
          else requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      }),
  );
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 160, startY + 40, { steps: 20 });
  await page.mouse.up();
  await page.getByRole('button', { name: 'Zoom in' }).click();
  const interactionFrameRate = await frameRatePromise;
  await page.waitForTimeout(1_500);

  const switchRequests: string[] = [];
  const recordSwitchRequest = (request: PlaywrightRequest): void => {
    if (request.url().includes('g6pd-deficiency'))
      switchRequests.push(request.url());
  };
  page.on('request', recordSwitchRequest);
  const warmStarted = Date.now();
  await chooseAtlasMap(page, 'g6pd-deficiency');
  const warmSelected = Date.now();
  const warmRendering = Date.now();
  await expect(
    page.locator(
      '[data-atlas-active="g6pd-deficiency"][data-atlas-ready="true"]',
    ),
  ).toBeVisible({ timeout: 45_000 });
  const warmReady = Date.now();
  const warmArtifactMs = warmReady - warmStarted;
  page.off('request', recordSwitchRequest);
  // The timed switch fetched G6PD's tiers, and only ones the pre-warm already holds.
  expect(switchRequests.length).toBeGreaterThan(0);
  expect(switchRequests.filter((url) => !prewarmed.includes(url))).toEqual([]);

  const browserMetrics = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl');
    const debug = gl?.getExtension('WEBGL_debug_renderer_info');
    const renderer =
      gl && debug
        ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL))
        : 'unknown';
    return {
      longTasks:
        (window as Window & { __atlasLongTasks?: number[] }).__atlasLongTasks ??
        [],
      renderer,
    };
  });
  const metrics: AtlasPerformanceMetrics = {
    interactionFrameRate,
    longTasks: browserMetrics.longTasks,
    renderer: browserMetrics.renderer,
    warmArtifactMs,
    warmRenderMs: warmReady - warmRendering,
    warmSelectMs: warmSelected - warmStarted,
  };
  await testInfo.attach('atlas-performance.json', {
    body: JSON.stringify(metrics, null, 2),
    contentType: 'application/json',
  });
  console.info(`Atlas performance: ${JSON.stringify(metrics)}`);

  // Fast-load design §B.1 skips budget assertions on software renderers, the warm switch among
  // them (headless SwiftShader takes 8-12 s); run headed on a hardware GPU (`--headed`) to assert.
  const softwareRenderer = /swiftshader|software/i.test(metrics.renderer);
  if (softwareRenderer) {
    testInfo.annotations.push({
      type: 'budgets skipped',
      description: `software renderer: ${metrics.renderer}`,
    });
    return;
  }
  expect.soft(metrics.warmArtifactMs).toBeLessThan(2_000);
  expect
    .soft(metrics.longTasks.filter((duration) => duration > 250))
    .toEqual([]);
  expect.soft(metrics.interactionFrameRate).toBeGreaterThanOrEqual(45);
});
