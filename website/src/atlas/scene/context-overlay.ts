/** Worker-parsed Natural Earth borders and labels for Atlas design §11 (spec 2026-10-07 §B.6.9).
 *
 * Replaces GeoJsonDataSource, whose single onload task exceeded every
 * long-task budget. The GeoJSON is parsed in the data worker; borders and
 * labels are added in frame-budgeted slices; the surface-following height
 * adjustment is skipped at elevation 0 and computed in the worker from
 * render-tier rows on the first non-zero factor.
 */

import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Cartesian3,
  Cartographic,
  Color,
  ComponentDatatype,
  Credit,
  DistanceDisplayCondition,
  Ellipsoid,
  LabelCollection,
  LabelStyle,
  Material,
  NearFarScalar,
  PolylineCollection,
  PrimitiveCollection,
  type Polyline,
} from 'cesium';

import type { ExplorerSceneMode } from '../url-state';
import type { Metric } from '../visual-encoding';
import type { AtlasWorkerClient } from '../worker/client';
import type { ContextHeights, NaturalEarthBuffers } from '../worker/protocol';
import {
  countryLabelDepthTestDistance,
  countryLabelDistanceForScale,
  countryLabelHeight,
} from './geographic-overlay';
import {
  edgeRendererForMode,
  runSliced,
  type EdgeRenderer,
  type SliceOptions,
} from './sliced-lines';

export const BORDER_CLEARANCE_METRES = 1_800;
export const BORDER_WIDTH_PIXELS = 1.65;
const ELEVATION_THROTTLE_MS = 50;
const HEIGHT_CACHE_SIZE = 4;
const NATURAL_EARTH_CREDIT =
  '<a href="https://www.naturalearthdata.com/" target="_blank">Natural Earth</a> (public domain)';

export type ContextLoadStatus = 'ready' | 'fallback';
type LabelSink = Pick<LabelCollection, 'add' | 'show'>;

export interface ContextOverlayOptions {
  worker: Pick<AtlasWorkerClient, 'contextHeights' | 'parseContext'>;
  scene: { primitives: PrimitiveCollection; requestRender(): void };
  addCredit: (credit: Credit) => void;
  fetchBytes?: (url: string) => Promise<ArrayBuffer>;
  createLabels?: () => LabelSink;
  slice?: Omit<SliceOptions, 'onSlice' | 'signal'>;
  now?: () => number;
}

async function fetchArrayBuffer(url: string): Promise<ArrayBuffer> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(
      `Natural Earth request failed with HTTP ${response.status}`,
    );
  return response.arrayBuffer();
}

function cartesiansOf(values: Float64Array): Cartesian3[] {
  const positions: Cartesian3[] = [];
  for (let index = 0; index < values.length; index += 3)
    positions.push(
      new Cartesian3(values[index], values[index + 1], values[index + 2]),
    );
  return positions;
}

export class ContextOverlay {
  readonly collection = new PrimitiveCollection();
  readonly #options: ContextOverlayOptions;
  readonly #now: () => number;
  readonly #heights = new Map<string, ContextHeights>();
  readonly #pendingHeights = new Set<string>();
  #parsed: NaturalEarthBuffers | null = null;
  #ground = new Float64Array(0);
  #up = new Float64Array(0);
  #scratch = new Float64Array(0);
  #labels: { position: Cartesian3 }[] = [];
  #buffer: BufferPolylineCollection | null = null;
  #projected: PolylineCollection | null = null;
  #projectedLines: Polyline[] = [];
  #projectedMaterial: Material | null = null;
  #borderColor = Color.WHITE.withAlpha(0.5);
  #mode: ExplorerSceneMode = 'globe';
  #factor = 0;
  #surface: { artifactKey: string; metric: Metric } | null = null;
  #loading: Promise<ContextLoadStatus> | null = null;
  #ready = false;
  #lastElevationUpdate = Number.NEGATIVE_INFINITY;

  constructor(options: ContextOverlayOptions) {
    this.#options = options;
    this.#now = options.now ?? (() => performance.now());
    options.scene.primitives.add(this.collection);
  }

  isReady(): boolean {
    return this.#ready;
  }

  load(url: string): Promise<ContextLoadStatus> {
    this.#loading ??= this.#load(url);
    return this.#loading;
  }

