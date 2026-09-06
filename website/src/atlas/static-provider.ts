/** Validated static-file implementation of the Atlas design §11 data provider. */

import {
  atlasCatalogSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
  type ArtifactIdentity,
  type ArtifactRef,
  type AtlasCatalog,
  type ObservationArtifact,
  type SurfaceArtifact,
} from './contracts';
import type { AtlasDataProvider } from './provider';

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
  readonly #baseUrl: string;
  #catalog: AtlasCatalog | null = null;
  readonly #surfaces = new Map<string, SurfaceArtifact>();
  readonly #observations = new Map<string, ObservationArtifact>();

  constructor(baseUrl: string) {
    this.#baseUrl = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
  }

  async #getJson(path: string, signal?: AbortSignal): Promise<unknown> {
    const response = await fetch(
      `${this.#baseUrl}${path.replace(/^\/+/, '')}`,
      { signal },
    );
    if (!response.ok) {
      throw new Error(
        `Atlas request failed with HTTP ${response.status}: ${path}`,
      );
    }
    return response.json();
  }

  async getCatalog(signal?: AbortSignal): Promise<AtlasCatalog> {
    if (this.#catalog) return this.#catalog;
    const catalog = atlasCatalogSchema.parse(
      await this.#getJson('catalog.json', signal),
    );
    this.#catalog = catalog;
    return catalog;
  }

  async getSurface(
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<SurfaceArtifact> {
    const key = `${ref.id}:${ref.model_version}:${ref.data_version}:${ref.surface_url}`;
    const cached = this.#surfaces.get(key);
    if (cached) return cached;
    const artifact = surfaceArtifactSchema.parse(
      await this.#getJson(ref.surface_url, signal),
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
  ): Promise<ObservationArtifact> {
    const key = `${ref.id}:${ref.model_version}:${ref.data_version}:${ref.observations_url}`;
    const cached = this.#observations.get(key);
    if (cached) return cached;
    const artifact = observationArtifactSchema.parse(
      await this.#getJson(ref.observations_url, signal),
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
}
