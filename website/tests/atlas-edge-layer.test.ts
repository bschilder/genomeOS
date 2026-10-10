import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Cartesian3,
  Color,
  PolylineCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EdgeChunkBuffers } from '../src/atlas/geometry/edge-buffers';
import {
  createEdgeLayer,
  EDGE_ALPHA,
  type EdgeLayer,
  type EdgeSource,
} from '../src/atlas/scene/edge-layer';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';

const EDGE_CLEARANCE = 1_050;
type Ring = readonly (readonly [number, number])[];
const SQUARE: Ring = [
  [0, 0],
  [0.1, 0],
  [0.1, 0.1],
  [0, 0],
];
const TRIANGLE: Ring = [
  [1, 1],
  [1.1, 1],
  [1, 1.1],
  [1, 1],
];

function ecef(points: Ring, height: number): number[] {
  return points.flatMap(([lon, lat]) => {
    const position = Cartesian3.fromDegrees(lon, lat, height);
    return [position.x, position.y, position.z];
  });
}

/** `colors` are RGB triples per ring (worker colours); omitted, the buffers carry none. */
function edgeBuffers(
  chunk: number,
  rings: readonly Ring[],
  colors?: readonly number[],
): EdgeChunkBuffers {
  const offsets = [0];
  for (const ring of rings)
    offsets.push(offsets[offsets.length - 1] + ring.length);
  const points = rings.flat();
  const basePositions = Float64Array.from(ecef(points, EDGE_CLEARANCE));
  const rgba = colors
    ? Float32Array.from(
        Array.from({ length: colors.length / 3 }, (_, ring) => [
          colors[ring * 3],
          colors[ring * 3 + 1],
          colors[ring * 3 + 2],
          EDGE_ALPHA,
        ]).flat(),
      )
    : new Float32Array(0);
  return {
    baseHeights: new Float64Array(points.length).fill(1_000),
    basePositions,
    chunk,
    colors: rgba,
    normals: new Float32Array(basePositions.length),
    // The scene requests factor 1, so the worker's positions sit 1,000 m above the base here.
    positions: Float64Array.from(ecef(points, EDGE_CLEARANCE + 1_000)),
    ringOffsets: Uint32Array.from(offsets),
  };
}

function sourceOf(chunks: readonly EdgeChunkBuffers[]): EdgeSource {
  const rings = chunks.reduce(
    (total, b) => total + b.ringOffsets.length - 1,
    0,
  );
  const vertices = chunks.reduce(
    (total, b) => total + b.ringOffsets[b.ringOffsets.length - 1],
    0,
  );
  return async (onChunk) => {
    for (const [index, buffers] of chunks.entries()) {
      await Promise.resolve();
      onChunk({
        artifactKey: 'hbs-rs334:v3:map-2026-08',
        edges: buffers,
        id: 1,
        index,
        primitiveCountMax: rings,
        total: chunks.length,
        type: 'edges-chunk',
        vertexCountMax: vertices,
      });
    }
  };
}

function ringPositions(
  collection: BufferPolylineCollection,
  index: number,
): number[] {
  const line = new BufferPolyline();
  collection.get(index, line);
  // Cesium's d.ts types getPositions() as void; toJSON() is the typed accessor.
  return (line.toJSON() as { positions: number[] }).positions;
}

afterEach(() => vi.unstubAllGlobals());

