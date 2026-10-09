/** Pure rules of the Atlas artifact pipeline (Atlas design §11; spec 2026-10-07 §B.2, §B.6.8). */

import type {
  ArtifactRef,
  Observation,
  ObservationArtifact,
} from '../../atlas/contracts';
import type { SurfaceArtifact } from '../../atlas/surface-columns';
import {
  AtlasWorkerError,
  isArtifactValidationError,
} from '../../atlas/worker/client';
import type { DetailStatus } from './surface-cell-view';

export type DetailFailure = 'unavailable' | 'invalid';

export interface LoadedArtifact {
  readonly artifactKey: string;
  readonly ref: ArtifactRef;
  surface: SurfaceArtifact | null;
  observations: ObservationArtifact | null;
  observationMap: ReadonlyMap<string, Observation>;
}

export function createLoadedArtifact(
  artifactKey: string,
  ref: ArtifactRef,
): LoadedArtifact {
  return {
    artifactKey,
    observationMap: new Map(),
    observations: null,
    ref,
    surface: null,
  };
}

export function attachObservations(
  entry: LoadedArtifact,
  observations: ObservationArtifact | null,
): void {
  entry.observations = observations;
  entry.observationMap = new Map(
    (observations?.observations ?? []).map((observation) => [
      observation.source_record_id,
      observation,
    ]),
  );
}

export function detailStatusFor(
  surface: SurfaceArtifact | null,
  failure: DetailFailure | undefined,
): DetailStatus {
  if (failure) return failure;
  return surface?.detail ? 'ready' : 'loading';
}

/**
 * Corrupt data is the worker's checksum or validation failure (`isArtifactValidationError`, the
 * one owner of that rule); everything else is retryable.
 */
export function classifyDetailFailure(
  error: unknown,
): DetailFailure | 'aborted' {
  if (
    (error instanceof Error && error.name === 'AbortError') ||
    (error instanceof AtlasWorkerError && error.code === 'cancelled')
  )
    return 'aborted';
  return isArtifactValidationError(error) ? 'invalid' : 'unavailable';
}

export function withoutKey<T>(
  record: Readonly<Record<string, T>>,
  key: string,
): Record<string, T> {
  const next = { ...record };
  delete next[key];
  return next;
}
