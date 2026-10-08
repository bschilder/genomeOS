/** Shared Cesium scene contracts for Atlas design §11. */

import type { Primitive, PrimitiveCollection } from 'cesium';

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

export type SurfaceChunkPick = {
  kind: 'surface-chunk';
  artifactKey: string;
  chunk: number;
};

export interface ScientificPrimitiveGroup {
  collection: PrimitiveCollection;
  primitives: Primitive[];
  isReady(): boolean;
  readyCount(): number;
  totalCount(): number;
  setOpacity(opacity: number): void;
  setSurfaceOpacity(opacity: number): void;
  setCellEdges(visible: boolean): Promise<void>;
  setElevationFactor(factor: number, force?: boolean): void;
  setSceneMode(mode: ExplorerSceneMode): Promise<void>;
  setVisibility(surface: boolean, support: boolean): void;
}
export type ContextStatus = 'loading' | 'ready' | 'fallback';
export type AtlasMark =
  | 'observations-visible'
  | 'surface-first-chunk'
  | 'surface-visible'
  | 'ready'
  | 'values-ready'
  | 'edges-ready'
  | 'context-ready';

export interface SceneProgress {
  detail: string;
  progress: number | null;
}

export type SceneProgressListener = (progress: SceneProgress) => void;

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
    progress?: SceneProgressListener,
  ): Promise<void>;
  setMetric(metric: Metric, progress?: SceneProgressListener): Promise<void>;
  setSurfaceStyle(
    palette: PaletteId,
    opacity: number,
    cellEdges: boolean,
    edgeColorMode: EdgeColorMode,
    edgeFixedColor: string,
    geometry: SurfaceGeometry,
    progress?: SceneProgressListener,
  ): Promise<void>;
  setObservationStyle(
    style: ObservationPresentation,
    progress?: SceneProgressListener,
  ): Promise<void>;
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
  /**
   * A frame threw, inside Scene.render or in any listener, tick or resize the Atlas render loop
   * runs, and rendering stopped for good (Cesium globe design §12), so listeners offer a retry.
   * The error is reported once, a late listener still hears it, and none is reported after
   * destroy.
   */
  onRenderError(listener: (error: unknown) => void): () => void;
  destroy(): void;
}
