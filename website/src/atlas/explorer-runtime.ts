/** Small browser-runtime helpers for Atlas design §11. */

import type { ArtifactRef } from './contracts';
import {
  availableBasemaps,
  availableTerrains,
} from './scene/context-controller';
import type { SceneCapabilities } from './scene/types';
import type { ExplorerState } from './url-state';

export const PUBLIC_SCENE_CAPABILITIES: SceneCapabilities = {
  basemaps: availableBasemaps(''),
  terrains: availableTerrains(''),
};

export function artifactVersion(ref: ArtifactRef): string {
  return `${ref.model_version}/${ref.data_version}`;
}

export function displayKey(
  state: ExplorerState,
  reducedMotion: boolean,
): string {
  return [state.view, state.elevation, state.exaggeration, reducedMotion].join(
    ':',
  );
}

export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'An unexpected atlas error occurred.';
}

export function supportsWebGL(): boolean {
  const canvas = document.createElement('canvas');
  return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
}
