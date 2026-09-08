import { expect, test, type Page } from '@playwright/test';

interface AtlasPerformanceMetrics {
  interactionFrameRate: number;
  longTasks: number[];
  renderer: string;
  warmArtifactMs: number;
  warmRenderMs: number;
  warmSelectMs: number;
}

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
  await page.route('https://tile.openstreetmap.org/**', (route) =>
    route.abort(),
  );
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  await page.evaluate(async () => {
    await Promise.all([
      fetch('/data/atlas/g6pd-deficiency.surface.json'),
      fetch('/data/atlas/g6pd-deficiency.observations.json'),
    ]);
  });
  await chooseAtlasMap(page, 'g6pd-deficiency');
  await expect(
    page.locator(
      '[data-atlas-active="g6pd-deficiency"][data-atlas-ready="true"]',
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

  expect.soft(metrics.warmArtifactMs).toBeLessThan(2_000);
  const softwareRenderer = /swiftshader|software/i.test(metrics.renderer);
  if (!softwareRenderer) {
    expect
      .soft(metrics.longTasks.filter((duration) => duration > 250))
      .toEqual([]);
    expect.soft(metrics.interactionFrameRate).toBeGreaterThanOrEqual(45);
  }
});
