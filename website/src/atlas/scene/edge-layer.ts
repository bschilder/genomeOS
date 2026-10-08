/** Deferred H3 cell outlines from worker ring buffers for Atlas design §11 (spec 2026-10-07 §B.6.9).
 *
 * Outlines are never on the reveal path. The scene builds them after
 * `atlas:surface-visible`; the worker declares exact capacities so one
 * BufferPolylineCollection is allocated, and rings are added in
 * frame-budgeted slices. Elevation moves each vertex linearly from its base
 * position (factor 0) towards its position at exaggeration 1.
 */

import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Cartesian3,
  Color,
  ComponentDatatype,
  Material,
  PolylineCollection,
  PrimitiveCollection,
  type Polyline,
} from 'cesium';

import { EDGE_ALPHA, type EdgeChunkBuffers } from '../geometry/edge-buffers';
import type { ExplorerSceneMode } from '../url-state';
import type { EdgesChunkMessage } from '../worker/protocol';
import {
  abortError,
  edgeRendererForMode,
  runSliced,
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

function cartesiansOf(values: Float64Array): Cartesian3[] {
  const positions: Cartesian3[] = [];
  for (let index = 0; index < values.length; index += 3)
    positions.push(
      new Cartesian3(values[index], values[index + 1], values[index + 2]),
    );
  return positions;
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
  let built = false;
  let mode: ExplorerSceneMode = 'globe';
  let factor = 0;
  let generation = 0;
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
      material = Material.fromType('Color', { color });
      lineMaterials.set(key, material);
    }
    return material;
  };
  const positionsOf = ({ buffers, ring }: RingRef): Float64Array => {
    const start = buffers.ringOffsets[ring] * 3;
    const end = buffers.ringOffsets[ring + 1] * 3;
    if (factor === 0) return buffers.basePositions.subarray(start, end);
    if (scratch.length < end - start) scratch = new Float64Array(end - start);
    for (let index = start; index < end; index += 1) {
      const base = buffers.basePositions[index];
      scratch[index - start] =
        base + (buffers.positions[index] - base) * factor;
    }
    return scratch.subarray(0, end - start);
  };
  const sliceOptions = (signal: AbortSignal): SliceOptions => ({
    ...options.slice,
    onSlice: options.requestRender,
    signal,
  });
  const addBuffer = async (signal: AbortSignal): Promise<void> => {
    const target = new BufferPolylineCollection({
      allowPicking: false,
      positionDatatype: ComponentDatatype.DOUBLE,
      primitiveCountMax: Math.max(1, capacity.rings),
      vertexCountMax: Math.max(1, capacity.vertices),
    });
    collection.add(target);
    buffer = target;
    const polyline = new BufferPolyline();
    await runSliced(
      rings.length,
      (index) => {
        const ring = rings[index];
        target.add(
          {
            material: bufferMaterial(colorOf(ring)),
            positions: positionsOf(ring),
          },
          polyline,
        );
      },
      sliceOptions(signal),
    );
  };
  const addProjected = async (signal: AbortSignal): Promise<void> => {
    const target = new PolylineCollection();
    collection.add(target);
    projected = target;
    projectedLines = [];
    await runSliced(
      rings.length,
      (index) => {
        const ring = rings[index];
        projectedLines.push(
          target.add({
            material: lineMaterial(colorOf(ring)),
            positions: cartesiansOf(positionsOf(ring)),
            width: EDGE_WIDTH_PIXELS,
          }),
        );
      },
      sliceOptions(signal),
    );
  };
  const showRenderer = (renderer: EdgeRenderer) => {
    if (buffer) buffer.show = renderer === 'buffer';
    if (projected) projected.show = renderer === 'projected';
  };
  const ensureRenderer = async (
    renderer: EdgeRenderer,
    signal: AbortSignal,
  ): Promise<void> => {
    if (renderer === 'buffer' && !buffer) await addBuffer(signal);
    if (renderer === 'projected' && !projected) await addProjected(signal);
    showRenderer(renderer);
  };
  const clear = () => {
    collection.removeAll();
    buffer = null;
    projected = null;
    projectedLines = [];
    rings = [];
    built = false;
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
      signal?.addEventListener('abort', abort, { once: true });
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
        await ensureRenderer(edgeRendererForMode(mode), controller.signal);
        if (current !== generation) throw abortError();
        built = true;
        options.requestRender();
      } catch (error) {
        if (current === generation) clear();
        throw error;
      } finally {
        signal?.removeEventListener('abort', abort);
      }
    },
    isBuilt: () => built,
    ringCount: () => rings.length,
    async setMode(next) {
      mode = next;
      if (!built) return;
      await ensureRenderer(
        edgeRendererForMode(next),
        new AbortController().signal,
      );
      options.requestRender();
    },
    setElevationFactor(next, force = false) {
      const safe = Math.max(0, next);
      if (safe === factor && !force) return;
      factor = safe;
      if (!built) return;
      const time = now();
      if (
        !force &&
        safe !== 0 &&
        time - lastElevationUpdate < ELEVATION_THROTTLE_MS
      )
        return;
      lastElevationUpdate = time;
      if (buffer) {
        const polyline = new BufferPolyline();
        for (let index = 0; index < rings.length; index += 1) {
          buffer.get(index, polyline);
          polyline.setPositions(positionsOf(rings[index]));
        }
      }
      projectedLines.forEach((line, index) => {
        line.positions = cartesiansOf(positionsOf(rings[index]));
      });
      options.requestRender();
    },
    reset() {
      generation += 1;
      clear();
      options.requestRender();
    },
  };
}
