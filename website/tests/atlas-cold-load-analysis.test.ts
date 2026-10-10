/** Unit tests for the cold-load analysis (fast-load design §B.1). */
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  atlasLongFrames,
  attributeScript,
  bytesLedger,
  chunkFramesFrom,
  firstMarkTime,
  ledgerMarkdown,
  median,
  medianOrNull,
  requestDepths,
  revealStats,
  scaleCriticalPath,
  workerStepsFrom,
  type ChunkFrame,
  type LoafRecord,
  type NetworkRecord,
  type WorkerStep,
} from './support/cold-load-analysis';
import {
  COLD_LOAD_PROFILES,
  COLD_LOAD_RUNS,
  FAST_4G,
  QUIET_PERIOD_MS,
  SLOW_4G,
} from './support/cold-load-profiles';

const ORIGIN = 'http://127.0.0.1:4322';
const DOCUMENT = `${ORIGIN}/app/`;
const CESIUM = `${ORIGIN}/_astro/cesium.Ab12_c.js`;
const ISLAND = `${ORIGIN}/_astro/AtlasExplorer.Xy9.js`;
const CONTEXT = { origin: ORIGIN, documentUrl: DOCUMENT };

function record(
  url: string,
  encodedBytes: number,
  initiatorUrl: string | null,
): NetworkRecord {
  return {
    url,
    requests: 1,
    encodedBytes,
    contentEncoding: 'gzip',
    status: 200,
    failure: null,
    initiatorUrl,
  };
}

describe('cold-load profiles', () => {
  it('pins the DevTools presets, the runs and the B.1 budgets', () => {
    expect(FAST_4G).toEqual({
      latency: 165,
      downloadThroughput: 1_012_500,
      uploadThroughput: 168_750,
    });
    expect(SLOW_4G).toEqual({
      latency: 562.5,
      downloadThroughput: 180_000,
      uploadThroughput: 84_375,
    });
    expect(COLD_LOAD_RUNS).toBe(3);
    expect(QUIET_PERIOD_MS).toBe(1_000);
    expect(
      COLD_LOAD_PROFILES.map((p) => [
        p.name,
        p.viewport,
        p.deviceScaleFactor,
        p.isMobile,
        p.hasTouch,
        p.cpuThrottlingRate,
        p.network,
        p.budgets,
      ]),
    ).toEqual([
      [
        'desktop',
        { width: 1440, height: 900 },
        1,
        false,
        false,
        1,
        null,
        {
          observationsVisibleMs: 1_500,
          surfaceVisibleMs: 2_500,
          atlasLongFrameMs: 200,
          revealMs: null,
        },
      ],
      [
        'mobile-fast-4g',
        { width: 390, height: 844 },
        3,
        true,
        true,
        4,
        FAST_4G,
        {
          observationsVisibleMs: 4_000,
          surfaceVisibleMs: 6_000,
          atlasLongFrameMs: 800,
          revealMs: 1_100,
        },
      ],
      [
        'mobile-slow-4g',
        { width: 390, height: 844 },
        3,
        true,
        true,
        4,
        SLOW_4G,
        {
          observationsVisibleMs: 12_000,
          surfaceVisibleMs: 17_500,
          atlasLongFrameMs: 800,
          revealMs: null,
        },
      ],
    ]);
  });
});

describe('medians and marks', () => {
  it('takes the middle of three runs and refuses a failed run', () => {
    expect(median([3_000, 1_000, 2_000])).toBe(2_000);
    expect(median([1, 2, 3, 4])).toBe(2.5);
    expect(median([])).toBeNull();
    expect(medianOrNull([1, null, 3])).toBeNull();
    expect(medianOrNull([4, 1, 9])).toBe(4);
  });

  it('uses the first occurrence of a mark', () => {
    const marks = [
      { name: 'atlas:ready', startTime: 900, duration: 0, detail: null },
      { name: 'atlas:ready', startTime: 700, duration: 0, detail: null },
    ];
    expect(firstMarkTime(marks, 'atlas:ready')).toBe(700);
    expect(firstMarkTime(marks, 'atlas:surface-visible')).toBeNull();
  });
});

