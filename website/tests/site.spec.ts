import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { cellToLatLng } from 'h3-js';

import { installAtlasBrowserFixture } from './atlas-browser-fixture';

test.beforeEach(async ({ page }) => installAtlasBrowserFixture(page));
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

async function chooseAtlasMap(page: Page, id: string): Promise<void> {
  await page
    .getByRole('button', { name: /Select dataset\. Current dataset:/ })
    .click();
  await page.locator(`[role="option"][data-map-id="${id}"]`).click();
}

const topLevelRoutes = [
  '/',
  '/project/',
  '/working-groups/',
  '/contribute/',
  '/app/',
  '/docs/',
];

const brandAuditRoutes = [
  ...topLevelRoutes,
  '/docs/data-and-literature/',
  '/docs/deployment/',
  '/docs/issues-and-projects/',
  '/docs/local-development/',
  '/docs/modeling-and-validation/',
  '/docs/scientific-safeguards/',
  '/docs/system-overview/',
];

for (const route of topLevelRoutes) {
  test(`${route} has one primary heading and no serious axe violations`, async ({
    page,
  }) => {
    await page.goto(route);
    await expect(page.locator('h1')).toHaveCount(1);

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    const blocking = results.violations.filter(({ impact }) =>
      ['serious', 'critical'].includes(impact ?? ''),
    );
    expect(blocking).toEqual([]);
  });
}

test('primary navigation reaches working groups and exposes GitHub access', async ({
  page,
  isMobile,
}) => {
  await page.goto('/');
  const header = page.locator('.site-header');
  const launchAtlas = header.getByRole('link', { name: 'Launch Atlas' });
  await expect(launchAtlas).toHaveAttribute('href', '/app/');
  await expect(header.getByRole('link', { name: 'Preview' })).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'View genomeOS on GitHub' }).first(),
  ).toHaveAttribute('href', 'https://github.com/bschilder/genomeOS');

  if (isMobile) {
    await page.getByText('Menu', { exact: true }).click();
    await expect(launchAtlas).toBeVisible();
    await page
      .getByRole('navigation', { name: 'Mobile navigation' })
      .getByRole('link', { name: 'Working groups' })
      .click();
  } else {
    const headerLinks = await header.locator('a').allInnerTexts();
    expect(headerLinks.indexOf('Technical docs')).toBeLessThan(
      headerLinks.indexOf('Launch Atlas'),
    );
    expect(headerLinks.indexOf('Launch Atlas')).toBeLessThan(
      headerLinks.indexOf('GitHub'),
    );
    await launchAtlas.hover();
    await expect(launchAtlas.locator('svg')).toHaveCSS(
      'animation-name',
      'launch-rocket',
    );
    await page
      .getByRole('navigation', { name: 'Primary navigation' })
      .getByRole('link', { name: 'Working groups' })
      .click();
  }

  await expect(page).toHaveURL(/\/working-groups\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Choose the part of the problem',
  );
});

test('Atlas status replaces the launch action only on the Atlas page', async ({
  page,
}) => {
  await page.goto('/app/');
  const header = page.locator('.site-header');
  await expect(
    header.getByRole('link', { name: 'Launch Atlas', exact: true }),
  ).toHaveCount(0);
  await expect(header.getByLabel('Atlas status')).toContainText(
    /loading catalog|loading artifact|validating|rendering|Atlas ready/i,
  );

  await page.goto('/project/');
  await expect(header.getByLabel('Atlas status')).toHaveCount(0);
  await expect(
    header.getByRole('link', { name: 'Launch Atlas', exact: true }),
  ).toBeVisible();
});

test('Atlas status shows progress while a replacement dataset stays pending', async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.route('**/g6pd-deficiency.surface.json', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_800));
    await route.fallback();
  });
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  await chooseAtlasMap(page, 'g6pd-deficiency');
  const status = page.locator('[data-atlas-status-slot]');
  await expect(status).toContainText('Loading G6PD deficiency');
  const progress = status.locator('.atlas-status__meter');
  await expect(progress).toHaveAttribute('role', 'progressbar');
  await expect(progress).toHaveAttribute(
    'aria-label',
    'Atlas operation progress',
  );
  await expect(progress).toBeVisible();
  await expect(page.locator('[data-atlas-active="hbs-rs334"]')).toBeVisible();
  await expect(
    page.locator('[data-atlas-active="g6pd-deficiency"]'),
  ).toHaveAttribute('data-atlas-ready', 'true', { timeout: 45_000 });
});

test('navigation stays visible and condenses after scrolling', async ({
  page,
  isMobile,
}) => {
  await page.goto('/');
  const header = page.locator('.site-header');
  const initial = await header.boundingBox();
  expect(initial).not.toBeNull();

  await page.evaluate(() => window.scrollTo(0, 900));
  await expect(header).toHaveClass(/site-header--compact/);

  const scrolled = await header.boundingBox();
  expect(scrolled).not.toBeNull();
  expect(Math.abs(scrolled!.y)).toBeLessThanOrEqual(1);
  expect(scrolled!.height).toBeLessThan(initial!.height);

  const activeNavigationText = isMobile
    ? page.locator('.mobile-nav summary')
    : page
        .getByRole('navigation', { name: 'Primary navigation' })
        .locator('a')
        .first();
  const navFontSize = await activeNavigationText.evaluate((element) =>
    Number.parseFloat(getComputedStyle(element).fontSize),
  );
  expect(navFontSize).toBeGreaterThanOrEqual(16);
});

