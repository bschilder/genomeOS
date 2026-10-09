/**
 * One cold-load run, from CDP events to its verdict, and the summary across
 * runs (fast-load design §B.1). Nothing here drives a browser: the two CDP
 * helpers only subscribe to a `CdpConnection`, and the rest is pure, so
 * `tests/atlas-cold-load-run.test.ts` covers it under vitest.
 * `tests/atlas-cold-load.spec.ts` collects the page measurements it reads.
 */
import { artifactKeyFor } from '../../src/atlas/surface-columns';
import {
  artifactTierKey,
  type ArtifactTier,
  type FixtureCatalog,
} from '../atlas-browser-fixture';
import type { CdpConnection } from './cdp-connection';
import {
  atlasLongFrames,
  bytesLedger,
  chunkFramesFrom,
  firstMarkTime,
  medianOrNull,
  revealStats,
  scaleCriticalPath,
  workerStepsFrom,
  type ChunkFrame,
  type LedgerRow,
  type LoafRecord,
  type LongFrameSummary,
  type MilestoneTimes,
  type NetworkRecord,
  type ScaledTimeline,
  type TimingEntry,
  type WorkerStep,
} from './cold-load-analysis';
import { QUIET_PERIOD_MS, type ColdLoadProfile } from './cold-load-profiles';

/** `baseline` measures a pre-change build to `data-atlas-ready` and asserts nothing. */
export type ColdLoadMode = 'baseline' | 'current';

export type Outcome = 'settled' | 'error' | 'timeout';

export const CRITICAL_TIERS: readonly ArtifactTier[] = [
  'grid',
  'render',
  'observations',
];

/** The worker steps on the `surface-visible` critical path (§B.1 "Worker step timings"). */
export const SURFACE_WORKER_STEPS = [
  'verify-grid',
  'decode-grid',
  'topology',
  'verify-render',
  'decode-render',
  'mesh',
  'support',
] as const;

/** The two steps the worker posts for every chunk it streams. */
const PER_CHUNK_STEPS = ['mesh', 'support'] as const;

export const REQUIRED_MARKS = [
  'observations-visible',
  'surface-first-chunk',
  'surface-visible',
  'ready',
  'edges-ready',
  'context-ready',
] as const;