describe('User Timing parsing', () => {
  it('keeps worker steps of the measured artifact and the shared grid', () => {
    const steps = workerStepsFrom(
      [
        {
          name: 'atlas:worker:mesh',
          startTime: 414,
          duration: 10,
          detail: {
            step: 'mesh',
            chunk: 0,
            artifactKey: 'hbs-rs334:v3:map-2026-08',
          },
        },
        {
          name: 'atlas:worker:topology',
          startTime: 115,
          duration: 20,
          detail: { step: 'topology', chunk: null, artifactKey: null },
        },
        {
          name: 'atlas:worker:mesh',
          startTime: 500,
          duration: 10,
          detail: {
            step: 'mesh',
            chunk: 0,
            artifactKey: 'g6pd-deficiency:v3:map-2026-08',
          },
        },
        {
          name: 'atlas:observations-visible',
          startTime: 1,
          duration: 0,
          detail: null,
        },
      ],
      'hbs-rs334:v3:map-2026-08',
    );
    expect(steps).toEqual([
      { step: 'topology', chunk: null, start: 115, end: 135 },
      { step: 'mesh', chunk: 0, start: 414, end: 424 },
    ]);
  });

  it('reads chunk frames and reveal statistics', () => {
    const frames = chunkFramesFrom(
      [
        {
          name: 'atlas:chunk-frame',
          startTime: 450,
          duration: 20,
          detail: { artifactKey: 'k', chunks: [1] },
        },
        {
          name: 'atlas:chunk-frame',
          startTime: 430,
          duration: 20,
          detail: { artifactKey: 'k', chunks: [0] },
        },
        {
          name: 'atlas:chunk-frame',
          startTime: 470,
          duration: 5,
          detail: { artifactKey: 'other', chunks: [0] },
        },
      ],
      'k',
    );
    expect(frames).toEqual([
      { chunks: [0], start: 430, end: 450 },
      { chunks: [1], start: 450, end: 470 },
    ]);
    expect(revealStats(frames)).toEqual({
      frames: 2,
      totalMs: 40,
      longestFrameMs: 20,
    });
    expect(revealStats([])).toBeNull();
  });
});

