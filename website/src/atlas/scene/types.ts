/** Shared Cesium scene contracts for Atlas design §11. */

import type { ObservationArtifact, SurfaceArtifact } from '../contracts';
import type {
  ObservationColorVariable,
  ObservationShape,
  ObservationSizeRange,
  ObservationSizeVariable,
} from '../observation-encoding';
import type { Metric, PaletteId } from '../visual-encoding';
import type {
  BasemapId,
  CameraState,
  EdgeColorMode,
  ExplorerSceneMode,
  LayerVisibility,
  SurfaceGeometry,
  TerrainId,
} from '../url-state';
import type { ContextWarning } from './context-controller';
import type { ObservationPick } from './observation-layer';
import type { SurfacePick } from './surface-layer';

export type AtlasPick = SurfacePick | ObservationPick;
export interface AtlasHover {
  pick: AtlasPick;
  screenPosition: { x: number; y: number };
}
export type ContextStatus = 'loading' | 'ready' | 'fallback';

export interface SceneCapabilities {
  basemaps: Record<BasemapId, boolean>;
  terrains: Record<TerrainId, boolean>;
}

export interface ObservationPresentation {
  colorVariable: ObservationColorVariable;
  gradient: readonly [string, string, string];
  opacity: number;
  samplingAreaColor: string;
  sizeRange: ObservationSizeRange;
  samplingAreas: boolean;
  shape: ObservationShape;
  sizeVariable: ObservationSizeVariable;
  solidColor: string;
}

export interface AtlasSceneOptions {
  cesiumToken?: string;
  contextImageryUrl?: string;
  naturalEarthUrl: string;
  reducedMotion?: boolean;
}

export interface AtlasSceneController {
  setArtifact(
    surface: SurfaceArtifact,
    observations: ObservationArtifact | null,
  ): Promise<void>;
  setMetric(metric: Metric): Promise<void>;
  setSurfaceStyle(
    palette: PaletteId,
    opacity: number,
    cellEdges: boolean,
    edgeColorMode: EdgeColorMode,
    edgeFixedColor: string,
    geometry: SurfaceGeometry,
  ): Promise<void>;
  setObservationStyle(style: ObservationPresentation): Promise<void>;
  setBasemap(basemap: BasemapId): Promise<boolean>;
  setTerrain(terrain: TerrainId): Promise<boolean>;
  capabilities(): SceneCapabilities;
  setLayerVisibility(layers: LayerVisibility): void;
  setMapPresentation(
    basemapOpacity: number,
    basemapBrightness: number,
    dayNightLighting: boolean,
  ): void;
  setEarthOpacity(opacity: number): void;
  setOceanColor(color: string): void;
  setCountryBorderStyle(color: string, opacity: number): void;
  setElevation(enabled: boolean, exaggeration: number): Promise<void>;
  setSceneMode(mode: ExplorerSceneMode, reducedMotion: boolean): Promise<void>;
  setCamera(camera: CameraState, animated: boolean): void;
  setSelection(pick: AtlasPick | null): void;
  home(animated: boolean): void;
  zoom(direction: 'in' | 'out'): void;
  onPick(listener: (pick: AtlasPick | null) => void): () => void;
  onHover(listener: (hover: AtlasHover | null) => void): () => void;
  onCameraSettled(listener: (camera: CameraState) => void): () => void;
  onContextStatus(listener: (status: ContextStatus) => void): () => void;
  onWarning(
    listener: (warnings: readonly ContextWarning[]) => void,
  ): () => void;
  destroy(): void;
}
