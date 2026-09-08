/** Replaceable atlas-data boundary for Atlas design §11. */

import type {
  ArtifactRef,
  AtlasCatalog,
  ExternalInfo,
  ObservationArtifact,
  SurfaceArtifact,
} from './contracts';
import type { TransferProgressListener } from './progress';

export type AtlasDataProvider = {
  getCatalog(
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<AtlasCatalog>;
  getSurface(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<SurfaceArtifact>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ObservationArtifact | null>;
  getExternalInfo(
    ref: ArtifactRef,
    source: 'gnomad' | 'dbsnp',
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ExternalInfo>;
};
