/**
 * Validated static-file implementation of the Atlas design §11 data provider, loading the fast-load
 * design §B.2 tiers: inline catalog (§B.6.1), two data bases (§B.4), main-thread fetch with a
 * stall timeout and decoding in the data worker (§B.6.2–§B.6.3), progress from declared bytes only.
 */

import {
  atlasCatalogSchema,
  externalInfoSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
  type ArtifactRef,
  type AtlasCatalog,
  type ExternalInfo,
  type GridEntry,
  type ObservationArtifact,
  type SurfaceArtifact as SurfaceJsonArtifact,
} from './contracts';
import { contextSourceKey } from './context-sources';
import type { DecodedDetail, DecodedGrid } from './gosa/types';
import { assertIdentity } from './identity';
import {
  combineTransfers,
  type TransferProgress,
  type TransferProgressListener,
} from './progress';
import type { AtlasDataProvider } from './provider';
import { artifactKeyFor, type SurfaceArtifact } from './surface-columns';
import type { AtlasWorkerClient } from './worker/client';
import { assertDataBase, resolveDataUrl } from '../lib/data-url';

export interface StaticAtlasDataProviderOptions {
  /** Resolves grid, render, detail, surface, observation and download keys. */
  artifactDataBase: string;
  /** The document URL keys resolve against; defaults to `document.baseURI` at fetch time. */
  documentBase?: () => string;
  /** The parsed `#atlas-catalog` JSON, or undefined when the page has none. */
  inlineCatalog: unknown;
  /** Abort a transfer after this long without headers or a new body chunk. */
  requestStallMs?: number;
  /** Always same-origin: context sources and external caches. */
  siteDataBase: string;
  worker: AtlasWorkerClient;
}

interface ByteRequest {
  /** Catalog-declared decoded size; null makes progress indeterminate. */
  declaredBytes: number | null;
  /** performance mark recorded when the last byte arrives. */
  mark?: string;
  priority?: RequestPriority;
  progress?: TransferProgressListener;
  signal?: AbortSignal;
}

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException('Aborted', 'AbortError');
}

function abortable<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(abortReason(signal));
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(abortReason(signal));
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(
      (value) => {
        signal.removeEventListener('abort', onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener('abort', onAbort);
        reject(error);
      },
    );
  });
}

function markLastByte(name: string | undefined): void {
  if (!name) return;
  try {
    performance.mark(name);
  } catch {
    // Marks are diagnostics for the cold-load spec only.
  }
}