describe('long-animation-frame attribution', () => {
  it('attributes scripts by source URL and invoker', () => {
    const script = (
      sourceURL: string,
      invoker: string,
      invokerType: string,
    ) => ({ sourceURL, invoker, invokerType, startTime: 0, duration: 10 });
    expect(
      attributeScript(
        script(CESIUM, 'module', 'module-script'),
        CONTEXT,
        false,
      ),
    ).toBe('cesium-eval');
    expect(
      attributeScript(
        script(CESIUM, 'FrameRequestCallback', 'user-callback'),
        CONTEXT,
        false,
      ),
    ).toBe('cesium');
    expect(
      attributeScript(
        script(CESIUM, 'FrameRequestCallback', 'user-callback'),
        CONTEXT,
        true,
      ),
    ).toBe('atlas');
    expect(
      attributeScript(
        script(ISLAND, 'TimerHandler:setTimeout', 'user-callback'),
        CONTEXT,
        false,
      ),
    ).toBe('atlas');
    expect(
      attributeScript(
        script(DOCUMENT, 'inline', 'classic-script'),
        CONTEXT,
        false,
      ),
    ).toBe('atlas');
    expect(
      attributeScript(
        script('', 'MessagePort.onmessage', 'event-listener'),
        CONTEXT,
        false,
      ),
    ).toBe('atlas');
    expect(
      attributeScript(
        script('https://tile.openstreetmap.org/a.js', 'x', 'classic-script'),
        CONTEXT,
        false,
      ),
    ).toBe('other');
  });

  it('reports Atlas frames, excludes Cesium evaluation and frames outside the window', () => {
    const loafs: LoafRecord[] = [
      {
        startTime: 1_000,
        duration: 300,
        renderStart: 1_290,
        blockingDuration: 250,
        scripts: [
          {
            sourceURL: CESIUM,
            invoker: 'module',
            invokerType: 'module-script',
            startTime: 1_000,
            duration: 250,
          },
          {
            sourceURL: ISLAND,
            invoker: 'Worker.onmessage',
            invokerType: 'event-listener',
            startTime: 1_255,
            duration: 30,
          },
        ],
      },
      {
        startTime: 2_000,
        duration: 400,
        renderStart: 2_380,
        blockingDuration: 350,
        scripts: [
          {
            sourceURL: CESIUM,
            invoker: 'FrameRequestCallback',
            invokerType: 'user-callback',
            startTime: 2_010,
            duration: 350,
          },
        ],
      },
      {
        startTime: 3_000,
        duration: 260,
        renderStart: 3_250,
        blockingDuration: 210,
        scripts: [
          {
            sourceURL: CESIUM,
            invoker: 'FrameRequestCallback',
            invokerType: 'user-callback',
            startTime: 3_000,
            duration: 240,
          },
        ],
      },
      {
        startTime: 9_000,
        duration: 900,
        renderStart: 9_890,
        blockingDuration: 850,
        scripts: [
          {
            sourceURL: ISLAND,
            invoker: 'TimerHandler:setTimeout',
            invokerType: 'user-callback',
            startTime: 9_000,
            duration: 880,
          },
        ],
      },
    ];
    const summary = atlasLongFrames(
      loafs,
      [{ chunks: [0], start: 2_050, end: 2_390 }],
      { ...CONTEXT, windowEndMs: 5_000 },
    );
    expect(
      summary.frames.map((f) => [
        f.startTime,
        f.atlasFrameMs,
        f.cesiumEvalMs,
        f.chunkFrame,
      ]),
    ).toEqual([
      [2_000, 400, 0, true],
      [1_000, 50, 250, false],
    ]);
    expect(summary.maxAtlasFrameMs).toBe(400);
    expect(summary.cesiumEvalMs).toBe(250);
  });

  it('reports Cesium evaluation that Chrome attributes to the scene chunk', () => {
    // Chrome reports a dynamic import's whole module graph as one module-script
    // entry on the imported root, with the root's URL as invoker. Cesium is
    // imported through the scene chunk, so no entry names cesium.<hash>.js.
    const SCENE = `${ORIGIN}/_astro/atlas-scene.CVF3dbcv.js`;
    const evaluation = {
      sourceURL: SCENE,
      invoker: SCENE,
      invokerType: 'module-script',
      startTime: 1_500,
      duration: 320,
    };
    expect(attributeScript(evaluation, CONTEXT, false)).toBe('cesium-eval');
    expect(
      attributeScript(
        {
          ...evaluation,
          invoker: 'FrameRequestCallback',
          invokerType: 'user-callback',
        },
        CONTEXT,
        false,
      ),
    ).toBe('atlas');
    expect(
      attributeScript(
        { ...evaluation, sourceURL: ISLAND, invoker: ISLAND },
        CONTEXT,
        false,
      ),
    ).toBe('atlas');
    const summary = atlasLongFrames(
      [
        {
          startTime: 1_500,
          duration: 360,
          renderStart: 1_850,
          blockingDuration: 310,
          scripts: [
            evaluation,
            {
              sourceURL: ISLAND,
              invoker: 'Worker.onmessage',
              invokerType: 'event-listener',
              startTime: 1_825,
              duration: 20,
            },
          ],
        },
      ],
      [],
      { ...CONTEXT, windowEndMs: 5_000 },
    );
    expect(
      summary.frames.map((f) => [
        f.startTime,
        f.atlasScriptMs,
        f.cesiumEvalMs,
        f.atlasFrameMs,
      ]),
    ).toEqual([[1_500, 20, 320, 40]]);
    expect(summary.maxAtlasFrameMs).toBe(40);
    expect(summary.cesiumEvalMs).toBe(320);
  });

  it('names the built chunk that imports Cesium as the root of its evaluation', () => {
    const astro = path.resolve(import.meta.dirname, '../dist/_astro');
    const importsCesium = readdirSync(astro)
      .filter((name) => name.endsWith('.js'))
      .filter((name) =>
        /["']\.\/cesium\.[\w-]+\.js["']/.test(
          readFileSync(path.join(astro, name), 'utf8'),
        ),
      );
    expect(importsCesium).not.toEqual([]);
    for (const name of importsCesium) {
      const url = `${ORIGIN}/_astro/${name}`;
      expect(
        attributeScript(
          {
            sourceURL: url,
            invoker: url,
            invokerType: 'module-script',
            startTime: 0,
            duration: 10,
          },
          CONTEXT,
          false,
        ),
        name,
      ).toBe('cesium-eval');
    }
  });

  it('charges an Atlas frame only with time no Cesium or other script claims', () => {
    const summary = atlasLongFrames(
      [
        {
          startTime: 4_000,
          duration: 420,
          renderStart: 4_400,
          blockingDuration: 370,
          scripts: [
            {
              sourceURL: CESIUM,
              invoker: 'FrameRequestCallback',
              invokerType: 'user-callback',
              startTime: 4_000,
              duration: 300,
            },
            {
              sourceURL: ISLAND,
              invoker: 'Worker.onmessage',
              invokerType: 'event-listener',
              startTime: 4_300,
              duration: 40,
            },
            {
              sourceURL: 'https://tile.openstreetmap.org/a.js',
              invoker: 'x',
              invokerType: 'classic-script',
              startTime: 4_340,
              duration: 50,
            },
          ],
        },
      ],
      [],
      { ...CONTEXT, windowEndMs: 5_000 },
    );
    expect(
      summary.frames.map((f) => [f.startTime, f.atlasScriptMs, f.atlasFrameMs]),
    ).toEqual([[4_000, 40, 70]]);
    expect(summary.maxAtlasFrameMs).toBe(70);
  });
});

