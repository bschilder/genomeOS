/** Unit tests for one cold-load run's accounting and verdict (fast-load design §B.1). */
import { describe, expect, it } from 'vitest';

import type { FixtureCatalog } from './atlas-browser-fixture';
import { CdpConnection, type CdpSocket } from './support/cdp-connection';
import type { NetworkRecord, TimingEntry } from './support/cold-load-analysis';
import {
  COLD_LOAD_PROFILES,
  type ColdLoadProfileName,
} from './support/cold-load-profiles';
import {
  analyseRun,
  medianRun,
  summarise,
  throttleWorkers,
  trackNetwork,
  type ColdLoadMode,
  type ColdLoadRun,
  type PageMeasurements,
  type WorkerThrottleReport,
} from './support/cold-load-run';

class FakeSocket implements CdpSocket {
  sent: Record<string, unknown>[] = [];
  #message: ((data: string) => void) | undefined;
  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }
  close(): void {}
  onMessage(listener: (data: string) => void): void {
    this.#message = listener;
  }
  onClose(): void {}
  deliver(message: object): void {
    this.#message?.(JSON.stringify(message));
  }
}

/** Lets settled CDP commands reach their awaiting handlers. */
const flush = (): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, 0));

const ORIGIN = 'http://127.0.0.1:4322';
const DOCUMENT = `${ORIGIN}/app/`;
const BASE = `${ORIGIN}/data/atlas/`;
const WORKER = `${ORIGIN}/_astro/atlas-data.worker-Cz6HvHII.js`;
const ARTIFACT_KEY = 'hbs-rs334:m2:d3';
const GRID_KEY = 'grids/h3-r4.3bd2d6da9386f5ce.gosa';
const RENDER_KEY = 'surfaces/hbs-rs334/m2/d3/render.0011223344556677.gosa';
const OBSERVATIONS_KEY = 'hbs-rs334.observations.json';
const TIER_URLS = [GRID_KEY, RENDER_KEY, OBSERVATIONS_KEY].map(
  (key) => `${BASE}${key}`,
);

const CATALOG: FixtureCatalog = {
  grids: { g: { url: GRID_KEY } },
  artifacts: [
    {
      id: 'hbs-rs334',
      model_version: 'm2',
      data_version: 'd3',
      surface_url: 'hbs-rs334.surface.json',
      observations_url: OBSERVATIONS_KEY,
      downloads: {
        manifest: { url: 'hbs-rs334.manifest.json' },
        observations: null,
        surface: { url: 'hbs-rs334.surface.json' },
      },
      web: {
        grid_sha256: 'g',
        render: { url: RENDER_KEY },
        detail: {
          url: 'surfaces/hbs-rs334/m2/d3/detail.8899aabbccddeeff.gosa',
        },
      },
    },
  ],
};

const profile = (name: ColdLoadProfileName) => {
  const found = COLD_LOAD_PROFILES.find((candidate) => candidate.name === name);
  if (found === undefined) throw new Error(`no profile ${name}`);
  return found;
};

const mark = (name: string, startTime: number): TimingEntry => ({
  name: `atlas:${name}`,
  startTime,
  duration: 0,
  detail: null,
});

const step = (
  name: string,
  start: number,
  end: number,
  chunk: number | null = null,
  artifactKey: string | null = ARTIFACT_KEY,
): TimingEntry => ({
  name: `atlas:worker:${name}`,
  startTime: start,
  duration: end - start,
  detail: { step: name, chunk, artifactKey },
});

const chunkFrame = (
  chunks: number[],
  start: number,
  end: number,
): TimingEntry => ({
  name: 'atlas:chunk-frame',
  startTime: start,
  duration: end - start,
  detail: { artifactKey: ARTIFACT_KEY, chunks },
});

const MARKS: TimingEntry[] = [
  mark('observations-visible', 300),
  mark('surface-first-chunk', 600),
  mark('surface-visible', 900),
  mark('ready', 905),
  mark('edges-ready', 1_200),
  mark('context-ready', 1_300),
  mark('values-ready', 1_500),
];

const SHARED_STEPS: TimingEntry[] = [
  step('verify-grid', 100, 110, null, null),
  step('decode-grid', 110, 120, null, null),
  step('topology', 120, 160, null, null),
  step('verify-render', 200, 210),
  step('decode-render', 210, 220),
];

