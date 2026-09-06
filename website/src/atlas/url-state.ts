/** Shareable, field-by-field explorer URL state for Atlas design §11. */

import type { AtlasCatalog } from './contracts';
import type { Metric } from './visual-encoding';

export type ExplorerSceneMode = 'globe' | 'map' | 'perspective';
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
  metric: Metric;
  layers: LayerVisibility;
  view: ExplorerSceneMode;
  elevation: boolean;
  exaggeration: number;
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

  return {
    corrections,
    state: {
      artifactVersion,
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
      elevation: parseBoolean(params, 'elevation', false, corrections),
      entityId,
      exaggeration: parseNumber(
        params,
        'exaggeration',
        1,
        [0.25, 5],
        corrections,
      ),
      layers: parseLayers(params, corrections),
      metric: parseEnum(
        params,
        'metric',
        ['post_mean', 'post_sd'],
        'post_mean',
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
  params.set('metric', state.metric);
  params.set('layers', LAYERS.filter((layer) => state.layers[layer]).join(','));
  params.set('view', state.view);
  params.set('elevation', String(state.elevation));
  params.set('exaggeration', String(state.exaggeration));
  params.set('lon', String(state.camera.lon));
  params.set('lat', String(state.camera.lat));
  params.set('height', String(state.camera.height));
  params.set('heading', String(state.camera.heading));
  params.set('pitch', String(state.camera.pitch));
  return params.toString();
}
