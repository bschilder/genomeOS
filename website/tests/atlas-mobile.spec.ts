import { expect, test, type Locator, type Page } from '@playwright/test';

import { installAtlasBrowserFixture } from './atlas-browser-fixture';
import {
  centreOf,
  controlsSheet,
  dockedStackInOrder,
  INSPECTOR_CAMERA,
  panelSheet,
  PHONE_PROFILES,
  setSheetState,
  sheetGeometry,
  skipUnlessProject,
  startTouch,
  tapSelectNearCenter,
  touchDrag,
  waitForAtlasReady,
} from './atlas-mobile-helpers';
import { topLevelRoutes } from './site-routes';

/**
 * The panel sheet's peek band (§A.1.5 via §A.1.6): ≤ 18% of the explorer and
 * ≥ 56 px, glued to the explorer bottom, with the panel's h2 and Close inside.
 */
async function expectPanelPeekBand(page: Page, panel: Locator): Promise<void> {
  await expect(panelSheet(page)).toHaveAttribute('data-sheet-state', 'peek');
  await expect(async () => {
    const geometry = await sheetGeometry(page, '.atlas-right-rail');
    expect(geometry.sheetHeight).toBeGreaterThanOrEqual(56);
    expect(geometry.sheetHeight).toBeLessThanOrEqual(
      geometry.explorerHeight * 0.18,
    );
    expect(
      Math.abs(
        geometry.sheetTop + geometry.sheetHeight - geometry.explorerBottom,
      ),
    ).toBeLessThanOrEqual(1);
    for (const part of [
      panel.locator('h2'),
      panel.locator('.atlas-inspector__close'),
    ]) {
      const box = (await part.boundingBox())!;
      expect(box.y).toBeGreaterThanOrEqual(geometry.sheetTop);
      expect(box.y + box.height).toBeLessThanOrEqual(
        geometry.sheetTop + geometry.sheetHeight + 1,
      );
      // Shown whole: not squeezed shorter than its own content.
      expect(
        await part.evaluate(
          (element) => element.scrollHeight - element.clientHeight,
        ),
      ).toBeLessThanOrEqual(1);
    }
  }).toPass({ timeout: 10_000 });
}

/** The rail handle names the open panel's body, not the rail that holds the handle. */
async function expectHandleControls(page: Page, panel: Locator): Promise<void> {
  const bodyId = await panelSheet(page)
    .locator('.atlas-sheet__handle')
    .getAttribute('aria-controls');
  expect(bodyId).toBeTruthy();
  await expect(panel.locator(`[id="${bodyId}"]`)).toHaveClass(
    /atlas-panel-body/,
  );
}

/**
 * Records every focus move from now on. Chromium blurs a hidden or inert focus
 * only at its next rendering update, so a move to <body> shows up here as a
 * focusout with no related target even when the end state looks right.
 */
async function recordFocusTrail(page: Page): Promise<void> {
  await page.evaluate(() => {
    const trail: string[] = [];
    Object.assign(window, { atlasFocusTrail: trail });
    document.addEventListener(
      'focusout',
      (event) => {
        const next = event.relatedTarget;
        trail.push(
          next instanceof Element
            ? `focus → ${next.tagName.toLowerCase()}.${next.className}`
            : 'focus → none',
        );
      },
      true,
    );
  });
}

async function focusTrail(page: Page): Promise<unknown> {
  return page.evaluate(
    () => (window as unknown as { atlasFocusTrail: unknown }).atlasFocusTrail,
  );
}

test.beforeEach(async ({ page }) => installAtlasBrowserFixture(page));
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