test('visible project names use the wordmark typography', async ({ page }) => {
  for (const route of brandAuditRoutes) {
    await page.goto(route);
    const unstyled = await page.evaluate(() => {
      const failures: string[] = [];
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
      );
      let node = walker.nextNode();
      while (node) {
        if (node.nodeValue?.includes('genomeOS')) {
          const parent = node.parentElement;
          const nonVisual = parent?.closest('script, style, title, code, pre');
          if (
            parent &&
            !nonVisual &&
            getComputedStyle(parent).display !== 'none'
          ) {
            const wordmark = parent.closest<HTMLElement>(
              '.brand-name, .wordmark, .site-title',
            );
            if (!wordmark) {
              failures.push(
                `${parent.tagName.toLowerCase()}: missing wordmark`,
              );
            } else if (
              !getComputedStyle(wordmark).fontFamily.includes('Raleway')
            ) {
              failures.push(`${parent.tagName.toLowerCase()}: wrong font`);
            }
          }
        }
        node = walker.nextNode();
      }
      return failures;
    });
    expect(unstyled, `${route} has unstyled genomeOS text`).toEqual([]);
  }
});

test('project page labels all three capability states', async ({ page }) => {
  await page.goto('/project/');
  await expect(
    page.getByRole('heading', { name: 'Available now' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'In active development' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Future exploration' }),
  ).toBeVisible();
});

test('working-group page links each group to issue work', async ({ page }) => {
  await page.goto('/working-groups/');
  await expect(
    page.getByRole('link', { name: 'Browse matching issues' }),
  ).toHaveCount(3);
  await expect(page.getByText('Group forming')).toHaveCount(3);
});

test('mobile navigation is a keyboard-operable disclosure', async ({
  page,
  isMobile,
}) => {
  test.skip(
    !isMobile,
    'mobile navigation is only rendered as the active control on narrow screens',
  );
  await page.goto('/');
  const menu = page.getByText('Menu', { exact: true });
  await menu.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('navigation', { name: 'Mobile navigation' }),
  ).toBeVisible();
  await expect(
    page
      .getByRole('navigation', { name: 'Mobile navigation' })
      .getByRole('link', { name: 'Technical docs' }),
  ).toBeVisible();
});

test('404 page offers three recovery routes', async ({ page }) => {
  await page.goto('/404.html');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'That route is outside the atlas.',
  );
  const recovery = page.locator('main');
  await expect(recovery.getByRole('link', { name: /Home/ })).toBeVisible();
  await expect(
    recovery.getByRole('link', { name: /Contribute/ }),
  ).toBeVisible();
  await expect(
    recovery.getByRole('link', { name: /Technical docs/ }),
  ).toBeVisible();
});

for (const route of topLevelRoutes) {
  test(`${route} does not create horizontal page scrolling`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    await page.goto(route);

    const hasHorizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
}

test('reduced-motion preferences disable decorative hero movement', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');

  const animationName = await page
    .locator('.hero__image')
    .evaluate((element) => getComputedStyle(element).animationName);
  expect(animationName).toBe('none');

  const header = page.locator('.site-header');
  await page.evaluate(() => window.scrollTo(0, 900));
  await expect(header).not.toHaveClass(/site-header--compact/);
  expect(Math.abs((await header.boundingBox())!.y)).toBeLessThanOrEqual(1);
});

test('public typography keeps body and supporting text comfortably large', async ({
  page,
}) => {
  await page.goto('/');

  const typeSizes = await page.evaluate(() => {
    const selectors = [
      'body',
      '.desktop-nav a',
      '.section-kicker',
      '.site-footer p',
      '.mission-copy p',
    ];
    return Object.fromEntries(
      selectors.map((selector) => [
        selector,
        Number.parseFloat(
          getComputedStyle(document.querySelector(selector)!).fontSize,
        ),
      ]),
    );
  });

  expect(typeSizes.body).toBeGreaterThanOrEqual(19);
  for (const [selector, size] of Object.entries(typeSizes)) {
    if (selector !== 'body') expect(size).toBeGreaterThanOrEqual(16);
  }
});

test('metric digits use a common height and baseline', async ({ page }) => {
  await page.goto('/');

  const numericStyle = await page
    .locator('.metric data')
    .first()
    .evaluate((element) => ({
      family: getComputedStyle(element).fontFamily,
      variant: getComputedStyle(element).fontVariantNumeric,
    }));
  expect(numericStyle.family).toContain('Figtree');
  expect(numericStyle.variant).toContain('lining-nums');
  expect(numericStyle.variant).toContain('tabular-nums');
});