async function readBody(
  response: Response,
  onChunk: (loadedBytes: number) => void,
): Promise<ArrayBuffer> {
  if (!response.body) {
    const buffer = await response.arrayBuffer();
    onChunk(buffer.byteLength);
    return buffer;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loadedBytes = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loadedBytes += value.byteLength;
    onChunk(loadedBytes);
  }
  const bytes = new Uint8Array(loadedBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes.buffer;
}

export class StaticAtlasDataProvider implements AtlasDataProvider {
  static readonly defaultRequestStallMs = 15_000;

  readonly #artifactDataBase: string;
  readonly #documentBase: () => string;
  readonly #inlineCatalog: unknown;
  readonly #siteDataBase: string;
  readonly #stallMs: number;
  readonly #worker: AtlasWorkerClient;
  #catalog: AtlasCatalog | null = null;
  readonly #external = new Map<string, ExternalInfo>();
  readonly #grids = new Map<string, Promise<DecodedGrid>>();
  readonly #legacySurfaces = new Map<string, SurfaceJsonArtifact>();
  readonly #observations = new Map<string, ObservationArtifact>();
  readonly #surfaces = new Map<string, SurfaceArtifact>();

  constructor(options: StaticAtlasDataProviderOptions) {
    const stallMs =
      options.requestStallMs ?? StaticAtlasDataProvider.defaultRequestStallMs;
    if (!Number.isFinite(stallMs) || stallMs <= 0) {
      throw new Error(
        'Atlas request stall timeout must be positive and finite',
      );
    }
    assertDataBase(options.artifactDataBase);
    assertDataBase(options.siteDataBase);
    this.#artifactDataBase = options.artifactDataBase;
    this.#documentBase = options.documentBase ?? (() => document.baseURI);
    this.#inlineCatalog = options.inlineCatalog;
    this.#siteDataBase = options.siteDataBase;
    this.#stallMs = stallMs;
    this.#worker = options.worker;
  }

  #artifactUrl(key: string): string {
    return resolveDataUrl(key, this.#artifactDataBase, this.#documentBase());
  }

  #siteUrl(key: string): string {
    return resolveDataUrl(key, this.#siteDataBase, this.#documentBase());
  }

  /** One fetch with a stall timeout that restarts on headers and on every body chunk. */
  async #fetchBytes(
    url: string,
    label: string,
    request: ByteRequest,
  ): Promise<ArrayBuffer> {
    const controller = new AbortController();
    let stalled = false;
    let timer: ReturnType<typeof globalThis.setTimeout> | undefined;
    const arm = () => {
      globalThis.clearTimeout(timer);
      timer = globalThis.setTimeout(() => {
        stalled = true;
        controller.abort();
      }, this.#stallMs);
    };
    const forwardAbort = () => controller.abort(request.signal?.reason);
    if (request.signal?.aborted) forwardAbort();
    else
      request.signal?.addEventListener('abort', forwardAbort, { once: true });
    arm();
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        mode: 'cors',
        signal: controller.signal,
        ...(request.priority ? { priority: request.priority } : {}),
      });
      if (!response.ok) {
        throw new Error(
          `Atlas request failed with HTTP ${response.status}: ${label}`,
        );
      }
      arm();
      const totalBytes = request.declaredBytes;
      request.progress?.({ loadedBytes: 0, totalBytes });
      const buffer = await readBody(response, (loadedBytes) => {
        arm();
        request.progress?.({ loadedBytes, totalBytes });
      });
      markLastByte(request.mark);
      return buffer;
    } catch (error) {
      if (stalled) {
        throw new Error(
          `Atlas request stalled: no data for ${this.#stallMs} ms: ${label}`,
        );
      }
      throw error;
    } finally {
      globalThis.clearTimeout(timer);
      request.signal?.removeEventListener('abort', forwardAbort);
    }
  }

  async #fetchJson(
    url: string,
    label: string,
    request: ByteRequest,
  ): Promise<unknown> {
    return JSON.parse(
      new TextDecoder().decode(await this.#fetchBytes(url, label, request)),
    );
  }

  #parsedCatalog(): AtlasCatalog {
    if (!this.#catalog) {
      if (this.#inlineCatalog === undefined || this.#inlineCatalog === null) {
        throw new Error(
          'The Atlas catalog is missing from this page or is not valid JSON.',
        );
      }
      this.#catalog = atlasCatalogSchema.parse(this.#inlineCatalog);
    }
    return this.#catalog;
  }

  async getCatalog(
    _signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<AtlasCatalog> {
    const catalog = this.#parsedCatalog();
    progress?.({ loadedBytes: 1, totalBytes: 1 });
    return catalog;
  }

  /** Absolute URL of a catalog context source; call on the client only. */
  contextSourceUrl(catalog: AtlasCatalog, id: string): string {
    return this.#siteUrl(contextSourceKey(catalog, id));
  }

  /** The shared grid: fetched once per session, independent of any one caller's abort. */
  #grid(
    gridSha256: string,
    entry: GridEntry,
    progress?: TransferProgressListener,
  ): Promise<DecodedGrid> {
    const cached = this.#grids.get(gridSha256);
    if (cached) return cached;
    const pending = this.#fetchBytes(this.#artifactUrl(entry.url), entry.url, {
      declaredBytes: entry.bytes,
      mark: `atlas:last-byte:grid:${gridSha256}`,
      progress,
    }).then((buffer) => this.#worker.loadGrid(buffer, { entry, gridSha256 }));
    this.#grids.set(gridSha256, pending);
    pending.catch(() => {
      if (this.#grids.get(gridSha256) === pending)
        this.#grids.delete(gridSha256);
    });
    return pending;
  }

  async getSurface(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<SurfaceArtifact> {
    const key = artifactKeyFor(ref);
    const cached = this.#surfaces.get(key);
    if (cached) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return cached;
    }
    const catalog = this.#parsedCatalog();
    const gridSha256 = ref.web.grid_sha256;
    const entry = catalog.grids[gridSha256];
    if (!entry) {
      throw new Error(
        `Atlas grid ${gridSha256} for ${ref.id} is not declared in the catalog`,
      );
    }
    const parts = new Map<'grid' | 'render', TransferProgress>();
    const track = (
      part: 'grid' | 'render',
      totalBytes: number,
    ): TransferProgressListener => {
      parts.set(part, { loadedBytes: 0, totalBytes });
      return (transfer) => {
        parts.set(part, transfer);
        progress?.(combineTransfers([...parts.values()]));
      };
    };
    const gridProgress = this.#grids.has(gridSha256)
      ? undefined
      : track('grid', entry.bytes);
    const renderProgress = track('render', ref.web.render.bytes);
    const local = new AbortController();
    const forward = () => local.abort(signal?.reason);
    if (signal?.aborted) forward();
    else signal?.addEventListener('abort', forward, { once: true });
    try {
      const [grid, buffer] = await Promise.all([
        abortable(this.#grid(gridSha256, entry, gridProgress), local.signal),
        this.#fetchBytes(
          this.#artifactUrl(ref.web.render.url),
          ref.web.render.url,
          {
            declaredBytes: ref.web.render.bytes,
            mark: `atlas:last-byte:render:${key}`,
            progress: renderProgress,
            signal: local.signal,
          },
        ),
      ]);
      const render = await this.#worker.loadRender(buffer, ref, signal);
      const surface: SurfaceArtifact = {
        artifact: render.artifact,
        artifactKey: key,
        detail: null,
        grid,
        support: render.support,
        values: { post_mean: render.post_mean, post_sd: render.post_sd },
      };
      this.#surfaces.set(key, surface);
      return surface;
    } catch (error) {
      local.abort();
      throw error;
    } finally {
      signal?.removeEventListener('abort', forward);
    }
  }

  async getSurfaceDetail(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<DecodedDetail> {
    const surface = await this.getSurface(ref, signal);
    if (surface.detail) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return surface.detail;
    }
    const buffer = await this.#fetchBytes(
      this.#artifactUrl(ref.web.detail.url),
      ref.web.detail.url,
      {
        declaredBytes: ref.web.detail.bytes,
        mark: `atlas:last-byte:detail:${surface.artifactKey}`,
        priority: 'low',
        progress,
        signal,
      },
    );
    const detail = await this.#worker.loadDetail(buffer, ref, signal);
    surface.detail = detail;
    return detail;
  }

  /**
   * @deprecated Transitional full-precision JSON surface for the pre-columnar scene (fast-load
   * design §B.6.4). Removed with its last caller when the scene consumes `getSurface`.
   */
  async getSurfaceJson(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<SurfaceJsonArtifact> {
    const key = artifactKeyFor(ref);
    const cached = this.#legacySurfaces.get(key);
    if (cached) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return cached;
    }
    const artifact = surfaceArtifactSchema.parse(
      await this.#fetchJson(
        this.#artifactUrl(ref.surface_url),
        ref.surface_url,
        {
          declaredBytes: null,
          progress,
          signal,
        },
      ),
    );
    assertIdentity(ref, artifact.artifact);
    if (artifact.cells.length !== ref.n_cells) {
      throw new Error(
        `Atlas artifact row-count mismatch: expected ${ref.n_cells}, ` +
          `received ${artifact.cells.length}`,
      );
    }
    this.#legacySurfaces.set(key, artifact);
    return artifact;
  }

  async getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ObservationArtifact | null> {
    if (!ref.observations_available) return null;
    const key = `${artifactKeyFor(ref)}:${ref.observations_url}`;
    const cached = this.#observations.get(key);
    if (cached) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return cached;
    }
    const artifact = observationArtifactSchema.parse(
      await this.#fetchJson(
        this.#artifactUrl(ref.observations_url),
        ref.observations_url,
        {
          declaredBytes: ref.observations_bytes ?? null,
          mark: `atlas:last-byte:observations:${artifactKeyFor(ref)}`,
          progress,
          signal,
        },
      ),
    );
    assertIdentity(ref, artifact.artifact);
    if (artifact.observations.length !== ref.n_observations) {
      throw new Error(
        `Atlas observation count mismatch: expected ${ref.n_observations}, ` +
          `received ${artifact.observations.length}`,
      );
    }
    this.#observations.set(key, artifact);
    return artifact;
  }

  async getExternalInfo(
    ref: ArtifactRef,
    source: 'gnomad' | 'dbsnp' | 'alphagenome',
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ExternalInfo> {
    const resource = ref.external_resources.find(
      (candidate) => candidate.source === source,
    );
    if (!resource) {
      throw new Error(
        `${source} lookup is unavailable because ${ref.label} has no reviewed identifier for that resource.`,
      );
    }
    const key = `${source}:${resource.cache_sha256}`;
    const cached = this.#external.get(key);
    if (cached) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return cached;
    }
    const info = externalInfoSchema.parse(
      await this.#fetchJson(
        this.#siteUrl(resource.cache_url),
        resource.cache_url,
        {
          declaredBytes: null,
          progress,
          signal,
        },
      ),
    );
    if (
      info.source !== source ||
      info.query.normalized_variant_id !== resource.normalized_variant_id
    ) {
      throw new Error(`${source} cache identity does not match the catalog`);
    }
    if (
      (resource.source === 'gnomad' &&
        (info.source !== 'gnomad' ||
          info.query.dataset !== resource.dataset)) ||
      (resource.source === 'dbsnp' &&
        (info.source !== 'dbsnp' || info.query.rsid !== resource.rsid)) ||
      (resource.source === 'alphagenome' &&
        (info.source !== 'alphagenome' ||
          info.method !== resource.method ||
          info.record.model_version !== resource.model_version))
    ) {
      throw new Error(`${source} cache query does not match the catalog`);
    }
    this.#external.set(key, info);
    return info;
  }
}