const CHUNK_STEPS: TimingEntry[] = [
  step('mesh', 300, 340, 0),
  step('support', 340, 350, 0),
  step('mesh', 350, 450, 1),
  step('support', 450, 460, 1),
];

const FRAMES: TimingEntry[] = [
  chunkFrame([0], 580, 600),
  chunkFrame([1], 880, 900),
];

function measurements(
  overrides: Partial<PageMeasurements> = {},
): PageMeasurements {
  return {
    marks: MARKS,
    measures: [
      ...SHARED_STEPS,
      ...CHUNK_STEPS,
      // Another artifact's chunk: never charged to this one.
      step('mesh', 470, 2_000, 0, 'g6pd-deficiency:m1:d1'),
      ...FRAMES,
    ],
    resources: TIER_URLS.map((name, index) => ({
      name,
      responseEnd: 150 + index * 50,
    })),
    navigationResponseEnd: 50,
    loaf: [],
    attributes: { 'data-atlas-ready': 905 },
    probeErrors: [],
    renderer:
      'ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)',
    preloads: TIER_URLS,
    catalogText: JSON.stringify(CATALOG),
    documentUrl: DOCUMENT,
    origin: ORIGIN,
    errorText: null,
    collectedAt: 2_400,
    ...overrides,
  };
}

const networkRecord = (url: string): NetworkRecord => ({
  url,
  requests: 1,
  encodedBytes: 10_000,
  contentEncoding: 'gzip',
  status: 200,
  failure: null,
  initiatorUrl: null,
});

const REFUSED: WorkerThrottleReport = {
  targets: 2,
  throttled: 0,
  refusals: [
    `${WORKER}: Emulation.setCPUThrottlingRate: Operation is only supported for pages, not workers`,
  ],
  paused: [],
  resumeFailures: [],
};

const THROTTLED: WorkerThrottleReport = {
  targets: 2,
  throttled: 2,
  refusals: [],
  paused: [],
  resumeFailures: [],
};

function run(
  args: {
    mode?: ColdLoadMode;
    name?: ColdLoadProfileName;
    measured?: Partial<PageMeasurements>;
    records?: NetworkRecord[];
    workerThrottle?: WorkerThrottleReport | null;
    index?: number;
  } = {},
): ColdLoadRun {
  const name = args.name ?? 'mobile-fast-4g';
  return analyseRun({
    mode: args.mode ?? 'current',
    index: args.index ?? 0,
    profile: profile(name),
    measurements: measurements(args.measured),
    records: args.records ?? TIER_URLS.map(networkRecord),
    workerThrottle:
      args.workerThrottle === undefined
        ? name === 'desktop'
          ? null
          : REFUSED
        : args.workerThrottle,
    pageErrors: [],
    outcome: 'settled',
  });
}

/** A copy of `base` with other surface-visible times. */
function withSurfaceVisible(
  base: ColdLoadRun,
  raw: number | null,
  scaled: number | null,
): ColdLoadRun {
  return {
    ...base,
    raw: { ...base.raw, surfaceVisible: raw },
    scaled:
      base.scaled === null
        ? null
        : {
            ...base.scaled,
            marks: { ...base.scaled.marks, surfaceVisible: scaled },
          },
  };
}

