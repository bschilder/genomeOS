/** Stable scene defaults and view policy for Atlas design §11. */

import { Color, type Viewer } from 'cesium';

import type {
  CameraState,
  ExplorerSceneMode,
  LayerVisibility,
} from '../url-state';
import type { ObservationPresentation } from './types';
import { DEFAULT_OBSERVATION_SIZE_RANGE } from '../observation-encoding';

export interface EarthOpacityTarget {
  depthTestAgainstTerrain: boolean;
  translucency: {
    backFaceAlpha: number;
    enabled: boolean;
    frontFaceAlpha: number;
  };
}

export interface OceanColorTarget {
  baseColor: Color;
}

export function applyOceanColor(globe: OceanColorTarget, color: string): void {
  globe.baseColor = Color.fromCssColorString(color);
}

export function applyEarthOpacity(
  globe: EarthOpacityTarget,
  opacity: number,
): void {
  const safeOpacity = Math.min(1, Math.max(0.15, opacity));
  globe.depthTestAgainstTerrain = true;
  globe.translucency.frontFaceAlpha = safeOpacity;
  globe.translucency.backFaceAlpha = safeOpacity;
  globe.translucency.enabled = safeOpacity < 1;
}

export const DEFAULT_LAYERS: LayerVisibility = {
  context: true,
  countries: true,
  observations: true,
  support: true,
  surface: true,
};

export const DEFAULT_OBSERVATIONS: ObservationPresentation = {
  colorVariable: 'solid',
  gradient: ['#24144b', '#ad8bff', '#f4c86a'],
  opacity: 1,
  samplingAreaColor: '#9af9e2',
  sizeRange: DEFAULT_OBSERVATION_SIZE_RANGE,
  samplingAreas: true,
  shape: 'sphere',
  sizeVariable: 'frequency',
  solidColor: '#f4fbff',
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
  applyOceanColor(scene.globe, '#071b35');
  applyEarthOpacity(scene.globe, 1);
  scene.globe.enableLighting = true;
  scene.globe.showGroundAtmosphere = true;
  scene.fog.enabled = true;
  scene.fog.density = 0.00012;
  scene.highDynamicRange = true;
  scene.postProcessStages.fxaa.enabled = true;
  scene.postProcessStages.bloom.enabled = false;
  viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 1.5);
}
