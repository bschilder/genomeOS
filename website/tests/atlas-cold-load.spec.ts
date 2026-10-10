/**
 * Cold-load measurement contract (fast-load design §B.1).
 *
 *   npm run build && npm run test:performance -- atlas-cold-load
 *
 * Headed Chrome on a hardware GPU; three fresh contexts per profile. The
 * observations-visible, surface-visible and reveal budgets are asserted on the
 * median of the three runs; the Atlas long-frame cap, the transport checks and
 * "no request timeout or error" hold for every run. Budgets are skipped on
 * software renderers. Baseline mode (ATLAS_COLD_LOAD_BASELINE=1 with
 * ATLAS_COLD_LOAD_BASE_URL) measures a pre-change build to `data-atlas-ready`
 * and asserts nothing. The browser side lives here; the run analysis is in
 * `support/cold-load-run.ts`.
 */
import { writeFileSync } from 'node:fs';
import os from 'node:os';

import {
  chromium,
  devices,
  errors,
  expect,
  test,
  type Browser,
  type Page,
} from '@playwright/test';

import { ledgerMarkdown, type LoafRecord } from './support/cold-load-analysis';
import {
  COLD_LOAD_PROFILES,
  COLD_LOAD_RUNS,
  QUIET_PERIOD_MS,
  type ColdLoadProfile,
} from './support/cold-load-profiles';
import {
  analyseRun,
  medianRun,
  summarise,
  throttleWorkers,
  trackNetwork,
  type ColdLoadMode,
  type ColdLoadRun,
  type Outcome,
  type PageMeasurements,
} from './support/cold-load-run';
import {
  CdpConnection,
  assertDevToolsPortFree,
  browserProcessId,
  browserWebSocketUrl,
} from './support/cdp-connection';
import { assertProductionBuild } from './support/production-build';

const MODE: ColdLoadMode =
  process.env.ATLAS_COLD_LOAD_BASELINE === '1' ? 'baseline' : 'current';
const CDP_PORT = Number(process.env.ATLAS_COLD_LOAD_CDP_PORT ?? '9333');
const SOFTWARE_RENDERER = /swiftshader|software|llvmpipe/i;
const BLOCKED_TILES = '*tile.openstreetmap.org*';
const SETTLED_ATTRIBUTES =
  MODE === 'current'
    ? ['data-atlas-ready', 'data-atlas-edges-ready', 'data-atlas-context-ready']
    : ['data-atlas-ready'];

interface ColdLoadProbe {
  loaf: LoafRecord[];
  attributes: Record<string, number>;
  errors: string[];
}

function installColdLoadProbes(): void {
  const probe: ColdLoadProbe = { loaf: [], attributes: {}, errors: [] };
  (window as unknown as { __atlasColdLoad: ColdLoadProbe }).__atlasColdLoad =
    probe;
  performance.setResourceTimingBufferSize(2_000);
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const frame = entry as unknown as LoafRecord;
        probe.loaf.push({
          startTime: frame.startTime,
          duration: frame.duration,
          renderStart: frame.renderStart,
          blockingDuration: frame.blockingDuration,
          scripts: frame.scripts.map((script) => ({
            sourceURL: script.sourceURL,
            invoker: script.invoker,
            invokerType: script.invokerType,
            startTime: script.startTime,
            duration: script.duration,
          })),
        });
      }
    }).observe({ type: 'long-animation-frame', buffered: true });
  } catch (error) {
    probe.errors.push(`long-animation-frame observer failed: ${String(error)}`);
  }
  new MutationObserver((records) => {
    for (const record of records) {
      const name = record.attributeName;
      const target = record.target as Element;
      if (!name || !target.classList.contains('atlas-explorer')) continue;
      if (target.getAttribute(name) === 'true' && !(name in probe.attributes))
        probe.attributes[name] = performance.now();
    }
  }).observe(document, {
    subtree: true,
    attributes: true,
    attributeFilter: [
      'data-atlas-ready',
      'data-atlas-observations-visible',
      'data-atlas-surface-visible',
      'data-atlas-values-ready',
      'data-atlas-edges-ready',
      'data-atlas-context-ready',
    ],
  });
}