test('multi-scale illustrations load with accessible descriptions', async ({
  page,
}) => {
  await page.goto('/project/');
  const images = page.locator('.vision-card img');
  await expect(images).toHaveCount(3);
  for (const image of await images.all()) {
    await image.scrollIntoViewIfNeeded();
    await expect(image).toHaveJSProperty('complete', true);
    expect(await image.getAttribute('alt')).not.toBe('');
    expect(
      await image.evaluate((element: HTMLImageElement) => element.naturalWidth),
    ).toBe(1536);
  }
});

test('introduction pages avoid unexplained internal milestone codes', async ({
  page,
}) => {
  for (const route of ['/', '/project/', '/app/']) {
    await page.goto(route);
    const text = await page.locator('main').innerText();
    expect(text).not.toMatch(/\bP[0-9]+\b/);
  }
});

test('application cards reveal on scroll and respond to hover', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'hover movement is a pointer interaction');
  await page.goto('/');

  const card = page.locator('.application-card').first();
  await card.scrollIntoViewIfNeeded();
  await expect(card).toHaveClass(/is-visible/);
  const restingTransform = await card.evaluate(
    (element) => getComputedStyle(element).transform,
  );
  await card.hover();
  await page.waitForTimeout(250);
  const hoverTransform = await card.evaluate(
    (element) => getComputedStyle(element).transform,
  );
  expect(hoverTransform).not.toBe(restingTransform);
});

test('explorer changes entity, metric, context, and elevation', async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  const layers = page.getByRole('group', { name: 'Layers' });
  await expect(
    layers.getByRole('checkbox', { name: 'Observation radii', exact: true }),
  ).toBeVisible();
  await expect(
    layers.getByRole('checkbox', { name: 'Cell outlines', exact: true }),
  ).toBeChecked();
  await expect(
    layers.locator('.atlas-layer-row .atlas-info-tip__trigger'),
  ).toHaveCount(7);
  const countryContext = layers.getByRole('checkbox', {
    name: 'Country outlines',
    exact: true,
  });
  await expect(countryContext).toBeChecked();
  await countryContext.uncheck();
  await expect(page).toHaveURL(/layers=(?:(?!countries)[^&])*(?:&|$)/);
  await expect(
    layers.getByRole('checkbox', { name: 'Geography', exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole('application', { name: 'genomeOS globe explorer' }),
  ).toBeVisible();
  await expect(page.locator('.atlas-brand')).toHaveCount(0);
  await expect(
    page
      .getByRole('complementary', { name: 'Explorer controls' })
      .locator('.atlas-kicker'),
  ).toHaveText('genomeOS Atlas');
  await chooseAtlasMap(page, 'g6pd-deficiency');
  await page.getByRole('radio', { name: 'Uncertainty' }).check();
  await page
    .getByRole('checkbox', { name: 'Geography', exact: true })
    .uncheck();
  await page.locator('summary').filter({ hasText: /^Map$/ }).click();
  await page
    .locator('summary')
    .filter({ hasText: /^Inferred surface$/ })
    .click();
  const surfacePalette = page.getByLabel('Surface palette', { exact: true });
  await expect(surfacePalette).toHaveValue('plasma');
  await surfacePalette.selectOption('cividis');
  await expect(page).toHaveURL(/palette=cividis/);
  await page.getByRole('radio', { name: 'Posterior estimate' }).check();
  await expect(surfacePalette).toHaveValue('rainbow');
  await expect(page).not.toHaveURL(/palette=cividis/);
  await page.getByRole('radio', { name: 'Uncertainty' }).check();
  await expect(surfacePalette).toHaveValue('plasma');
  await page.getByRole('radio', { name: 'Map' }).check();
  await page.getByLabel('Statistical elevation', { exact: true }).check();
  await expect(
    page.locator('[data-atlas-active="g6pd-deficiency"]'),
  ).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole('radio', { name: 'Perspective' })).toBeChecked();
  await expect(page).toHaveURL(/entity=g6pd-deficiency/);
  await expect(page).toHaveURL(/metric=post_sd/);
});

test('explorer switches among globe, map, and perspective views', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 30_000,
  });
  await page.locator('summary').filter({ hasText: /^Map$/ }).click();
  await page
    .locator('summary')
    .filter({ hasText: /^Inferred surface$/ })
    .click();

  for (const view of ['Map', 'Perspective', 'Globe']) {
    const control = page.getByRole('radio', { name: view });
    await control.check();
    await expect(control).toBeChecked();
  }
  await expect(page).toHaveURL(/view=globe/);
});