  setSurface(artifactKey: string | null, metric: Metric): void {
    this.#surface = artifactKey ? { artifactKey, metric } : null;
    if (this.#factor > 0) this.#requestHeights();
    this.#applyElevation(true);
  }

  setElevationFactor(factor: number, force = false): void {
    const safeFactor = Math.max(0, factor);
    const changed = safeFactor !== this.#factor;
    this.#factor = safeFactor;
    if (safeFactor > 0) this.#requestHeights();
    if (changed || force) this.#applyElevation(force);
  }

  async setSceneMode(mode: ExplorerSceneMode): Promise<void> {
    this.#mode = mode;
    if (this.#ready) await this.#ensureRenderer(edgeRendererForMode(mode));
  }

  setVisible(visible: boolean): void {
    this.collection.show = visible;
    this.#options.scene.requestRender();
  }

  setBorderStyle(cssColor: string, opacity: number): void {
    this.#borderColor = Color.fromCssColorString(cssColor).withAlpha(
      Math.min(1, Math.max(0, opacity)),
    );
    if (this.#buffer) {
      const material = new BufferPolylineMaterial({
        color: this.#borderColor,
        width: BORDER_WIDTH_PIXELS,
      });
      const polyline = new BufferPolyline();
      for (let index = 0; index < this.#buffer.primitiveCount; index += 1) {
        this.#buffer.get(index, polyline);
        polyline.setMaterial(material);
      }
    }
    if (this.#projectedMaterial)
      this.#projectedMaterial.uniforms.color = this.#borderColor.clone();
    this.#options.scene.requestRender();
  }

  async #load(url: string): Promise<ContextLoadStatus> {
    try {
      const bytes = await (this.#options.fetchBytes ?? fetchArrayBuffer)(url);
      const parsed = await this.#options.worker.parseContext(bytes);
      this.#options.addCredit(new Credit(NATURAL_EARTH_CREDIT, true));
      this.#parsed = parsed;
      const vertices = parsed.lonLat.length / 2;
      this.#ground = new Float64Array(vertices * 3);
      this.#up = new Float64Array(vertices * 3);
      await runSliced(
        vertices,
        (index) => this.#prepareVertex(index),
        this.#slice(),
      );
      await this.#ensureRenderer(edgeRendererForMode(this.#mode));
      await this.#addLabels(parsed);
      this.#ready = true;
      this.#applyElevation(true);
      return 'ready';
    } catch (error) {
      console.warn('Geographic reference overlay could not be loaded.', error);
      return 'fallback';
    }
  }

  #slice(): SliceOptions {
    return {
      ...this.#options.slice,
      onSlice: () => this.#options.scene.requestRender(),
    };
  }

  #prepareVertex(index: number): void {
    const lonLat = this.#parsed!.lonLat;
    const lon = lonLat[index * 2];
    const lat = lonLat[index * 2 + 1];
    const ground = Cartesian3.fromDegrees(lon, lat, 0, Ellipsoid.WGS84);
    const up = Ellipsoid.WGS84.geodeticSurfaceNormalCartographic(
      Cartographic.fromDegrees(lon, lat),
    );
    this.#ground.set([ground.x, ground.y, ground.z], index * 3);
    this.#up.set([up.x, up.y, up.z], index * 3);
  }

  #currentHeights(): ContextHeights | null {
    const surface = this.#surface;
    if (!surface || this.#factor === 0) return null;
    return (
      this.#heights.get(`${surface.artifactKey}:${surface.metric}`) ?? null
    );
  }

  #ringPositions(ring: number, heights: ContextHeights | null): Float64Array {
    const offsets = this.#parsed!.ringOffsets;
    const start = offsets[ring];
    const end = offsets[ring + 1];
    const length = (end - start) * 3;
    if (this.#scratch.length < length) this.#scratch = new Float64Array(length);
    for (let index = start; index < end; index += 1) {
      const height =
        (heights?.borderHeights[index] ?? 0) * this.#factor +
        BORDER_CLEARANCE_METRES;
      const target = (index - start) * 3;
      for (let axis = 0; axis < 3; axis += 1)
        this.#scratch[target + axis] =
          this.#ground[index * 3 + axis] + this.#up[index * 3 + axis] * height;
    }
    return this.#scratch.subarray(0, length);
  }

  #labelPosition(index: number, heights: ContextHeights | null): Cartesian3 {
    const label = this.#parsed!.labels[index];
    return Cartesian3.fromDegrees(
      label.lon,
      label.lat,
      countryLabelHeight(heights?.labelHeights[index] ?? 0, this.#factor),
    );
  }