function collectPageMeasurements(): PageMeasurements {
  const probe = (window as unknown as { __atlasColdLoad: ColdLoadProbe })
    .__atlasColdLoad;
  const timing = (type: 'mark' | 'measure') =>
    performance
      .getEntriesByType(type)
      .filter((entry) => entry.name.startsWith('atlas:'))
      .map((entry) => ({
        name: entry.name,
        startTime: entry.startTime,
        duration: entry.duration,
        detail: (entry as PerformanceMark).detail ?? null,
      }));
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl');
  const debug = gl?.getExtension('WEBGL_debug_renderer_info');
  const navigation = performance.getEntriesByType('navigation')[0] as
    PerformanceNavigationTiming | undefined;
  return {
    marks: timing('mark'),
    measures: timing('measure'),
    resources: performance.getEntriesByType('resource').map((entry) => ({
      name: entry.name,
      responseEnd: (entry as PerformanceResourceTiming).responseEnd,
    })),
    navigationResponseEnd: navigation?.responseEnd ?? 0,
    loaf: probe.loaf,
    attributes: probe.attributes,
    probeErrors: probe.errors,
    renderer:
      gl && debug
        ? String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL))
        : 'unknown',
    preloads: [
      ...document.querySelectorAll<HTMLLinkElement>(
        'link[rel="preload"][as="fetch"]',
      ),
    ].map((link) => link.href),
    surfaceDownloads:
      document
        .getElementById('atlas-catalog')
        ?.getAttribute('data-surface-downloads') ?? null,
    catalogText: document.getElementById('atlas-catalog')?.textContent ?? null,
    documentUrl: location.href,
    origin: location.origin,
    errorText: document.querySelector('.atlas-error')?.textContent ?? null,
    collectedAt: performance.now(),
  };
}

async function pageTargetIds(cdp: CdpConnection): Promise<string[]> {
  const { targetInfos } = await cdp.send<{
    targetInfos: { targetId: string; type: string }[];
  }>('Target.getTargets');
  return targetInfos
    .filter((target) => target.type === 'page')
    .map((target) => target.targetId);
}

async function waitForSettled(page: Page, timeoutMs: number): Promise<Outcome> {
  try {
    const handle = await page.waitForFunction(
      (names: string[]) => {
        if (document.querySelector('.atlas-error')) return 'error';
        const explorer = document.querySelector('.atlas-explorer');
        return explorer !== null &&
          names.every((name) => explorer.getAttribute(name) === 'true')
          ? 'settled'
          : false;
      },
      SETTLED_ATTRIBUTES,
      { polling: 250, timeout: timeoutMs },
    );
    return (await handle.jsonValue()) as Outcome;
  } catch (error) {
    if (error instanceof errors.TimeoutError) return 'timeout';
    throw error;
  }
}

