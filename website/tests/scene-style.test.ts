import { describe, expect, it, vi } from 'vitest';

import type { AtlasCatalog } from '../src/atlas/contracts';
import { applySceneStyle, observationStyleFor } from '../src/atlas/scene-style';
import type { AtlasSceneController } from '../src/atlas/scene/types';
import { parseExplorerState, type ExplorerState } from '../src/atlas/url-state';

const catalog = {
  artifacts: [
    { data_version: 'map-2026-08', id: 'hbs-rs334', model_version: 'v1' },
  ],
} as AtlasCatalog;

function recordingController() {
  const resolved = () => Promise.resolve(true);
  return {
    setBasemap: vi.fn(resolved),
    setCountryBorderStyle: vi.fn(),
    setEarthOpacity: vi.fn(),
    setLayerVisibility: vi.fn(),
    setMapPresentation: vi.fn(),
    setMetric: vi.fn(() => Promise.resolve()),
    setObservationStyle: vi.fn(() => Promise.resolve()),
    setOceanColor: vi.fn(),
    setSurfaceStyle: vi.fn(() => Promise.resolve()),
    setTerrain: vi.fn(resolved),
  };
}

describe('applySceneStyle', () => {
  const state: ExplorerState = {
    ...parseExplorerState('', catalog).state,
    basemap: 'openstreetmap',
    cellEdges: false,
    countryBorderColor: '#ffaa00',
    countryBorderOpacity: 0.3,
    earthOpacity: 0.8,
    layers: {
      context: false,
      countries: true,
      observations: true,
      support: false,
      surface: true,
    },
    metric: 'post_sd',
    oceanColor: '#112233',
    surfaceGeometry: 'hexagons',
    surfacePalette: 'viridis',
    terrain: 'smooth-globe',
  };

  it('pushes every scene-style field of the current state to a new scene', () => {
    const controller = recordingController();
    applySceneStyle(controller as unknown as AtlasSceneController, state);
    expect(controller.setMetric).toHaveBeenCalledWith('post_sd');
    expect(controller.setSurfaceStyle).toHaveBeenCalledWith(
      'viridis',
      state.surfaceOpacity,
      false,
      state.edgeColorMode,
      state.edgeFixedColor,
      'hexagons',
    );
    expect(controller.setObservationStyle).toHaveBeenCalledWith(
      observationStyleFor(state),
    );
    expect(controller.setBasemap).toHaveBeenCalledWith('openstreetmap');
    expect(controller.setMapPresentation).toHaveBeenCalledWith(
      state.basemapOpacity,
      state.basemapBrightness,
      state.dayNightLighting,
    );
    expect(controller.setTerrain).toHaveBeenCalledWith('smooth-globe');
    expect(controller.setLayerVisibility).toHaveBeenCalledWith(state.layers);
    expect(controller.setEarthOpacity).toHaveBeenCalledWith(0.8);
    expect(controller.setOceanColor).toHaveBeenCalledWith('#112233');
    expect(controller.setCountryBorderStyle).toHaveBeenCalledWith(
      '#ffaa00',
      0.3,
    );
  });

  it('builds the observation presentation from the observation fields', () => {
    expect(observationStyleFor(state)).toEqual({
      colorVariable: state.observationColor,
      gradient: state.observationGradient,
      opacity: state.observationOpacity,
      samplingAreaColor: state.samplingAreaColor,
      samplingAreas: state.samplingAreas,
      shape: state.observationShape,
      sizeRange: state.observationSizeRange,
      sizeVariable: state.observationSize,
      solidColor: state.observationSolidColor,
    });
  });
});
