/** Main-thread client of the Atlas data worker for Atlas design §11 and fast-load design §B.6.3. */

import type { ArtifactRef } from '../contracts';
import type { GosaErrorCode } from '../gosa/container';
import type { DecodedDetail, DecodedGrid, DecodedRender } from '../gosa/types';
import { artifactKeyFor } from '../surface-columns';
import {
  TERMINAL_RESPONSES,
  type BuildChunksBody,
  type BuildEdgesBody,
  type ChunkMessage,
  type ContextHeights,
  type ContextHeightsBody,
  type EdgesChunkMessage,
  type GridExpect,
  type NaturalEarthBuffers,
  type RecolourBody,
  type StepName,
  type StepTimingMessage,
  type WorkerErrorCode,
  type WorkerOutbound,
  type WorkerRequest,
  type WorkerResponse,
  type WorkerResponseOf,
  type WorkerResponseType,
} from './protocol';

/** One worker step in milliseconds of the page's time origin (fast-load design §B.1). */
export interface StepTiming {
  artifactKey: string | null;
  chunk: number | null;
  end: number;
  start: number;
  step: StepName;
}

export class AtlasWorkerError extends Error {
  readonly code: WorkerErrorCode;
  readonly gosaCode: GosaErrorCode | null;

  constructor(
    code: WorkerErrorCode,
    message: string,
    gosaCode: GosaErrorCode | null,
  ) {
    super(message);
    this.name = 'AtlasWorkerError';
    this.code = code;
    this.gosaCode = gosaCode;
  }
}

/** True for a checksum or validation failure (Cesium design §12: render nothing, offer Retry data). */
export function isArtifactValidationError(error: unknown): boolean {
  return (
    error instanceof AtlasWorkerError &&
    (error.code === 'checksum' || error.code === 'validation')
  );
}

interface Pending {
  onMessage?: (message: WorkerResponse) => void;
  reject(error: unknown): void;
  resolve(message: WorkerResponse): void;
}

function abortError(): DOMException {
  return new DOMException(
    'The Atlas worker request was aborted.',
    'AbortError',
  );
}

function createDataWorker(): Worker {
  return new Worker(new URL('./atlas-data.worker.ts', import.meta.url), {
    name: 'atlas-data',
    type: 'module',
  });
}

/** Stand-in whose every request fails with the reason the real Worker could not start. */
class UnavailableWorker extends EventTarget {
  readonly #reason: string;

  constructor(reason: string) {
    super();
    this.#reason = reason;
  }

  postMessage(): void {
    queueMicrotask(() =>
      this.dispatchEvent(
        Object.assign(new Event('error'), {
          message: `The Atlas data worker could not start: ${this.#reason}`,
        }),
      ),
    );
  }

  terminate(): void {}
}

/**
 * A worker `error` event or `terminate()` is final: the client stops the worker, fails every
 * pending request and rejects every later one with the same error without posting it. A dead
 * worker so ends each load, and each "Retry data", in a failure, never an endless "Loading" (RF5).
 */
export class AtlasWorkerClient {
  readonly #pending = new Map<number, Pending>();
  readonly #renders = new Map<string, DecodedRender>();
  readonly #timings = new Set<(timing: StepTiming) => void>();
  readonly #worker: Worker;
  #failure: Error | null = null;
  #nextId = 1;

