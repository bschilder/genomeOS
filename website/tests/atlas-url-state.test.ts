import { describe, expect, it } from 'vitest';

import type { AtlasCatalog } from '../src/atlas/contracts';
import {
  parseExplorerState,
  serializeExplorerState,
  type ExplorerState,
} from '../src/atlas/url-state';

const catalog = {
  artifacts: [
    {
      data_version: 'map-2026-08',
      id: 'hbs-rs334',
      model_version: 'v1',
    },
  ],
} as AtlasCatalog;

describe('explorer URL state', () => {
  it('preserves an unavailable requested entity instead of substituting', () => {
    const parsed = parseExplorerState('?entity=missing', catalog);
    expect(parsed.state.entityId).toBe('missing');
    expect(parsed.corrections).toContainEqual(
      expect.objectContaining({ field: 'entity', reason: 'unavailable' }),
    );
  });

  it('round-trips every stable public field', () => {
    const state: ExplorerState = {
      artifactVersion: 'v1/map-2026-08',
      camera: {
        heading: 30,
        height: 4_500_000,
        lat: 12.4,
        lon: -74.1,
        pitch: -45,
      },
      elevation: true,
      entityId: 'hbs-rs334',
      exaggeration: 2.5,
      layers: {
        context: true,
        observations: false,
        support: true,
        surface: true,
      },
      metric: 'post_sd',
      view: 'perspective',
    };

    const serialized = serializeExplorerState(state);
    expect(parseExplorerState(serialized, catalog)).toEqual({
      corrections: [],
      state,
    });
    expect(serialized).not.toContain('inspector');
  });

  it('corrects only malformed fields and preserves elevation in map view', () => {
    const parsed = parseExplorerState(
      '?entity=hbs-rs334&metric=nope&elevation=yes&view=map&lat=200&lon=-30',
      catalog,
    );

    expect(parsed.state.entityId).toBe('hbs-rs334');
    expect(parsed.state.metric).toBe('post_mean');
    expect(parsed.state.elevation).toBe(false);
    expect(parsed.state.view).toBe('map');
    expect(parsed.state.camera.lon).toBe(-30);
    expect(parsed.corrections.map(({ field }) => field).sort()).toEqual([
      'elevation',
      'lat',
      'metric',
    ]);

    const mapWithElevation = parseExplorerState(
      '?entity=hbs-rs334&view=map&elevation=true',
      catalog,
    );
    expect(mapWithElevation.state.elevation).toBe(true);
  });

  it('retains a requested unavailable version', () => {
    const parsed = parseExplorerState(
      '?entity=hbs-rs334&version=v9%2Ffuture',
      catalog,
    );
    expect(parsed.state.artifactVersion).toBe('v9/future');
    expect(parsed.corrections).toContainEqual(
      expect.objectContaining({ field: 'version', reason: 'unavailable' }),
    );
  });
});