async function runColdLoad(
  browser: Browser,
  cdp: CdpConnection,
  profile: ColdLoadProfile,
  baseUrl: string,
  index: number,
): Promise<ColdLoadRun> {
  const context = await browser.newContext({
    viewport: profile.viewport,
    deviceScaleFactor: profile.deviceScaleFactor,
    isMobile: profile.isMobile,
    hasTouch: profile.hasTouch,
    ...(profile.isMobile ? { userAgent: devices['Pixel 7'].userAgent } : {}),
    extraHTTPHeaders: { 'Accept-Encoding': 'gzip, deflate' },
  });
  await context.addInitScript(installColdLoadProbes);
  const existing = new Set(await pageTargetIds(cdp));
  const page = await context.newPage();
  const targetId = (await pageTargetIds(cdp)).find((id) => !existing.has(id));
  if (targetId === undefined)
    throw new Error('Could not find the CDP target of the new page.');
  const { sessionId } = await cdp.send<{ sessionId: string }>(
    'Target.attachToTarget',
    { targetId, flatten: true },
  );
  const network = trackNetwork(cdp, sessionId);
  const workers =
    profile.cpuThrottlingRate > 1
      ? throttleWorkers(cdp, sessionId, profile.cpuThrottlingRate)
      : null;
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  try {
    await cdp.send('Network.enable', {}, sessionId);
    await cdp.send(
      'Network.setBlockedURLs',
      { urls: [BLOCKED_TILES] },
      sessionId,
    );
    if (profile.network)
      await cdp.send(
        'Network.emulateNetworkConditions',
        { offline: false, ...profile.network },
        sessionId,
      );
    if (profile.cpuThrottlingRate > 1) {
      await cdp.send(
        'Emulation.setCPUThrottlingRate',
        { rate: profile.cpuThrottlingRate },
        sessionId,
      );
      await cdp.send(
        'Target.setAutoAttach',
        { autoAttach: true, flatten: true, waitForDebuggerOnStart: true },
        sessionId,
      );
    }
    await page.goto(`${baseUrl}/app/`, { waitUntil: 'commit' });
    const outcome = await waitForSettled(page, profile.timeoutMs);
    await page.waitForTimeout(QUIET_PERIOD_MS);
    const measurements = await page.evaluate(collectPageMeasurements);
    return analyseRun({
      mode: MODE,
      index,
      profile,
      measurements,
      records: network.records(),
      workerThrottle: workers?.report() ?? null,
      pageErrors,
      outcome,
    });
  } finally {
    network.dispose();
    workers?.dispose();
    await cdp
      .send('Target.detachFromTarget', { sessionId })
      .catch(() => undefined);
    await context.close();
  }
}

/**
 * The DevTools endpoint must belong to the Chrome this test launched: compare
 * its browser process with the one Playwright drives.
 */
async function assertLaunchedBrowser(
  browser: Browser,
  cdp: CdpConnection,
): Promise<void> {
  const session = await browser.newBrowserCDPSession();
  try {
    const launched = browserProcessId(
      await session.send('SystemInfo.getProcessInfo'),
    );
    const endpoint = browserProcessId(
      await cdp.send<{ processInfo: { type: string; id: number }[] }>(
        'SystemInfo.getProcessInfo',
      ),
    );
    if (endpoint !== launched)
      throw new Error(
        `The DevTools endpoint on port ${CDP_PORT} belongs to browser process ${endpoint}, ` +
          `not to the launched Chrome (${launched}). Close the other browser or set ` +
          'ATLAS_COLD_LOAD_CDP_PORT to a free port.',
      );
  } finally {
    await session.detach();
  }
}

function machine(browser: Browser) {
  const cpus = os.cpus();
  return {
    platform: `${os.platform()} ${os.release()}`,
    arch: os.arch(),
    cpu: cpus[0]?.model ?? 'unknown',
    cores: cpus.length,
    memoryGiB: Math.round(os.totalmem() / 2 ** 30),
    browser: `chrome ${browser.version()}`,
  };
}