describe('analyseRun', () => {
  it('charges the catalog artifact steps and scales unthrottled workers ×4', () => {
    const result = run();
    expect(result.errors).toEqual([]);
    expect(result.workersThrottled).toBe(false);
    expect(result.workerScale).toBe(4);
    expect(result.scaled?.factor).toBe(4);
    // Five grid and render steps plus mesh and support for two chunks; the
    // other artifact's mesh is not among them.
    expect(result.scaled?.steps).toHaveLength(9);
    expect(result.scaled?.marks.surfaceVisible).toBeGreaterThan(900);
    expect(result.raw.surfaceVisible).toBe(900);
    expect(result.reveal).toEqual({
      frames: 2,
      totalMs: 320,
      longestFrameMs: 20,
    });
  });

  it('keeps observed times when every worker took the throttle, and on desktop', () => {
    const throttled = run({ workerThrottle: THROTTLED });
    expect(throttled.workersThrottled).toBe(true);
    expect(throttled.workerScale).toBe(1);
    expect(throttled.scaled?.marks.surfaceVisible).toBe(900);
    expect(throttled.errors).toEqual([]);

    const desktop = run({ name: 'desktop' });
    expect(desktop.workersThrottled).toBeNull();
    expect(desktop.workerScale).toBe(1);
    expect(desktop.scaled).toBeNull();
    expect(desktop.errors).toEqual([]);
  });

  it('counts a page with no attached worker as unthrottled', () => {
    const result = run({
      workerThrottle: { ...THROTTLED, targets: 0, throttled: 0 },
    });
    expect(result.workersThrottled).toBe(false);
    expect(result.workerScale).toBe(4);
  });

  it('reports missing surface worker steps instead of scaling without them', () => {
    const result = run({
      measured: {
        measures: [
          ...SHARED_STEPS.filter(
            (entry) => entry.name !== 'atlas:worker:decode-render',
          ),
          ...CHUNK_STEPS.filter(
            (entry) =>
              !(
                entry.name === 'atlas:worker:support' &&
                (entry.detail as { chunk: number }).chunk === 1
              ),
          ),
          ...FRAMES,
        ],
      },
    });
    expect(result.errors).toEqual([
      `missing worker step atlas:worker:decode-render for ${ARTIFACT_KEY}`,
      `chunks 1 of ${ARTIFACT_KEY} were revealed without an atlas:worker:support step`,
    ]);
  });

  it('reports steps posted under another artifact key', () => {
    const result = run({
      measured: {
        measures: [
          ...SHARED_STEPS,
          ...CHUNK_STEPS.map((entry) => ({
            ...entry,
            detail: {
              ...(entry.detail as object),
              artifactKey: 'hbs-rs334:m2',
            },
          })),
          ...FRAMES,
        ],
      },
    });
    expect(result.errors).toEqual([
      `missing worker step atlas:worker:mesh for ${ARTIFACT_KEY}`,
      `missing worker step atlas:worker:support for ${ARTIFACT_KEY}`,
      `chunks 0, 1 of ${ARTIFACT_KEY} were revealed without an atlas:worker:mesh step`,
      `chunks 0, 1 of ${ARTIFACT_KEY} were revealed without an atlas:worker:support step`,
    ]);
  });

  it('reports missing or partial chunk frames', () => {
    const none = run({
      measured: { measures: [...SHARED_STEPS, ...CHUNK_STEPS] },
    });
    expect(none.errors).toEqual([
      `missing atlas:chunk-frame measures for ${ARTIFACT_KEY}`,
    ]);
    expect(none.reveal).toBeNull();

    const partial = run({
      measured: {
        measures: [...SHARED_STEPS, ...CHUNK_STEPS, FRAMES[0]],
      },
    });
    expect(partial.errors).toEqual([
      `chunks 1 of ${ARTIFACT_KEY} were meshed but are in no atlas:chunk-frame measure`,
    ]);
  });

  it('reports a page without its inline catalog', () => {
    const result = run({ measured: { catalogText: null } });
    expect(result.errors).toContain(
      'no inline #atlas-catalog: worker steps, chunk frames and tier URLs cannot be attributed',
    );
  });

  it('reports a target that was not resumed or is still paused', () => {
    const result = run({
      workerThrottle: {
        ...REFUSED,
        paused: [`worker ${ORIGIN}/cesium/Workers/transferTypedArrayTest.js`],
        resumeFailures: [
          `worker ${WORKER}: Runtime.runIfWaitingForDebugger: Target closed`,
        ],
      },
    });
    expect(result.errors).toEqual([
      `target not resumed: worker ${WORKER}: Runtime.runIfWaitingForDebugger: Target closed`,
      `target still paused (Runtime.runIfWaitingForDebugger unanswered): worker ${ORIGIN}/cesium/Workers/transferTypedArrayTest.js`,
    ]);
  });

  it('measures a baseline to data-atlas-ready with observed times', () => {
    const surfaceJson = `${BASE}hbs-rs334.surface.json`;
    const observationsJson = `${BASE}hbs-rs334.observations.json`;
    const result = run({
      mode: 'baseline',
      measured: {
        marks: [],
        measures: [],
        preloads: [],
        catalogText: null,
        attributes: { 'data-atlas-ready': 4_200 },
      },
      records: [surfaceJson, observationsJson].map(networkRecord),
    });
    expect(result.errors).toEqual([]);
    expect(result.workersThrottled).toBe(false);
    expect(result.workerScale).toBe(1);
    expect(result.scaled).toBeNull();
    expect(result.raw.ready).toBe(4_200);
    expect(result.transport.map((entry) => entry.tier)).toEqual([
      'surface-json',
      'observations-json',
    ]);
    expect(result.ledger.map((row) => row.milestone)).toEqual([
      'ready (baseline)',
    ]);
  });
});

