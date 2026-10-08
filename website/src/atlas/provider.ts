/** Replaceable atlas-data boundary for Atlas design §11 and fast-load design §B.6. */

import type {
  ArtifactRef,
  AtlasCatalog,
  ExternalInfo,
  ObservationArtifact,
} from './contracts';
import type { DecodedDetail } from './gosa/types';
import type { TransferProgressListener } from './progress';
import type { SurfaceArtifact } from './surface-columns';

export type AtlasDataProvider = {
  getCatalog(
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<AtlasCatalog>;
  /** The columnar grid + render tiers; colour, height and bins only. */
  getSurface(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<SurfaceArtifact>;
  /** The float64 detail tier, attached to the cached surface; the only source of displayed numbers. */
  getSurfaceDetail(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<DecodedDetail>;
  getObservations(
    ref: ArtifactRef,
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ObservationArtifact | null>;
  getExternalInfo(
    ref: ArtifactRef,
    source: 'gnomad' | 'dbsnp' | 'alphagenome',
    signal?: AbortSignal,
    progress?: TransferProgressListener,
  ): Promise<ExternalInfo>;
};
