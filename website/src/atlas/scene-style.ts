/** Push the explorer's complete scene style to a newly available scene (Atlas design §11; fast-load design §B.6.11). */

import type {
  AtlasSceneController,
  ObservationPresentation,
} from './scene/types';
import type { ExplorerState } from './url-state';

export function observationStyleFor(
  state: ExplorerState,
): ObservationPresentation {
  return {
    colorVariable: state.observationColor,
    gradient: state.observationGradient,
    opacity: state.observationOpacity,
    samplingAreaColor: state.samplingAreaColor,
    samplingAreas: state.samplingAreas,
    shape: state.observationShape,
    sizeRange: state.observationSizeRange,
    sizeVariable: state.observationSize,
    solidColor: state.observationSolidColor,
  };
}

/** Every scene-style setter, applied directly (no activity) when a scene is created or recreated. */
export function applySceneStyle(
  controller: AtlasSceneController,
  state: ExplorerState,
): void {
  void controller.setMetric(state.metric);
  void controller.setSurfaceStyle(
    state.surfacePalette,
    state.surfaceOpacity,
    state.cellEdges,
    state.edgeColorMode,
    state.edgeFixedColor,
    state.surfaceGeometry,
  );
  void controller.setObservationStyle(observationStyleFor(state));
  void controller.setBasemap(state.basemap);
  controller.setMapPresentation(
    state.basemapOpacity,
    state.basemapBrightness,
    state.dayNightLighting,
  );
  void controller.setTerrain(state.terrain);
  controller.setLayerVisibility(state.layers);
  controller.setEarthOpacity(state.earthOpacity);
  controller.setOceanColor(state.oceanColor);
  controller.setCountryBorderStyle(
    state.countryBorderColor,
    state.countryBorderOpacity,
  );
}