describe('worker-scaled critical path', () => {
  const STEPS: WorkerStep[] = [
    { step: 'verify-grid', chunk: null, start: 100, end: 110 },
    { step: 'decode-grid', chunk: null, start: 110, end: 115 },
    { step: 'topology', chunk: null, start: 115, end: 135 },
    { step: 'verify-render', chunk: null, start: 400, end: 410 },
    { step: 'decode-render', chunk: null, start: 410, end: 414 },
    { step: 'mesh', chunk: 0, start: 414, end: 424 },
    { step: 'support', chunk: 0, start: 424, end: 426 },
    { step: 'mesh', chunk: 1, start: 426, end: 436 },
    { step: 'support', chunk: 1, start: 436, end: 438 },
  ];
  const FRAMES: ChunkFrame[] = [
    { chunks: [0], start: 430, end: 450 },
    { chunks: [1], start: 450, end: 470 },
  ];
  const MARKS = {
    observationsVisible: 300,
    surfaceFirstChunk: 450,
    surfaceVisible: 480,
    ready: 500,
  };

  it('is the identity at factor 1', () => {
    const timeline = scaleCriticalPath({
      factor: 1,
      steps: STEPS,
      frames: FRAMES,
      marks: MARKS,
    });
    expect(timeline.marks).toEqual(MARKS);
    expect(timeline.steps.map((s) => [s.scaledStart, s.scaledEnd])).toEqual(
      STEPS.map((s) => [s.start, s.end]),
    );
  });

  it('scales worker steps ×4 and keeps their dependencies', () => {
    const timeline = scaleCriticalPath({
      factor: 4,
      steps: STEPS,
      frames: FRAMES,
      marks: MARKS,
    });
    expect(
      timeline.steps.map((s) => [s.step, s.chunk, s.scaledStart, s.scaledEnd]),
    ).toEqual([
      ['verify-grid', null, 100, 140],
      ['decode-grid', null, 140, 160],
      ['topology', null, 160, 240],
      ['verify-render', null, 400, 440],
      ['decode-render', null, 440, 456],
      ['mesh', 0, 456, 496],
      ['support', 0, 496, 504],
      ['mesh', 1, 504, 544],
      ['support', 1, 544, 552],
    ]);
    expect(timeline.marks).toEqual({
      observationsVisible: 300,
      surfaceFirstChunk: 524,
      surfaceVisible: 582,
      ready: 602,
    });
  });

  it('charges nothing for topology hidden under the render download', () => {
    const timeline = scaleCriticalPath({
      factor: 4,
      steps: [
        { step: 'verify-grid', chunk: null, start: 100, end: 102 },
        { step: 'decode-grid', chunk: null, start: 102, end: 103 },
        { step: 'topology', chunk: null, start: 103, end: 113 },
        { step: 'verify-render', chunk: null, start: 2_000, end: 2_002 },
        { step: 'decode-render', chunk: null, start: 2_002, end: 2_003 },
        { step: 'mesh', chunk: 0, start: 2_003, end: 2_013 },
      ],
      frames: [{ chunks: [0], start: 2_020, end: 2_030 }],
      marks: {
        observationsVisible: 900,
        surfaceFirstChunk: 2_030,
        surfaceVisible: 2_030,
        ready: 2_100,
      },
    });
    expect(timeline.steps.find((s) => s.step === 'topology')?.scaledEnd).toBe(
      152,
    );
    expect(timeline.marks).toEqual({
      observationsVisible: 900,
      surfaceFirstChunk: 2_062,
      surfaceVisible: 2_062,
      ready: 2_132,
    });
  });
});