test('explorer restores a complete shareable URL', async ({ page }) => {
  test.setTimeout(90_000);
  const servedCatalog = await page.request.get('/data/atlas/catalog.json');
  expect(servedCatalog.ok()).toBe(true);
  const servedArtifacts = (await servedCatalog.json()) as {
    artifacts: { id: string; model_version: string }[];
  };
  expect(servedArtifacts.artifacts).toHaveLength(30);
  expect(servedArtifacts.artifacts).toContainEqual(
    expect.objectContaining({
      id: 'g6pd-deficiency',
      model_version: 'v3',
    }),
  );
  const query = new URLSearchParams({
    elevation: 'true',
    entity: 'g6pd-deficiency',
    exaggeration: '2.5',
    heading: '12',
    height: '4200000',
    lat: '1',
    layers: 'surface,support',
    lon: '9',
    metric: 'post_sd',
    pitch: '-55',
    version: 'v3/map-2026-08',
    view: 'perspective',
  });
  await page.goto(`/app/?${query}`);
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  await expect(
    page.getByRole('button', { name: /Select dataset\. Current dataset:/ }),
  ).toContainText('G6PD deficiency');
  await expect(page.getByRole('radio', { name: 'Uncertainty' })).toBeChecked();
  await page.locator('summary').filter({ hasText: /^Map$/ }).click();
  await page
    .locator('summary')
    .filter({ hasText: /^Inferred surface$/ })
    .click();
  await expect(page.getByRole('radio', { name: 'Perspective' })).toBeChecked();
  await expect(
    page.getByLabel('Statistical elevation', { exact: true }),
  ).toBeChecked();
  await expect(page.getByLabel('Height exaggeration')).toHaveValue('2.5');
  await expect(
    page.getByRole('checkbox', { name: 'Measured points', exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole('checkbox', { name: 'Geography', exact: true }),
  ).not.toBeChecked();
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 30_000,
  });
  await expect(page).toHaveURL(/lon=9(?:&|%|$)/);
  await expect(page).toHaveURL(/lat=1(?:&|%|$)/);
  await expect(page).toHaveURL(/height=4200000(?:&|%|$)/);
});

test('explorer recovers a stale version link for an available map', async ({
  page,
}) => {
  test.setTimeout(60_000);
  const servedCatalog = await page.request.get('/data/atlas/catalog.json');
  expect(servedCatalog.ok()).toBe(true);
  const servedArtifacts = (await servedCatalog.json()) as {
    artifacts: {
      data_version: string;
      id: string;
      model_version: string;
    }[];
  };
  const current = servedArtifacts.artifacts.find(
    ({ id }) => id === 'hbs-rs334',
  );
  expect(current).toBeDefined();

  await page.goto(
    '/app/?entity=hbs-rs334&version=v1%2Fmap-2026-08&metric=post_mean',
  );

  await expect
    .poll(() => new URL(page.url()).searchParams.get('version'), {
      timeout: 45_000,
    })
    .toBe(`${current!.model_version}/${current!.data_version}`);
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.locator('.atlas-error')).toHaveCount(0);
  await expect(
    page.getByText('Corrected invalid link fields: version.', { exact: false }),
  ).toBeVisible();
});