/** What the spec reads from the page once the run has settled. */
export interface PageMeasurements {
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

export interface WorkerThrottleReport {
  /** Auto-attached dedicated-worker targets. */
  targets: number;
  /** Worker targets that accepted `Emulation.setCPUThrottlingRate`. */
  throttled: number;
  refusals: string[];
  /** Auto-attached targets still paused: `Runtime.runIfWaitingForDebugger` has not answered. */
  paused: string[];
  /** `Runtime.runIfWaitingForDebugger` failures on targets that stayed attached, so stayed paused. */
  resumeFailures: string[];
}

export interface ColdLoadRun {
  index: number;
  outcome: Outcome;
  renderer: string;
  workerThrottle: WorkerThrottleReport | null;
  /** See `workersThrottled`. */
  workersThrottled: boolean | null;
  /** 1, or the CPU rate when a current build's workers ran unthrottled (the scaled critical path). */
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

export type TimesAre =
  'observed' | 'worker-scaled critical path' | 'observed, workers unthrottled';

interface CdpInitiator {
  url?: string;
  stack?: CdpStackTrace;
}

interface CdpStackTrace {
  callFrames: { url: string }[];
  parent?: CdpStackTrace;
}

export function initiatorUrl(
  initiator: CdpInitiator | undefined,
): string | null {
  if (initiator?.url) return initiator.url;
  for (let stack = initiator?.stack; stack; stack = stack.parent) {
    const frame = stack.callFrames.find((candidate) => candidate.url !== '');
    if (frame) return frame.url;
  }
  return null;
}

function reason(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Per URL, from the page session's `Network.*` events: network requests (a
 * memory or disk cache hit is not one), encoded bytes on the link, the last
 * status and `content-encoding`, the last failure and the first initiator.
 */
export function trackNetwork(
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

/**
 * Throttles each dedicated worker the page session auto-attaches
 * (`waitForDebuggerOnStart`), then resumes every auto-attached target.
 * Refused throttles and failed or unanswered resumes are reported, not
 * swallowed: a target left paused would otherwise end the run as an
 * unexplained timeout. A target that detaches first is gone, not paused.
 */
export function throttleWorkers(
  cdp: CdpConnection,
  pageSession: string,
  rate: number,
): { report(): WorkerThrottleReport; dispose(): void } {
  let targets = 0;
  let throttled = 0;
  const refusals: string[] = [];
  const resumeFailures: string[] = [];
  /** Session id → target URL, from attach until the resume settles or the target detaches. */
  const paused = new Map<string, string>();
  const detached = new Set<string>();
  const subscriptions = [
    cdp.on('Target.attachedToTarget', (params, source) => {
      if (source !== pageSession) return;
      const event = params as {
        sessionId: string;
        targetInfo: { type: string; url: string };
        waitingForDebugger: boolean;
      };
      const label = `${event.targetInfo.type} ${event.targetInfo.url}`;
      if (event.waitingForDebugger) paused.set(event.sessionId, label);
      void (async () => {
        if (event.targetInfo.type === 'worker') {
          targets += 1;
          try {
            await cdp.send(
              'Emulation.setCPUThrottlingRate',
              { rate },
              event.sessionId,
            );
            throttled += 1;
          } catch (error) {
            refusals.push(`${event.targetInfo.url}: ${reason(error)}`);
          }
        }
        if (!event.waitingForDebugger) return;
        try {
          await cdp.send(
            'Runtime.runIfWaitingForDebugger',
            {},
            event.sessionId,
          );
        } catch (error) {
          // CdpConnection runs Target.detachedFromTarget listeners before the
          // rejection it causes reaches this handler.
          if (!detached.has(event.sessionId))
            resumeFailures.push(`${label}: ${reason(error)}`);
        } finally {
          paused.delete(event.sessionId);
        }
      })();
    }),
    cdp.on('Target.detachedFromTarget', (params, source) => {
      if (source !== pageSession) return;
      const { sessionId } = params as { sessionId: string };
      detached.add(sessionId);
      paused.delete(sessionId);
    }),
  ];
  return {
    report: () => ({
      targets,
      throttled,
      refusals: [...refusals],
      paused: [...paused.values()],
      resumeFailures: [...resumeFailures],
    }),
    dispose: () => {
      for (const unsubscribe of subscriptions) unsubscribe();
    },
  };
}

/**
 * Whether every worker ran under the profile's CPU throttling; null when the
 * profile does not throttle the CPU. No report, or no attached worker at all,
 * counts as unthrottled: the data worker always exists, so not seeing it means
 * auto-attach missed it.
 */
export function workersThrottled(
  profile: Pick<ColdLoadProfile, 'cpuThrottlingRate'>,
  throttle: WorkerThrottleReport | null,
): boolean | null {
  if (profile.cpuThrottlingRate <= 1) return null;
  return (
    throttle !== null &&
    throttle.targets > 0 &&
    throttle.throttled === throttle.targets
  );
}

function chunkList(chunks: Iterable<number>): string {
  return [...chunks].sort((left, right) => left - right).join(', ');
}

/**
 * The step timings and chunk frames the scaled critical path, the reveal
 * statistics and the long-frame attribution are built from. Without them
 * those numbers silently fall back to observed times, so each gap is a run
 * error.
 */
export function workerTimingErrors(
  artifactKey: string,
  steps: readonly WorkerStep[],
  frames: readonly ChunkFrame[],
): string[] {
  const errors = SURFACE_WORKER_STEPS.filter(
    (name) => !steps.some((step) => step.step === name),
  ).map(
    (name) => `missing worker step atlas:worker:${name} for ${artifactKey}`,
  );
  if (frames.length === 0) {
    errors.push(`missing atlas:chunk-frame measures for ${artifactKey}`);
    return errors;
  }
  const revealed = new Set(frames.flatMap((frame) => frame.chunks));
  for (const name of PER_CHUNK_STEPS) {
    const timed = new Set(
      steps.flatMap((step) =>
        step.step === name && step.chunk !== null ? [step.chunk] : [],
      ),
    );
    const untimed = [...revealed].filter((chunk) => !timed.has(chunk));
    if (untimed.length > 0)
      errors.push(
        `chunks ${chunkList(untimed)} of ${artifactKey} were revealed without an atlas:worker:${name} step`,
      );
    if (name !== 'mesh') continue;
    const unrevealed = [...timed].filter((chunk) => !revealed.has(chunk));
    if (unrevealed.length > 0)
      errors.push(
        `chunks ${chunkList(unrevealed)} of ${artifactKey} were meshed but are in no atlas:chunk-frame measure`,
      );
  }
  return errors;
}

export function analyseRun(args: {
  mode: ColdLoadMode;
  index: number;
  profile: ColdLoadProfile;
  measurements: PageMeasurements;
  records: NetworkRecord[];
  workerThrottle: WorkerThrottleReport | null;
  pageErrors: string[];
  outcome: Outcome;
}): ColdLoadRun {
  const { mode, profile, measurements: m, records } = args;
  const catalog = m.catalogText
    ? (JSON.parse(m.catalogText) as FixtureCatalog)
    : null;
  const selected = catalog?.artifacts[0] ?? null;
  const artifactKey = selected ? artifactKeyFor(selected) : null;
  const mark = (name: string): number | null =>
    firstMarkTime(m.marks, `atlas:${name}`);
  const raw =
    mode === 'current'
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
  const throttledWorkers = workersThrottled(profile, throttle);
  // Only a current build posts worker step timings, so only its critical path
  // can be rescaled; a baseline's times stay observed (and say so).
  const workerScale =
    mode === 'current' && throttledWorkers === false
      ? profile.cpuThrottlingRate
      : 1;
  const scaled =
    mode === 'current' && profile.cpuThrottlingRate > 1
      ? scaleCriticalPath({ factor: workerScale, steps, frames, marks: raw })
      : null;
  const settledAt =
    mode === 'current'
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
      mode === 'current'
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
    ...(throttle?.resumeFailures ?? []).map(
      (failure) => `target not resumed: ${failure}`,
    ),
    ...(throttle?.paused ?? []).map(
      (target) =>
        `target still paused (Runtime.runIfWaitingForDebugger unanswered): ${target}`,
    ),
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
    ...(mode === 'current'
      ? [
          ...(artifactKey === null
            ? [
                'no inline #atlas-catalog: worker steps, chunk frames and tier URLs cannot be attributed',
              ]
            : workerTimingErrors(artifactKey, steps, frames)),
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
    workersThrottled: throttledWorkers,
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

/**
 * Medians across runs. Times are the scaled critical path when any run's
 * workers ran unthrottled in a current build, else observed; a baseline with
 * unthrottled workers says so, since it has no step timings to scale.
 */
export function summarise(runs: readonly ColdLoadRun[]) {
  const scaledInUse = runs.some((run) => run.workerScale > 1);
  const timesAre: TimesAre = scaledInUse
    ? 'worker-scaled critical path'
    : runs.some((run) => run.workersThrottled === false)
      ? 'observed, workers unthrottled'
      : 'observed';
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
    timesAre,
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

/** The run whose ledger is reported: the median by surface-visible (baseline: ready); a run without it sorts last. */
export function medianRun(
  runs: readonly ColdLoadRun[],
  mode: ColdLoadMode,
): ColdLoadRun {
  const time = (run: ColdLoadRun): number =>
    (mode === 'current'
      ? (run.scaled?.marks.surfaceVisible ?? run.raw.surfaceVisible)
      : run.raw.ready) ?? Number.POSITIVE_INFINITY;
  const sorted = [...runs].sort((left, right) => time(left) - time(right) || 0);
  return sorted[Math.floor(sorted.length / 2)];
}