describe('deferred cell outlines', () => {
  it('allocates one buffer collection from the declared capacity and adds every ring', async () => {
    const requestRender = vi.fn();
    const layer = createEdgeLayer({ requestRender });
    const first = edgeBuffers(0, [SQUARE, TRIANGLE], [1, 0, 0, 0, 1, 0]);
    const second = edgeBuffers(1, [SQUARE]);

    await layer.build(sourceOf([first, second]), '#ff3366', 'globe', 0);

    const buffer = layer.collection.get(0) as BufferPolylineCollection;
    expect(layer.collection.length).toBe(1);
    expect(buffer).toBeInstanceOf(BufferPolylineCollection);
    expect(buffer.primitiveCountMax).toBe(3);
    expect(buffer.vertexCountMax).toBe(12);
    expect(buffer.primitiveCount).toBe(3);
    expect(ringPositions(buffer, 0)).toEqual(
      Array.from(first.basePositions.subarray(0, 12)),
    );
    expect(layer.isBuilt()).toBe(true);
    expect(layer.ringCount()).toBe(3);
    expect(requestRender).toHaveBeenCalled();

    layer.reset();
    expect(layer.collection.length).toBe(0);
    expect(layer.isBuilt()).toBe(false);
  });

  it('colours matched rings from the worker and fixed rings from the chosen colour', async () => {
    const layer = createEdgeLayer({ requestRender: vi.fn() });
    await layer.build(
      sourceOf([
        edgeBuffers(0, [SQUARE], [0, 1, 0]),
        edgeBuffers(1, [TRIANGLE]),
      ]),
      '#ff3366',
      'globe',
      0,
    );
    const buffer = layer.collection.get(0) as BufferPolylineCollection;
    const line = new BufferPolyline();
    const material = new BufferPolylineMaterial();

    buffer.get(0, line);
    line.getMaterial(material);
    expect([
      material.color.red,
      material.color.green,
      material.color.blue,
    ]).toEqual([0, 1, 0]);
    expect(material.color.alpha).toBeCloseTo(EDGE_ALPHA, 2);
    expect(material.width).toBe(2);

    buffer.get(1, line);
    line.getMaterial(material);
    const fixed = Color.fromCssColorString('#ff3366');
    expect(material.color.red).toBeCloseTo(fixed.red, 2);
    expect(material.color.green).toBeCloseTo(fixed.green, 2);
    expect(material.color.blue).toBeCloseTo(fixed.blue, 2);
  });

  it('raises every vertex linearly with the elevation factor', async () => {
    const layer = createEdgeLayer({ requestRender: vi.fn() });
    await layer.build(
      sourceOf([edgeBuffers(0, [SQUARE])]),
      '#ffffff',
      'globe',
      0,
    );

    layer.setElevationFactor(2, true);

    const raised = ringPositions(
      layer.collection.get(0) as BufferPolylineCollection,
      0,
    );
    const expected = ecef(SQUARE, EDGE_CLEARANCE + 2_000);
    raised.forEach((value, index) =>
      expect(value).toBeCloseTo(expected[index], 3),
    );
  });

  it('builds a projected outline renderer for map and perspective views', async () => {
    stubCesiumBrowserImageTypes();
    const layer = createEdgeLayer({ requestRender: vi.fn() });
    await layer.build(
      sourceOf([edgeBuffers(0, [SQUARE, TRIANGLE])]),
      '#ffffff',
      'globe',
      0,
    );

    await layer.setMode('map');
    const buffer = layer.collection.get(0) as BufferPolylineCollection;
    const projected = layer.collection.get(1) as PolylineCollection;
    expect(projected).toBeInstanceOf(PolylineCollection);
    expect(projected.length).toBe(2);
    expect(projected.get(0).positions).toHaveLength(SQUARE.length);
    expect(buffer.show).toBe(false);
    expect(projected.show).toBe(true);

    await layer.setMode('globe');
    expect(buffer.show).toBe(true);
    expect(projected.show).toBe(false);
  });

  it('refuses a declared capacity that does not match the rings received', async () => {
    const layer = createEdgeLayer({ requestRender: vi.fn() });
    const buffers = edgeBuffers(0, [SQUARE]);
    const lying: EdgeSource = async (onChunk) =>
      onChunk({
        artifactKey: 'hbs-rs334:v3:map-2026-08',
        edges: buffers,
        id: 1,
        index: 0,
        primitiveCountMax: 2,
        total: 1,
        type: 'edges-chunk',
        vertexCountMax: 4,
      });

    await expect(layer.build(lying, '#ffffff', 'globe', 0)).rejects.toThrow(
      /capacity mismatch/,
    );
    expect(layer.isBuilt()).toBe(false);
    expect(layer.collection.length).toBe(0);
  });

  it('abandons a superseded build without leaving outlines behind', async () => {
    const layer = createEdgeLayer({ requestRender: vi.fn() });
    const controller = new AbortController();
    controller.abort();

    await expect(
      layer.build(
        sourceOf([edgeBuffers(0, [SQUARE])]),
        '#ffffff',
        'globe',
        0,
        controller.signal,
      ),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(layer.collection.length).toBe(0);
  });
});

/** One ring per slice, so any build of two or more rings yields between rings; `atNextYield` makes a call
 * land at the next yield, while rings are still being added. */
function interleaved() {
  let pending: (() => void) | null = null;
  return {
    atNextYield(action: () => void) {
      pending = action;
    },
    slice: {
      sliceMs: 0,
      yieldFn: async () => {
        const action = pending;
        pending = null;
        action?.();
      },
    },
  };
}

function projectedPositions(
  collection: PolylineCollection,
  index: number,
): number[] {
  return collection
    .get(index)
    .positions.flatMap((position: Cartesian3) => [
      position.x,
      position.y,
      position.z,
    ]);
}

function outlinePositions(layer: EdgeLayer, index: number): number[] {
  const renderer = layer.collection.get(0) as
    BufferPolylineCollection | PolylineCollection;
  return renderer instanceof BufferPolylineCollection
    ? ringPositions(renderer, index)
    : projectedPositions(renderer, index);
}

function expectRingsAt(
  layer: EdgeLayer,
  rings: readonly Ring[],
  height: number,
): void {
  rings.forEach((ring, index) => {
    const expected = ecef(ring, height);
    const positions = outlinePositions(layer, index);
    expect(positions).toHaveLength(expected.length);
    positions.forEach((value, component) =>
      expect(value).toBeCloseTo(expected[component], 3),
    );
  });
}

describe('cell outlines built across several slices', () => {
  const RINGS: readonly Ring[] = [SQUARE, TRIANGLE, SQUARE];

  it('releases projected outlines that share a material on reset, and builds again', async () => {
    stubCesiumBrowserImageTypes();
    const layer = createEdgeLayer({
      requestRender: vi.fn(),
      slice: interleaved().slice,
    });
    // Every ring takes the fixed colour, so all projected lines use one material.
    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);
    await layer.setMode('map');
    const projected = layer.collection.get(1) as PolylineCollection;
    expect(projected.length).toBe(3);
    const material = projected.get(0).material;
    expect(material.type).toBe('Color');
    expect(material.uniforms.color).toEqual(Color.WHITE.withAlpha(EDGE_ALPHA));
    expect(projected.get(2).material).toBe(material);

    expect(() => layer.reset()).not.toThrow();
    expect(layer.collection.length).toBe(0);
    expect(layer.isBuilt()).toBe(false);

    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'map', 0);
    expect(layer.isBuilt()).toBe(true);
    expect(layer.collection.length).toBe(1);
    expect((layer.collection.get(0) as PolylineCollection).length).toBe(3);
    expect(() => layer.reset()).not.toThrow();
    expect(layer.collection.length).toBe(0);
  });

  it.each(['globe', 'map'] as const)(
    'raises every %s ring when the elevation changes while rings are added',
    async (mode) => {
      stubCesiumBrowserImageTypes();
      const { atNextYield, slice } = interleaved();
      const layer = createEdgeLayer({ requestRender: vi.fn(), slice });
      atNextYield(() => layer.setElevationFactor(2, true));

      await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', mode, 0);

      expectRingsAt(layer, RINGS, EDGE_CLEARANCE + 2_000);
    },
  );

  it('keeps one height when a throttled elevation change lands while rings are added', async () => {
    const { atNextYield, slice } = interleaved();
    const layer = createEdgeLayer({
      now: () => 0,
      requestRender: vi.fn(),
      slice,
    });
    atNextYield(() => {
      layer.setElevationFactor(1);
      // Within the 50 ms throttle: recorded, not yet drawn.
      layer.setElevationFactor(2);
    });

    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);
    expectRingsAt(layer, RINGS, EDGE_CLEARANCE + 1_000);

    layer.setElevationFactor(2, true);
    expectRingsAt(layer, RINGS, EDGE_CLEARANCE + 2_000);
  });

  it.each([
    ['a map build', 'map', 'map'],
    ['a switch to perspective', 'globe', 'perspective'],
  ] as const)(
    'keeps the projected outlines hidden until every ring is added (%s)',
    async (_label, buildMode, viewMode) => {
      // Cesium rebuilds a shown PolylineCollection's vertex arrays for every ring added so far on
      // each render, so drawing it slice by slice costs time quadratic in the ring count (about
      // 80 s of 0.2-2 fps on a phone at 77k rings). Hidden, it is built once, when shown.
      stubCesiumBrowserImageTypes();
      const shownWhileAdding: boolean[] = [];
      let layer: EdgeLayer | null = null;
      const slice = {
        sliceMs: 0,
        yieldFn: async () => {
          const projected = layer?.collection.get(layer.collection.length - 1);
          if (projected instanceof PolylineCollection)
            shownWhileAdding.push(projected.show);
        },
      };
      layer = createEdgeLayer({ requestRender: vi.fn(), slice });
      await layer.build(
        sourceOf([edgeBuffers(0, RINGS)]),
        '#ffffff',
        buildMode,
        0,
      );
      await layer.setMode(viewMode);

      const projected = layer.collection.get(
        layer.collection.length - 1,
      ) as PolylineCollection;
      expect(projected).toBeInstanceOf(PolylineCollection);
      expect(projected.length).toBe(RINGS.length);
      expect(shownWhileAdding.length).toBeGreaterThan(0);
      expect(shownWhileAdding.every((shown) => !shown)).toBe(true);
      expect(projected.show).toBe(true);
    },
  );

  it('moves no ring when a forced elevation change finds every renderer at that factor', async () => {
    // The scene forces setElevationFactor before every artifact switch. A forced call at the
    // drawn factor used to rewrite all ~77k rings, and Cesium re-packed the whole collection on
    // the next frame: a 0.3-0.5 s frame per desktop switch, 1.2-1.7 s on a 4x phone.
    stubCesiumBrowserImageTypes();
    const setPositions = vi.spyOn(BufferPolyline.prototype, 'setPositions');
    const layer = createEdgeLayer({ requestRender: vi.fn() });
    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);
    await layer.setMode('map');
    const projected = layer.collection.get(1) as PolylineCollection;
    const drawn = RINGS.map((_, index) => projected.get(index).positions);
    setPositions.mockClear();

    layer.setElevationFactor(0, true);
    expect(setPositions).not.toHaveBeenCalled();
    RINGS.forEach((_, index) =>
      expect(projected.get(index).positions).toBe(drawn[index]),
    );

    // A real change still moves both renderers.
    layer.setElevationFactor(2, true);
    expect(setPositions).toHaveBeenCalledTimes(RINGS.length);
    RINGS.forEach((_, index) =>
      expect(projected.get(index).positions).not.toBe(drawn[index]),
    );
    setPositions.mockRestore();
  });

  it('shows projected outlines when the view switches to map while the build adds rings', async () => {
    stubCesiumBrowserImageTypes();
    const { atNextYield, slice } = interleaved();
    const layer = createEdgeLayer({ requestRender: vi.fn(), slice });
    atNextYield(() => void layer.setMode('map'));

    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);

    const buffer = layer.collection.get(0) as BufferPolylineCollection;
    const projected = layer.collection.get(1) as PolylineCollection;
    expect(projected).toBeInstanceOf(PolylineCollection);
    expect(projected.length).toBe(3);
    expect(buffer.show).toBe(false);
    expect(projected.show).toBe(true);
  });

  it('shows the renderer of the last view when two switches overlap', async () => {
    stubCesiumBrowserImageTypes();
    const { atNextYield, slice } = interleaved();
    const layer = createEdgeLayer({ requestRender: vi.fn(), slice });
    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);
    let back: Promise<void> | undefined;
    atNextYield(() => {
      back = layer.setMode('globe');
    });

    await layer.setMode('map');
    await back;

    expect(back).toBeDefined();
    const buffer = layer.collection.get(0) as BufferPolylineCollection;
    const projected = layer.collection.get(1) as PolylineCollection;
    expect(projected.length).toBe(3);
    expect(buffer.show).toBe(true);
    expect(projected.show).toBe(false);
  });

  it('reset cancels a projected build that a view switch started', async () => {
    stubCesiumBrowserImageTypes();
    const { atNextYield, slice } = interleaved();
    const layer = createEdgeLayer({ requestRender: vi.fn(), slice });
    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);
    atNextYield(() => layer.reset());

    await expect(layer.setMode('map')).resolves.toBeUndefined();

    expect(layer.collection.length).toBe(0);
    expect(layer.isBuilt()).toBe(false);
    expect(layer.ringCount()).toBe(0);
  });

  it('reset abandons a build that is adding rings, and a later build succeeds', async () => {
    const { atNextYield, slice } = interleaved();
    const layer = createEdgeLayer({ requestRender: vi.fn(), slice });
    atNextYield(() => layer.reset());

    await expect(
      layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(layer.collection.length).toBe(0);
    expect(layer.isBuilt()).toBe(false);

    await layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0);
    expect(layer.isBuilt()).toBe(true);
    expect(layer.collection.length).toBe(1);
    expect(
      (layer.collection.get(0) as BufferPolylineCollection).primitiveCount,
    ).toBe(3);
  });

  it('a new build supersedes one that is adding rings', async () => {
    const { atNextYield, slice } = interleaved();
    const layer = createEdgeLayer({ requestRender: vi.fn(), slice });
    let second: Promise<void> | undefined;
    atNextYield(() => {
      second = layer.build(
        sourceOf([edgeBuffers(0, [TRIANGLE])]),
        '#ffffff',
        'globe',
        0,
      );
    });

    await expect(
      layer.build(sourceOf([edgeBuffers(0, RINGS)]), '#ffffff', 'globe', 0),
    ).rejects.toMatchObject({ name: 'AbortError' });
    await second;

    expect(layer.isBuilt()).toBe(true);
    expect(layer.ringCount()).toBe(1);
    expect(layer.collection.length).toBe(1);
    const buffer = layer.collection.get(0) as BufferPolylineCollection;
    expect(buffer.primitiveCount).toBe(1);
    expectRingsAt(layer, [TRIANGLE], EDGE_CLEARANCE);
  });
});