test('explorer exposes the full catalog and shareable appearance controls', async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.locator('[data-atlas-status-slot]')).toContainText(
    'Atlas ready',
  );
  await expect(page.locator('.atlas-explorer > .atlas-status')).toHaveCount(0);

  const entity = page.getByRole('button', {
    name: /Select dataset\. Current dataset:/,
  });
  await entity.click();
  await expect(
    page
      .getByRole('listbox', { name: 'Available genetic maps' })
      .getByRole('option'),
  ).toHaveCount(30);
  await page.keyboard.press('Escape');
  const completeSurface = await page.request.get(
    '/data/atlas/hbs-rs334.surface.json',
  );
  expect(completeSurface.ok()).toBe(true);
  expect(
    ((await completeSurface.json()) as { cells: unknown[] }).cells,
  ).toHaveLength(77_844);
  const completeObservations = await page.request.get(
    '/data/atlas/hbs-rs334.observations.json',
  );
  expect(completeObservations.ok()).toBe(true);
  expect(
    ((await completeObservations.json()) as { observations: unknown[] })
      .observations,
  ).toHaveLength(1_071);

  const mapHelp = page.getByRole('button', { name: 'About map selection' });
  await mapHelp.click();
  await expect(
    page.getByRole('tooltip').filter({ hasText: 'Choose a versioned' }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('tooltip').filter({ hasText: 'Choose a versioned' }),
  ).toHaveCount(0);
  await expect(mapHelp).toBeFocused();

  await expect(page.getByText('Map appearance', { exact: true })).toHaveCount(
    0,
  );
  await page.locator('summary').filter({ hasText: /^Map$/ }).click();
  const earthStyleButton = page.getByRole('button', {
    name: 'Choose basemap and terrain',
  });
  await expect(earthStyleButton).toBeVisible();
  const basemapOpacity = page.getByLabel(/Basemap opacity/);
  const basemapBrightness = page.getByLabel(/Basemap brightness/);
  const dayNight = page.getByRole('checkbox', {
    name: 'Day/night lighting',
    exact: true,
  });
  await expect(basemapOpacity).toHaveAttribute('min', '0');
  await expect(basemapOpacity).toHaveAttribute('max', '100');
  await expect(basemapBrightness).toHaveAttribute('min', '0');
  await expect(basemapBrightness).toHaveAttribute('max', '100');
  await expect(basemapOpacity).toHaveValue('100');
  await expect(basemapBrightness).toHaveValue('50');
  const oceanColor = page.getByLabel('Ocean color', { exact: true });
  await expect(oceanColor).toHaveValue('#071b35');
  await expect(dayNight).toBeChecked();
  await basemapOpacity.fill('82');
  await basemapBrightness.fill('70');
  await oceanColor.fill('#225588');
  await dayNight.uncheck();
  await expect(
    page.getByLabel('Surface palette', { exact: true }),
  ).not.toBeVisible();
  await page
    .locator('summary')
    .filter({ hasText: /^Inferred surface$/ })
    .click();
  await page
    .getByLabel('Surface palette', { exact: true })
    .selectOption('golden');
  await page.getByLabel(/Surface opacity/).fill('0.65');
  const earthOpacity = page.locator('#atlas-earth-opacity');
  await expect(earthOpacity).toHaveValue('1');
  await earthOpacity.fill('0.76');
  await expect(
    page
      .getByLabel('Surface geometry', { exact: true })
      .locator('option[value="hexagons"]'),
  ).toHaveText('Flat hexagons');
  await expect(
    page
      .getByLabel('Surface geometry', { exact: true })
      .locator('option[value="honmoon"]'),
  ).toHaveText('Honmoon');
  await expect(
    page
      .getByLabel('Surface geometry', { exact: true })
      .locator('option[value="honmoon-fill"]'),
  ).toHaveText('Honmoon (fill)');
  await page
    .getByLabel('Surface geometry', { exact: true })
    .selectOption('honmoon');
  await expect(page).toHaveURL(/geometry=honmoon/);
  await page
    .getByLabel('Surface geometry', { exact: true })
    .selectOption('honmoon-fill');
  await page
    .getByRole('checkbox', { name: 'Cell outlines', exact: true })
    .check();
  await page
    .getByRole('combobox', { name: 'Edge color', exact: true })
    .selectOption('fixed');
  await page.getByLabel('Fixed edge color', { exact: true }).fill('#ff3366');
  await page.getByRole('radio', { name: 'Map' }).check();

  await page.locator('summary', { hasText: 'Measured points' }).click();
  await page
    .getByLabel('Marker shape', { exact: true })
    .selectOption({ label: 'Domes' });
  await expect(page).toHaveURL(/obsShape=hemisphere/);
  await page.getByLabel('Marker shape', { exact: true }).selectOption('pin');
  await page
    .getByLabel('Marker color', { exact: true })
    .selectOption('gradient');
  const markerGradient = page.getByRole('group', {
    name: 'Marker gradient colors',
  });
  await expect(markerGradient.getByText('Low', { exact: true })).toBeVisible();
  await expect(
    markerGradient.getByText('Midpoint', { exact: true }),
  ).toBeVisible();
  await expect(markerGradient.getByText('High', { exact: true })).toBeVisible();
  await page.getByLabel('Low gradient color').fill('#112233');
  await page.getByLabel(/Marker opacity/).fill('0.62');
  await page.getByLabel('Marker size', { exact: true }).selectOption('an');
  const sizeRanges = page
    .getByRole('group', { name: 'Marker size range' })
    .locator('input[type="range"]');
  await expect(sizeRanges.nth(0)).toHaveAttribute('min', '12');
  await expect(sizeRanges.nth(0)).toHaveAttribute('max', '96');
  await expect(sizeRanges.nth(1)).toHaveAttribute('min', '12');
  await expect(sizeRanges.nth(1)).toHaveAttribute('max', '96');
  await sizeRanges.nth(0).fill('72');
  await expect(sizeRanges.nth(1)).toHaveValue('72');
  await sizeRanges.nth(1).fill('36');
  await expect(sizeRanges.nth(0)).toHaveValue('36');
  const samplingHelp = page.getByRole('button', {
    name: 'About observation radii',
  });
  await samplingHelp.scrollIntoViewIfNeeded();
  await samplingHelp.click();
  const samplingTooltip = page.getByRole('tooltip');
  await expect(samplingTooltip).toBeVisible();
  const tooltipBox = await samplingTooltip.boundingBox();
  const viewport = page.viewportSize();
  expect(tooltipBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(tooltipBox!.x).toBeGreaterThanOrEqual(0);
  expect(tooltipBox!.y).toBeGreaterThanOrEqual(0);
  expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(
    viewport!.width,
  );
  expect(tooltipBox!.y + tooltipBox!.height).toBeLessThanOrEqual(
    viewport!.height,
  );
  await page.keyboard.press('Escape');
  await page
    .getByLabel('Observation radius color', { exact: true })
    .fill('#44ccaa');
  await page
    .getByRole('checkbox', { name: 'Observation radii', exact: true })
    .uncheck();

  await expect(page).toHaveURL(/palette=golden/);
  await expect(page).toHaveURL(/basemapOpacity=0.82/);
  await expect(page).toHaveURL(/basemapBrightness=0.7/);
  await expect(page).toHaveURL(/oceanColor=%23225588/);
  await expect(page).toHaveURL(/dayNight=false/);
  await expect(page).toHaveURL(/opacity=0.65/);
  await expect(page).toHaveURL(/earthOpacity=0.76/);
  await expect(page).toHaveURL(/geometry=honmoon-fill/);
  await expect(page).toHaveURL(/edges=true/);
  await expect(page).toHaveURL(/edgeColor=fixed/);
  await expect(page).toHaveURL(/edgeFixed=%23ff3366/);
  await expect(page).toHaveURL(/view=map/);
  await expect(page).toHaveURL(/obsShape=pin/);
  await expect(page).toHaveURL(/obsColor=gradient/);
  await expect(page).toHaveURL(/obsLow=%23112233/);
  await expect(page).toHaveURL(/obsOpacity=0.62/);
  await expect(page).toHaveURL(/obsSize=an/);
  await expect(page).toHaveURL(/samplingAreas=false/);
  await expect(page).toHaveURL(/samplingColor=%2344ccaa/);

  await page.getByText('Keys', { exact: true }).click();
  await expect(page.getByText(/arrows or WASD to pan/)).toBeVisible();
});

