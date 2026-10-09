/**
 * Pure analysis for the cold-load measurement contract (fast-load design
 * §B.1): medians, long-animation-frame attribution, the worker-scaled critical
 * path and the bytes ledger. No Playwright or browser dependency.
 */
import { CHUNK_FRAME_MEASURE } from '../../src/atlas/scene/chunk-scheduler';
import type { NetworkConditions } from './cold-load-profiles';

export interface TimingEntry {
  name: string;
  startTime: number;
  duration: number;
  detail: unknown;
}

export interface LoafScriptRecord {
  sourceURL: string;
  invoker: string;
  invokerType: string;
  startTime: number;
  duration: number;
}

export interface LoafRecord {
  startTime: number;
  duration: number;
  renderStart: number;
  blockingDuration: number;
  scripts: LoafScriptRecord[];
}

export interface WorkerStep {
  step: string;
  chunk: number | null;
  start: number;
  end: number;
}

export interface ScaledWorkerStep extends WorkerStep {
  scaledStart: number;
  scaledEnd: number;
}

export interface ChunkFrame {
  chunks: number[];
  start: number;
  end: number;
}

export interface MilestoneTimes {
  observationsVisible: number | null;
  surfaceFirstChunk: number | null;
  surfaceVisible: number | null;
  ready: number | null;
}

export interface NetworkRecord {
  url: string;
  requests: number;
  encodedBytes: number;
  contentEncoding: string | null;
  status: number | null;
  failure: string | null;
  initiatorUrl: string | null;
}

export const WORKER_STEP_PREFIX = 'atlas:worker:';

export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}

/** A failed run (null) makes the median null, so a budget cannot pass on two runs. */
export function medianOrNull(
  values: readonly (number | null)[],
): number | null {
  const numbers = values.filter((value): value is number => value !== null);
  return numbers.length === values.length ? median(numbers) : null;
}

export function firstMarkTime(
  marks: readonly TimingEntry[],
  name: string,
): number | null {
  const times = marks
    .filter((entry) => entry.name === name)
    .map((entry) => entry.startTime);
  return times.length === 0 ? null : Math.min(...times);
}

export function workerStepsFrom(
  measures: readonly TimingEntry[],
  artifactKey: string,
): WorkerStep[] {
  return measures
    .filter((entry) => entry.name.startsWith(WORKER_STEP_PREFIX))
    .flatMap((entry) => {
      const detail = (entry.detail ?? {}) as {
        step?: unknown;
        chunk?: unknown;
        artifactKey?: unknown;
      };
      const key = detail.artifactKey ?? null;
      if (key !== null && key !== artifactKey) return [];
      return [
        {
          step:
            typeof detail.step === 'string'
              ? detail.step
              : entry.name.slice(WORKER_STEP_PREFIX.length),
          chunk: typeof detail.chunk === 'number' ? detail.chunk : null,
          start: entry.startTime,
          end: entry.startTime + entry.duration,
        },
      ];
    })
    .sort((left, right) => left.start - right.start || left.end - right.end);
}

export function chunkFramesFrom(
  measures: readonly TimingEntry[],
  artifactKey: string,
): ChunkFrame[] {
  return measures
    .filter((entry) => entry.name === CHUNK_FRAME_MEASURE)
    .flatMap((entry) => {
      const detail = (entry.detail ?? {}) as {
        artifactKey?: unknown;
        chunks?: unknown;
      };
      if (detail.artifactKey !== artifactKey || !Array.isArray(detail.chunks))
        return [];
      return [
        {
          chunks: detail.chunks.filter(
            (chunk): chunk is number => typeof chunk === 'number',
          ),
          start: entry.startTime,
          end: entry.startTime + entry.duration,
        },
      ];
    })
    .sort((left, right) => left.end - right.end);
}

export function revealStats(
  frames: readonly ChunkFrame[],
): { frames: number; totalMs: number; longestFrameMs: number } | null {
  if (frames.length === 0) return null;
  return {
    frames: frames.length,
    totalMs: frames[frames.length - 1].end - frames[0].start,
    longestFrameMs: Math.max(...frames.map((frame) => frame.end - frame.start)),
  };
}

export type ScriptAttribution = 'atlas' | 'cesium' | 'cesium-eval' | 'other';

export interface AttributionContext {
  origin: string;
  documentUrl: string;
}

