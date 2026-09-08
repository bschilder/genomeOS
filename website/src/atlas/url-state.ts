/** Shareable, field-by-field explorer URL state for Atlas design §11. */

import type { AtlasCatalog } from './contracts';
import type {
  ObservationColorVariable,
  ObservationShape,
  ObservationSizeRange,
  ObservationSizeVariable,
} from './observation-encoding';
import {
  DEFAULT_OBSERVATION_SIZE_RANGE,
  MAX_OBSERVATION_MARKER_SIZE,
  MIN_OBSERVATION_MARKER_SIZE,
} from './observation-encoding';
import {
  BASEMAP_IDS,
  TERRAIN_IDS,
  type BasemapId,
  type TerrainId,
} from './earth-style-catalog';
import { defaultPalette, type Metric, type PaletteId } from './visual-encoding';

export type ExplorerSceneMode = 'globe' | 'map' | 'perspective';
export type { BasemapId, TerrainId } from './earth-style-catalog';
export type LayerId =
  'surface' | 'observations' | 'support' | 'context' | 'countries';
export type LayerVisibility = Record<LayerId, boolean>;
export type EdgeColorMode = 'fixed' | 'matched';
export type SurfaceGeometry =
  'triangles' | 'hexagons' | 'extruded' | 'honmoon' | 'honmoon-fill';

export interface CameraState {
  lon: number;
  lat: number;
  height: number;
  heading: number;
  pitch: number;
}

export interface ExplorerState {
  entityId: string;
  artifactVersion: string;
  basemap: BasemapId;
  basemapBrightness: number;
  basemapOpacity: number;
  metric: Metric;
  surfacePalette: PaletteId;
  paletteMode: 'metric-default' | 'custom';
  surfaceOpacity: number;
  surfaceGeometry: SurfaceGeometry;
  earthOpacity: number;
  oceanColor: string;
  cellEdges: boolean;
  edgeColorMode: EdgeColorMode;
  edgeFixedColor: string;
  countryBorderColor: string;
  countryBorderOpacity: number;
  dayNightLighting: boolean;
  layers: LayerVisibility;
  view: ExplorerSceneMode;
  terrain: TerrainId;
  elevation: boolean;
  exaggeration: number;
  observationShape: ObservationShape;
  observationColor: ObservationColorVariable;
  observationSolidColor: string;
  observationGradient: readonly [string, string, string];
  observationOpacity: number;
  observationSize: ObservationSizeVariable;
  observationSizeRange: ObservationSizeRange;
  samplingAreaColor: string;
  samplingAreas: boolean;
  camera: CameraState;
}

export interface StateCorrection {
  field: string;
  reason: 'malformed' | 'unavailable';
  value: string;
}

export interface ParsedExplorerState {
  state: ExplorerState;
  corrections: StateCorrection[];
}

const LAYERS = [
  'surface',
  'observations',
  'support',
  'context',
  'countries',
] as const;
const DEFAULT_LAYERS: LayerVisibility = {
  surface: true,
  observations: true,
  support: true,
  context: true,
  countries: true,
};
const DEFAULT_CAMERA: CameraState = {
  lon: 20,
  lat: 12,
  height: 18_000_000,
  heading: 0,
  pitch: -90,
};
const PALETTES = [
  'genome',
  'signal',
  'viridis',
  'cividis',
  'plasma',
  'rainbow',
  'golden',
] as const;
const DEFAULT_SOLID_COLOR = '#f4fbff';
const DEFAULT_GRADIENT = ['#24144b', '#ad8bff', '#f4c86a'] as const;
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function versionOf(ref: AtlasCatalog['artifacts'][number]): string {
  return `${ref.model_version}/${ref.data_version}`;
}

function parseEnum<T extends string>(
  params: URLSearchParams,
  field: string,
  choices: readonly T[],
  fallback: T,
  corrections: StateCorrection[],
): T {
  const raw = params.get(field);
  if (raw === null) return fallback;
  if (choices.includes(raw as T)) return raw as T;
  corrections.push({ field, reason: 'malformed', value: raw });
  return fallback;
}

function parseBoolean(
  params: URLSearchParams,
  field: string,
  fallback: boolean,
  corrections: StateCorrection[],
): boolean {
  const raw = params.get(field);
  if (raw === null) return fallback;
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  corrections.push({ field, reason: 'malformed', value: raw });
  return fallback;
}

function parseNumber(
  params: URLSearchParams,
  field: string,
  fallback: number,
  bounds: readonly [number, number],
  corrections: StateCorrection[],
): number {
  const raw = params.get(field);
  if (raw === null) return fallback;
  const parsed = Number(raw);
  if (Number.isFinite(parsed) && parsed >= bounds[0] && parsed <= bounds[1])
    return parsed;
  corrections.push({ field, reason: 'malformed', value: raw });
  return fallback;
}

function parseColor(
  params: URLSearchParams,
  field: string,
  fallback: string,
  corrections: StateCorrection[],
): string {
  const raw = params.get(field);
  if (raw === null) return fallback;
  if (HEX_COLOR.test(raw)) return raw.toLowerCase();
  corrections.push({ field, reason: 'malformed', value: raw });
  return fallback;
}