test('explorer groups and explains maps before selection', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  await page.getByRole('button', { name: /Select dataset/i }).click();
  const picker = page.getByRole('dialog', { name: 'Select dataset' });
  await expect(picker).toBeVisible();
  await expect(
    picker.getByRole('heading', { name: 'Red blood cell disorders' }),
  ).toBeVisible();
  await expect(
    picker.getByRole('heading', { name: 'Natural killer-cell receptors' }),
  ).toBeVisible();
  await expect(picker).toContainText('Hemoglobin S');
  await expect(picker).toContainText('This map shows');

  const search = picker.getByRole('searchbox', { name: 'Search maps' });
  await search.press('Tab');
  await expect(picker.getByRole('option').first()).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(picker.getByRole('option').nth(1)).toBeFocused();
  await search.focus();
  await search.fill('allopurinol');
  await expect(
    picker.getByRole('option', { name: /HLA-B\*58:01/ }),
  ).toBeVisible();
  await picker.getByRole('option', { name: /HLA-B\*58:01/ }).click();

  await expect(picker).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: /Select dataset/i }),
  ).toContainText('HLA class I');
  await expect(page).toHaveURL(/entity=hla-b-58-01/);
});

test('explorer offers the full basemap and terrain gallery', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  await page.locator('summary').filter({ hasText: /^Map$/ }).click();
  await page
    .getByRole('button', { name: 'Choose basemap and terrain' })
    .click();
  const picker = page.getByRole('dialog', { name: 'Basemap and terrain' });
  await expect(picker).toBeVisible();
  await expect(picker.getByRole('radio', { name: /basemap/i })).toHaveCount(22);
  await expect(picker.getByRole('radio', { name: /terrain/i })).toHaveCount(2);
  const basemapTile = await picker
    .getByRole('radio', { name: 'ArcGIS World Imagery basemap' })
    .boundingBox();
  const terrainTile = await picker
    .getByRole('radio', { name: 'Smooth Globe terrain' })
    .boundingBox();
  expect(basemapTile).not.toBeNull();
  expect(terrainTile).not.toBeNull();
  expect(Math.abs(terrainTile!.width - basemapTile!.width)).toBeLessThanOrEqual(
    1,
  );
  expect(
    Math.abs(terrainTile!.height - basemapTile!.height),
  ).toBeLessThanOrEqual(1);
  await expect(
    picker.getByRole('radio', { name: 'Bing Maps Roads basemap' }),
  ).toHaveAttribute('aria-disabled', 'true');

  await picker.getByRole('radio', { name: 'Blue Marble basemap' }).hover();
  await expect(
    picker.getByRole('tooltip').filter({ hasText: 'NASA' }),
  ).toBeVisible();
  await picker.getByRole('radio', { name: 'OpenStreetMap basemap' }).click();
  await expect(picker).toHaveCount(0);
  await expect(page).toHaveURL(/basemap=openstreetmap/);
});

test('left control sections expand and collapse with motion', async ({
  page,
}) => {
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  const sheet = page
    .locator('details.atlas-control-sheet')
    .filter({ has: page.locator('summary', { hasText: /^Map$/ }) });
  const transition = await sheet.evaluate((element) => {
    const style = getComputedStyle(element, '::details-content');
    return {
      duration: style.transitionDuration,
      property: style.transitionProperty,
    };
  });

  expect(transition.property).toContain('block-size');
  expect(transition.duration).not.toBe('0s');
  await sheet.locator('summary').click();
  await expect(sheet).toHaveAttribute('open', '');
  await sheet.locator('summary').click();
  await expect(sheet).not.toHaveAttribute('open', '');
});