describe('summarise', () => {
  it('judges the scaled critical path when workers ran unthrottled', () => {
    const base = run();
    const runs = [
      withSurfaceVisible(base, 900, 1_080),
      withSurfaceVisible(base, 950, 1_200),
      withSurfaceVisible(base, 1_000, 1_100),
    ];
    const summary = summarise(runs);
    expect(summary.timesAre).toBe('worker-scaled critical path');
    expect(summary.surfaceVisibleMs).toBe(1_100);
    expect(summary.rawSurfaceVisibleMs).toBe(950);
    expect(summary.workerThrottleRefusals).toHaveLength(3);
  });

  it('reports observed times on desktop', () => {
    const base = run({ name: 'desktop' });
    const summary = summarise([
      withSurfaceVisible(base, 900, null),
      withSurfaceVisible(base, 950, null),
      withSurfaceVisible(base, 1_000, null),
    ]);
    expect(summary.timesAre).toBe('observed');
    expect(summary.surfaceVisibleMs).toBe(950);
  });

  it('keeps a baseline on observed times even when its workers were not throttled', () => {
    const baseline = (ready: number, index: number): ColdLoadRun =>
      run({
        mode: 'baseline',
        index,
        measured: {
          marks: [],
          measures: [],
          preloads: [],
          catalogText: null,
          attributes: { 'data-atlas-ready': ready },
        },
        records: [],
      });
    const runs = [baseline(4_200, 0), baseline(3_900, 1), baseline(5_000, 2)];
    const summary = summarise(runs);
    expect(summary.timesAre).toBe('observed, workers unthrottled');
    expect(summary.readyMs).toBe(4_200);
    expect(summary.rawReadyMs).toBe(4_200);
    expect(summary.surfaceVisibleMs).toBeNull();
    expect(medianRun(runs, 'baseline').index).toBe(0);
  });
});

describe('medianRun', () => {
  it('picks the median by the judged surface-visible time; a run without it sorts last', () => {
    const base = run();
    const runs = [
      { ...withSurfaceVisible(base, 900, 1_080), index: 0 },
      { ...withSurfaceVisible(base, 950, 1_200), index: 1 },
      { ...withSurfaceVisible(base, 1_000, 1_100), index: 2 },
    ];
    expect(medianRun(runs, 'current').index).toBe(2);
    const failed = { ...withSurfaceVisible(base, null, null), index: 3 };
    expect(medianRun([failed, runs[1], runs[0]], 'current').index).toBe(1);
  });
});

describe('trackNetwork', () => {
  it('counts network requests and encoded bytes per URL from the page session only', () => {
    const socket = new FakeSocket();
    const cdp = new CdpConnection(socket);
    const network = trackNetwork(cdp, 'page');
    const grid = TIER_URLS[0];
    const tile = 'https://a.tile.openstreetmap.org/1/0/0.png';
    const script = `${ORIGIN}/_astro/client.Ab12.js`;
    const event = (method: string, params: object, sessionId = 'page') =>
      socket.deliver({ method, params, sessionId });

    event('Network.requestWillBeSent', {
      requestId: 'r1',
      request: { url: grid },
      initiator: {
        type: 'script',
        stack: {
          callFrames: [{ url: '' }],
          parent: { callFrames: [{ url: script }] },
        },
      },
    });
    event('Network.responseReceived', {
      requestId: 'r1',
      response: { status: 200, headers: { 'Content-Encoding': ' GZIP ' } },
    });
    event('Network.loadingFinished', {
      requestId: 'r1',
      encodedDataLength: 1_000,
    });
    // A memory-cache hit is announced but is not a network request.
    event('Network.requestWillBeSent', {
      requestId: 'r2',
      request: { url: grid },
    });
    event('Network.requestServedFromCache', { requestId: 'r2' });
    event('Network.loadingFinished', { requestId: 'r2', encodedDataLength: 0 });
    event('Network.requestWillBeSent', {
      requestId: 'r3',
      request: { url: tile },
    });
    event('Network.loadingFailed', {
      requestId: 'r3',
      errorText: 'net::ERR_BLOCKED_BY_CLIENT',
      blockedReason: 'inspector',
    });
    event(
      'Network.requestWillBeSent',
      { requestId: 'r4', request: { url: grid } },
      'other-page',
    );

    expect(network.records()).toEqual([
      {
        url: grid,
        requests: 1,
        encodedBytes: 1_000,
        contentEncoding: 'gzip',
        status: 200,
        failure: null,
        initiatorUrl: script,
      },
      {
        url: tile,
        requests: 1,
        encodedBytes: 0,
        contentEncoding: null,
        status: null,
        failure: 'net::ERR_BLOCKED_BY_CLIENT (inspector)',
        initiatorUrl: null,
      },
    ]);

    network.dispose();
    event('Network.requestWillBeSent', {
      requestId: 'r5',
      request: { url: grid },
    });
    expect(network.records()[0].requests).toBe(1);
  });
});

