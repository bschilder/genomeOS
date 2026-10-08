import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/atlas/worker/client', () => ({
  startAtlasWorker: vi.fn(() => ({ kind: 'fake-worker-client' })),
}));

import {
  atlasWorker,
  bootAtlas,
  loadAtlasSceneModule,
} from '../src/atlas/boot';
import * as catalog from '../src/atlas/earth-style-catalog';
import * as contextController from '../src/atlas/scene/context-controller';
import * as scenePolicy from '../src/atlas/scene/scene-policy';
import { startAtlasWorker } from '../src/atlas/worker/client';

describe('island boot', () => {
  it('does nothing during server rendering', () => {
    expect(typeof window).toBe('undefined');
    bootAtlas();
    expect(startAtlasWorker).not.toHaveBeenCalled();
  });

  it('starts exactly one data worker per page', () => {
    expect(atlasWorker()).toBe(atlasWorker());
    expect(startAtlasWorker).toHaveBeenCalledTimes(1);
  });

  it('shares one lazy scene-module import', async () => {
    const first = loadAtlasSceneModule();
    expect(loadAtlasSceneModule()).toBe(first);
    expect(typeof (await first).createAtlasScene).toBe('function');
  });
});

describe('Cesium-free helpers', () => {
  it('live in earth-style-catalog and stay re-exported from their old homes', () => {
    expect(contextController.availableBasemaps).toBe(catalog.availableBasemaps);
    expect(contextController.availableTerrains).toBe(catalog.availableTerrains);
    expect(contextController.ionCapability).toBe(catalog.ionCapability);
    expect(scenePolicy.resolveElevationView).toBe(catalog.resolveElevationView);
    expect(catalog.resolveElevationView('map', true)).toBe('perspective');
    expect(catalog.ionCapability('')).toEqual({
      available: false,
      reason: catalog.ION_UNAVAILABLE,
    });
  });
});