test('explorer provides versioned downloads and gated external lookups', async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.goto('/app/');
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });

  await page.locator('.atlas-downloads > summary').click();
  await expect(
    page.getByRole('link', { name: 'Artifact manifest' }),
  ).toHaveAttribute('href', '/data/atlas/hbs-rs334.manifest.json');
  await expect(
    page.getByRole('link', { name: 'Measured observations' }),
  ).toHaveAttribute('href', '/data/atlas/hbs-rs334.observations.json');
  await expect(
    page.getByRole('link', { name: 'Inferred surface' }),
  ).toHaveAttribute('href', '/data/atlas/hbs-rs334.surface.json');

  await page.getByRole('button', { name: 'More info' }).click();
  const externalPanel = page.getByRole('complementary', {
    name: 'External variant information',
  });
  await expect(externalPanel).toBeVisible();
  await expect(
    page.locator('.atlas-right-rail').filter({ has: externalPanel }),
  ).toBeVisible();
  await externalPanel.getByRole('button', { name: 'gnomAD' }).click();
  await expect(
    page.getByText('chr11-5227002-T-A', { exact: true }),
  ).toBeVisible();
  await expect(externalPanel).toContainText('Allele frequency');
  await expect(externalPanel).toContainText('Homozygous alternate');
  await expect(externalPanel).toContainText('Canonical transcript');
  await expect(
    externalPanel.getByRole('button', { name: /Genetic ancestry.*10 groups/ }),
  ).toBeVisible();
  await externalPanel
    .getByRole('button', { name: /Genetic ancestry.*10 groups/ })
    .click();
  await expect(
    externalPanel.getByRole('heading', {
      name: 'Genetic ancestry group frequencies',
    }),
  ).toBeVisible();
  await expect(
    externalPanel.getByRole('row', { name: /African\/African American/ }),
  ).toContainText('4.9487%');
  await expect(externalPanel).toContainText('not geographic populations');
  await externalPanel
    .getByRole('button', { name: 'Back to variant overview' })
    .click();

  await externalPanel
    .getByRole('button', { name: /Genomic constraint.*1 kb/ })
    .click();
  await expect(
    externalPanel.getByRole('heading', {
      name: 'Genomic constraint of surrounding 1 kb region',
    }),
  ).toBeVisible();
  await expect(
    externalPanel.getByRole('img', {
      name: /Z score -0\.56.*-10.*10/,
    }),
  ).toBeVisible();
  await expect(externalPanel).toContainText('144.26');
  await expect(externalPanel).toContainText('gnomAD v3.1.2');
  await externalPanel
    .getByRole('button', { name: 'Back to variant overview' })
    .click();

  await externalPanel
    .getByRole('button', { name: /ClinVar.*18 conditions/ })
    .click();
  await expect(
    externalPanel.getByRole('heading', { name: 'ClinVar conditions' }),
  ).toBeVisible();
  await expect(externalPanel).toContainText('71 submissions');
  await expect(
    externalPanel.getByRole('link', { name: 'Hb SS disease' }),
  ).toHaveAttribute('href', 'https://www.ncbi.nlm.nih.gov/medgen/C0002895/');
  await expect(externalPanel).toContainText('not a diagnosis');
  await expect(
    page.getByRole('link', { name: /Open this variant in gnomAD/ }),
  ).toHaveAttribute('target', '_blank');
  const downloadPromise = page.waitForEvent('download');
  await externalPanel
    .getByRole('button', { name: 'Download displayed data' })
    .click();
  expect((await downloadPromise).suggestedFilename()).toBe(
    'chr11-5227002-T-A.gnomad.gnomad_r4.json',
  );
  await externalPanel.getByRole('button', { name: 'dbSNP' }).click();
  await expect(
    externalPanel.getByRole('heading', { name: 'rs334', exact: true }),
  ).toBeVisible();
  await expect(externalPanel).toContainText('SPDI representation');
  await expect(
    page.getByRole('link', { name: /Open this record in dbSNP/ }),
  ).toHaveAttribute('target', '_blank');
  await page.keyboard.press('Escape');
  await expect(externalPanel).toHaveCount(0);

  await chooseAtlasMap(page, 'g6pd-deficiency');
  await expect(
    page.locator('[data-atlas-active="g6pd-deficiency"]'),
  ).toHaveAttribute('data-atlas-ready', 'true', { timeout: 45_000 });
  await expect(page.getByRole('button', { name: 'More info' })).toBeDisabled();
  await expect(externalPanel).toHaveCount(0);
});