/** Task 80 (B5.11)'s stable Cesium chunk. */
const CESIUM_CHUNK = /\/_astro\/cesium\.[\w-]+\.js(?:[?#]|$)/;
/**
 * The lazy scene chunk (`src/atlas/scene/atlas-scene.ts`), which
 * `loadAtlasSceneModule()` in `src/atlas/boot.ts` loads with `import()`. It is
 * the only chunk that statically imports the Cesium chunk
 * (tests/atlas-cold-load-analysis.test.ts checks this against the build).
 */
const SCENE_CHUNK = /\/_astro\/atlas-scene\.[\w-]+\.js(?:[?#]|$)/;
const ASTRO_SCRIPT = /\/_astro\/[^/]+\.js(?:[?#]|$)/;
const WORKER_MESSAGE_INVOKER = /Worker|MessagePort/;

/**
 * Attributes one long-animation-frame script by its source URL and invoker.
 *
 * - Cesium module evaluation is reported separately (`cesium-eval`). Chrome
 *   reports the evaluation of a dynamic import's whole module graph as one
 *   `module-script` entry whose `sourceURL` is the imported root. Cesium is
 *   imported only through the scene chunk, so its evaluation arrives on
 *   `atlas-scene.<hash>.js`, never on `cesium.<hash>.js`. That entry also
 *   holds the scene chunk's own top-level evaluation, which is small next to
 *   Cesium's and is counted as Cesium evaluation with it. A `module-script`
 *   entry on the Cesium chunk itself, which Chrome produces only if Cesium is
 *   imported directly, also counts as Cesium evaluation.
 * - Other Cesium-chunk work counts as Cesium, except on frames that add Atlas
 *   chunk primitives (`inChunkFrame`), where all of it counts as Atlas. The
 *   spec charges only `Primitive.update` to Atlas there, but a script entry
 *   names only its entry point (Cesium's render-loop callback), not the
 *   functions it calls, so `Primitive.update` cannot be told apart from the
 *   rest of that render. Charging the whole callback can over-report Atlas
 *   on chunk frames, never under-report it.
 * - Worker and `MessagePort` handlers, every other same-origin `/_astro/`
 *   chunk and the document's own scripts count as Atlas; the rest is `other`.
 */
export function attributeScript(
  script: LoafScriptRecord,
  context: AttributionContext,
  inChunkFrame: boolean,
): ScriptAttribution {
  if (
    script.invokerType === 'module-script' &&
    (SCENE_CHUNK.test(script.sourceURL) || CESIUM_CHUNK.test(script.sourceURL))
  )
    return 'cesium-eval';
  if (CESIUM_CHUNK.test(script.sourceURL))
    return inChunkFrame ? 'atlas' : 'cesium';
  if (WORKER_MESSAGE_INVOKER.test(script.invoker)) return 'atlas';
  if (
    script.sourceURL.startsWith(context.origin) &&
    (ASTRO_SCRIPT.test(script.sourceURL) ||
      script.sourceURL === context.documentUrl)
  )
    return 'atlas';
  return 'other';
}

export interface LongFrameReport {
  startTime: number;
  duration: number;
  atlasScriptMs: number;
  cesiumEvalMs: number;
  /**
   * Frame duration minus every script attributed to something other than
   * Atlas (in any frame): Cesium module evaluation, Cesium work outside chunk
   * frames and `other` scripts. Time that no script entry claims (style,
   * layout, paint, and scripts under the 5 ms reporting threshold) stays
   * charged to Atlas, so against the attribution rules this can over-report
   * an Atlas frame, never under-report it.
   */
  atlasFrameMs: number;
  chunkFrame: boolean;
  scripts: {
    sourceURL: string;
    invoker: string;
    invokerType: string;
    attribution: ScriptAttribution;
    duration: number;
  }[];
}

export interface LongFrameSummary {
  frames: LongFrameReport[];
  maxAtlasFrameMs: number;
  cesiumEvalMs: number;
}

function overlaps(loaf: LoafRecord, frame: ChunkFrame): boolean {
  return (
    frame.start < loaf.startTime + loaf.duration && frame.end > loaf.startTime
  );
}

export function atlasLongFrames(
  loafs: readonly LoafRecord[],
  chunkFrames: readonly ChunkFrame[],
  context: AttributionContext & { windowEndMs: number },
): LongFrameSummary {
  const frames: LongFrameReport[] = [];
  let cesiumEvalMs = 0;
  for (const loaf of loafs) {
    if (loaf.startTime > context.windowEndMs) continue;
    const chunkFrame = chunkFrames.some((frame) => overlaps(loaf, frame));
    const scripts = loaf.scripts.map((script) => ({
      sourceURL: script.sourceURL,
      invoker: script.invoker,
      invokerType: script.invokerType,
      attribution: attributeScript(script, context, chunkFrame),
      duration: script.duration,
    }));
    const total = (kind: ScriptAttribution): number =>
      scripts
        .filter((script) => script.attribution === kind)
        .reduce((sum, script) => sum + script.duration, 0);
    const evaluationMs = total('cesium-eval');
    cesiumEvalMs += evaluationMs;
    const atlasScriptMs = total('atlas');
    if (atlasScriptMs === 0 && !chunkFrame) continue;
    const notAtlasMs = evaluationMs + total('cesium') + total('other');
    frames.push({
      startTime: loaf.startTime,
      duration: loaf.duration,
      atlasScriptMs,
      cesiumEvalMs: evaluationMs,
      atlasFrameMs: Math.max(0, loaf.duration - notAtlasMs),
      chunkFrame,
      scripts,
    });
  }
  frames.sort((left, right) => right.atlasFrameMs - left.atlasFrameMs);
  return {
    frames,
    maxAtlasFrameMs: frames[0]?.atlasFrameMs ?? 0,
    cesiumEvalMs,
  };
}

const STEP_DEPENDENCIES: Record<string, (step: WorkerStep) => string[]> = {
  'decode-grid': () => ['verify-grid'],
  topology: () => ['decode-grid'],
  'decode-render': () => ['verify-render', 'decode-grid'],
  mesh: () => ['topology', 'decode-render'],
  support: (step) => [`mesh:${step.chunk}`],
};

function stepId(step: WorkerStep): string {
  return step.chunk === null ? step.step : `${step.step}:${step.chunk}`;
}

export interface ScaledTimeline {
  factor: number;
  steps: ScaledWorkerStep[];
  marks: MilestoneTimes;
}

/** Rebuild the critical path with worker steps × `factor` (see B5.12 notes). */
export function scaleCriticalPath(input: {
  factor: number;
  steps: readonly WorkerStep[];
  frames: readonly ChunkFrame[];
  marks: MilestoneTimes;
}): ScaledTimeline {
  const scaledEnds = new Map<string, number>();
  const steps: ScaledWorkerStep[] = [];
  let workerFree = Number.NEGATIVE_INFINITY;
  for (const step of [...input.steps].sort(
    (left, right) => left.start - right.start,
  )) {
    const dependencies = STEP_DEPENDENCIES[step.step]?.(step) ?? [];
    const scaledStart = Math.max(
      step.start,
      workerFree,
      ...dependencies.map(
        (id) => scaledEnds.get(id) ?? Number.NEGATIVE_INFINITY,
      ),
    );
    const scaledEnd = scaledStart + input.factor * (step.end - step.start);
    const id = stepId(step);
    scaledEnds.set(id, Math.max(scaledEnds.get(id) ?? scaledEnd, scaledEnd));
    steps.push({ ...step, scaledStart, scaledEnd });
    workerFree = scaledEnd;
  }
  const chunkDone = (chunk: number): number =>
    Math.max(
      scaledEnds.get(`mesh:${chunk}`) ?? Number.NEGATIVE_INFINITY,
      scaledEnds.get(`support:${chunk}`) ?? Number.NEGATIVE_INFINITY,
    );
  let previous = Number.NEGATIVE_INFINITY;
  const reveals = [...input.frames]
    .sort((left, right) => left.end - right.end)
    .map((frame) => {
      const frameMs = frame.end - frame.start;
      const done = Math.max(
        Number.NEGATIVE_INFINITY,
        ...frame.chunks.map(chunkDone),
      );
      const scaledReveal = Math.max(
        frame.end,
        done + frameMs,
        previous + frameMs,
      );
      previous = scaledReveal;
      return { frame, scaledReveal };
    });
  const shift = (
    observed: number | null,
    anchor: { frame: ChunkFrame; scaledReveal: number } | undefined,
  ): number | null =>
    observed === null || anchor === undefined
      ? observed
      : anchor.scaledReveal + (observed - anchor.frame.end);
  const surfaceFirstChunk = shift(input.marks.surfaceFirstChunk, reveals[0]);
  const surfaceVisible = shift(
    input.marks.surfaceVisible,
    reveals[reveals.length - 1],
  );
  const ready =
    input.marks.ready === null ||
    input.marks.surfaceVisible === null ||
    surfaceVisible === null
      ? input.marks.ready
      : input.marks.ready + (surfaceVisible - input.marks.surfaceVisible);
  return {
    factor: input.factor,
    steps,
    marks: {
      observationsVisible: input.marks.observationsVisible,
      surfaceFirstChunk,
      surfaceVisible,
      ready,
    },
  };
}

/** Serial request depth (document = 1) from CDP initiators; unknown parents count as the document. */
export function requestDepths(
  records: readonly NetworkRecord[],
  documentUrl: string,
): Map<string, number> {
  const byUrl = new Map(records.map((record) => [record.url, record] as const));
  const depths = new Map<string, number>([[documentUrl, 1]]);
  const depthOf = (url: string, path: ReadonlySet<string>): number => {
    const known = depths.get(url);
    if (known !== undefined) return known;
    const parent = byUrl.get(url)?.initiatorUrl ?? documentUrl;
    const parentDepth =
      parent === url ||
      path.has(parent) ||
      (!byUrl.has(parent) && parent !== documentUrl)
        ? 1
        : depthOf(parent, new Set([...path, url]));
    depths.set(url, parentDepth + 1);
    return parentDepth + 1;
  };
  for (const record of records) depthOf(record.url, new Set());
  return depths;
}

export interface LedgerMilestone {
  name: string;
  observedMs: number | null;
  scaledMs: number | null;
  budgetMs: number;
  tierUrls: readonly string[];
  workerSteps: readonly string[];
}

export interface LedgerRow {
  milestone: string;
  observedMs: number | null;
  scaledMs: number | null;
  budgetMs: number;
  linkBytes: number;
  transferMs: number | null;
  roundTrips: number;
  latencyMs: number | null;
  cpuMs: number;
  predictedMs: number;
}

/**
 * Per milestone: gzip bytes on the link ÷ bandwidth + serial round trips ×
 * latency + CPU (main-thread long frames + critical worker steps).
 */
export function bytesLedger(input: {
  network: NetworkConditions | null;
  documentUrl: string;
  records: readonly NetworkRecord[];
  responseEnds: ReadonlyMap<string, number>;
  loafs: readonly LoafRecord[];
  steps: readonly ScaledWorkerStep[];
  milestones: readonly LedgerMilestone[];
}): LedgerRow[] {
  const depths = requestDepths(input.records, input.documentUrl);
  return input.milestones.map((milestone) => {
    const at = milestone.observedMs ?? Number.POSITIVE_INFINITY;
    const done = (url: string): boolean =>
      (input.responseEnds.get(url) ?? Number.POSITIVE_INFINITY) <= at;
    const linkBytes = input.records
      .filter((record) => done(record.url))
      .reduce((sum, record) => sum + record.encodedBytes, 0);
    const critical = [
      input.documentUrl,
      ...milestone.tierUrls,
      ...input.records
        .filter((record) => ASTRO_SCRIPT.test(record.url) && done(record.url))
        .map((record) => record.url),
    ];
    const roundTrips = Math.max(...critical.map((url) => depths.get(url) ?? 1));
    const mainMs = input.loafs
      .filter((loaf) => loaf.startTime + loaf.duration <= at)
      .reduce((sum, loaf) => sum + loaf.duration, 0);
    const workerAt = milestone.scaledMs ?? at;
    const workerMs = input.steps
      .filter(
        (step) =>
          milestone.workerSteps.includes(step.step) &&
          step.scaledEnd <= workerAt,
      )
      .reduce((sum, step) => sum + (step.scaledEnd - step.scaledStart), 0);
    const transferMs = input.network
      ? (linkBytes / input.network.downloadThroughput) * 1_000
      : null;
    const latencyMs = input.network ? roundTrips * input.network.latency : null;
    const cpuMs = mainMs + workerMs;
    return {
      milestone: milestone.name,
      observedMs: milestone.observedMs,
      scaledMs: milestone.scaledMs,
      budgetMs: milestone.budgetMs,
      linkBytes,
      transferMs,
      roundTrips,
      latencyMs,
      cpuMs,
      predictedMs: (transferMs ?? 0) + (latencyMs ?? 0) + cpuMs,
    };
  });
}

export function ledgerMarkdown(
  title: string,
  rows: readonly LedgerRow[],
): string {
  const ms = (value: number | null): string =>
    value === null ? '—' : `${Math.round(value).toLocaleString('en-US')} ms`;
  const lines = [
    `### ${title}`,
    '',
    '| Milestone | Link bytes (gzip) | ÷ bandwidth | Round trips × latency | CPU | Predicted | Observed | Scaled | Budget |',
    '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ...rows.map(
      (row) =>
        `| ${row.milestone} | ${row.linkBytes.toLocaleString('en-US')} B | ${ms(row.transferMs)} | ${row.roundTrips} RTT = ${ms(row.latencyMs)} | ${ms(row.cpuMs)} | ${ms(row.predictedMs)} | ${ms(row.observedMs)} | ${ms(row.scaledMs)} | ${ms(row.budgetMs)} |`,
    ),
  ];
  return `${lines.join('\n')}\n`;
}