describe('throttleWorkers', () => {
  const attach = (
    socket: FakeSocket,
    sessionId: string,
    type: string,
    url: string,
    parent = 'page',
  ) =>
    socket.deliver({
      method: 'Target.attachedToTarget',
      sessionId: parent,
      params: {
        sessionId,
        targetInfo: { type, url },
        waitingForDebugger: true,
      },
    });

  it('throttles each worker, then resumes it, and records refusals', async () => {
    const socket = new FakeSocket();
    const workers = throttleWorkers(new CdpConnection(socket), 'page', 4);
    attach(socket, 'w1', 'worker', WORKER);
    attach(socket, 'w9', 'worker', WORKER, 'other-page');
    expect(socket.sent).toEqual([
      {
        id: 1,
        method: 'Emulation.setCPUThrottlingRate',
        params: { rate: 4 },
        sessionId: 'w1',
      },
    ]);
    expect(workers.report().paused).toEqual([`worker ${WORKER}`]);

    socket.deliver({
      id: 1,
      error: { message: 'Operation is only supported for pages, not workers' },
    });
    await flush();
    expect(socket.sent[1]).toEqual({
      id: 2,
      method: 'Runtime.runIfWaitingForDebugger',
      params: {},
      sessionId: 'w1',
    });
    socket.deliver({ id: 2, result: {} });
    await flush();
    expect(workers.report()).toEqual({
      targets: 1,
      throttled: 0,
      refusals: [
        `${WORKER}: Emulation.setCPUThrottlingRate: Operation is only supported for pages, not workers`,
      ],
      paused: [],
      resumeFailures: [],
    });
  });

  it('reports a failed resume and a resume that never answers', async () => {
    const socket = new FakeSocket();
    const workers = throttleWorkers(new CdpConnection(socket), 'page', 4);
    attach(socket, 'w1', 'worker', WORKER);
    socket.deliver({ id: 1, result: {} });
    await flush();
    socket.deliver({ id: 2, error: { message: 'Target closed' } });
    await flush();
    attach(socket, 'f1', 'iframe', `${ORIGIN}/frame.html`);
    await flush();
    expect(socket.sent.at(-1)).toEqual({
      id: 3,
      method: 'Runtime.runIfWaitingForDebugger',
      params: {},
      sessionId: 'f1',
    });
    expect(workers.report()).toEqual({
      targets: 1,
      throttled: 1,
      refusals: [],
      paused: [`iframe ${ORIGIN}/frame.html`],
      resumeFailures: [
        `worker ${WORKER}: Runtime.runIfWaitingForDebugger: Target closed`,
      ],
    });
  });

  it('does not report a target that detached before its resume answered', async () => {
    const socket = new FakeSocket();
    const workers = throttleWorkers(new CdpConnection(socket), 'page', 4);
    attach(socket, 'w1', 'worker', WORKER);
    socket.deliver({ id: 1, result: {} });
    await flush();
    socket.deliver({
      method: 'Target.detachedFromTarget',
      sessionId: 'page',
      params: { sessionId: 'w1' },
    });
    await flush();
    expect(workers.report()).toEqual({
      targets: 1,
      throttled: 1,
      refusals: [],
      paused: [],
      resumeFailures: [],
    });

    workers.dispose();
    attach(socket, 'w2', 'worker', WORKER);
    expect(workers.report().targets).toBe(1);
  });
});
