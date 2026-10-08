/** Frame-budgeted surface chunk reveal for Atlas design §11 (spec 2026-10-07 §B.6.7).
 *
 * Adding a primitive is free; Cesium combines and uploads it inside the next
 * render. So the scheduler adds a batch, requests a render, times that render
 * from `preUpdate` to `postRender`, and sizes the next batch so chunk work
 * stays within the frame budget over a baseline frame. At least one chunk is
 * added per frame, and the next batch waits until the previous one is ready.
 */

import type { Scene } from 'cesium';

import type { ChunkMessage } from '../worker/protocol';
import type { SurfaceChunkGroup } from './surface-chunk-layer';

export const DESKTOP_FRAME_BUDGET_MS = 8;
export const COARSE_POINTER_FRAME_BUDGET_MS = 50;
export const SEAM_CHUNK_COST = 4;
export const MAX_BATCH_COST = 64;
const CHUNK_STALL_TIMEOUT_MS = 30_000;

export interface RevealStats {
  frames: number;
  totalMs: number;
  longestFrameMs: number;
}

/** `detail` of each `atlas:chunk-frame` measure (tests/atlas-cold-load.spec.ts reads it). */
export interface ChunkFrameDetail {
  artifactKey: string;
  chunks: number[];
}

export const CHUNK_FRAME_MEASURE = 'atlas:chunk-frame';

/** The render that follows a batch add, as a User Timing measure (fast-load design §B.1 long tasks). */
export function measureChunkFrame(
  start: number,
  end: number,
  detail: ChunkFrameDetail,
): void {
  try {
    performance.measure(CHUNK_FRAME_MEASURE, { detail, end, start });
  } catch {
    // Diagnostic only: a clock mismatch must never stop the reveal.
  }
}

export interface ChunkScheduleOptions {
  frameBudgetMs: number;
  order: number[];
  /** A hidden tab renders no frames; the stall timeout waits for it to be shown again. */
  isHidden?: () => boolean;
  /** Defaults to `measureChunkFrame`; times are those of `now`. */
  measureFrame?: (start: number, end: number, detail: ChunkFrameDetail) => void;
  signal?: AbortSignal;
  onBeforeAdd?: (message: ChunkMessage) => void;
  onAdded?: (message: ChunkMessage) => void;
  now?: () => number;
  stallTimeoutMs?: number;
}

export type ChunkSchedulerScene = Pick<
  Scene,
  'postRender' | 'preUpdate' | 'requestRender'
>;
export type ChunkTarget = Pick<
  SurfaceChunkGroup,
  'addChunk' | 'readyCount' | 'totalCount'
>;

export interface MessageQueue<T> extends AsyncIterable<T> {
  push(item: T): void;
  end(): void;
  fail(error: unknown): void;
}

export function createMessageQueue<T>(): MessageQueue<T> {
  const items: T[] = [];
  let ended = false;
  let failure: { error: unknown } | null = null;
  let wake: (() => void) | null = null;
  const notify = () => {
    wake?.();
    wake = null;
  };
  return {
    push(item) {
      if (ended) return;
      items.push(item);
      notify();
    },
    end() {
      ended = true;
      notify();
    },
    fail(error) {
      failure = { error };
      ended = true;
      notify();
    },
    async *[Symbol.asyncIterator]() {
      while (true) {
        if (items.length > 0) {
          yield items.shift()!;
          continue;
        }
        if (failure) throw failure.error;
        if (ended) return;
        await new Promise<void>((resolve) => {
          wake = resolve;
        });
      }
    },
  };
}

export function revealFrameBudgetMs(coarsePointer: boolean): number {
  return coarsePointer
    ? COARSE_POINTER_FRAME_BUDGET_MS
    : DESKTOP_FRAME_BUDGET_MS;
}

export function nextBatchCost(
  frameBudgetMs: number,
  workMs: number,
  addedCost: number,
): number {
  if (addedCost <= 0) return 1;
  const perUnitMs = Math.max(0, workMs) / addedCost;
  if (perUnitMs === 0) return MAX_BATCH_COST;
  return Math.min(
    MAX_BATCH_COST,
    Math.max(1, Math.floor(frameBudgetMs / perUnitMs)),
  );
}

function chunkCost(message: ChunkMessage): number {
  return message.seam ? SEAM_CHUNK_COST : 1;
}

function isAsyncIterable<T>(
  value: AsyncIterable<T> | readonly T[],
): value is AsyncIterable<T> {
  return Symbol.asyncIterator in value;
}