function parseLayers(
  params: URLSearchParams,
  corrections: StateCorrection[],
): LayerVisibility {
  const raw = params.get('layers');
  if (raw === null) return { ...DEFAULT_LAYERS };
  const selected = raw.split(',');
  if (
    selected.length === 0 ||
    selected.some((value) => !LAYERS.includes(value as LayerId))
  ) {
    corrections.push({ field: 'layers', reason: 'malformed', value: raw });
    return { ...DEFAULT_LAYERS };
  }
  return Object.fromEntries(
    LAYERS.map((layer) => [layer, selected.includes(layer)]),
  ) as LayerVisibility;
}

function parseRange(
  params: URLSearchParams,
  minimumField: string,
  maximumField: string,
  fallback: ObservationSizeRange,
  bounds: ObservationSizeRange,
  corrections: StateCorrection[],
): ObservationSizeRange {
  const correctionsBefore = corrections.length;
  const minimum = parseNumber(
    params,
    minimumField,
    fallback[0],
    bounds,
    corrections,
  );
  const maximum = parseNumber(
    params,
    maximumField,
    fallback[1],
    bounds,
    corrections,
  );
  if (corrections.length !== correctionsBefore) return fallback;
  if (minimum <= maximum) return [minimum, maximum];
  corrections.push(
    {
      field: minimumField,
      reason: 'malformed',
      value: params.get(minimumField) ?? String(minimum),
    },
    {
      field: maximumField,
      reason: 'malformed',
      value: params.get(maximumField) ?? String(maximum),
    },
  );
  return fallback;
}

export function parseExplorerState(
  input: string | URLSearchParams,
  catalog: AtlasCatalog,
): ParsedExplorerState {
  const params =
    typeof input === 'string'
      ? new URLSearchParams(input.startsWith('?') ? input.slice(1) : input)
      : input;
  const corrections: StateCorrection[] = [];
  const defaultRef = catalog.artifacts[0];
  const requestedEntity = params.get('entity');
  const entityId = requestedEntity ?? defaultRef.id;
  const selectedRef = catalog.artifacts.find(
    (artifact) => artifact.id === entityId,
  );
  if (requestedEntity !== null && selectedRef === undefined) {
    corrections.push({
      field: 'entity',
      reason: 'unavailable',
      value: requestedEntity,
    });
  }

  const requestedVersion = params.get('version');
  let artifactVersion =
    requestedVersion ?? (selectedRef ? versionOf(selectedRef) : '');
  if (
    requestedVersion !== null &&
    selectedRef !== undefined &&
    requestedVersion !== versionOf(selectedRef)
  ) {
    artifactVersion = versionOf(selectedRef);
    corrections.push({
      field: 'version',
      reason: 'unavailable',
      value: requestedVersion,
    });
  }
  const metric = parseEnum(
    params,
    'metric',
    ['post_mean', 'post_sd'],
    'post_mean',
    corrections,
  );
  const paletteValue = params.get('palette');
  const surfacePalette = parseEnum(
    params,
    'palette',
    PALETTES,
    defaultPalette(metric),
    corrections,
  );
  const paletteMode =
    paletteValue !== null && PALETTES.includes(paletteValue as PaletteId)
      ? 'custom'
      : 'metric-default';
  const elevation = parseBoolean(params, 'elevation', false, corrections);

  return {
    corrections,
    state: {
      artifactVersion,
      basemap: parseEnum(
        params,
        'basemap',
        BASEMAP_IDS,
        'dark-streets',
        corrections,
      ),
      basemapBrightness: parseNumber(
        params,
        'basemapBrightness',
        0.5,
        [0, 1],
        corrections,
      ),
      basemapOpacity: parseNumber(
        params,
        'basemapOpacity',
        1,
        [0, 1],
        corrections,
      ),
      camera: {
        heading: parseNumber(
          params,
          'heading',
          DEFAULT_CAMERA.heading,
          [-360, 360],
          corrections,
        ),
        height: parseNumber(
          params,
          'height',
          DEFAULT_CAMERA.height,
          [100, 100_000_000],
          corrections,
        ),
        lat: parseNumber(
          params,
          'lat',
          DEFAULT_CAMERA.lat,
          [-90, 90],
          corrections,
        ),
        lon: parseNumber(
          params,
          'lon',
          DEFAULT_CAMERA.lon,
          [-180, 180],
          corrections,
        ),
        pitch: parseNumber(
          params,
          'pitch',
          DEFAULT_CAMERA.pitch,
          [-90, 0],
          corrections,
        ),
      },
      elevation,
      cellEdges: parseBoolean(params, 'edges', true, corrections),
      earthOpacity: parseNumber(
        params,
        'earthOpacity',
        1,
        [0.15, 1],
        corrections,
      ),
      oceanColor: parseColor(params, 'oceanColor', '#071b35', corrections),
      edgeColorMode: parseEnum(
        params,
        'edgeColor',
        ['fixed', 'matched'],
        'matched',
        corrections,
      ),
      edgeFixedColor: parseColor(params, 'edgeFixed', '#b9f5ff', corrections),
      countryBorderColor: parseColor(
        params,
        'countryColor',
        '#ffffff',
        corrections,
      ),
      countryBorderOpacity: parseNumber(
        params,
        'countryOpacity',
        0.5,
        [0, 1],
        corrections,
      ),
      dayNightLighting: parseBoolean(params, 'dayNight', true, corrections),
      entityId,
      exaggeration: parseNumber(
        params,
        'exaggeration',
        1,
        [0.25, 5],
        corrections,
      ),
      layers: parseLayers(params, corrections),
      metric,
      observationColor: parseEnum(
        params,
        'obsColor',
        ['solid', 'gradient', 'study', 'ac'],
        'solid',
        corrections,
      ),
      observationGradient: [
        parseColor(params, 'obsLow', DEFAULT_GRADIENT[0], corrections),
        parseColor(params, 'obsMid', DEFAULT_GRADIENT[1], corrections),
        parseColor(params, 'obsHigh', DEFAULT_GRADIENT[2], corrections),
      ],
      observationOpacity: parseNumber(
        params,
        'obsOpacity',
        0.95,
        [0.1, 1],
        corrections,
      ),
      observationSizeRange: parseRange(
        params,
        'pointMin',
        'pointMax',
        DEFAULT_OBSERVATION_SIZE_RANGE,
        [MIN_OBSERVATION_MARKER_SIZE, MAX_OBSERVATION_MARKER_SIZE],
        corrections,
      ),
      observationSolidColor: parseColor(
        params,
        'obsSolid',
        DEFAULT_SOLID_COLOR,
        corrections,
      ),
      observationShape: parseEnum(
        params,
        'obsShape',
        ['circle', 'hemisphere', 'pin'],
        'hemisphere',
        corrections,
      ),
      observationSize: parseEnum(
        params,
        'obsSize',
        ['fixed', 'frequency', 'ac', 'an'],
        'frequency',
        corrections,
      ),
      paletteMode,
      samplingAreaColor: parseColor(
        params,
        'samplingColor',
        '#9af9e2',
        corrections,
      ),
      samplingAreas: parseBoolean(params, 'samplingAreas', true, corrections),
      surfaceOpacity: parseNumber(
        params,
        'opacity',
        0.58,
        [0.2, 1],
        corrections,
      ),
      surfaceGeometry: parseEnum(
        params,
        'geometry',
        ['triangles', 'hexagons', 'extruded', 'honmoon', 'honmoon-fill'],
        'triangles',
        corrections,
      ),
      surfacePalette,
      terrain: parseEnum(
        params,
        'terrain',
        TERRAIN_IDS,
        'smooth-globe',
        corrections,
      ),
      view: parseEnum(
        params,
        'view',
        ['globe', 'map', 'perspective'],
        'globe',
        corrections,
      ),
    },
  };
}