for (const profile of COLD_LOAD_PROFILES) {
  test(`cold load (${MODE}): ${profile.name}`, async ({}, testInfo) => {
    test.skip(
      testInfo.project.name !== 'desktop-chromium',
      'The cold-load spec launches its own headed Chrome once.',
    );
    test.setTimeout(COLD_LOAD_RUNS * (profile.timeoutMs + 30_000) + 60_000);
    const baseUrl =
      process.env.ATLAS_COLD_LOAD_BASE_URL ??
      String(testInfo.project.use.baseURL);
    if (MODE === 'current') await assertProductionBuild(baseUrl);
    await assertDevToolsPortFree(CDP_PORT);
    const browser = await chromium.launch({
      channel: 'chrome',
      headless: false,
      args: [`--remote-debugging-port=${CDP_PORT}`],
    });
    let cdp: CdpConnection | null = null;
    try {
      cdp = await CdpConnection.open(await browserWebSocketUrl(CDP_PORT));
      await assertLaunchedBrowser(browser, cdp);
      const runs: ColdLoadRun[] = [];
      for (let index = 0; index < COLD_LOAD_RUNS; index += 1)
        runs.push(await runColdLoad(browser, cdp, profile, baseUrl, index));
      const summary = summarise(runs);
      const renderer = runs[0]?.renderer ?? 'unknown';
      const software = SOFTWARE_RENDERER.test(renderer);
      const report = JSON.stringify(
        {
          mode: MODE,
          profile,
          machine: machine(browser),
          renderer,
          softwareRenderer: software,
          summary,
          runs,
        },
        null,
        2,
      );
      const ledger = ledgerMarkdown(
        `${MODE} · ${profile.name} (median run; times are ${summary.timesAre})`,
        medianRun(runs, MODE).ledger,
      );
      writeFileSync(
        testInfo.outputPath(`atlas-cold-load-${profile.name}.json`),
        report,
      );
      writeFileSync(
        testInfo.outputPath(`atlas-cold-load-${profile.name}-ledger.md`),
        ledger,
      );
      await testInfo.attach(`atlas-cold-load-${profile.name}.json`, {
        body: report,
        contentType: 'application/json',
      });
      await testInfo.attach(`atlas-cold-load-${profile.name}-ledger.md`, {
        body: ledger,
        contentType: 'text/markdown',
      });
      console.info(
        `Atlas cold load ${MODE} ${profile.name}: ${JSON.stringify(summary)}`,
      );
      if (MODE === 'baseline') return;

      for (const run of runs) {
        expect
          .soft(run.errors, `run ${run.index}: no request timeout or error`)
          .toEqual([]);
        for (const transfer of run.transport)
          expect
            .soft(
              ['gzip', 'br'],
              `run ${run.index}: ${transfer.tier} content-encoding`,
            )
            .toContain(transfer.contentEncoding);
        expect
          .soft(
            run.preloads.map((preload) => preload.url).sort(),
            `run ${run.index}: preloads`,
          )
          .toEqual(
            run.transport
              .filter((transfer) => transfer.preloaded)
              .map((transfer) => transfer.url)
              .sort(),
          );
        for (const preload of run.preloads)
          expect
            .soft(
              preload.requests,
              `run ${run.index}: ${preload.url} fetched once`,
            )
            .toBe(1);
      }
      if (software) {
        testInfo.annotations.push({
          type: 'budgets skipped',
          description: `software renderer: ${renderer}`,
        });
        return;
      }
      const { budgets } = profile;
      const at = (value: number | null): number =>
        value ?? Number.POSITIVE_INFINITY;
      expect
        .soft(
          at(summary.observationsVisibleMs),
          'observations-visible (median)',
        )
        .toBeLessThanOrEqual(budgets.observationsVisibleMs);
      expect
        .soft(at(summary.surfaceVisibleMs), 'surface-visible (median)')
        .toBeLessThanOrEqual(budgets.surfaceVisibleMs);
      // §B.1 "Additionally": no Atlas main-thread long animation frame above the cap within the
      // window — a per-run limit, so one bad run fails even when the other two are fast. The
      // median stays in the summary as a reported number only.
      for (const run of runs)
        expect
          .soft(
            run.longFrames.maxAtlasFrameMs,
            `run ${run.index}: longest Atlas animation frame`,
          )
          .toBeLessThanOrEqual(budgets.atlasLongFrameMs);
      if (budgets.revealMs !== null)
        expect
          .soft(
            at(summary.revealMs),
            'surface reveal from first chunk (median)',
          )
          .toBeLessThanOrEqual(budgets.revealMs);
    } finally {
      cdp?.close();
      await browser.close();
    }
  });
}