  constructor(worker: Worker = createDataWorker()) {
    this.#worker = worker;
    worker.addEventListener('message', (event: MessageEvent<WorkerOutbound>) =>
      this.#receive(event.data),
    );
    // A script that fails to load fires a bare Event, so `message` may be undefined.
    worker.addEventListener('error', (event: ErrorEvent) =>
      this.#die(
        new Error(
          `Atlas data worker failed: ${event.message || 'unknown error'}`,
        ),
      ),
    );
    // One undeliverable response with an unknown id; the worker itself is still running.
    worker.addEventListener('messageerror', () =>
      this.#failAll(new Error('Atlas data worker sent an unreadable message')),
    );
  }

  /** A client whose requests reject with `reason` (used when `new Worker` throws). */
  static unavailable(reason: unknown): AtlasWorkerClient {
    const message = reason instanceof Error ? reason.message : String(reason);
    return new AtlasWorkerClient(
      new UnavailableWorker(message) as unknown as Worker,
    );
  }

  async loadGrid(
    buf: ArrayBuffer,
    expect: GridExpect,
    signal?: AbortSignal,
  ): Promise<DecodedGrid> {
    const { grid } = await this.#request<'grid-ready'>(
      (id) => ({ buf, expect, id, type: 'load-grid' }),
      [buf],
      signal,
    );
    return grid;
  }

  async loadRender(
    buf: ArrayBuffer,
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<DecodedRender> {
    const { render } = await this.#request<'render-ready'>(
      (id) => ({ buf, id, ref, type: 'load-render' }),
      [buf],
      signal,
    );
    this.#renders.set(artifactKeyFor(ref), render);
    return render;
  }

  /** The render tier's columns are copied (not transferred) for the cross-tier check. */
  async loadDetail(
    buf: ArrayBuffer,
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<DecodedDetail> {
    const render = this.#renders.get(artifactKeyFor(ref));
    if (!render)
      throw new Error(`Load the ${ref.id} render tier before its detail tier`);
    const { detail } = await this.#request<'detail-ready'>(
      (id) => ({ buf, id, ref, render, type: 'load-detail' }),
      [buf],
      signal,
    );
    return detail;
  }

  /** Surface + support chunks in camera order (fast-load design §B.6.5); resolves at `chunks-done`. */
  async buildChunks(
    req: BuildChunksBody,
    onChunk: (message: ChunkMessage) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    await this.#request<'chunks-done'>(
      (id) => ({ ...req, id, type: 'build-chunks' }),
      [],
      signal,
      (message) => {
        if (message.type === 'chunk') onChunk(message);
      },
    );
  }

  /**
   * Every chunk again in plan order with new colours (§B.6.13): the worker rebuilds each chunk from
   * its cached topology, chunk plan and vertex means, not from a cached mesh; anchors are null.
   */
  async recolour(
    req: RecolourBody,
    onChunk: (message: ChunkMessage) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const { artifactKey, geometry, gridSha256, metric, palette } = req;
    await this.#request<'chunks-done'>(
      (id) => ({
        artifactKey,
        geometry,
        gridSha256,
        id,
        metric,
        palette,
        type: 'recolour',
      }),
      [],
      signal,
      (message) => {
        if (message.type === 'chunk') onChunk(message);
      },
    );
  }

  /** Cell-outline ring buffers with the exact capacity on every message (§B.6.9). */
  async buildEdges(
    req: BuildEdgesBody,
    onChunk: (message: EdgesChunkMessage) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    await this.#request<'edges-done'>(
      (id) => ({ ...req, id, type: 'build-edges' }),
      [],
      signal,
      (message) => {
        if (message.type === 'edges-chunk') onChunk(message);
      },
    );
  }

  /** Parses the Natural Earth GeoJSON in the worker; `json` is transferred. */
  async parseContext(
    json: ArrayBuffer,
    signal?: AbortSignal,
  ): Promise<NaturalEarthBuffers> {
    const { buffers } = await this.#request<'context-ready'>(
      (id) => ({ id, json, type: 'parse-context' }),
      [json],
      signal,
    );
    return buffers;
  }

  /** Border and label heights at exaggeration 1 over the displayed render tier (§B.6.9). */
  async contextHeights(
    req: ContextHeightsBody,
    signal?: AbortSignal,
  ): Promise<ContextHeights> {
    const { borderHeights, labelHeights } =
      await this.#request<'context-heights-ready'>(
        (id) => ({ ...req, id, type: 'context-heights' }),
        [],
        signal,
      );
    return { borderHeights, labelHeights };
  }

  onStepTiming(listener: (timing: StepTiming) => void): () => void {
    this.#timings.add(listener);
    return () => this.#timings.delete(listener);
  }

  /** Final: pending and later requests reject with "Atlas data worker terminated". */
  terminate(): void {
    this.#die(new Error('Atlas data worker terminated'));
  }

  #request<K extends WorkerResponseType>(
    build: (id: number) => WorkerRequest,
    transfer: Transferable[],
    signal?: AbortSignal,
    onMessage?: (message: WorkerResponse) => void,
  ): Promise<WorkerResponseOf<K>> {
    if (signal?.aborted) return Promise.reject(abortError());
    if (this.#failure) return Promise.reject(this.#failure);
    const id = this.#nextId++;
    return new Promise<WorkerResponseOf<K>>((resolve, reject) => {
      const onAbort = () => {
        if (!this.#pending.delete(id)) return;
        this.#worker.postMessage({ id, type: 'cancel' });
        reject(abortError());
      };
      const release = () => signal?.removeEventListener('abort', onAbort);
      signal?.addEventListener('abort', onAbort, { once: true });
      this.#pending.set(id, {
        onMessage,
        reject: (error) => {
          release();
          reject(error);
        },
        resolve: (message) => {
          release();
          // The terminal response for this id is the one paired with request K
          // (WorkerResponseMap), which the union type cannot express; a direct
          // union-to-member cast is TS2352, hence the `unknown` step.
          resolve(message as unknown as WorkerResponseOf<K>);
        },
      });
      try {
        this.#worker.postMessage(build(id), { transfer });
      } catch (error) {
        this.#pending.delete(id);
        release();
        reject(error);
      }
    });
  }

  #receive(message: WorkerOutbound): void {
    if (message.type === 'step-timing') {
      this.#emitTiming(message);
      return;
    }
    const pending = this.#pending.get(message.id);
    if (!pending) return;
    if (message.type === 'error') {
      this.#pending.delete(message.id);
      pending.reject(
        new AtlasWorkerError(message.code, message.message, message.gosaCode),
      );
      return;
    }
    if (TERMINAL_RESPONSES.has(message.type)) {
      this.#pending.delete(message.id);
      pending.resolve(message);
    } else pending.onMessage?.(message);
  }

  #emitTiming(message: StepTimingMessage): void {
    const timing: StepTiming = {
      artifactKey: message.artifactKey,
      chunk: message.chunk,
      end: message.endEpochMs - performance.timeOrigin,
      start: message.startEpochMs - performance.timeOrigin,
      step: message.step,
    };
    try {
      // Read by tests/atlas-cold-load.spec.ts to rebuild the worker critical path.
      performance.measure(`atlas:worker:${timing.step}`, {
        detail: {
          artifactKey: timing.artifactKey,
          chunk: timing.chunk,
          step: timing.step,
        },
        end: timing.end,
        start: timing.start,
      });
    } catch {
      // A measure is diagnostic only; clock skew must never break loading.
    }
    for (const listener of this.#timings) listener(timing);
  }

  /** The first cause wins; a later `terminate()` of a crashed worker keeps the crash message. */
  #die(error: Error): void {
    this.#failure ??= error;
    this.#worker.terminate();
    this.#failAll(this.#failure);
  }

  #failAll(error: Error): void {
    const pending = [...this.#pending.values()];
    this.#pending.clear();
    for (const entry of pending) entry.reject(error);
  }
}

/** The page's data worker; never throws, so a blocked Worker becomes a reported load failure. */
export function startAtlasWorker(): AtlasWorkerClient {
  try {
    return new AtlasWorkerClient(createDataWorker());
  } catch (error) {
    return AtlasWorkerClient.unavailable(error);
  }
}
