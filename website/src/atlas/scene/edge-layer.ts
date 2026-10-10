/** Deferred H3 cell outlines from worker ring buffers for Atlas design §11 (spec 2026-10-07 §B.6.9).
 *
 * Outlines are never on the reveal path. The scene builds them after
 * `atlas:surface-visible`; the worker declares exact capacities so one
 * BufferPolylineCollection is allocated, and rings are added in
 * frame-budgeted slices. Elevation moves each vertex linearly from its base
 * position (factor 0) towards its position at exaggeration 1.
 *
 * Calls may land between slices. `reset()` and a new `build` cancel any
 * slicing in progress; the renderer for the latest view is built and shown;
 * an elevation change raises the rings already added, and later rings are
 * added at the height the renderer is drawn at.
 */

import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Color,
  ComponentDatatype,
  PolylineCollection,
  PrimitiveCollection,
  type Material,
  type Polyline,
} from 'cesium';

import { EDGE_ALPHA, type EdgeChunkBuffers } from '../geometry/edge-buffers';
import type { ExplorerSceneMode } from '../url-state';
import type { EdgesChunkMessage } from '../worker/protocol';
import {
  abortError,
  cartesiansOf,
  edgeRendererForMode,
  runSliced,
  SharedColorMaterial,
  type EdgeRenderer,
  type SliceOptions,
} from './sliced-lines';

export const EDGE_WIDTH_PIXELS = 2;
// One owner: the worker bakes this alpha into ring RGBA, and fixed colours here use the same value.
export { EDGE_ALPHA };
const ELEVATION_THROTTLE_MS = 50;

export type EdgeSource = (
  onChunk: (message: EdgesChunkMessage) => void,
  signal: AbortSignal,
) => Promise<void>;

export interface EdgeLayerOptions {
  requestRender: () => void;
  slice?: Omit<SliceOptions, 'onSlice' | 'signal'>;
  now?: () => number;
}

export interface EdgeLayer {
  readonly collection: PrimitiveCollection;
  build(
    source: EdgeSource,
    fixedColor: string,
    mode: ExplorerSceneMode,
    factor: number,
    signal?: AbortSignal,
  ): Promise<void>;
  isBuilt(): boolean;
  ringCount(): number;
  setMode(mode: ExplorerSceneMode): Promise<void>;
  setElevationFactor(factor: number, force?: boolean): void;
  reset(): void;
}

interface RingRef {
  buffers: EdgeChunkBuffers;
  ring: number;
}

function ringsOf(buffers: EdgeChunkBuffers): RingRef[] {
  return Array.from(
    { length: Math.max(0, buffers.ringOffsets.length - 1) },
    (_, ring) => ({ buffers, ring }),
  );
}