test('explorer previews and opens separate surface and observation inspectors', async ({
  page,
  isMobile,
}) => {
  test.skip(
    isMobile,
    'coordinate-sensitive canvas picking is covered in the desktop project',
  );
  test.setTimeout(120_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const query = new URLSearchParams({
    heading: '0',
    height: '1000000',
    lat: '40.4407',
    lon: '-3.7201',
    pitch: '-90',
  });
  await page.goto(`/app/?${query}`);
  await expect(page.locator('[data-atlas-ready="true"]')).toBeVisible({
    timeout: 45_000,
  });
  const canvas = page.locator('.atlas-scene canvas').first();
  const hoverPreview = page.locator('.atlas-hover-preview');
  const hoverNearCenter = async () => {
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    for (const [offsetX, offsetY] of [
      [0, 0],
      [-18, 0],
      [18, 0],
      [0, -18],
      [0, 18],
      [-18, -18],
      [18, -18],
      [-18, 18],
      [18, 18],
    ]) {
      await page.mouse.move(
        box!.x + box!.width / 2 + offsetX,
        box!.y + box!.height / 2 + offsetY,
      );
      if (await hoverPreview.isVisible()) return;
    }
  };
  const clickNearCenter = async (inspector: Locator) => {
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    for (const [offsetX, offsetY] of [
      [0, 0],
      [-18, 0],
      [18, 0],
      [0, -18],
      [0, 18],
      [-18, -18],
      [18, -18],
      [-18, 18],
      [18, 18],
    ]) {
      await page.mouse.click(
        box!.x + box!.width / 2 + offsetX,
        box!.y + box!.height / 2 + offsetY,
      );
      if (await inspector.isVisible()) return;
    }
  };

  await page
    .getByRole('checkbox', { name: 'Measured points', exact: true })
    .uncheck();
  await page
    .getByRole('checkbox', { name: 'Observation radii', exact: true })
    .uncheck();
  await expect
    .poll(() => new URL(page.url()).searchParams.get('layers'))
    .not.toContain('observations');
  const surfaceInspector = page.getByRole('complementary', {
    name: 'Selected map cell',
  });
  await hoverNearCenter();
  await expect(hoverPreview).toContainText('Modeled estimate');
  await expect(hoverPreview).toContainText('Posterior');
  await expect(hoverPreview).toContainText('95% credible range');
  await expect(hoverPreview).toContainText('Uncertainty');
  await clickNearCenter(surfaceInspector);
  await expect(surfaceInspector).toBeVisible();
  await expect(hoverPreview).toBeVisible();
  const cellId = await surfaceInspector
    .locator('dt', { hasText: 'Cell ID' })
    .locator('..')
    .locator('dd')
    .innerText();
  const [centroidLat, centroidLon] = cellToLatLng(cellId);
  const mapOptions = surfaceInspector.getByRole('button', {
    name: 'Choose how to open this cell in Google Maps',
  });
  const triggerCoordinates = mapOptions.locator(
    '.atlas-centroid-link__coordinates span',
  );
  await expect(triggerCoordinates).toHaveCount(2);
  await expect(triggerCoordinates.nth(0)).toHaveText(
    `${centroidLon.toFixed(4)}° lon`,
  );
  await expect(triggerCoordinates.nth(1)).toHaveText(
    `${centroidLat.toFixed(4)}° lat`,
  );
  await mapOptions.click();
  const centroidLink = surfaceInspector.getByRole('link', {
    name: 'Centroid',
  });
  await expect(centroidLink).toHaveAttribute('target', '_blank');
  await expect(centroidLink).toHaveAttribute(
    'href',
    /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=/,
  );
  await expect(
    centroidLink.locator('.atlas-centroid-link__coordinates span'),
  ).toHaveCount(2);
  const polygonLink = surfaceInspector.getByRole('link', {
    name: 'Polygon',
  });
  await expect(polygonLink).toHaveAttribute('target', '_blank');
  await expect(polygonLink).toHaveAttribute(
    'href',
    /\/app\/polygon\/\?cell=[0-9a-f]{15}$/,
  );
  await expect(mapOptions.locator('[data-google-maps-icon]')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(surfaceInspector).toHaveCount(0);
  await expect(hoverPreview).toHaveCount(0);

  await page
    .getByRole('checkbox', { name: 'Measured points', exact: true })
    .check();
  await page
    .getByRole('checkbox', { name: 'Observation radii', exact: true })
    .check();
  await page.locator('summary', { hasText: 'Measured points' }).click();
  await page.getByLabel('Marker color', { exact: true }).selectOption('ac');
  await page
    .getByRole('checkbox', { name: 'Inferred surface', exact: true })
    .uncheck();
  await expect(page).toHaveURL(/layers=[^&]*observations/);
  await page.waitForTimeout(650);
  const observationInspector = page.getByRole('complementary', {
    name: 'Selected observation',
  });
  await hoverNearCenter();
  await expect(hoverPreview).toBeVisible();
  await expect(hoverPreview).toContainText('Allele count (AC)');
  await expect(
    hoverPreview.locator('[data-observation-color]'),
  ).toHaveAttribute('data-observation-color', /^#[0-9a-f]{6}$/);
  await clickNearCenter(observationInspector);
  await expect(observationInspector).toBeVisible();
  await expect(observationInspector).toContainText('Allele count (AC)');
  await expect(
    observationInspector.locator('[data-observation-color]'),
  ).toHaveAttribute('data-observation-color', /^#[0-9a-f]{6}$/);
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox).not.toBeNull();
  await page.mouse.move(
    canvasBox!.x + canvasBox!.width / 2,
    canvasBox!.y + canvasBox!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    canvasBox!.x + canvasBox!.width / 2 + 90,
    canvasBox!.y + canvasBox!.height / 2 + 40,
    { steps: 4 },
  );
  await page.mouse.up();
  await expect(hoverPreview).toHaveCount(0);
  await expect(observationInspector).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(observationInspector).toHaveCount(0);
});

test('explorer reports unavailable WebGL with a retry action', async ({
  page,
}) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = () => null;
  });
  await page.goto('/app/');
  await expect(page.getByText('This globe needs WebGL')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry globe' })).toBeVisible();
});

test('polygon map validates a selected model cell before loading Google Maps', async ({
  page,
}) => {
  await page.goto('/app/polygon/?cell=83754efffffffff');
  await expect(page.getByRole('status')).toContainText(
    'domain-restricted Google Maps browser key',
  );
});