describe('bytes ledger', () => {
  const A = `${ORIGIN}/_astro/a.js`;
  const RENDER = `${ORIGIN}/data/atlas/surfaces/hbs-rs334/v3/map-2026-08/render.1111.gosa`;
  const OBSERVATIONS = `${ORIGIN}/data/atlas/hbs-rs334.observations.json`;
  const LATE = `${ORIGIN}/data/atlas/ne-50m-admin-0.geojson`;
  const records = [
    record(DOCUMENT, 1_000, null),
    record(A, 2_000, DOCUMENT),
    record(CESIUM, 3_000, A),
    record(RENDER, 4_000, DOCUMENT),
    record(OBSERVATIONS, 500, null),
    record(LATE, 9_999, 'chrome-extension://x/y.js'),
  ];

  it('derives request depth from initiators', () => {
    const depths = requestDepths(records, DOCUMENT);
    expect(
      [DOCUMENT, A, CESIUM, RENDER, OBSERVATIONS, LATE].map((url) =>
        depths.get(url),
      ),
    ).toEqual([1, 2, 3, 2, 2, 2]);
  });

  it('adds link bytes ÷ bandwidth, round trips × latency and CPU per milestone', () => {
    const rows = bytesLedger({
      network: FAST_4G,
      documentUrl: DOCUMENT,
      records,
      responseEnds: new Map([
        [DOCUMENT, 100],
        [A, 300],
        [CESIUM, 800],
        [RENDER, 900],
        [OBSERVATIONS, 400],
        [LATE, 9_000],
      ]),
      loafs: [
        {
          startTime: 200,
          duration: 100,
          renderStart: 290,
          blockingDuration: 50,
          scripts: [],
        },
        {
          startTime: 850,
          duration: 200,
          renderStart: 1_040,
          blockingDuration: 150,
          scripts: [],
        },
      ],
      steps: [
        {
          step: 'decode-render',
          chunk: null,
          start: 905,
          end: 910,
          scaledStart: 900,
          scaledEnd: 920,
        },
        {
          step: 'mesh',
          chunk: 0,
          start: 910,
          end: 920,
          scaledStart: 920,
          scaledEnd: 960,
        },
      ],
      milestones: [
        {
          name: 'observations-visible',
          observedMs: 500,
          scaledMs: null,
          budgetMs: 4_000,
          tierUrls: [OBSERVATIONS],
          workerSteps: [],
        },
        {
          name: 'surface-visible',
          observedMs: 1_100,
          scaledMs: 1_100,
          budgetMs: 6_000,
          tierUrls: [RENDER],
          workerSteps: ['decode-render', 'mesh'],
        },
      ],
    });
    expect(
      rows.map((r) => [
        r.milestone,
        r.linkBytes,
        r.roundTrips,
        r.latencyMs,
        r.cpuMs,
      ]),
    ).toEqual([
      ['observations-visible', 3_500, 2, 330, 100],
      ['surface-visible', 10_500, 3, 495, 360],
    ]);
    expect(rows[0]?.transferMs).toBeCloseTo(3.4568, 3);
    expect(rows[0]?.predictedMs).toBeCloseTo(433.4568, 3);
    expect(rows[1]?.predictedMs).toBeCloseTo(865.3704, 3);
    expect(ledgerMarkdown('fast 4G', rows)).toContain(
      '| surface-visible | 10,500 B |',
    );
  });
});
