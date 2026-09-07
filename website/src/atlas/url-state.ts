/** Shareable, field-by-field explorer URL state for Atlas design §11. */

import type { AtlasCatalog } from './contracts';
import type {
  ObservationColorVariable,
  ObservationShape,
  ObservationSizeRange,
  ObservationSizeVariable,
} from './observation-encoding';
import { defaultPalette, type Metric, type PaletteId } from './visual-encoding';

export type ExplorerSceneMode = 'globe' | 'map' | 'perspective';
export type BasemapId = 'dark-streets' | 'roads' | 'aerial' | 'aerial-labels';
export type TerrainId = 'smooth-globe' | 'world-terrain';
export type LayerId = 'surface' | 'observations' | 'support' | 'context';
export type LayerVisibility = Record<LayerId, boolean>;

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
  metric: Metric;
  surfacePalette: PaletteId;
  paletteMode: 'metric-default' | 'custom';
  surfaceOpacity: number;
  cellEdges: boolean;
  layers: LayerVisibility;
  view: ExplorerSceneMode;
  terrain: TerrainId;
  elevation: boolean;
  exaggeration: number;
  observationShape: ObservationShape;
  observationColor: ObservationColorVariable;
  observationSize: ObservationSizeVariable;
  observationPointRange: ObservationSizeRange;
  observationHemisphereRange: ObservationSizeRange;
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

const LAYERS = ['surface', 'observations', 'support', 'context'] as const;
const DEFAULT_LAYERS: LayerVisibility = {
  surface: true,
  observations: true,
  support: true,
  context: true,
};
const DEFAULT_CAMERA: CameraState = {
  lon: 20,
  lat: 12,
  height: 18_000_000,
  heading: 0,
  pitch: -90,
};
const PALETTES = ['genome', 'signal', 'viridis', 'cividis', 'plasma'] as const;
const DEFAULT_POINT_RANGE: ObservationSizeRange = [6, 18];
const DEFAULT_HEMISPHERE_RANGE: ObservationSizeRange = [40, 300];

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
  const artifactVersion =
    requestedVersion ?? (selectedRef ? versionOf(selectedRef) : '');
  if (
    requestedVersion !== null &&
    selectedRef !== undefined &&
    requestedVersion !== versionOf(selectedRef)
  ) {
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
        ['dark-streets', 'roads', 'aerial', 'aerial-labels'],
        'dark-streets',
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
      cellEdges: parseBoolean(params, 'edges', false, corrections),
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
        ['white', 'study', 'frequency', 'ac'],
        'white',
        corrections,
      ),
      observationHemisphereRange: parseRange(
        params,
        'domeMin',
        'domeMax',
        DEFAULT_HEMISPHERE_RANGE,
        [10, 500],
        corrections,
      ),
      observationPointRange: parseRange(
        params,
        'pointMin',
        'pointMax',
        DEFAULT_POINT_RANGE,
        [4, 40],
        corrections,
      ),
      observationShape: parseEnum(
        params,
        'obsShape',
        ['circle', 'hemisphere', 'pin'],
        'circle',
        corrections,
      ),
      observationSize: parseEnum(
        params,
        'obsSize',
        ['fixed', 'frequency', 'ac', 'an'],
        'fixed',
        corrections,
      ),
      paletteMode,
      samplingAreas: parseBoolean(params, 'samplingAreas', true, corrections),
      surfaceOpacity: parseNumber(
        params,
        'opacity',
        0.86,
        [0.45, 1],
        corrections,
      ),
      surfacePalette,
      terrain: parseEnum(
        params,
        'terrain',
        ['smooth-globe', 'world-terrain'],
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
  params.set('metric', state.metric);
  if (state.paletteMode === 'custom')
    params.set('palette', state.surfacePalette);
  params.set('opacity', String(state.surfaceOpacity));
  params.set('edges', String(state.cellEdges));
  params.set('layers', LAYERS.filter((layer) => state.layers[layer]).join(','));
  params.set('view', state.view);
  params.set('terrain', state.terrain);
  params.set('elevation', String(state.elevation));
  params.set('exaggeration', String(state.exaggeration));
  params.set('obsShape', state.observationShape);
  params.set('obsColor', state.observationColor);
  params.set('obsSize', state.observationSize);
  params.set('pointMin', String(state.observationPointRange[0]));
  params.set('pointMax', String(state.observationPointRange[1]));
  params.set('domeMin', String(state.observationHemisphereRange[0]));
  params.set('domeMax', String(state.observationHemisphereRange[1]));
  params.set('samplingAreas', String(state.samplingAreas));
  params.set('lon', String(state.camera.lon));
  params.set('lat', String(state.camera.lat));
  params.set('height', String(state.camera.height));
  params.set('heading', String(state.camera.heading));
  params.set('pitch', String(state.camera.pitch));
  return params.toString();
}