export function createEdgeLayer(options: EdgeLayerOptions): EdgeLayer {
  const collection = new PrimitiveCollection();
  const now = options.now ?? (() => performance.now());
  const bufferMaterials = new Map<string, BufferPolylineMaterial>();
  const lineMaterials = new Map<string, Material>();
  let rings: RingRef[] = [];
  let capacity = { rings: 0, vertices: 0 };
  let fixedColor = Color.WHITE.withAlpha(EDGE_ALPHA);
  let buffer: BufferPolylineCollection | null = null;
  let projected: PolylineCollection | null = null;
  let projectedLines: Polyline[] = [];
  // The factor each renderer's rings are drawn at. Rings added in later slices use it, so a renderer
  // never mixes heights; `raise` moves it to `factor`.
  let bufferFactor = 0;
  let projectedFactor = 0;
  let built = false;
  let mode: ExplorerSceneMode = 'globe';
  let factor = 0;
  let generation = 0;
  // Aborted by every clear(), which cancels the slicing of whichever build or view switch is running.
  let lifetime = new AbortController();
  let lastElevationUpdate = Number.NEGATIVE_INFINITY;
  let scratch = new Float64Array(0);

  // The worker writes RGBA per ring for matched and fixed colours alike (geometry/edge-buffers.ts); a
  // buffer without colours falls back to the caller's fixed colour.
  const colorOf = ({ buffers, ring }: RingRef): Color =>
    buffers.colors.length >= (ring + 1) * 4
      ? new Color(
          buffers.colors[ring * 4],
          buffers.colors[ring * 4 + 1],
          buffers.colors[ring * 4 + 2],
          buffers.colors[ring * 4 + 3],
        )
      : fixedColor;
  const keyOf = (color: Color) =>
    `${color.red}:${color.green}:${color.blue}:${color.alpha}`;
  const bufferMaterial = (color: Color): BufferPolylineMaterial => {
    const key = keyOf(color);
    let material = bufferMaterials.get(key);
    if (!material) {
      material = new BufferPolylineMaterial({
        color,
        width: EDGE_WIDTH_PIXELS,
      });
      bufferMaterials.set(key, material);
    }
    return material;
  };
  const lineMaterial = (color: Color): Material => {
    const key = keyOf(color);
    let material = lineMaterials.get(key);
    if (!material) {
      material = new SharedColorMaterial(color);
      lineMaterials.set(key, material);
    }
    return material;
  };
  const positionsOf = (
    { buffers, ring }: RingRef,
    at: number,
  ): Float64Array => {
    const start = buffers.ringOffsets[ring] * 3;
    const end = buffers.ringOffsets[ring + 1] * 3;
    if (at === 0) return buffers.basePositions.subarray(start, end);
    if (scratch.length < end - start) scratch = new Float64Array(end - start);
    for (let index = start; index < end; index += 1) {
      const base = buffers.basePositions[index];
      scratch[index - start] = base + (buffers.positions[index] - base) * at;
    }
    return scratch.subarray(0, end - start);
  };
  const sliceOptions = (signal: AbortSignal): SliceOptions => ({
    ...options.slice,
    onSlice: options.requestRender,
    signal,
  });
  const addBuffer = async (signal: AbortSignal): Promise<void> => {
    const list = rings;
    const target = new BufferPolylineCollection({
      allowPicking: false,
      positionDatatype: ComponentDatatype.DOUBLE,
      primitiveCountMax: Math.max(1, capacity.rings),
      vertexCountMax: Math.max(1, capacity.vertices),
    });
    collection.add(target);
    buffer = target;
    bufferFactor = factor;
    const polyline = new BufferPolyline();
    await runSliced(
      list.length,
      (index) => {
        const ring = list[index];
        target.add(
          {
            material: bufferMaterial(colorOf(ring)),
            positions: positionsOf(ring, bufferFactor),
          },
          polyline,
        );
      },
      sliceOptions(signal),
    );
  };
  // Hidden until every ring is added: Cesium rebuilds a shown PolylineCollection's vertex arrays,
  // for every polyline added so far, on each render after an add, so a render per slice costs time
  // quadratic in the ring count (≈80 s at 0.2–2 fps on a 4× phone for 77k rings). `showRenderer`
  // shows it once it is complete, and Cesium builds it once.
  const addProjected = async (signal: AbortSignal): Promise<void> => {
    const list = rings;
    const target = new PolylineCollection({ show: false });
    const lines: Polyline[] = [];
    collection.add(target);
    projected = target;
    projectedLines = lines;
    projectedFactor = factor;
    await runSliced(
      list.length,
      (index) => {
        const ring = list[index];
        lines.push(
          target.add({
            material: lineMaterial(colorOf(ring)),
            positions: cartesiansOf(positionsOf(ring, projectedFactor)),
            width: EDGE_WIDTH_PIXELS,
          }),
        );
      },
      sliceOptions(signal),
    );
  };
  /** Moves every ring drawn so far, in both renderers, to `factor`. */
  const raise = () => {
    if (buffer) {
      const polyline = new BufferPolyline();
      for (let index = 0; index < buffer.primitiveCount; index += 1) {
        buffer.get(index, polyline);
        polyline.setPositions(positionsOf(rings[index], factor));
      }
      bufferFactor = factor;
    }
    if (projected) {
      projectedLines.forEach((line, index) => {
        line.positions = cartesiansOf(positionsOf(rings[index], factor));
      });
      projectedFactor = factor;
    }
  };
  const showRenderer = (renderer: EdgeRenderer) => {
    if (buffer) buffer.show = renderer === 'buffer';
    if (projected) projected.show = renderer === 'projected';
  };
  // Re-reads `mode` after every await: a view switch that lands while a renderer is being built is
  // honoured when that build ends, and the last switch decides which renderer is shown.
  const ensureRenderer = async (signal: AbortSignal): Promise<void> => {
    for (;;) {
      if (signal.aborted) throw abortError();
      const renderer = edgeRendererForMode(mode);
      if (renderer === 'buffer' && !buffer) await addBuffer(signal);
      else if (renderer === 'projected' && !projected)
        await addProjected(signal);
      else {
        showRenderer(renderer);
        return;
      }
    }
  };
  const clear = () => {
    lifetime.abort();
    lifetime = new AbortController();
    buffer = null;
    projected = null;
    projectedLines = [];
    rings = [];
    built = false;
    collection.removeAll();
    lineMaterials.clear();
  };

  return {
    collection,
    async build(source, color, nextMode, nextFactor, signal) {
      if (built) return;
      const current = ++generation;
      clear();
      fixedColor = Color.fromCssColorString(color).withAlpha(EDGE_ALPHA);
      mode = nextMode;
      factor = Math.max(0, nextFactor);
      const controller = new AbortController();
      const abort = () => controller.abort();
      const owner = lifetime.signal;
      signal?.addEventListener('abort', abort, { once: true });
      owner.addEventListener('abort', abort, { once: true });
      if (signal?.aborted) controller.abort();
      try {
        const received: EdgeChunkBuffers[] = [];
        let declared = { rings: 0, vertices: 0 };
        await source((message) => {
          declared = {
            rings: message.primitiveCountMax,
            vertices: message.vertexCountMax,
          };
          received.push(message.edges);
        }, controller.signal);
        if (current !== generation || controller.signal.aborted)
          throw abortError();
        rings = received.flatMap(ringsOf);
        const vertices = received.reduce(
          (total, buffers) =>
            total + (buffers.ringOffsets[buffers.ringOffsets.length - 1] ?? 0),
          0,
        );
        if (declared.rings !== rings.length || declared.vertices !== vertices)
          throw new Error(
            `Cell outline capacity mismatch: declared ${declared.rings} rings and ${declared.vertices} vertices, received ${rings.length} and ${vertices}`,
          );
        capacity = declared;
        await ensureRenderer(controller.signal);
        if (current !== generation) throw abortError();
        built = true;
        options.requestRender();
      } catch (error) {
        if (current === generation) clear();
        throw error;
      } finally {
        signal?.removeEventListener('abort', abort);
        owner.removeEventListener('abort', abort);
      }
    },
    isBuilt: () => built,
    ringCount: () => rings.length,
    async setMode(next) {
      mode = next;
      if (!built) return;
      const { signal } = lifetime;
      try {
        await ensureRenderer(signal);
      } catch (error) {
        // reset() discarded these outlines; the next build is told its mode.
        if (signal.aborted && (error as Error | null)?.name === 'AbortError')
          return;
        throw error;
      }
      options.requestRender();
    },
    setElevationFactor(next, force = false) {
      const safe = Math.max(0, next);
      if (safe === factor && !force) return;
      factor = safe;
      // Nothing drawn yet: the build adds its first rings at `factor`.
      if (!buffer && !projected) return;
      const time = now();
      if (
        !force &&
        safe !== 0 &&
        time - lastElevationUpdate < ELEVATION_THROTTLE_MS
      )
        return;
      lastElevationUpdate = time;
      raise();
      options.requestRender();
    },
    reset() {
      generation += 1;
      clear();
      options.requestRender();
    },
  };
}
