/** Catalog-identity comparison shared by every Atlas payload loader (Atlas design §11; fast-load design §B.3). */

import type { ArtifactIdentity, ArtifactRef } from './contracts';

export const IDENTITY_FIELDS = [
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

export function identityMessage(
  field: string,
  requested: unknown,
  received: unknown,
): string {
  return (
    `Atlas artifact identity mismatch for ${field}: requested ${String(requested)}, ` +
    `received ${String(received)}`
  );
}

export function identityMismatch(
  ref: ArtifactRef,
  loaded: ArtifactIdentity,
): string | null {
  for (const field of IDENTITY_FIELDS) {
    if (loaded[field] !== ref[field]) {
      return identityMessage(field, ref[field], loaded[field]);
    }
  }
  return null;
}

export function assertIdentity(
  ref: ArtifactRef,
  loaded: ArtifactIdentity,
): void {
  const mismatch = identityMismatch(ref, loaded);
  if (mismatch) throw new Error(mismatch);
}
