/** Basemap and physical-terrain lifecycle for Atlas design §11. */

import {
  Credit,
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  IonWorldImageryStyle,
  UrlTemplateImageryProvider,
  createWorldImageryAsync,
  createWorldTerrainAsync,
  type Viewer,
} from 'cesium';

import type { BasemapId, TerrainId } from '../url-state';

export interface SceneCapability {
  available: boolean;
  reason?: string;
}

export interface ContextWarning {
  id: 'basemap' | 'terrain';
  message: string;
}

export interface ContextWarningClear {
  id: ContextWarning['id'];
  message: null;
}

export type ContextWarningUpdate = ContextWarning | ContextWarningClear;
export type ContextWarningListener = (warning: ContextWarningUpdate) => void;

const ION_UNAVAILABLE = 'Cesium ion access is unavailable in this build.';

export function ionCapability(token: string): SceneCapability {
  return token.trim()
    ? { available: true }
    : { available: false, reason: ION_UNAVAILABLE };
}

export function availableBasemaps(token: string): Record<BasemapId, boolean> {
  const ionAvailable = ionCapability(token).available;
  return {
    'aerial-labels': ionAvailable,
    aerial: ionAvailable,
    'dark-streets': true,
    roads: ionAvailable,
  };
}

export function availableTerrains(token: string): Record<TerrainId, boolean> {
  return {
    'smooth-globe': true,
    'world-terrain': ionCapability(token).available,
  };
}

function styleLayer(layer: ImageryLayer, basemap: BasemapId): void {
  const style = {
    'aerial-labels': { alpha: 0.78, brightness: 0.64, saturation: 0.68 },
    aerial: { alpha: 0.72, brightness: 0.6, saturation: 0.72 },
    'dark-streets': { alpha: 0.63, brightness: 0.55, saturation: 0.48 },
    roads: { alpha: 0.72, brightness: 0.58, saturation: 0.52 },
  }[basemap];
  layer.alpha = style.alpha;
  layer.brightness = style.brightness;
  layer.contrast = 1.2;
  layer.saturation = style.saturation;
}

function publicMapLayer(url: string): ImageryLayer {
  return new ImageryLayer(
    new UrlTemplateImageryProvider({
      credit: new Credit(
        '<a href="https://www.openstreetmap.org/copyright" target="_blank">© OpenStreetMap contributors</a>',
        true,
      ),
      enablePickFeatures: false,
      maximumLevel: 18,
      url,
    }),
  );
}

async function ionMapLayer(basemap: Exclude<BasemapId, 'dark-streets'>) {
  const style = {
    'aerial-labels': IonWorldImageryStyle.AERIAL_WITH_LABELS,
    aerial: IonWorldImageryStyle.AERIAL,
    roads: IonWorldImageryStyle.ROAD,
  }[basemap];
  return new ImageryLayer(await createWorldImageryAsync({ style }));
}

export class ContextController {
  readonly #viewer: Viewer;
  readonly #token: string;
  readonly #publicImageryUrl: string;
  readonly #onWarning: ContextWarningListener;
  #activeLayer: ImageryLayer | null = null;
  #basemapSequence = 0;
  #terrainSequence = 0;

  constructor(
    viewer: Viewer,
    token: string,
    publicImageryUrl: string,
    onWarning: ContextWarningListener,
  ) {
    this.#viewer = viewer;
    this.#token = token.trim();
    this.#publicImageryUrl = publicImageryUrl;
    this.#onWarning = onWarning;
    if (this.#token) Ion.defaultAccessToken = this.#token;
  }

  capabilities(): {
    basemaps: Record<BasemapId, boolean>;
    terrains: Record<TerrainId, boolean>;
  } {
    return {
      basemaps: availableBasemaps(this.#token),
      terrains: availableTerrains(this.#token),
    };
  }

  async setBasemap(basemap: BasemapId): Promise<boolean> {
    const sequence = ++this.#basemapSequence;
    if (!availableBasemaps(this.#token)[basemap]) {
      this.#onWarning({
        id: 'basemap',
        message: `${ION_UNAVAILABLE} The previous basemap remains active.`,
      });
      return false;
    }
    try {
      const incoming =
        basemap === 'dark-streets'
          ? publicMapLayer(this.#publicImageryUrl)
          : await ionMapLayer(basemap);
      if (sequence !== this.#basemapSequence) return false;
      styleLayer(incoming, basemap);
      const previous = this.#activeLayer;
      this.#viewer.imageryLayers.add(incoming, 0);
      this.#activeLayer = incoming;
      if (previous) this.#viewer.imageryLayers.remove(previous, true);
      incoming.errorEvent.addEventListener(() => {
        if (this.#activeLayer !== incoming) return;
        this.#onWarning({
          id: 'basemap',
          message: `${basemap} map tiles could not be loaded. Try another basemap.`,
        });
      });
      this.#onWarning({ id: 'basemap', message: null });
      this.#viewer.scene.requestRender();
      return true;
    } catch {
      if (sequence === this.#basemapSequence) {
        this.#onWarning({
          id: 'basemap',
          message: `${basemap} could not be loaded. The previous basemap remains active.`,
        });
      }
      return false;
    }
  }

  async setTerrain(terrain: TerrainId): Promise<boolean> {
    const sequence = ++this.#terrainSequence;
    if (!availableTerrains(this.#token)[terrain]) {
      this.#onWarning({
        id: 'terrain',
        message: `${ION_UNAVAILABLE} The smooth globe remains active.`,
      });
      return false;
    }
    try {
      const provider =
        terrain === 'smooth-globe'
          ? new EllipsoidTerrainProvider()
          : await createWorldTerrainAsync({
              requestVertexNormals: true,
              requestWaterMask: true,
            });
      if (sequence !== this.#terrainSequence) return false;
      this.#viewer.terrainProvider = provider;
      this.#onWarning({ id: 'terrain', message: null });
      this.#viewer.scene.requestRender();
      return true;
    } catch {
      if (sequence === this.#terrainSequence) {
        this.#onWarning({
          id: 'terrain',
          message: `${terrain} could not be loaded. The previous terrain remains active.`,
        });
      }
      return false;
    }
  }

  setVisible(visible: boolean): void {
    if (this.#activeLayer) this.#activeLayer.show = visible;
  }
}