export function serializeExplorerState(state: ExplorerState): string {
  const params = new URLSearchParams();
  params.set('entity', state.entityId);
  params.set('version', state.artifactVersion);
  params.set('basemap', state.basemap);
  params.set('basemapBrightness', String(state.basemapBrightness));
  params.set('basemapOpacity', String(state.basemapOpacity));
  params.set('metric', state.metric);
  if (state.paletteMode === 'custom')
    params.set('palette', state.surfacePalette);
  params.set('opacity', String(state.surfaceOpacity));
  params.set('geometry', state.surfaceGeometry);
  params.set('earthOpacity', String(state.earthOpacity));
  params.set('oceanColor', state.oceanColor);
  params.set('edges', String(state.cellEdges));
  params.set('edgeColor', state.edgeColorMode);
  params.set('edgeFixed', state.edgeFixedColor);
  params.set('countryColor', state.countryBorderColor);
  params.set('countryOpacity', String(state.countryBorderOpacity));
  params.set('dayNight', String(state.dayNightLighting));
  params.set('layers', LAYERS.filter((layer) => state.layers[layer]).join(','));
  params.set('view', state.view);
  params.set('terrain', state.terrain);
  params.set('elevation', String(state.elevation));
  params.set('exaggeration', String(state.exaggeration));
  params.set('obsShape', state.observationShape);
  params.set('obsColor', state.observationColor);
  params.set('obsSolid', state.observationSolidColor);
  params.set('obsLow', state.observationGradient[0]);
  params.set('obsMid', state.observationGradient[1]);
  params.set('obsHigh', state.observationGradient[2]);
  params.set('obsOpacity', String(state.observationOpacity));
  params.set('obsSize', state.observationSize);
  params.set('pointMin', String(state.observationSizeRange[0]));
  params.set('pointMax', String(state.observationSizeRange[1]));
  params.set('samplingColor', state.samplingAreaColor);
  params.set('samplingAreas', String(state.samplingAreas));
  params.set('lon', String(state.camera.lon));
  params.set('lat', String(state.camera.lat));
  params.set('height', String(state.camera.height));
  params.set('heading', String(state.camera.heading));
  params.set('pitch', String(state.camera.pitch));
  return params.toString();
}
