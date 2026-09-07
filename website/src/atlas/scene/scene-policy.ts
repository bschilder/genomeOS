/** Stable scene defaults and view policy for Atlas design §11. */

import { Color, type Viewer } from 'cesium';

import type {
  CameraState,
  ExplorerSceneMode,
  LayerVisibility,
} from '../url-state';
import type { ObservationPresentation } from './types';

export const DEFAULT_LAYERS: LayerVisibility = {
  context: true,
  observations: true,
  support: true,
  surface: true,
};

export const DEFAULT_OBSERVATIONS: ObservationPresentation = {
  colorVariable: 'white',
  hemisphereRange: [40, 300],
  pointRange: [6, 18],
  samplingAreas: true,
  shape: 'circle',
  sizeVariable: 'fixed',
};

export const HOME_CAMERA: CameraState = {
  heading: 0,
  height: 16_500_000,
  lat: 12,
  lon: 20,
  pitch: -90,
};

export function resolveElevationView(
  view: ExplorerSceneMode,
  elevationEnabled: boolean,
): ExplorerSceneMode {
  return view === 'map' && elevationEnabled ? 'perspective' : view;
}

export function styleAtlasScene(viewer: Viewer): void {
  const scene = viewer.scene;
  scene.backgroundColor = Color.fromCssColorString('#020712');
  scene.globe.baseColor = Color.fromCssColorString('#071b35');
  scene.globe.enableLighting = true;
  scene.globe.showGroundAtmosphere = true;
  scene.fog.enabled = true;
  scene.fog.density = 0.00012;
  scene.highDynamicRange = true;
  scene.postProcessStages.fxaa.enabled = true;
  scene.postProcessStages.bloom.enabled = true;
  scene.postProcessStages.bloom.uniforms.brightness = -0.18;
  scene.postProcessStages.bloom.uniforms.contrast = 92;
  viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 1.5);
}