for (const phone of PHONE_PROFILES) {
  test.describe(`${phone.name} phone`, () => {
    test.use(phone.use);
    test.beforeEach(({}, testInfo) =>
      skipUnlessProject(testInfo, 'mobile-chromium'),
    );

    for (const route of topLevelRoutes) {
      test(`${route} fits the phone width without zooming out`, async ({
        page,
      }) => {
        await page.goto(route);
        if (route === '/app/') await waitForAtlasReady(page);
        const fit = await page.evaluate(() => ({
          clientWidth: document.documentElement.clientWidth,
          scale: window.visualViewport?.scale ?? 1,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
        expect(fit.scale).toBe(1);
      });
    }

    test('the Atlas header keeps the status chip beside a 44 px menu', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const header = await page.evaluate(() => {
        const inner = document.querySelector('.site-header__inner')!;
        const chip = document.querySelector(
          '.atlas-navbar-status-slot .atlas-status',
        )!;
        const label = chip.querySelector('.atlas-status__copy strong')!;
        const menu = document
          .querySelector('.mobile-nav summary')!
          .getBoundingClientRect();
        return {
          chipRight: chip.getBoundingClientRect().right,
          clientWidth: inner.clientWidth,
          label: label.textContent,
          labelOverflow: getComputedStyle(label).textOverflow,
          menuHeight: menu.height,
          menuLeft: menu.left,
          menuWidth: menu.width,
          scrollWidth: inner.scrollWidth,
          wordmarkFont: getComputedStyle(document.querySelector('.wordmark')!)
            .fontFamily,
        };
      });
      expect(header.scrollWidth).toBeLessThanOrEqual(header.clientWidth);
      expect(header.chipRight).toBeLessThanOrEqual(header.menuLeft);
      expect(header.menuWidth).toBeGreaterThanOrEqual(44);
      expect(header.menuHeight).toBeGreaterThanOrEqual(44);
      expect(header.label).toBe('Atlas ready');
      expect(header.labelOverflow).toBe('ellipsis');
      expect(header.wordmarkFont).toContain('Raleway');
      await expect(page.locator('.mobile-nav summary')).toHaveAccessibleName(
        'Menu',
      );
    });

    test('Atlas status detail stays in the live region while visually hidden', async ({
      page,
    }) => {
      await page.goto('/app/', { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(
        () => {
          const detail = document.querySelector(
            '[data-atlas-status-slot] [role="status"] .atlas-status__copy small',
          );
          if (!detail) return false;
          const style = getComputedStyle(detail);
          return (
            style.display !== 'none' &&
            style.position === 'absolute' &&
            detail.getBoundingClientRect().width <= 1
          );
        },
        null,
        { polling: 'raf', timeout: 30_000 },
      );
    });

    test('/app/ fills the phone below the header without vertical scroll', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const shell = await page.evaluate(() => ({
        clientHeight: document.documentElement.clientHeight,
        explorerBottom: document
          .querySelector('.atlas-explorer')!
          .getBoundingClientRect().bottom,
        innerHeight: window.innerHeight,
        scrollHeight: document.documentElement.scrollHeight,
      }));
      expect(shell.scrollHeight).toBeLessThanOrEqual(shell.clientHeight);
      expect(
        Math.abs(shell.explorerBottom - shell.innerHeight),
      ).toBeLessThanOrEqual(0.5);
    });

    test('controls sheet cycles by tap and keyboard with named states', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(handle).toHaveAccessibleName('Explorer controls, peek');
      await expect(handle).toHaveAttribute('aria-expanded', 'false');
      const bodyId = await handle.getAttribute('aria-controls');
      expect(bodyId).toBeTruthy();
      await expect(page.locator(`[id="${bodyId}"]`)).toHaveClass(
        /atlas-sheet__body/,
      );

      await handle.tap();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
      await expect(handle).toHaveAccessibleName(
        'Explorer controls, half height',
      );
      await expect(handle).toHaveAttribute('aria-expanded', 'true');

      await handle.focus();
      await page.keyboard.press('Enter');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'full');
      await expect(handle).toHaveAccessibleName(
        'Explorer controls, full height',
      );
      await expect(handle).toHaveAttribute('aria-expanded', 'true');
      await expect(handle).toBeFocused();

      await page.keyboard.press('Enter');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(handle).toHaveAttribute('aria-expanded', 'false');
      await expect(handle).toBeFocused();
      await page.keyboard.press('Space');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');

      // Space straight after a touch tap advances exactly once: Chromium still
      // dispatches a native click on Space keyup while the tapped button is
      // :active, and onKeyUp cancels it (a second advance would land on 'half').
      await handle.tap();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'full');
      await handle.focus();
      await page.keyboard.press('Space');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
    });

    test('peek keeps the globe open and the sheet body inert', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      await expect
        .poll(async () => {
          const geometry = await sheetGeometry(page);
          return (
            geometry.sheetHeight >= 56 &&
            geometry.sheetHeight <= geometry.explorerHeight * 0.18 &&
            Math.abs(
              geometry.sheetTop +
                geometry.sheetHeight -
                geometry.explorerBottom,
            ) <= 1
          );
        })
        .toBe(true);
      await expect(sheet.locator('.atlas-sheet__body')).toHaveAttribute(
        'inert',
        '',
      );
      const summary = sheet.locator('.atlas-sheet__summary');
      await expect(summary).toHaveText('HbS (rs334) · Posterior estimate');
      await expect(
        summary.locator(
          'a, button, input, select, textarea, details, [tabindex]',
        ),
      ).toHaveCount(0);

      await sheet.locator('.atlas-sheet__handle').focus();
      let leftSheet = false;
      for (let press = 0; press < 3; press += 1) {
        await page.keyboard.press('Tab');
        const focus = await page.evaluate(() => ({
          inBody: Boolean(
            document.activeElement?.closest('.atlas-sheet__body'),
          ),
          inSheet: Boolean(
            document.activeElement?.closest('aside.atlas-controls'),
          ),
        }));
        expect(focus.inBody).toBe(false);
        if (!focus.inSheet) leftSheet = true;
      }
      expect(leftSheet).toBe(true);
    });

    test('half and full scroll the sheet body instead of moving it off-screen', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const body = sheet.locator('.atlas-sheet__body');

      await setSheetState(sheet, 'half');
      await expect
        .poll(async () => {
          const geometry = await sheetGeometry(page);
          return Math.abs(geometry.sheetHeight - geometry.explorerHeight / 2);
        })
        .toBeLessThanOrEqual(2);
      await expect(body).not.toHaveAttribute('inert');
      await expect(
        sheet.locator('details.atlas-control-sheet').filter({
          has: page.locator('summary', { hasText: /^Scientific layers$/ }),
        }),
      ).toHaveAttribute('open', '');

      await setSheetState(sheet, 'full');
      await expect
        .poll(async () => {
          const geometry = await sheetGeometry(page);
          return (
            geometry.sheetHeight > geometry.explorerHeight / 2 + 2 &&
            geometry.sheetHeight <= geometry.explorerHeight * 0.88 + 1
          );
        })
        .toBe(true);
      const scroll = await body.evaluate((element) => ({
        overflowY: getComputedStyle(element).overflowY,
        overscroll: getComputedStyle(element).overscrollBehaviorY,
      }));
      expect(scroll).toEqual({ overflowY: 'auto', overscroll: 'contain' });
      const keys = sheet.locator('.atlas-keyboard-help summary');
      await keys.scrollIntoViewIfNeeded();
      const [keysBox, bodyBox, geometry] = await Promise.all([
        keys.boundingBox(),
        body.boundingBox(),
        sheetGeometry(page),
      ]);
      expect(keysBox!.y).toBeGreaterThanOrEqual(bodyBox!.y - 1);
      expect(keysBox!.y + keysBox!.height).toBeLessThanOrEqual(
        bodyBox!.y + bodyBox!.height + 1,
      );
      expect(bodyBox!.y + bodyBox!.height).toBeLessThanOrEqual(
        geometry.explorerBottom + 1,
      );
    });

    test('entering peek moves focus to the handle before the body goes inert', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      await setSheetState(sheet, 'full');
      await sheet
        .locator('summary', { hasText: /^Scientific layers$/ })
        .focus();
      await page.keyboard.press('Escape');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(sheet.locator('.atlas-sheet__handle')).toBeFocused();
      await expect(sheet.locator('.atlas-sheet__body')).toHaveAttribute(
        'inert',
        '',
      );
    });

    test('narrowing into the phone layout at peek moves focus to the handle first', async ({
      page,
    }) => {
      const phoneViewport = page.viewportSize()!;
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      await page.setViewportSize({ height: phoneViewport.height, width: 1024 });
      await expect(sheet).not.toHaveAttribute('data-sheet-state');
      await expect(sheet.locator('.atlas-sheet__body')).not.toHaveAttribute(
        'inert',
      );
      const layers = sheet.locator('summary', {
        hasText: /^Scientific layers$/,
      });
      await layers.focus();
      await expect(layers).toBeFocused();
      // Chromium blurs an inert-ed focus only at its next rendering update, so
      // the end state alone cannot show the order: also record which element
      // has focus at the moment React sets `inert` on the sheet body.
      await page.evaluate(() => {
        const trail: string[] = [];
        Object.assign(window, { atlasFocusTrail: trail });
        const name = (node: EventTarget | null) =>
          node instanceof Element
            ? `${node.tagName.toLowerCase()}.${node.className}`
            : 'none';
        document.addEventListener(
          'focusout',
          (event) => trail.push(`focus → ${name(event.relatedTarget)}`),
          true,
        );
        const setAttribute = Element.prototype.setAttribute;
        Element.prototype.setAttribute = function (key, value) {
          if (key === 'inert' && this.matches('[data-sheet-body]'))
            trail.push(`inert with focus on ${name(document.activeElement)}`);
          setAttribute.call(this, key, value);
        };
      });

      await page.setViewportSize(phoneViewport);
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect(sheet.locator('.atlas-sheet__body')).toHaveAttribute(
        'inert',
        '',
      );
      await expect(sheet.locator('.atlas-sheet__handle')).toBeFocused();
      // Focus went straight from the summary to the handle, never to <body>,
      // and only then did the body go inert.
      const trail = await page.evaluate(
        () =>
          (window as unknown as { atlasFocusTrail: unknown }).atlasFocusTrail,
      );
      expect(trail).toEqual([
        'focus → button.atlas-sheet__handle',
        'inert with focus on button.atlas-sheet__handle',
      ]);
    });

    test('the legend and credits dock above the sheet in every state', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      for (const state of ['peek', 'half', 'full'] as const) {
        await setSheetState(sheet, state);
        await expect.poll(() => dockedStackInOrder(page)).toBe(true);
      }
    });

    test('reduced motion snaps the sheet without animation', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const duration = await controlsSheet(page).evaluate((element) =>
        Number.parseFloat(getComputedStyle(element).transitionDuration),
      );
      expect(duration).toBeLessThan(0.001);
    });

    test('the dataset selector sits on top while the sheet is at peek', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      await expect(controlsSheet(page)).toHaveAttribute(
        'data-sheet-state',
        'peek',
      );
      const trigger = page.getByRole('button', {
        name: /Select dataset\. Current dataset:/,
      });
      await expect(trigger).toBeVisible();
      await expect(
        page
          .locator('.atlas-top-slot')
          .getByRole('button', { name: /Select dataset\. Current dataset:/ }),
      ).toHaveCount(1);
      const placement = await trigger.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const explorer = document.querySelector('.atlas-explorer')!;
        const bounds = explorer.getBoundingClientRect();
        const hit = document.elementFromPoint(
          rect.left + rect.width / 2,
          rect.top + rect.height / 2,
        );
        return {
          firstChild:
            explorer.firstElementChild?.classList.contains('atlas-top-slot') ??
            false,
          hitsTrigger: hit !== null && element.contains(hit),
          topFraction: (rect.bottom - bounds.top) / bounds.height,
        };
      });
      expect(placement).toEqual({
        firstChild: true,
        hitsTrigger: true,
        topFraction: expect.any(Number),
      });
      expect(placement.topFraction).toBeLessThan(0.2);
      await trigger.click();
      await expect(
        page.getByRole('dialog', { name: 'Select dataset' }),
      ).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(trigger).toBeFocused();
    });

    test('Tab from the header reaches the selector before the globe', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      await page.locator('.mobile-nav summary').focus();
      await page.keyboard.press('Tab');
      await expect(
        page.getByRole('button', { name: /Select dataset\. Current dataset:/ }),
      ).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(page.locator('.atlas-scene')).toBeFocused();
      // Cesium's attribution links are focusable descendants of the canvas region
      // (its bottomContainer stays inside .atlas-scene, §A.1.7), so they come
      // between the canvas and the sheet. Walk them, allowing nothing else, and
      // stop at the first focus target outside them; a loop rather than a fixed
      // count, because map credits and "Data attribution" load asynchronously.
      const visited: string[] = [];
      for (let step = 0; step < 12; step += 1) {
        await page.keyboard.press('Tab');
        const inCredits = await page.evaluate(
          () =>
            document.activeElement?.closest(
              '.atlas-scene .cesium-viewer-bottom',
            ) != null,
        );
        if (!inCredits) break;
        visited.push(
          await page.evaluate(
            () =>
              document.activeElement?.textContent?.trim() ||
              document.activeElement?.tagName ||
              '',
          ),
        );
      }
      expect(visited.length).toBeGreaterThan(0); // the Cesium logo is always an in-scene link
      await expect(
        controlsSheet(page).locator('.atlas-sheet__handle'),
      ).toBeFocused();
    });

    test('one visually hidden h1 and no duplicated controls', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(
        page.locator('.atlas-top-slot > h1.visually-hidden'),
      ).toHaveCount(1);
      await expect(
        page.getByRole('heading', {
          level: 1,
          name: 'Explore human genetic variation',
        }),
      ).toHaveCount(1);
      await expect(page.locator('#atlas-earth-opacity')).toHaveCount(1);
      await expect(page.locator('#atlas-sampling-areas')).toHaveCount(1);
      await expect(page.locator('input[name="metric"]')).toHaveCount(2);
      await expect(
        page.getByRole('complementary', { name: 'Explorer controls' }),
      ).toHaveCount(1);
      await expect(
        controlsSheet(page).locator('.atlas-field--entity'),
      ).toHaveCount(0);
      await expect(
        page.getByRole('button', { name: 'About map selection' }),
      ).toHaveCount(1);
      await expect(
        page
          .locator('.atlas-sheet__handle-row')
          .getByRole('button', { name: 'About map selection' }),
      ).toHaveCount(1);
    });

    test('a warning banner pushes the selector below it', async ({ page }) => {
      await page.goto(
        '/app/?entity=hbs-rs334&version=v1%2Fmap-2026-08&metric=post_mean',
      );
      await waitForAtlasReady(page);
      const banner = page.locator('.atlas-warning-banner');
      await expect(banner).toBeVisible();
      const [bannerBox, slotBox] = await Promise.all([
        banner.boundingBox(),
        page.locator('.atlas-top-slot').boundingBox(),
      ]);
      expect(bannerBox!.y + bannerBox!.height).toBeLessThanOrEqual(slotBox!.y);
    });

    test('a view notice opens below the top selector', async ({ page }) => {
      // The notice is placed from --atlas-top-slot-height, which must follow
      // the trigger's height in map-catalog.css.
      await page.goto('/app/?view=map');
      await waitForAtlasReady(page);
      await setSheetState(controlsSheet(page), 'full');
      await page
        .locator('summary')
        .filter({ hasText: /^Inferred surface$/ })
        .click();
      await page.getByLabel('Statistical elevation', { exact: true }).check();
      const notice = page.locator('.atlas-view-notice');
      await expect(notice).toBeVisible();
      const [triggerBox, noticeBox] = await Promise.all([
        page
          .locator('.atlas-top-slot .atlas-map-catalog__trigger')
          .boundingBox(),
        notice.boundingBox(),
      ]);
      expect(triggerBox!.y + triggerBox!.height).toBeLessThanOrEqual(
        noticeBox!.y,
      );
    });

    test('touch drags step the controls sheet without page scroll or pointercancel', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      await handle.evaluate((element) => {
        element.dataset.cancels = '0';
        element.addEventListener('pointercancel', () => {
          element.dataset.cancels = String(Number(element.dataset.cancels) + 1);
        });
      });
      const explorer = page.locator('.atlas-explorer');
      const offset = () =>
        explorer.evaluate((element) =>
          Number.parseFloat(
            element.style.getPropertyValue('--atlas-sheet-offset'),
          ),
        );
      const start = await sheetGeometry(page);
      const lift = start.explorerHeight / 2 - start.sheetHeight;

      const from = await centreOf(handle);
      const gesture = await startTouch(page, from);
      for (let step = 1; step <= 4; step += 1) {
        await gesture.move({ x: from.x, y: from.y - (lift * step) / 8 });
        await page.waitForTimeout(16);
      }
      await expect.poll(offset).toBeGreaterThan(start.sheetHeight + 20);
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      for (let step = 5; step <= 8; step += 1) {
        await gesture.move({ x: from.x, y: from.y - (lift * step) / 8 });
        await page.waitForTimeout(16);
      }
      await gesture.end();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');

      const atHalf = await centreOf(handle);
      await touchDrag(page, atHalf, {
        x: atHalf.x,
        y: atHalf.y - start.explorerHeight / 4,
      });
      await expect(sheet).toHaveAttribute('data-sheet-state', 'full');

      const scrollBefore = await page.evaluate(() => window.scrollY);
      const atFull = await centreOf(handle);
      await touchDrag(page, atFull, {
        x: atFull.x,
        y: atFull.y + start.explorerHeight / 4,
      });
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
      expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);

      const body = sheet.locator('.atlas-sheet__body');
      await body.evaluate((element) => element.scrollTo(0, 0));
      const inBody = await centreOf(body);
      await touchDrag(page, inBody, { x: inBody.x, y: inBody.y + 150 });
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
      expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);
      expect(await body.evaluate((element) => element.scrollTop)).toBe(0);
      await expect(handle).toHaveAttribute('data-cancels', '0');
    });

    test('a mouse drag moves one step and the next click and Enter still cycle', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      const start = await sheetGeometry(page);
      const from = await centreOf(handle);
      await page.mouse.move(from.x, from.y);
      await page.mouse.down();
      await page.mouse.move(from.x, from.y - 40, { steps: 4 });
      await page.mouse.move(
        from.x,
        from.y - (start.explorerHeight / 2 - start.sheetHeight),
        { steps: 4 },
      );
      await page.mouse.up();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
      await page.waitForTimeout(100);
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
      await handle.click();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'full');
      await handle.focus();
      await page.keyboard.press('Enter');
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
    });

    test('a pointercancel mid-drag restores the pre-drag state', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      const explorer = page.locator('.atlas-explorer');
      // `HTMLElement` selects the HTMLElementEventMap overload, so `event` is a
      // PointerEvent; the default `SVGElement | HTMLElement` leaves it a plain Event.
      await handle.evaluate((element: HTMLElement) => {
        element.addEventListener(
          'pointerdown',
          (event) => {
            element.dataset.pointerId = String(event.pointerId);
          },
          { once: true },
        );
      });
      const before = await sheetGeometry(page);
      const from = await centreOf(handle);
      await page.mouse.move(from.x, from.y);
      await page.mouse.down();
      await page.mouse.move(from.x, from.y - 60, { steps: 3 });
      await expect(explorer).toHaveAttribute('data-sheet-dragging', '');
      const pointerId = Number(await handle.getAttribute('data-pointer-id'));
      await handle.dispatchEvent('pointercancel', {
        bubbles: true,
        isPrimary: true,
        pointerId,
        pointerType: 'mouse',
      });
      await expect(explorer).not.toHaveAttribute('data-sheet-dragging', '');
      await page.mouse.move(8, 8);
      await page.mouse.up();
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect
        .poll(async () =>
          Math.abs(
            (await sheetGeometry(page)).sheetHeight - before.sheetHeight,
          ),
        )
        .toBeLessThanOrEqual(1);
      const variables = await explorer.evaluate((element) => ({
        offset: element.style.getPropertyValue('--atlas-sheet-offset'),
        rest: element.style.getPropertyValue('--atlas-sheet-rest'),
      }));
      expect(variables.offset).toBe(variables.rest);
    });

    test('a released drag carries the docked strips on from the finger', async ({
      page,
    }) => {
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      const explorer = page.locator('.atlas-explorer');
      const start = await sheetGeometry(page);
      // Slow the document timeline 50× so the 220 ms release transitions are
      // still running when they are sampled.
      const cdp = await page.context().newCDPSession(page);
      await cdp.send('Animation.enable');
      await cdp.send('Animation.setPlaybackRate', { playbackRate: 0.02 });
      const from = await centreOf(handle);
      await page.mouse.move(from.x, from.y);
      await page.mouse.down();
      await page.mouse.move(
        from.x,
        from.y - (start.explorerHeight / 2 - start.sheetHeight) / 2,
        { steps: 6 },
      );
      await expect
        .poll(() =>
          explorer.evaluate((element) =>
            Number.parseFloat(
              element.style.getPropertyValue('--atlas-sheet-offset'),
            ),
          ),
        )
        .toBeGreaterThan(start.sheetHeight + 20);
      await page.mouse.up();
      // Each docked strip's gap to the sheet's top edge, sampled at the start
      // and the middle of the release transitions and again at rest.
      const release = await page.evaluate(() => {
        const sheetElement = document.querySelector('aside.atlas-controls')!;
        const strips = [
          '.atlas-data-credit',
          '.atlas-scene .cesium-viewer-bottom',
          '.atlas-legend',
        ];
        const gaps = () => {
          const top = sheetElement.getBoundingClientRect().top;
          return strips.map((selector) => {
            const rect = document
              .querySelector(selector)
              ?.getBoundingClientRect();
            return rect && rect.height > 0 ? top - rect.bottom : null;
          });
        };
        const transitions = document
          .getAnimations()
          .filter(
            (animation): animation is CSSTransition =>
              animation instanceof CSSTransition,
          );
        for (const transition of transitions) transition.pause();
        const samples = [0, 110].map((time) => {
          for (const transition of transitions) transition.currentTime = time;
          return gaps();
        });
        for (const transition of transitions) transition.finish();
        return {
          properties: transitions.map(
            (transition) => transition.transitionProperty,
          ),
          rest: gaps(),
          samples,
        };
      });
      expect(release.properties).toContain('height');
      expect(release.rest.filter((gap) => gap !== null)).not.toHaveLength(0);
      for (const sample of release.samples) {
        sample.forEach((gap, strip) => {
          const rest = release.rest[strip];
          if (rest === null || rest === undefined) expect(gap).toBeNull();
          else expect(Math.abs(gap! - rest)).toBeLessThanOrEqual(1.5);
        });
      }
    });

    test('leaving the phone layout mid-drag ends the drag', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const phoneViewport = page.viewportSize()!;
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const sheet = controlsSheet(page);
      const handle = sheet.locator('.atlas-sheet__handle');
      const explorer = page.locator('.atlas-explorer');
      const before = await sheetGeometry(page);
      const from = await centreOf(handle);
      const gesture = await startTouch(page, from);
      for (let step = 1; step <= 4; step += 1) {
        await gesture.move({ x: from.x, y: from.y - 15 * step });
        await page.waitForTimeout(16);
      }
      await expect(explorer).toHaveAttribute('data-sheet-dragging', '');
      // A rotation or a zoom across 52rem unmounts the handle under the
      // finger, so its lostpointercapture fires at the document.
      await page.setViewportSize({ height: phoneViewport.height, width: 1024 });
      await expect(sheet).not.toHaveAttribute('data-sheet-state');
      await expect(explorer).not.toHaveAttribute('data-sheet-dragging');
      await gesture.end();
      await page.setViewportSize(phoneViewport);
      await expect(sheet).toHaveAttribute('data-sheet-state', 'peek');
      await expect
        .poll(async () =>
          Math.abs(
            (await sheetGeometry(page)).sheetHeight - before.sheetHeight,
          ),
        )
        .toBeLessThanOrEqual(1);
      // Every touch has a fresh pointer id, so only a cleared session lets
      // the next drag start.
      const atPeek = await centreOf(handle);
      await touchDrag(page, atPeek, {
        x: atPeek.x,
        y: atPeek.y - (before.explorerHeight / 2 - before.sheetHeight),
      });
      await expect(sheet).toHaveAttribute('data-sheet-state', 'half');
    });

    test('a one-finger drag at the centre turns the globe', async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      const before = new URL(page.url()).searchParams.get('lon');
      expect(before).not.toBeNull();
      const centre = await centreOf(
        page.locator('.atlas-scene canvas').first(),
      );
      await touchDrag(
        page,
        centre,
        { x: centre.x + 120, y: centre.y + 10 },
        10,
      );
      await expect
        .poll(() => new URL(page.url()).searchParams.get('lon'), {
          timeout: 10_000,
        })
        .not.toBe(before);
    });

    test('tapping the globe opens the inspector sheet and Escape restores the controls', async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`/app/?${INSPECTOR_CAMERA}`);
      await waitForAtlasReady(page);
      await page.locator('[data-atlas-external-slot]').evaluate((element) => {
        (element as HTMLElement).dataset.probe = 'stable';
      });
      const controls = controlsSheet(page);
      const rail = panelSheet(page);
      await tapSelectNearCenter(page);
      const inspector = page.locator('.atlas-inspector');
      await expect(inspector).toBeVisible();
      await expect(rail).toHaveAttribute('data-sheet-state', 'half');
      await expect(rail.locator('.atlas-sheet__handle')).toHaveAccessibleName(
        'Selection details, half height',
      );
      await expectHandleControls(page, inspector);
      await expect(controls).toBeHidden();
      await expect(controls).toHaveAttribute('inert', '');

      // The body scrolls under a fixed peek row, so a scrolled inspector still
      // peeks at its h2 and Close (a scrolled inspector box dropped to 53 px).
      const body = inspector.locator('.atlas-panel-body');
      await body.evaluate((element) => {
        element.scrollTop = element.scrollHeight;
      });
      await expect
        .poll(() => body.evaluate((element) => element.scrollTop))
        .toBeGreaterThan(0);
      expect(await inspector.evaluate((element) => element.scrollTop)).toBe(0);
      await setSheetState(rail, 'peek');
      await expect(body).toHaveAttribute('inert', '');
      await expectPanelPeekBand(page, inspector);
      // A long population label stays one line at peek.
      await inspector.locator('h2').evaluate((heading) => {
        heading.textContent =
          'Colombia Sierra Nevada de Santa Marta Arsario pop 2';
      });
      await expectPanelPeekBand(page, inspector);
      await setSheetState(rail, 'half');
      await expect(
        page.getByRole('heading', {
          level: 1,
          name: 'Explore human genetic variation',
        }),
      ).toHaveCount(1);
      await expect.poll(() => dockedStackInOrder(page)).toBe(true);

      await page
        .getByRole('button', { name: /Select dataset\. Current dataset:/ })
        .click();
      const catalog = page.getByRole('dialog', { name: 'Select dataset' });
      await expect(catalog).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(catalog).toHaveCount(0);
      await expect(inspector).toBeVisible();

      await page.keyboard.press('Escape');
      await expect(inspector).toHaveCount(0);
      await expect(controls).toBeVisible();
      await expect(controls).not.toHaveAttribute('inert');
      await expect(controls).toHaveAttribute('data-sheet-state', 'peek');
      expect(
        await page.evaluate(
          () =>
            document.activeElement !== null &&
            document.activeElement !== document.body,
        ),
      ).toBe(true);
      await expect(
        page.locator('[data-atlas-external-slot][data-probe="stable"]'),
      ).toHaveCount(1);
    });

    test('More info opens the panel sheet on its Close button and gives focus back', async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`/app/?${INSPECTOR_CAMERA}`);
      await waitForAtlasReady(page);
      const controls = controlsSheet(page);
      const rail = panelSheet(page);
      await setSheetState(controls, 'half');
      const moreInfo = page.getByRole('button', { name: 'More info' });
      await moreInfo.click();
      const external = page.getByRole('complementary', {
        name: 'External variant information',
      });
      await expect(external).toBeVisible();
      const close = external.getByRole('button', {
        name: 'Close external information',
      });
      await expect(close).toBeFocused();
      await expect(controls).toBeHidden();
      await expect(rail).toHaveAttribute('data-sheet-state', 'half');
      await expect(rail.locator('.atlas-sheet__handle')).toHaveAccessibleName(
        'External information, half height',
      );
      await expectHandleControls(page, external);

      await close.click();
      await expect(external).toHaveCount(0);
      await expect(controls).toBeVisible();
      await expect(controls).toHaveAttribute('data-sheet-state', 'half');
      await expect(moreInfo).toBeFocused();

      await moreInfo.click();
      await expect(external).toBeVisible();
      await setSheetState(rail, 'peek');
      await expect(rail.locator('.atlas-panel-body')).toHaveAttribute(
        'inert',
        '',
      );
      await expect(
        external.getByRole('heading', { name: 'Variant information' }),
      ).toBeVisible();
      await expectPanelPeekBand(page, external);

      await tapSelectNearCenter(page);
      await expect(page.locator('.atlas-inspector')).toBeVisible();
      await expect(external).toHaveCount(0);
      await expect(rail).toHaveAttribute('data-sheet-state', 'half');
      expect(
        await page.evaluate(
          () =>
            document.activeElement !== null &&
            document.activeElement !== document.body,
        ),
      ).toBe(true);

      // Escape on the inspector restores the controls sheet's *prior* state (§A.3).
      // The controls were left at 'half' before More info hid them, so a reset to
      // peek is distinguishable here (the first test starts at peek, where it is not).
      await page.keyboard.press('Escape');
      await expect(page.locator('.atlas-inspector')).toHaveCount(0);
      await expect(controls).toBeVisible();
      await expect(controls).not.toHaveAttribute('inert');
      await expect(controls).toHaveAttribute('data-sheet-state', 'half');
      await expect(controls.locator('[data-sheet-body][inert]')).toHaveCount(0);
      expect(
        await page.evaluate(
          () =>
            document.activeElement !== null &&
            document.activeElement !== document.body,
        ),
      ).toBe(true);
    });

    test('crossing the 52rem switch point with a panel open leaves the controls usable', async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`/app/?${INSPECTOR_CAMERA}`);
      await waitForAtlasReady(page);
      await tapSelectNearCenter(page);
      const phoneViewport = page.viewportSize();
      if (phoneViewport === null)
        throw new Error('the phone context has no viewport');
      const controls = controlsSheet(page);
      await expect(panelSheet(page)).toHaveAttribute(
        'data-sheet-state',
        'half',
      );
      await expect(controls).toBeHidden();
      const closeInspector = page.getByRole('button', {
        name: 'Close inspector',
      });

      // Leaving the phone layout unmounts the focused handle: focus stays on
      // the inspector instead of falling to <body>.
      await panelSheet(page).locator('.atlas-sheet__handle').focus();
      await page.setViewportSize({ height: 900, width: 1280 });
      await expect(controls).toBeVisible();
      await expect(controls).not.toHaveAttribute('data-sheet-state');
      await expect(controls).not.toHaveAttribute('inert');
      await expect(page.locator('.atlas-inspector')).toBeVisible();
      await expect(closeInspector).toBeFocused();

      // Entering it hides the focused desktop control: focus moves to the
      // inspector's Close before the controls go hidden and inert.
      const layers = controls.locator('summary', {
        hasText: /^Scientific layers$/,
      });
      await layers.focus();
      await recordFocusTrail(page);
      await page.setViewportSize(phoneViewport);
      await expect(panelSheet(page)).toHaveAttribute(
        'data-sheet-state',
        /^(peek|half|full)$/,
      );
      await expect(controls).toBeHidden();
      await expect(closeInspector).toBeFocused();
      expect(await focusTrail(page)).toEqual([
        'focus → button.atlas-inspector__close',
      ]);
      expect(
        await page.evaluate(
          () => document.activeElement?.closest('[inert]') ?? null,
        ),
      ).toBeNull();

      // Focus inside the open panel stays put both ways. The phone rules apply
      // before React marks the rail as a sheet, so they must never hide a rail
      // that holds a panel (that blurred its focus to <body> in some runs).
      const rail = panelSheet(page);
      expect(
        await rail.evaluate((element) => {
          const state = element.getAttribute('data-sheet-state')!;
          element.removeAttribute('data-sheet-state');
          const display = getComputedStyle(element).display;
          element.setAttribute('data-sheet-state', state);
          return display;
        }),
      ).not.toBe('none');
      await page.setViewportSize({ height: 900, width: 1280 });
      await expect(closeInspector).toBeFocused();
      await recordFocusTrail(page);
      await page.setViewportSize(phoneViewport);
      await expect(rail).toHaveAttribute(
        'data-sheet-state',
        /^(peek|half|full)$/,
      );
      await expect(closeInspector).toBeFocused();
      expect(await focusTrail(page)).toEqual([]);
    });

    test('crossing into the phone layout with More info open moves focus to its Close', async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const phoneViewport = page.viewportSize();
      if (phoneViewport === null)
        throw new Error('the phone context has no viewport');
      await page.setViewportSize({ height: 900, width: 1280 });
      await page.goto(`/app/?${INSPECTOR_CAMERA}`);
      await waitForAtlasReady(page);
      const moreInfo = page.getByRole('button', { name: 'More info' });
      await moreInfo.click();
      const external = page.getByRole('complementary', {
        name: 'External variant information',
      });
      await expect(external).toBeVisible();
      await expect(moreInfo).toBeFocused();
      await recordFocusTrail(page);

      const closeExternal = external.getByRole('button', {
        name: 'Close external information',
      });
      await page.setViewportSize(phoneViewport);
      await expect(panelSheet(page)).toHaveAttribute(
        'data-sheet-state',
        /^(peek|half|full)$/,
      );
      await expect(controlsSheet(page)).toBeHidden();
      await expect(closeExternal).toBeFocused();
      expect(await focusTrail(page)).toEqual([
        'focus → button.atlas-inspector__close',
      ]);

      // On desktop both panels stay open. Focus on the earlier one, the
      // inspector, which the phone layout then closes: focus goes to the
      // latest panel's Close, not to <body> when the inspector unmounts.
      await page.setViewportSize({ height: 900, width: 1280 });
      await expect(closeExternal).toBeFocused();
      await page
        .getByRole('button', { name: 'Close external information' })
        .click();
      await tapSelectNearCenter(page);
      const inspector = page.locator('.atlas-inspector');
      await moreInfo.click();
      await expect(external).toBeVisible();
      await expect(inspector).toBeVisible();
      await page.getByRole('button', { name: 'Close inspector' }).focus();
      await recordFocusTrail(page);
      await page.setViewportSize(phoneViewport);
      await expect(inspector).toHaveCount(0);
      await expect(closeExternal).toBeFocused();
      expect(await focusTrail(page)).toEqual([
        'focus → button.atlas-inspector__close',
      ]);
    });

    test('the click of the globe tap that opened the panel sheet does not reach it', async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(`/app/?${INSPECTOR_CAMERA}`);
      await waitForAtlasReady(page);
      await tapSelectNearCenter(page);
      const rail = panelSheet(page);
      await setSheetState(rail, 'half');
      // Picking runs on pointerup, so Chromium can hit-test the tap's click
      // after the sheet is laid out under the finger. Replay that order: the
      // pointer goes down outside the rail and its click lands on the handle.
      const delivered = await page.evaluate(() => {
        const init = { bubbles: true, cancelable: true, pointerId: 41 };
        document
          .querySelector('.atlas-scene')!
          .dispatchEvent(new PointerEvent('pointerdown', init));
        return document
          .querySelector('.atlas-right-rail .atlas-sheet__handle')!
          .dispatchEvent(new PointerEvent('click', init));
      });
      expect(delivered).toBe(false);
      await expect(rail).toHaveAttribute('data-sheet-state', 'half');
      // A tap that starts on the handle still cycles the sheet.
      await rail.locator('.atlas-sheet__handle').tap();
      await expect(rail).toHaveAttribute('data-sheet-state', 'full');
    });
  });
}