  async #ensureRenderer(renderer: EdgeRenderer): Promise<void> {
    if (renderer === 'buffer' && !this.#buffer) await this.#addBuffer();
    if (renderer === 'projected' && !this.#projected)
      await this.#addProjected();
    if (this.#buffer) this.#buffer.show = renderer === 'buffer';
    if (this.#projected) this.#projected.show = renderer === 'projected';
    this.#options.scene.requestRender();
  }

  async #addBuffer(): Promise<void> {
    const parsed = this.#parsed!;
    const rings = parsed.ringOffsets.length - 1;
    const target = new BufferPolylineCollection({
      allowPicking: false,
      positionDatatype: ComponentDatatype.DOUBLE,
      primitiveCountMax: Math.max(1, rings),
      vertexCountMax: Math.max(1, parsed.lonLat.length / 2),
    });
    this.collection.add(target);
    this.#buffer = target;
    const material = new BufferPolylineMaterial({
      color: this.#borderColor,
      width: BORDER_WIDTH_PIXELS,
    });
    const polyline = new BufferPolyline();
    const heights = this.#currentHeights();
    await runSliced(
      rings,
      (ring) =>
        target.add(
          { material, positions: this.#ringPositions(ring, heights) },
          polyline,
        ),
      this.#slice(),
    );
  }

  async #addProjected(): Promise<void> {
    const rings = this.#parsed!.ringOffsets.length - 1;
    const target = new PolylineCollection();
    this.collection.add(target);
    this.#projected = target;
    this.#projectedLines = [];
    const material = Material.fromType('Color', {
      color: this.#borderColor.clone(),
    });
    this.#projectedMaterial = material;
    const heights = this.#currentHeights();
    await runSliced(
      rings,
      (ring) => {
        this.#projectedLines.push(
          target.add({
            material,
            positions: cartesiansOf(this.#ringPositions(ring, heights)),
            width: BORDER_WIDTH_PIXELS,
          }),
        );
      },
      this.#slice(),
    );
  }

  async #addLabels(parsed: NaturalEarthBuffers): Promise<void> {
    const labels = (
      this.#options.createLabels ?? (() => new LabelCollection())
    )();
    this.collection.add(labels);
    this.#labels = [];
    const outlineColor = Color.fromCssColorString('#020712').withAlpha(0.98);
    const heights = this.#currentHeights();
    await runSliced(
      parsed.labels.length,
      (index) => {
        const { minLabel, text } = parsed.labels[index];
        this.#labels.push(
          labels.add({
            disableDepthTestDistance: countryLabelDepthTestDistance(minLabel),
            distanceDisplayCondition: new DistanceDisplayCondition(
              0,
              countryLabelDistanceForScale(minLabel),
            ),
            fillColor: Color.WHITE,
            font: '600 17px Inter, system-ui, sans-serif',
            outlineColor,
            outlineWidth: 5,
            position: this.#labelPosition(index, heights),
            scaleByDistance: new NearFarScalar(
              1_000_000,
              1.08,
              24_000_000,
              0.76,
            ),
            style: LabelStyle.FILL_AND_OUTLINE,
            text,
          }),
        );
      },
      this.#slice(),
    );
  }

  #requestHeights(): void {
    const surface = this.#surface;
    if (!surface) return;
    const key = `${surface.artifactKey}:${surface.metric}`;
    if (this.#heights.has(key) || this.#pendingHeights.has(key)) return;
    this.#pendingHeights.add(key);
    this.#options.worker
      .contextHeights({
        artifactKey: surface.artifactKey,
        metric: surface.metric,
      })
      .then((heights) => {
        this.#pendingHeights.delete(key);
        this.#heights.set(key, heights);
        while (this.#heights.size > HEIGHT_CACHE_SIZE)
          this.#heights.delete(this.#heights.keys().next().value!);
        const current = this.#surface;
        if (current && `${current.artifactKey}:${current.metric}` === key)
          this.#applyElevation(true);
      })
      .catch((error: unknown) => {
        this.#pendingHeights.delete(key);
        console.warn('Country outlines could not follow the surface.', error);
      });
  }

  #applyElevation(force: boolean): void {
    if (!this.#ready) return;
    const time = this.#now();
    if (
      !force &&
      this.#factor !== 0 &&
      time - this.#lastElevationUpdate < ELEVATION_THROTTLE_MS
    )
      return;
    this.#lastElevationUpdate = time;
    const heights = this.#currentHeights();
    if (this.#buffer) {
      const polyline = new BufferPolyline();
      for (let ring = 0; ring < this.#buffer.primitiveCount; ring += 1) {
        this.#buffer.get(ring, polyline);
        polyline.setPositions(this.#ringPositions(ring, heights));
      }
    }
    this.#projectedLines.forEach((line, ring) => {
      line.positions = cartesiansOf(this.#ringPositions(ring, heights));
    });
    this.#labels.forEach((label, index) => {
      label.position = this.#labelPosition(index, heights);
    });
    this.#options.scene.requestRender();
  }
}
