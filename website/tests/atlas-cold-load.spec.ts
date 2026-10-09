/**
 * Cold-load measurement contract (fast-load design §B.1).
 *
 *   npm run build && npm run test:performance -- atlas-cold-load
 *
 * Headed Chrome on a hardware GPU; three fresh contexts per profile; budgets
 * are asserted on medians and skipped on software renderers. Baseline mode
 * (ATLAS_COLD_LOAD_BASELINE=1 with ATLAS_COLD_LOAD_BASE_URL) measures a
 * pre-change build to `data-atlas-ready` and asserts nothing.
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

import {
  artifactTierKey,
  type ArtifactTier,
  type FixtureCatalog,
} from './atlas-browser-fixture';
import {
  atlasLongFrames,
  bytesLedger,
  chunkFramesFrom,
  firstMarkTime,
  ledgerMarkdown,
  medianOrNull,
  revealStats,
  scaleCriticalPath,
  workerStepsFrom,
  type LedgerRow,
  type LoafRecord,
  type LongFrameSummary,
  type MilestoneTimes,
  type NetworkRecord,
  type ScaledTimeline,
  type TimingEntry,
} from './support/cold-load-analysis';
import {
  COLD_LOAD_PROFILES,
  COLD_LOAD_RUNS,
  QUIET_PERIOD_MS,
  type ColdLoadProfile,
} from './support/cold-load-profiles';
import { CdpConnection, browserWebSocketUrl } from './support/cdp-connection';
import { assertProductionBuild } from './support/production-build';

const MODE: 'baseline' | 'current' =
  process.env.ATLAS_COLD_LOAD_BASELINE === '1' ? 'baseline' : 'current';
const CDP_PORT = Number(process.env.ATLAS_COLD_LOAD_CDP_PORT ?? '9333');
const SOFTWARE_RENDERER = /swiftshader|software|llvmpipe/i;
const BLOCKED_TILES = '*tile.openstreetmap.org*';
const CRITICAL_TIERS: readonly ArtifactTier[] = [
  'grid',
  'render',
  'observations',
];
const SURFACE_WORKER_STEPS = [
  'verify-grid',
  'decode-grid',
  'topology',
  'verify-render',
  'decode-render',
  'mesh',
  'support',
];
const REQUIRED_MARKS = [
  'observations-visible',
  'surface-first-chunk',
  'surface-visible',
  'ready',
  'edges-ready',
  'context-ready',
] as const;
const SETTLED_ATTRIBUTES =
  MODE === 'current'
    ? ['data-atlas-ready', 'data-atlas-edges-ready', 'data-atlas-context-ready']
    : ['data-atlas-ready'];

interface ColdLoadProbe {
  loaf: LoafRecord[];
  attributes: Record<string, number>;
  errors: string[];
}

interface PageMeasurements {
  marks: TimingEntry[];
  measures: TimingEntry[];
  resources: { name: string; responseEnd: number }[];
  navigationResponseEnd: number;
  loaf: LoafRecord[];
  attributes: Record<string, number>;
  probeErrors: string[];
  renderer: string;
  preloads: string[];
  catalogText: string | null;
  documentUrl: string;
  origin: string;
  errorText: string | null;
  collectedAt: number;
}

interface WorkerThrottleReport {
  targets: number;
  throttled: number;
  refusals: string[];
}

type Outcome = 'settled' | 'error' | 'timeout';

interface ColdLoadRun {
  index: number;
  outcome: Outcome;
  renderer: string;
  workerThrottle: WorkerThrottleReport | null;
  workerScale: number;
  raw: MilestoneTimes & {
    valuesReady: number | null;
    edgesReady: number | null;
    contextReady: number | null;
  };
  scaled: ScaledTimeline | null;
  reveal: { frames: number; totalMs: number; longestFrameMs: number } | null;
  longFrames: LongFrameSummary;
  transport: {
    tier: string;
    url: string | null;
    contentEncoding: string | null;
  }[];
  preloads: { url: string; requests: number }[];
  ledger: LedgerRow[];
  network: NetworkRecord[];
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
    catalogText: document.getElementById('atlas-catalog')?.textContent ?? null,
    documentUrl: location.href,
    origin: location.origin,
    errorText: document.querySelector('.atlas-error')?.textContent ?? null,
    collectedAt: performance.now(),
  };
}

interface CdpInitiator {
  url?: string;
  stack?: CdpStackTrace;
}

interface CdpStackTrace {
  callFrames: { url: string }[];
  parent?: CdpStackTrace;
}

function initiatorUrl(initiator: CdpInitiator | undefined): string | null {
  if (initiator?.url) return initiator.url;
  for (let stack = initiator?.stack; stack; stack = stack.parent) {
    const frame = stack.callFrames.find((candidate) => candidate.url !== '');
    if (frame) return frame.url;
  }
  return null;
}

function trackNetwork(
  cdp: CdpConnection,
  sessionId: string,
): { records(): NetworkRecord[]; dispose(): void } {
  const urls = new Map<string, string>();
  const records = new Map<string, NetworkRecord>();
  const recordFor = (requestId: string): NetworkRecord | null => {
    const url = urls.get(requestId);
    return url === undefined ? null : (records.get(url) ?? null);
  };
  const subscriptions = [
    cdp.on('Network.requestWillBeSent', (params, source) => {
      if (source !== sessionId) return;
      const event = params as {
        requestId: string;
        request: { url: string };
        initiator?: CdpInitiator;
      };
      urls.set(event.requestId, event.request.url);
      const record = records.get(event.request.url) ?? {
        url: event.request.url,
        requests: 0,
        encodedBytes: 0,
        contentEncoding: null,
        status: null,
        failure: null,
        initiatorUrl: initiatorUrl(event.initiator),
      };
      record.requests += 1;
      records.set(record.url, record);
    }),
    cdp.on('Network.requestServedFromCache', (params, source) => {
      if (source !== sessionId) return;
      const record = recordFor((params as { requestId: string }).requestId);
      if (record) record.requests -= 1;
    }),
    cdp.on('Network.responseReceived', (params, source) => {
      if (source !== sessionId) return;
      const event = params as {
        requestId: string;
        response: { status: number; headers: Record<string, string> };
      };
      const record = recordFor(event.requestId);
      if (!record) return;
      record.status = event.response.status;
      const encoding = Object.entries(event.response.headers).find(
        ([name]) => name.toLowerCase() === 'content-encoding',
      );
      record.contentEncoding = encoding
        ? encoding[1].trim().toLowerCase()
        : null;
    }),
    cdp.on('Network.loadingFinished', (params, source) => {
      if (source !== sessionId) return;
      const event = params as { requestId: string; encodedDataLength: number };
      const record = recordFor(event.requestId);
      if (record) record.encodedBytes += event.encodedDataLength;
    }),
    cdp.on('Network.loadingFailed', (params, source) => {
      if (source !== sessionId) return;
      const event = params as {
        requestId: string;
        errorText: string;
        blockedReason?: string;
      };
      const record = recordFor(event.requestId);
      if (record)
        record.failure = event.blockedReason
          ? `${event.errorText} (${event.blockedReason})`
          : event.errorText;
    }),
  ];
  return {
    records: () => [...records.values()].map((record) => ({ ...record })),
    dispose: () => {
      for (const unsubscribe of subscriptions) unsubscribe();
    },
  };
}

function throttleWorkers(
  cdp: CdpConnection,
  pageSession: string,
  rate: number,
): { report(): WorkerThrottleReport; dispose(): void } {
  const report: WorkerThrottleReport = {
    targets: 0,
    throttled: 0,
    refusals: [],
  };
  const dispose = cdp.on('Target.attachedToTarget', (params, source) => {
    if (source !== pageSession) return;
    const event = params as {
      sessionId: string;
      targetInfo: { type: string; url: string };
      waitingForDebugger: boolean;
    };
    void (async () => {
      if (event.targetInfo.type === 'worker') {
        report.targets += 1;
        try {
          await cdp.send(
            'Emulation.setCPUThrottlingRate',
            { rate },
            event.sessionId,
          );
          report.throttled += 1;
        } catch (error) {
          report.refusals.push(
            `${event.targetInfo.url}: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
      }
      if (event.waitingForDebugger)
        await cdp
          .send('Runtime.runIfWaitingForDebugger', {}, event.sessionId)
          .catch(() => undefined);
    })();
  });
  return { report: () => report, dispose };
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

function analyseRun(args: {
  index: number;
  profile: ColdLoadProfile;
  measurements: PageMeasurements;
  records: NetworkRecord[];
  workerThrottle: WorkerThrottleReport | null;
  pageErrors: string[];
  outcome: Outcome;
}): ColdLoadRun {
  const { profile, measurements: m, records } = args;
  const catalog = m.catalogText
    ? (JSON.parse(m.catalogText) as FixtureCatalog)
    : null;
  const selected = catalog?.artifacts[0] ?? null;
  const artifactKey = selected
    ? `${selected.id}:${selected.model_version}:${selected.data_version}`
    : null;
  const mark = (name: string): number | null =>
    firstMarkTime(m.marks, `atlas:${name}`);
  const raw =
    MODE === 'current'
      ? {
          observationsVisible: mark('observations-visible'),
          surfaceFirstChunk: mark('surface-first-chunk'),
          surfaceVisible: mark('surface-visible'),
          ready: mark('ready'),
          valuesReady: mark('values-ready'),
          edgesReady: mark('edges-ready'),
          contextReady: mark('context-ready'),
        }
      : {
          observationsVisible: null,
          surfaceFirstChunk: null,
          surfaceVisible: null,
          ready: m.attributes['data-atlas-ready'] ?? null,
          valuesReady: null,
          edgesReady: null,
          contextReady: null,
        };
  const steps = artifactKey ? workerStepsFrom(m.measures, artifactKey) : [];
  const frames = artifactKey ? chunkFramesFrom(m.measures, artifactKey) : [];
  const throttle = args.workerThrottle;
  const everyWorkerThrottled =
    throttle !== null &&
    throttle.targets > 0 &&
    throttle.throttled === throttle.targets;
  const workerScale =
    profile.cpuThrottlingRate > 1 && !everyWorkerThrottled
      ? profile.cpuThrottlingRate
      : 1;
  const scaled =
    MODE === 'current' && profile.cpuThrottlingRate > 1
      ? scaleCriticalPath({ factor: workerScale, steps, frames, marks: raw })
      : null;
  const settledAt =
    MODE === 'current'
      ? Math.max(raw.edgesReady ?? 0, raw.contextReady ?? 0)
      : (raw.ready ?? 0);
  const longFrames = atlasLongFrames(m.loaf, frames, {
    origin: m.origin,
    documentUrl: m.documentUrl,
    windowEndMs: settledAt > 0 ? settledAt + QUIET_PERIOD_MS : m.collectedAt,
  });
  const recordFor = (url: string): NetworkRecord | null =>
    records.find((record) => record.url === url) ?? null;
  const tierUrls =
    catalog && selected
      ? CRITICAL_TIERS.map((tier) => {
          const key = artifactTierKey(catalog, selected.id, tier);
          return {
            tier: tier as string,
            url: m.preloads.find((href) => href.endsWith(`/${key}`)) ?? null,
          };
        })
      : records
          .filter((record) =>
            /\.(surface|observations)\.json(?:$|\?)/.test(record.url),
          )
          .map((record) => ({
            tier: record.url.includes('.surface.')
              ? 'surface-json'
              : 'observations-json',
            url: record.url as string | null,
          }));
  const responseEnds = new Map<string, number>([
    [m.documentUrl, m.navigationResponseEnd],
    ...m.resources.map((entry) => [entry.name, entry.responseEnd] as const),
  ]);
  const urlsFor = (tiers: string[]): string[] =>
    tierUrls.flatMap((entry) =>
      tiers.includes(entry.tier) && entry.url !== null ? [entry.url] : [],
    );
  const ledger = bytesLedger({
    network: profile.network,
    documentUrl: m.documentUrl,
    records,
    responseEnds,
    loafs: m.loaf,
    steps:
      scaled?.steps ??
      steps.map((step) => ({
        ...step,
        scaledStart: step.start,
        scaledEnd: step.end,
      })),
    milestones:
      MODE === 'current'
        ? [
            {
              name: 'observations-visible',
              observedMs: raw.observationsVisible,
              scaledMs: scaled?.marks.observationsVisible ?? null,
              budgetMs: profile.budgets.observationsVisibleMs,
              tierUrls: urlsFor(['observations']),
              workerSteps: [],
            },
            {
              name: 'surface-visible',
              observedMs: raw.surfaceVisible,
              scaledMs: scaled?.marks.surfaceVisible ?? null,
              budgetMs: profile.budgets.surfaceVisibleMs,
              tierUrls: urlsFor(['grid', 'render']),
              workerSteps: SURFACE_WORKER_STEPS,
            },
          ]
        : [
            {
              name: 'ready (baseline)',
              observedMs: raw.ready,
              scaledMs: null,
              budgetMs: profile.budgets.surfaceVisibleMs,
              tierUrls: urlsFor(['surface-json', 'observations-json']),
              workerSteps: [],
            },
          ],
  });
  const runErrors = [
    ...args.pageErrors.map((message) => `pageerror: ${message}`),
    ...m.probeErrors,
    ...(args.outcome === 'settled'
      ? []
      : [
          `run ended in ${args.outcome}${m.errorText ? `: ${m.errorText.trim()}` : ''}`,
        ]),
    ...records
      .filter((record) => !record.url.includes('tile.openstreetmap.org'))
      .flatMap((record) => [
        ...(record.failure === null
          ? []
          : [`request failed: ${record.url} (${record.failure})`]),
        ...(record.status !== null && record.status >= 400
          ? [`HTTP ${record.status}: ${record.url}`]
          : []),
      ]),
    ...(MODE === 'current'
      ? [
          ...REQUIRED_MARKS.filter((name) => mark(name) === null).map(
            (name) => `missing mark atlas:${name}`,
          ),
          ...tierUrls
            .filter((entry) => entry.url === null)
            .map((entry) => `no preload link for the ${entry.tier} tier`),
        ]
      : []),
  ];
  return {
    index: args.index,
    outcome: args.outcome,
    renderer: m.renderer,
    workerThrottle: throttle,
    workerScale,
    raw,
    scaled,
    reveal: revealStats(frames),
    longFrames,
    transport: tierUrls.map((entry) => ({
      ...entry,
      contentEncoding: entry.url
        ? (recordFor(entry.url)?.contentEncoding ?? null)
        : null,
    })),
    preloads: m.preloads.map((url) => ({
      url,
      requests: recordFor(url)?.requests ?? 0,
    })),
    ledger,
    network: records,
    errors: runErrors,
  };
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

function summarise(runs: readonly ColdLoadRun[]) {
  const scaledInUse = runs.some((run) => run.workerScale > 1);
  const pick =
    (name: keyof MilestoneTimes) =>
    (run: ColdLoadRun): number | null =>
      scaledInUse ? (run.scaled?.marks[name] ?? null) : run.raw[name];
  const reveal = (run: ColdLoadRun): number | null => {
    const first = pick('surfaceFirstChunk')(run);
    const visible = pick('surfaceVisible')(run);
    return first === null || visible === null ? null : visible - first;
  };
  return {
    timesAre: scaledInUse ? 'worker-scaled critical path' : 'observed',
    observationsVisibleMs: medianOrNull(runs.map(pick('observationsVisible'))),
    surfaceFirstChunkMs: medianOrNull(runs.map(pick('surfaceFirstChunk'))),
    surfaceVisibleMs: medianOrNull(runs.map(pick('surfaceVisible'))),
    readyMs: medianOrNull(runs.map(pick('ready'))),
    rawObservationsVisibleMs: medianOrNull(
      runs.map((run) => run.raw.observationsVisible),
    ),
    rawSurfaceVisibleMs: medianOrNull(
      runs.map((run) => run.raw.surfaceVisible),
    ),
    rawReadyMs: medianOrNull(runs.map((run) => run.raw.ready)),
    revealMs: medianOrNull(runs.map(reveal)),
    revealFrames: medianOrNull(runs.map((run) => run.reveal?.frames ?? null)),
    revealTotalMs: medianOrNull(runs.map((run) => run.reveal?.totalMs ?? null)),
    longestRevealFrameMs: medianOrNull(
      runs.map((run) => run.reveal?.longestFrameMs ?? null),
    ),
    maxAtlasFrameMs: medianOrNull(
      runs.map((run) => run.longFrames.maxAtlasFrameMs),
    ),
    cesiumEvalMs: medianOrNull(runs.map((run) => run.longFrames.cesiumEvalMs)),
    workerThrottleRefusals: runs.flatMap(
      (run) => run.workerThrottle?.refusals ?? [],
    ),
  };
}

function medianRun(runs: readonly ColdLoadRun[]): ColdLoadRun {
  const time = (run: ColdLoadRun): number =>
    (MODE === 'current'
      ? (run.scaled?.marks.surfaceVisible ?? run.raw.surfaceVisible)
      : run.raw.ready) ?? Number.POSITIVE_INFINITY;
  const sorted = [...runs].sort((left, right) => time(left) - time(right) || 0);
  return sorted[Math.floor(sorted.length / 2)];
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
    const browser = await chromium.launch({
      channel: 'chrome',
      headless: false,
      args: [`--remote-debugging-port=${CDP_PORT}`],
    });
    const cdp = await CdpConnection.open(await browserWebSocketUrl(CDP_PORT));
    try {
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
        medianRun(runs).ledger,
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
          .toEqual(run.transport.map((transfer) => transfer.url).sort());
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
      cdp.close();
      await browser.close();
    }
  });
}