/*
 * /app/ sets viewport-fit=cover (§A.1.1), so a landscape iPhone lays the page
 * under the notch and the rounded corners and reports them as side insets.
 * Chromium takes the insets from a CDP override; these are Apple's landscape
 * values for each size (812 px is inside 52rem, 844 and 932 px are not).
 */
const LANDSCAPE_PHONES = [
  { inset: 50, viewport: { height: 375, width: 812 } },
  { inset: 47, viewport: { height: 390, width: 844 } },
  { inset: 59, viewport: { height: 430, width: 932 } },
] as const;

for (const phone of LANDSCAPE_PHONES) {
  const { height, width } = phone.viewport;
  test.describe(`${width}x${height} landscape phone`, () => {
    test.use({
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: true,
      viewport: phone.viewport,
    });
    test.beforeEach(({}, testInfo) =>
      skipUnlessProject(testInfo, 'mobile-chromium'),
    );

    test('the Atlas header stays inside the side safe areas', async ({
      page,
    }) => {
      const cdp = await page.context().newCDPSession(page);
      await cdp.send('Emulation.setSafeAreaInsetsOverride', {
        insets: { bottom: 21, left: phone.inset, right: phone.inset, top: 0 },
      });
      await page.goto('/app/');
      await waitForAtlasReady(page);
      await page.locator('.skip-link').focus();
      const header = await page.evaluate(() => {
        const box = (selector: string) =>
          document.querySelector(selector)!.getBoundingClientRect();
        const inner = document.querySelector('.site-header__inner')!;
        return {
          backgroundLeft: box('.site-header').left,
          backgroundRight: box('.site-header').right,
          clientWidth: document.documentElement.clientWidth,
          innerClientWidth: inner.clientWidth,
          innerScrollWidth: inner.scrollWidth,
          menuRight: box('.mobile-nav summary').right,
          skipLinkLeft: box('.skip-link').left,
          wordmarkLeft: box('.wordmark').left,
        };
      });
      const safeRight = header.clientWidth - phone.inset;
      // Soft, so one run names every element that sits under an inset.
      expect.soft(header.wordmarkLeft).toBeGreaterThanOrEqual(phone.inset);
      expect.soft(header.menuRight).toBeLessThanOrEqual(safeRight);
      expect.soft(header.skipLinkLeft).toBeGreaterThanOrEqual(phone.inset);
      expect(header.innerScrollWidth).toBeLessThanOrEqual(
        header.innerClientWidth,
      );
      // The header background still runs edge to edge under the insets.
      expect(header.backgroundLeft).toBe(0);
      expect(header.backgroundRight).toBe(header.clientWidth);
    });
  });
}
