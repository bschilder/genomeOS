/** Validated static-file implementation of the Atlas design §11 data provider. */

import {
  atlasCatalogSchema,
  externalInfoSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
  type ArtifactIdentity,
  type ArtifactRef,
  type AtlasCatalog,
  type ObservationArtifact,
  type SurfaceArtifact,
  type ExternalInfo,
} from './contracts';
import type { AtlasDataProvider } from './provider';
import type { TransferProgressListener } from './progress';

const IDENTITY_FIELDS = [
  'artifact_format',
  'data_version',
  'entity_type',
  'hf_dataset',
  'hf_revision',
  'id',
  'measurement',
  'model_version',
  'registry_version',
  'resolution',
  'target_grid_source',
  'target_grid_version',
  'variant_id',
] as const satisfies readonly (keyof ArtifactIdentity)[];

function assertIdentity(ref: ArtifactRef, loaded: ArtifactIdentity): void {
  for (const field of IDENTITY_FIELDS) {
    if (loaded[field] !== ref[field]) {
      throw new Error(
        `Atlas artifact identity mismatch for ${field}: requested ${String(ref[field])}, ` +
          `received ${String(loaded[field])}`,
      );
    }
  }
}

export class StaticAtlasDataProvider implements AtlasDataProvider {
  static readonly defaultRequestTimeoutMs = 15_000;

  readonly #baseUrl: string;
  readonly #requestTimeoutMs: number;
  #catalog: AtlasCatalog | null = null;
  readonly #surfaces = new Map<string, SurfaceArtifact>();
  readonly #observations = new Map<string, ObservationArtifact>();
  readonly #external = new Map<string, ExternalInfo>();

  constructor(
    baseUrl: string,
    requestTimeoutMs = StaticAtlasDataProvider.defaultRequestTimeoutMs,
  ) {
    if (!Number.isFinite(requestTimeoutMs) || requestTimeoutMs <= 0) {
      throw new Error('Atlas request timeout must be positive and finite');
    }
    this.#baseUrl = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
    this.#requestTimeoutMs = requestTimeoutMs;
  }

  async #getJson(
    path: string,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<unknown> {
    const controller = new AbortController();
    let timedOut = false;
    const forwardAbort = () => controller.abort(signal?.reason);
    if (signal?.aborted) forwardAbort();
    else signal?.addEventListener('abort', forwardAbort, { once: true });
    const timeout = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.#requestTimeoutMs);

    try {
      const response = await fetch(
        `${this.#baseUrl}${path.replace(/^\/+/, '')}`,
        { signal: controller.signal },
      );
      if (!response.ok) {
        throw new Error(
          `Atlas request failed with HTTP ${response.status}: ${path}`,
        );
      }
      if (!progress) return response.json();
      const declaredSize = Number(response.headers.get('Content-Length'));
      const contentEncoding = response.headers.get('Content-Encoding');
      const totalBytes =
        (!contentEncoding || contentEncoding === 'identity') &&
        Number.isFinite(declaredSize) &&
        declaredSize > 0
          ? declaredSize
          : null;
      progress({ loadedBytes: 0, totalBytes });
      if (!response.body) {
        const body = await response.text();
        const loadedBytes = new TextEncoder().encode(body).length;
        progress({ loadedBytes, totalBytes });
        return JSON.parse(body);
      }
      const chunks: string[] = [];
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let loadedBytes = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(decoder.decode(value, { stream: true }));
        loadedBytes += value.byteLength;
        progress({ loadedBytes, totalBytes });
      }
      chunks.push(decoder.decode());
      progress({ loadedBytes, totalBytes });
      return JSON.parse(chunks.join(''));
    } catch (error) {
      if (timedOut) {
        throw new Error(
          `Atlas request timed out after ${this.#requestTimeoutMs} ms: ${path}`,
        );
      }
      throw error;
    } finally {
      globalThis.clearTimeout(timeout);
      signal?.removeEventListener('abort', forwardAbort);
    }
  }

  async getCatalog(
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<AtlasCatalog> {
    if (this.#catalog) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return this.#catalog;
    }
    const catalog = atlasCatalogSchema.parse(
      await this.#getJson('catalog.json', signal, progress),
    );
    this.#catalog = catalog;
    return catalog;
  }

  async getSurface(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<SurfaceArtifact> {
    const key = `${ref.id}:${ref.model_version}:${ref.data_version}:${ref.surface_url}`;
    const cached = this.#surfaces.get(key);
    if (cached) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return cached;
    }
    const artifact = surfaceArtifactSchema.parse(
      await this.#getJson(ref.surface_url, signal, progress),
    );
    assertIdentity(ref, artifact.artifact);
    if (artifact.cells.length !== ref.n_cells) {
      throw new Error(
        `Atlas artifact row-count mismatch: expected ${ref.n_cells}, ` +
          `received ${artifact.cells.length}`,
      );
    }
    this.#surfaces.set(key, artifact);
    return artifact;
  }

  async getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ObservationArtifact | null> {
    if (!ref.observations_available) return null;
    const key = `${ref.id}:${ref.model_version}:${ref.data_version}:${ref.observations_url}`;
    const cached = this.#observations.get(key);
    if (cached) {
      progress?.({ loadedBytes: 1, totalBytes: 1 });
      return cached;
    }
    const artifact = observationArtifactSchema.parse(
      await this.#getJson(ref.observations_url, signal, progress),
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
      await this.#getJson(resource.cache_url, signal, progress),
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
          info.record.model_version !== resource.model_version))
    ) {
      throw new Error(`${source} cache query does not match the catalog`);
    }
    this.#external.set(key, info);
    return info;
  }
}
