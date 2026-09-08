/** Replaceable atlas-data boundary for Atlas design §11. */

import type {
  ArtifactRef,
  AtlasCatalog,
  ExternalInfo,
  ObservationArtifact,
  SurfaceArtifact,
} from './contracts';

export type AtlasDataProvider = {
  getCatalog(signal?: AbortSignal): Promise<AtlasCatalog>;
  getSurface(ref: ArtifactRef, signal?: AbortSignal): Promise<SurfaceArtifact>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
  ): Promise<ObservationArtifact | null>;
  getExternalInfo(
    ref: ArtifactRef,
    source: 'gnomad' | 'dbsnp',
    signal?: AbortSignal,
  ): Promise<ExternalInfo>;
};