export function scheduleChunks(
  scene: ChunkSchedulerScene,
  group: ChunkTarget,
  chunks: AsyncIterable<ChunkMessage> | readonly ChunkMessage[],
  options: ChunkScheduleOptions,
): Promise<RevealStats> {
  const now = options.now ?? (() => performance.now());
  const rank = new Map(options.order.map((chunk, index) => [chunk, index]));
  const rankOf = (message: ChunkMessage) =>
    rank.get(message.chunk) ?? Number.POSITIVE_INFINITY;
  const pending: { arrival: number; message: ChunkMessage }[] = [];
  let arrivals = 0;
  const enqueue = (message: ChunkMessage) =>
    pending.push({ arrival: arrivals++, message });

  return new Promise<RevealStats>((resolve, reject) => {
    const stats: RevealStats = { frames: 0, longestFrameMs: 0, totalMs: 0 };
    let settled = false;
    let streamDone = false;
    let phase: 'baseline' | 'idle' | 'rendering' = 'baseline';
    let frameStartedAt: number | null = null;
    let baselineMs = 0;
    let batchCost = 1;
    let inFlightCost = 0;
    let firstAddAt: number | null = null;
    let unmeasured: ChunkFrameDetail | null = null;
    let stallTimer: ReturnType<typeof setTimeout> | undefined;

    const removePreUpdate = scene.preUpdate.addEventListener(() => {
      frameStartedAt = now();
    });
    const removePostRender = scene.postRender.addEventListener(() =>
      onRendered(),
    );
    const onAbort = () =>
      settle(new DOMException('Chunk reveal was superseded', 'AbortError'));
    function settle(error?: unknown): void {
      if (settled) return;
      settled = true;
      removePreUpdate();
      removePostRender();
      clearTimeout(stallTimer);
      options.signal?.removeEventListener('abort', onAbort);
      if (error === undefined) resolve(stats);
      else reject(error);
    }
    const isHidden =
      options.isHidden ??
      (() =>
        typeof document !== 'undefined' &&
        document.visibilityState === 'hidden');
    const armStallTimer = () => {
      clearTimeout(stallTimer);
      stallTimer = setTimeout(() => {
        // A phone that switches apps mid-reveal must not come back to an error.
        if (isHidden()) {
          armStallTimer();
          return;
        }
        settle(new Error('Cesium geometry build timed out'));
      }, options.stallTimeoutMs ?? CHUNK_STALL_TIMEOUT_MS);
    };
    const allReady = () => group.readyCount() >= group.totalCount();
    const addNextBatch = (): boolean => {
      if (pending.length === 0) return false;
      pending.sort(
        (first, second) =>
          rankOf(first.message) - rankOf(second.message) ||
          first.arrival - second.arrival,
      );
      let cost = 0;
      const batch: ChunkFrameDetail = { artifactKey: '', chunks: [] };
      do {
        const { message } = pending.shift()!;
        options.onBeforeAdd?.(message);
        group.addChunk(message.surface, message.support);
        options.onAdded?.(message);
        batch.artifactKey = message.artifactKey;
        batch.chunks.push(message.chunk);
        cost += chunkCost(message);
      } while (
        pending.length > 0 &&
        cost + chunkCost(pending[0].message) <= batchCost
      );
      unmeasured = batch;
      firstAddAt ??= now();
      inFlightCost = cost;
      phase = 'rendering';
      armStallTimer();
      scene.requestRender();
      return true;
    };
    const finishIfComplete = () => {
      if (!streamDone || pending.length > 0 || phase !== 'idle') return;
      stats.totalMs = firstAddAt === null ? 0 : now() - firstAddAt;
      settle();
    };
    const advance = () => {
      if (settled || phase !== 'idle') return;
      if (!addNextBatch()) finishIfComplete();
    };
    function onRendered(): void {
      if (settled) return;
      const duration =
        frameStartedAt === null ? 0 : Math.max(0, now() - frameStartedAt);
      if (phase === 'baseline') {
        baselineMs = duration;
        phase = 'idle';
        advance();
        return;
      }
      if (phase !== 'rendering') return;
      stats.frames += 1;
      stats.longestFrameMs = Math.max(stats.longestFrameMs, duration);
      if (unmeasured && frameStartedAt !== null) {
        (options.measureFrame ?? measureChunkFrame)(
          frameStartedAt,
          now(),
          unmeasured,
        );
        unmeasured = null;
      }
      if (!allReady()) {
        scene.requestRender();
        return;
      }
      batchCost = nextBatchCost(
        options.frameBudgetMs,
        duration - baselineMs,
        inFlightCost,
      );
      phase = 'idle';
      advance();
    }

    options.signal?.addEventListener('abort', onAbort, { once: true });
    if (options.signal?.aborted) {
      onAbort();
      return;
    }
    if (isAsyncIterable(chunks)) {
      void (async () => {
        try {
          for await (const message of chunks) {
            if (settled) return;
            enqueue(message);
            advance();
          }
          streamDone = true;
          advance();
        } catch (error) {
          settle(error);
        }
      })();
    } else {
      for (const message of chunks) enqueue(message);
      streamDone = true;
    }
    armStallTimer();
    scene.requestRender();
  });
}
