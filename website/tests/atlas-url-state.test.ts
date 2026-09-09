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
      basemapBrightness: 0.68,
      basemapOpacity: 0.72,
      camera: {
        heading: 30,
        height: 4_500_000,
        lat: 12.4,
        lon: -74.1,
        pitch: -45,
      },
      elevation: true,
      earthOpacity: 0.81,
      countryBorderColor: '#ffffff',
      countryBorderOpacity: 0.5,
      dayNightLighting: true,
      edgeColorMode: 'fixed',
      edgeFixedColor: '#cceeff',
      entityId: 'hbs-rs334',
      exaggeration: 2.5,
      cellEdges: true,
      layers: {
        context: true,
        countries: false,
        observations: false,
        support: true,
        surface: true,
      },
      metric: 'post_sd',
      observationColor: 'study',
      observationGradient: ['#112233', '#44aa88', '#ffcc66'],
      observationOpacity: 0.74,
      observationSizeRange: [17, 42],
      observationShape: 'pin',
      observationSize: 'ac',
      observationSolidColor: '#abcdef',
      oceanColor: '#123456',
      paletteMode: 'custom',
      samplingAreas: false,
      samplingAreaColor: '#55ddcc',
      surfaceOpacity: 0.72,
      surfaceGeometry: 'extruded',
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

  it.each([
    'arcgis-imagery',
    'blue-marble',
    'google-contour',
    'natural-earth-ii',
    'stadia-watercolor',
  ])('preserves the gallery basemap ID %s', (basemap) => {
    const parsed = parseExplorerState(
      `?entity=hbs-rs334&basemap=${basemap}`,
      catalog,
    );
    expect(parsed.state.basemap).toBe(basemap);
    expect(parsed.corrections).not.toContainEqual(
      expect.objectContaining({ field: 'basemap' }),
    );
  });

  it('defaults the Earth to fully opaque and rejects invalid opacity', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334', catalog).state.earthOpacity,
    ).toBe(1);

    const translucent = parseExplorerState(
      '?entity=hbs-rs334&earthOpacity=0.45',
      catalog,
    );
    expect(translucent.state.earthOpacity).toBe(0.45);

    const invalid = parseExplorerState(
      '?entity=hbs-rs334&earthOpacity=0',
      catalog,
    );
    expect(invalid.state.earthOpacity).toBe(1);
    expect(invalid.corrections).toContainEqual(
      expect.objectContaining({ field: 'earthOpacity', reason: 'malformed' }),
    );
  });

  it('defaults, validates, and shares the ocean color', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334', catalog).state.oceanColor,
    ).toBe('#071b35');

    const custom = parseExplorerState(
      '?entity=hbs-rs334&oceanColor=%23225588',
      catalog,
    );
    expect(custom.state.oceanColor).toBe('#225588');
    expect(custom.corrections).toEqual([]);

    const invalid = parseExplorerState(
      '?entity=hbs-rs334&oceanColor=navy',
      catalog,
    );
    expect(invalid.state.oceanColor).toBe('#071b35');
    expect(invalid.corrections).toContainEqual(
      expect.objectContaining({ field: 'oceanColor', reason: 'malformed' }),
    );
  });

  it('defaults to full-opacity half-bright basemap styling and validates shareable adjustments', () => {
    const defaults = parseExplorerState('?entity=hbs-rs334', catalog).state;
    expect(defaults.basemapOpacity).toBe(1);
    expect(defaults.basemapBrightness).toBe(0.5);
    expect(defaults.dayNightLighting).toBe(true);

    const adjusted = parseExplorerState(
      '?entity=hbs-rs334&basemapOpacity=0.64&basemapBrightness=0.75&dayNight=false',
      catalog,
    );
    expect(adjusted.state.basemapOpacity).toBe(0.64);
    expect(adjusted.state.basemapBrightness).toBe(0.75);
    expect(adjusted.state.dayNightLighting).toBe(false);
    expect(adjusted.corrections).toEqual([]);

    const invalid = parseExplorerState(
      '?entity=hbs-rs334&basemapOpacity=-0.01&basemapBrightness=1.01&dayNight=sometimes',
      catalog,
    );
    expect(invalid.state.basemapOpacity).toBe(1);
    expect(invalid.state.basemapBrightness).toBe(0.5);
    expect(invalid.state.dayNightLighting).toBe(true);
    expect(invalid.corrections.map(({ field }) => field).sort()).toEqual([
      'basemapBrightness',
      'basemapOpacity',
      'dayNight',
    ]);

    const zeroed = parseExplorerState(
      '?entity=hbs-rs334&basemapOpacity=0&basemapBrightness=0',
      catalog,
    );
    expect(zeroed.state.basemapOpacity).toBe(0);
    expect(zeroed.state.basemapBrightness).toBe(0);
    expect(zeroed.corrections).toEqual([]);
  });

  it('defaults to full-opacity frequency-sized sphere observations', () => {
    const state = parseExplorerState('?entity=hbs-rs334', catalog).state;
    expect(state.observationSize).toBe('frequency');
    expect(state.observationShape).toBe('sphere');
    expect(state.observationOpacity).toBe(1);
  });

  it('round-trips spheres and preserves explicitly selected domes', () => {
    const parsed = parseExplorerState(
      '?entity=hbs-rs334&obsShape=sphere',
      catalog,
    );

    expect(parsed.corrections).toEqual([]);
    expect(parsed.state.observationShape).toBe('sphere');
    expect(
      parseExplorerState(serializeExplorerState(parsed.state), catalog).state
        .observationShape,
    ).toBe('sphere');

    const dome = parseExplorerState(
      '?entity=hbs-rs334&obsShape=hemisphere&obsOpacity=0.62',
      catalog,
    );
    expect(dome.corrections).toEqual([]);
    expect(dome.state.observationShape).toBe('hemisphere');
    expect(dome.state.observationOpacity).toBe(0.62);
  });

  it('defaults and validates the sampling-area outline color', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334', catalog).state.samplingAreaColor,
    ).toBe('#9af9e2');
    const invalid = parseExplorerState(
      '?entity=hbs-rs334&samplingColor=teal',
      catalog,
    );
    expect(invalid.state.samplingAreaColor).toBe('#9af9e2');
    expect(invalid.corrections).toContainEqual(
      expect.objectContaining({ field: 'samplingColor', reason: 'malformed' }),
    );
  });

  it('defaults country outlines to half-opacity white and validates overrides', () => {
    const defaults = parseExplorerState('?entity=hbs-rs334', catalog).state;
    expect(defaults.countryBorderColor).toBe('#ffffff');
    expect(defaults.countryBorderOpacity).toBe(0.5);

    const custom = parseExplorerState(
      '?entity=hbs-rs334&countryColor=%23ff3366&countryOpacity=0.8',
      catalog,
    ).state;
    expect(custom.countryBorderColor).toBe('#ff3366');
    expect(custom.countryBorderOpacity).toBe(0.8);
  });

  it('tracks country outlines and labels independently from basemap geography', () => {
    const defaults = parseExplorerState('?entity=hbs-rs334', catalog).state;
    expect(defaults.layers.context).toBe(true);
    expect(defaults.layers.countries).toBe(true);

    const countriesOnly = parseExplorerState(
      '?entity=hbs-rs334&layers=countries',
      catalog,
    ).state;
    expect(countriesOnly.layers).toEqual({
      context: false,
      countries: true,
      observations: false,
      support: false,
      surface: false,
    });
  });

  it('defaults to smooth triangles and preserves every surface geometry', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334', catalog).state.surfaceGeometry,
    ).toBe('triangles');
    expect(
      parseExplorerState('?entity=hbs-rs334&geometry=hexagons', catalog).state
        .surfaceGeometry,
    ).toBe('hexagons');
    expect(
      parseExplorerState('?entity=hbs-rs334&geometry=extruded', catalog).state
        .surfaceGeometry,
    ).toBe('extruded');
    expect(
      parseExplorerState('?entity=hbs-rs334&geometry=honmoon', catalog).state
        .surfaceGeometry,
    ).toBe('honmoon');
    expect(
      parseExplorerState('?entity=hbs-rs334&geometry=honmoon-fill', catalog)
        .state.surfaceGeometry,
    ).toBe('honmoon-fill');
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

  it('corrects an unavailable version for an available entity', () => {
    const parsed = parseExplorerState(
      '?entity=hbs-rs334&version=v9%2Ffuture',
      catalog,
    );
    expect(parsed.state.artifactVersion).toBe('v1/map-2026-08');
    expect(parsed.corrections).toContainEqual(
      expect.objectContaining({ field: 'version', reason: 'unavailable' }),
    );
  });

  it('uses metric-specific palettes only when no explicit palette is present', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334&metric=post_mean', catalog).state,
    ).toMatchObject({
      paletteMode: 'metric-default',
      surfacePalette: 'rainbow',
    });
    expect(
      parseExplorerState('?entity=hbs-rs334&metric=post_sd', catalog).state,
    ).toMatchObject({
      paletteMode: 'metric-default',
      surfacePalette: 'plasma',
    });
    expect(
      parseExplorerState(
        '?entity=hbs-rs334&metric=post_sd&palette=genome',
        catalog,
      ).state,
    ).toMatchObject({ paletteMode: 'custom', surfacePalette: 'genome' });
  });

  it('shows cell outlines by default while preserving explicit URL choices', () => {
    expect(
      parseExplorerState('?entity=hbs-rs334', catalog).state.cellEdges,
    ).toBe(true);
    expect(
      parseExplorerState('?entity=hbs-rs334&elevation=true', catalog).state
        .cellEdges,
    ).toBe(true);
    expect(
      parseExplorerState('?entity=hbs-rs334&edges=false', catalog).state
        .cellEdges,
    ).toBe(false);
    expect(
      parseExplorerState('?entity=hbs-rs334&elevation=true&edges=true', catalog)
        .state.cellEdges,
    ).toBe(true);
  });

  it('corrects both fields of a reversed size range without touching valid state', () => {
    const parsed = parseExplorerState(
      '?entity=hbs-rs334&pointMin=40&pointMax=20&opacity=0.7',
      catalog,
    );
    expect(parsed.state.observationSizeRange).toEqual([12, 32]);
    expect(parsed.state.surfaceOpacity).toBe(0.7);
    expect(parsed.corrections.map(({ field }) => field).sort()).toEqual([
      'pointMax',
      'pointMin',
    ]);
  });
});
