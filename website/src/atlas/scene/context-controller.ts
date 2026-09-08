/** Basemap and physical-terrain lifecycle for Atlas design §11. */

import {
  ArcGisBaseMapType,
  ArcGisMapServerImageryProvider,
  Credit,
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  IonImageryProvider,
  IonWorldImageryStyle,
  OpenStreetMapImageryProvider,
  TileMapServiceImageryProvider,
  UrlTemplateImageryProvider,
  buildModuleUrl,
  createWorldImageryAsync,
  createWorldTerrainAsync,
  type Viewer,
} from 'cesium';

import { BASEMAP_OPTIONS, TERRAIN_OPTIONS } from '../earth-style-catalog';
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
  return Object.fromEntries(
    BASEMAP_OPTIONS.map(({ id, requiresIon }) => [
      id,
      !requiresIon || ionAvailable,
    ]),
  ) as Record<BasemapId, boolean>;
}

export function availableTerrains(token: string): Record<TerrainId, boolean> {
  const ionAvailable = ionCapability(token).available;
  return Object.fromEntries(
    TERRAIN_OPTIONS.map(({ id, requiresIon }) => [
      id,
      !requiresIon || ionAvailable,
    ]),
  ) as Record<TerrainId, boolean>;
}

export interface BasemapAppearanceTarget {
  alpha: number;
  brightness: number;
}

export function applyBasemapAppearance(
  layer: BasemapAppearanceTarget,
  opacity: number,
  brightness: number,
): void {
  layer.alpha = Math.min(1, Math.max(0, opacity));
  layer.brightness = Math.min(1, Math.max(0, brightness));
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

const STADIA_CREDIT = `&copy; <a href="https://www.stadiamaps.com/" target="_blank">Stadia Maps</a>
  &copy; <a href="https://stamen.com/" target="_blank">Stamen Design</a>
  &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a>
  &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>`;

async function galleryMapLayer(
  basemap: BasemapId,
  publicImageryUrl: string,
): Promise<ImageryLayer> {
  if (basemap === 'dark-streets') return publicMapLayer(publicImageryUrl);
  if (
    basemap === 'aerial' ||
    basemap === 'aerial-labels' ||
    basemap === 'roads'
  ) {
    const style = {
      aerial: IonWorldImageryStyle.AERIAL,
      'aerial-labels': IonWorldImageryStyle.AERIAL_WITH_LABELS,
      roads: IonWorldImageryStyle.ROAD,
    }[basemap];
    return new ImageryLayer(await createWorldImageryAsync({ style }));
  }
  if (basemap === 'arcgis-imagery') {
    return new ImageryLayer(
      await ArcGisMapServerImageryProvider.fromBasemapType(
        ArcGisBaseMapType.SATELLITE,
        { enablePickFeatures: false },
      ),
    );
  }
  if (basemap === 'arcgis-hillshade') {
    return new ImageryLayer(
      await ArcGisMapServerImageryProvider.fromBasemapType(
        ArcGisBaseMapType.HILLSHADE,
        { enablePickFeatures: false },
      ),
    );
  }
  if (basemap === 'esri-ocean') {
    return new ImageryLayer(
      await ArcGisMapServerImageryProvider.fromBasemapType(
        ArcGisBaseMapType.OCEANS,
        { enablePickFeatures: false },
      ),
    );
  }
  if (basemap === 'openstreetmap') {
    return new ImageryLayer(
      new OpenStreetMapImageryProvider({
        url: 'https://tile.openstreetmap.org/',
      }),
    );
  }
  if (
    basemap === 'stadia-watercolor' ||
    basemap === 'stadia-toner' ||
    basemap === 'stadia-smooth' ||
    basemap === 'stadia-dark'
  ) {
    const details = {
      'stadia-dark': ['alidade_smooth_dark', 'png'],
      'stadia-smooth': ['alidade_smooth', 'png'],
      'stadia-toner': ['stamen_toner', 'png'],
      'stadia-watercolor': ['stamen_watercolor', 'jpg'],
    }[basemap];
    return new ImageryLayer(
      new OpenStreetMapImageryProvider({
        credit: STADIA_CREDIT,
        fileExtension: details[1],
        retinaTiles:
          basemap !== 'stadia-watercolor' &&
          (globalThis.devicePixelRatio ?? 1) >= 2,
        url: `https://tiles.stadiamaps.com/tiles/${details[0]}/`,
      }),
    );
  }
  if (basemap === 'natural-earth-ii') {
    return new ImageryLayer(
      await TileMapServiceImageryProvider.fromUrl(
        buildModuleUrl('Assets/Textures/NaturalEarthII'),
      ),
    );
  }
  const assetId = {
    'azure-aerial': 3891168,
    'azure-roads': 3891169,
    'blue-marble': 3845,
    'earth-at-night': 3812,
    'google-contour': 3830186,
    'google-roadmap': 3830184,
    'google-satellite': 3830182,
    'google-satellite-labels': 3830183,
    'sentinel-2': 3954,
  }[basemap];
  return new ImageryLayer(await IonImageryProvider.fromAssetId(assetId));
}

export class ContextController {
  readonly #viewer: Viewer;
  readonly #token: string;
  readonly #publicImageryUrl: string;
  readonly #onWarning: ContextWarningListener;
  #activeLayer: ImageryLayer | null = null;
  #basemapBrightness = 0.5;
  #basemapOpacity = 1;
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
      const incoming = await galleryMapLayer(basemap, this.#publicImageryUrl);
      if (sequence !== this.#basemapSequence) return false;
      applyBasemapAppearance(
        incoming,
        this.#basemapOpacity,
        this.#basemapBrightness,
      );
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

  setAppearance(opacity: number, brightness: number): void {
    this.#basemapOpacity = opacity;
    this.#basemapBrightness = brightness;
    if (this.#activeLayer)
      applyBasemapAppearance(this.#activeLayer, opacity, brightness);
    this.#viewer.scene.requestRender();
  }
}
