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
      basemap: 'aerial-labels',
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
      cellEdges: true,
      layers: {
        context: true,
        observations: false,
        support: true,
        surface: true,
      },
      metric: 'post_sd',
      observationColor: 'study',
      observationHemisphereRange: [40, 320],
      observationPointRange: [7, 22],
      observationShape: 'pin',
      observationSize: 'ac',
      paletteMode: 'custom',
      samplingAreas: false,
      surfaceOpacity: 0.72,
      surfacePalette: 'cividis',
      terrain: 'world-terrain',
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

  it('uses metric-specific palettes only when no explicit palette is present', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334&metric=post_mean', catalog).state,
    ).toMatchObject({
      paletteMode: 'metric-default',
      surfacePalette: 'genome',
    });
    expect(
      parseExplorerState('?entity=hbs-rs334&metric=post_sd', catalog).state,
    ).toMatchObject({
      paletteMode: 'metric-default',
      surfacePalette: 'signal',
    });
    expect(
      parseExplorerState(
        '?entity=hbs-rs334&metric=post_sd&palette=genome',
        catalog,
      ).state,
    ).toMatchObject({ paletteMode: 'custom', surfacePalette: 'genome' });
  });

  it('builds cell edges only when explicitly requested', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334', catalog).state.cellEdges,
    ).toBe(false);
    expect(
      parseExplorerState('?entity=hbs-rs334&elevation=true', catalog).state
        .cellEdges,
    ).toBe(false);
    expect(
      parseExplorerState('?entity=hbs-rs334&elevation=true&edges=true', catalog)
        .state.cellEdges,
    ).toBe(true);
  });

  it('corrects both fields of a reversed size range without touching valid state', () => {
    const parsed = parseExplorerState(
      '?entity=hbs-rs334&pointMin=20&pointMax=5&domeMin=40&domeMax=300&opacity=0.7',
      catalog,
    );
    expect(parsed.state.observationPointRange).toEqual([6, 18]);
    expect(parsed.state.observationHemisphereRange).toEqual([40, 300]);
    expect(parsed.state.surfaceOpacity).toBe(0.7);
    expect(parsed.corrections.map(({ field }) => field).sort()).toEqual([
      'pointMax',
      'pointMin',
    ]);
  });
});
