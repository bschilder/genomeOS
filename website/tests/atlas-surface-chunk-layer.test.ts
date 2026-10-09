import {
  Cartesian3,
  Color,
  GeometryInstance,
  GeometryPipeline,
  type Material,
  Primitive,
  PrimitiveCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  MAX_ELEVATION_FACTOR,
  type SurfaceChunkBuffers,
} from '../src/atlas/geometry/surface-buffers';
import { needsLongitudeSplit } from '../src/atlas/geometry/wgs84';
import { animateSwap, fadeTogether } from '../src/atlas/scene/scene-transition';
import {
  createSurfaceChunkGroup,
  surfaceChunkPickId,
} from '../src/atlas/scene/surface-chunk-layer';
import type { ElevatedSurfaceAppearance } from '../src/atlas/scene/surface-appearance';
import type { SurfaceGeometry } from '../src/atlas/url-state';
import {
  emptySupport,
  maskedSupport,
  seamSurfaceBuffers,
  triangleSurfaceBuffers,
} from './helpers/chunk-buffers';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';

const KEY = 'hbs-rs334:v3:map-2026-08';

function group(geometry: SurfaceGeometry = 'triangles') {
  stubCesiumBrowserImageTypes();
  return createSurfaceChunkGroup({
    artifactKey: KEY,
    cellEdges: true,
    elevationFactor: 0,
    geometry,
    requestRender: vi.fn(),
    surfaceOpacity: 0.5,
  });
}

function markReady(primitives: readonly Primitive[]): void {
  for (const primitive of primitives)
    (primitive as unknown as { _ready: boolean })._ready = true;
}

type ChunkGroup = ReturnType<typeof group>;

/** Child `index` of the surface (0) or support (1) collection. */
function childAt(
  layer: ChunkGroup,
  layerIndex: 0 | 1,
  index: number,
): Primitive {
  return (layer.collection.get(layerIndex) as PrimitiveCollection).get(
    index,
  ) as Primitive;
}

function childrenOf(layer: ChunkGroup, layerIndex: 0 | 1): Primitive[] {
  const children = layer.collection.get(layerIndex) as PrimitiveCollection;
  return Array.from(
    { length: children.length },
    (_, index) => children.get(index) as Primitive,
  );
}

function alphaOf(material: Material, key: string): number {
  return (material.uniforms[key] as Color).alpha;
}

function fakeGroup(opacity: number) {
  return {
    collection: { show: true },
    isReady: () => true,
    opacity,
    readyCount: () => 1,
    setOpacity(value: number) {
      this.opacity = value;
    },
    totalCount: () => 1,
  };
}

/** Every vertex lifted along its elevation normal at the top exaggeration. */
function raisedVertices(buffers: SurfaceChunkBuffers): Cartesian3[] {
  return Array.from({ length: buffers.heights.length }, (_, vertex) => {
    const lift = buffers.heights[vertex] * MAX_ELEVATION_FACTOR;
    return new Cartesian3(
      buffers.positions[vertex * 3] +
        buffers.elevationNormals[vertex * 3] * lift,
      buffers.positions[vertex * 3 + 1] +
        buffers.elevationNormals[vertex * 3 + 1] * lift,
      buffers.positions[vertex * 3 + 2] +
        buffers.elevationNormals[vertex * 3 + 2] * lift,
    );
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('surface chunk group', () => {
  it('keeps the surface, support and edge child order', () => {
    const layer = group();
    expect(layer.collection.length).toBe(3);
    expect(layer.collection.get(2)).toBe(layer.edges.collection);
    expect(layer.collection.get(0)).toBeInstanceOf(PrimitiveCollection);
    expect(layer.collection.get(1)).toBeInstanceOf(PrimitiveCollection);
  });

  it('adds a chunk and its masked cells together with chunk pick ids', () => {
    const layer = group();
    const surface = triangleSurfaceBuffers(7);
    layer.addChunk(surface, maskedSupport(7));

    const surfaces = layer.collection.get(0) as PrimitiveCollection;
    const support = layer.collection.get(1) as PrimitiveCollection;
    expect(surfaces.length).toBe(1);
    expect(support.length).toBe(2);
    expect(layer.chunkCount()).toBe(1);
    expect(layer.totalCount()).toBe(3);
    expect(layer.readyCount()).toBe(0);
    expect(layer.readyChunkCount()).toBe(0);

    const primitive = surfaces.get(0) as Primitive;
    const instance = primitive.geometryInstances as GeometryInstance;
    expect(instance.id).toEqual(surfaceChunkPickId(KEY, 7));
    expect(instance.id).toEqual({
      artifactKey: KEY,
      chunk: 7,
      kind: 'surface-chunk',
    });
    const attributes = instance.geometry.attributes as unknown as Record<
      string,
      { values: ArrayLike<number> }
    >;
    expect(attributes.surfaceColor.values).toBe(surface.colors);
    expect(attributes.surfaceHeight.values).toBe(surface.heights);
    expect(attributes.surfaceValue.values).toBe(surface.values);
    expect(attributes.elevationNormal.values).toBe(surface.elevationNormals);
    expect(instance.geometry.indices).toBeInstanceOf(Uint32Array);
    expect(instance.geometry.boundingSphere!.radius).toBe(30_000);
    expect(instance.geometry.boundingSphere!.center.x).toBe(
      surface.boundingSphere.center[0],
    );
    const supportIds = [0, 1].map(
      (index) =>
        (
          (support.get(index) as Primitive)
            .geometryInstances as GeometryInstance
        ).id,
    );
    expect(supportIds).toEqual([
      surfaceChunkPickId(KEY, 7),
      surfaceChunkPickId(KEY, 7),
    ]);

    markReady(layer.primitives);
    expect(layer.readyCount()).toBe(3);
    expect(layer.isReady()).toBe(true);
    expect(layer.readyChunkCount()).toBe(1);
  });

  it('uses the existing hatch and palette-dot support materials', () => {
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    const support = layer.collection.get(1) as PrimitiveCollection;
    const unknown = (support.get(0) as Primitive).appearance.material;
    const prior = (support.get(1) as Primitive).appearance.material;

    expect(unknown.type).toBe('Grid');
    expect(prior.type).toBe('Dot');
    const dark = prior.uniforms.darkColor as Color;
    const palette = Color.fromCssColorString('#cc4778');
    expect(dark.red).toBeCloseTo(palette.red);
    expect(dark.green).toBeCloseTo(palette.green);
    expect(dark.blue).toBeCloseTo(palette.blue);
  });

  it('gamma-corrects vertex colours only for hexagon and extruded chunks', () => {
    const smooth = group('triangles');
    smooth.addChunk(triangleSurfaceBuffers(0), emptySupport(0));
    const binned = group('hexagons');
    binned.addChunk(triangleSurfaceBuffers(0), emptySupport(0));
    const uniformsOf = (layer: ReturnType<typeof group>) =>
      (
        ((layer.collection.get(0) as PrimitiveCollection).get(0) as Primitive)
          .appearance as ElevatedSurfaceAppearance
      ).uniforms;

    expect(uniformsOf(smooth).u_vertexColorGamma).toBe(0);
    expect(uniformsOf(binned).u_vertexColorGamma).toBe(1);
  });

  it('fades materials as the legacy group did and scales the hatch cell alpha', () => {
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    layer.setOpacity(0.5);
    const surface = (
      (layer.collection.get(0) as PrimitiveCollection).get(0) as Primitive
    ).appearance.material;
    const hatch = (
      (layer.collection.get(1) as PrimitiveCollection).get(0) as Primitive
    ).appearance.material;

    expect((surface.uniforms.color as Color).alpha).toBeCloseTo(
      0.9 * 0.5 * 0.5,
    );
    expect(hatch.uniforms.cellAlpha).toBeCloseTo(0.24 * 0.5);
    expect(layer.opacity()).toBe(0.5);

    layer.setSurfaceOpacity(1);
    expect((surface.uniforms.color as Color).alpha).toBeCloseTo(0.9 * 0.5);
  });

  it('hides layers per primitive so hidden chunks still finish building', () => {
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    layer.setVisibility(false, true);
    layer.addChunk(triangleSurfaceBuffers(1), maskedSupport(1));

    const surfaces = layer.collection.get(0) as PrimitiveCollection;
    const support = layer.collection.get(1) as PrimitiveCollection;
    expect(surfaces.show).toBe(true);
    expect(support.show).toBe(true);
    expect((surfaces.get(0) as Primitive).show).toBe(false);
    expect((surfaces.get(1) as Primitive).show).toBe(false);
    expect((support.get(2) as Primitive).show).toBe(true);
    expect(layer.edges.collection.show).toBe(false);
  });

  it('raises every chunk through its elevation uniform', () => {
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), emptySupport(0));
    layer.addChunk(triangleSurfaceBuffers(1), emptySupport(1));
    layer.setElevationFactor(3);
    const surfaces = layer.collection.get(0) as PrimitiveCollection;

    for (const index of [0, 1])
      expect(
        (
          (surfaces.get(index) as Primitive)
            .appearance as ElevatedSurfaceAppearance
        ).uniforms.u_elevationFactor,
      ).toBe(3);
  });

  it('adds only the mask when a chunk has no supported cells', () => {
    const layer = group();
    const empty = {
      ...triangleSurfaceBuffers(2),
      indices: new Uint16Array(0),
    };
    layer.addChunk(empty, maskedSupport(2));
    expect((layer.collection.get(0) as PrimitiveCollection).length).toBe(0);
    expect(layer.totalCount()).toBe(2);
  });

  it('fades a surface and its observations in one swap and retires both outgoing groups', async () => {
    const fake = (opacity: number) => ({
      collection: { show: true },
      isReady: () => true,
      opacity,
      readyCount: () => 1,
      setOpacity(value: number) {
        this.opacity = value;
      },
      totalCount: () => 1,
    });
    const [surfaceIn, pointsIn, surfaceOut, pointsOut] = [0, 0, 1, 1].map(fake);
    const viewer = {
      scene: { postRender: {}, primitives: {}, requestRender: vi.fn() },
    };

    await animateSwap(
      viewer as never,
      fadeTogether(surfaceIn, pointsIn)!,
      fadeTogether(surfaceOut, pointsOut),
      true,
      true,
    );

    expect([surfaceIn.opacity, pointsIn.opacity]).toEqual([1, 1]);
    expect([surfaceOut.opacity, pointsOut.opacity]).toEqual([0, 0]);
    expect([surfaceOut.collection.show, pointsOut.collection.show]).toEqual([
      false,
      false,
    ]);
    expect(fadeTogether(null, null)).toBeNull();
  });

  it('removes every member of an outgoing unit when the swap does not retain it', async () => {
    const [incoming, surfaceOut, pointsOut] = [0, 1, 1].map(fakeGroup);
    const remove = vi.fn(() => true);
    const viewer = {
      scene: { postRender: {}, primitives: { remove }, requestRender: vi.fn() },
    };
    const outgoing = fadeTogether(fadeTogether(surfaceOut), pointsOut);

    await animateSwap(viewer as never, incoming, outgoing, true);

    expect(outgoing?.members).toEqual([surfaceOut, pointsOut]);
    expect(remove.mock.calls).toEqual([
      [surfaceOut.collection],
      [pointsOut.collection],
    ]);
  });

  it('starts a chunk added mid-fade at the current fade', () => {
    const layer = group();
    layer.setOpacity(0.25);
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    const surface = childAt(layer, 0, 0).appearance.material;
    const hatch = childAt(layer, 1, 0).appearance.material;
    const dots = childAt(layer, 1, 1).appearance.material;

    expect(alphaOf(surface, 'color')).toBeCloseTo(0.9 * 0.25 * 0.5);
    expect(alphaOf(hatch, 'color')).toBeCloseTo(0.72 * 0.25 * 0.5);
    expect(hatch.uniforms.cellAlpha).toBeCloseTo(0.24 * 0.25);
    expect(alphaOf(dots, 'darkColor')).toBeCloseTo(0.46 * 0.25 * 0.5);
    expect(alphaOf(dots, 'lightColor')).toBeCloseTo(0.82 * 0.25 * 0.5);
  });

  it('counts a chunk ready only once its surface and every mask primitive are', () => {
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    layer.addChunk(
      { ...triangleSurfaceBuffers(1), indices: new Uint16Array(0) },
      maskedSupport(1),
    );

    markReady([childAt(layer, 0, 0)]);
    expect(layer.readyChunkCount()).toBe(0);
    markReady([childAt(layer, 1, 0)]);
    expect(layer.readyChunkCount()).toBe(0);
    markReady([childAt(layer, 1, 1)]);
    expect(layer.readyChunkCount()).toBe(1);
    // A chunk with no supported cells is ready once its mask is.
    markReady([childAt(layer, 1, 2), childAt(layer, 1, 3)]);
    expect(layer.readyChunkCount()).toBe(2);
  });

  it('builds a chunk added after an elevation change at the current factor', () => {
    const layer = group();
    layer.setElevationFactor(2.5);
    layer.addChunk(triangleSurfaceBuffers(0), emptySupport(0));

    expect(
      (childAt(layer, 0, 0).appearance as ElevatedSurfaceAppearance).uniforms
        .u_elevationFactor,
    ).toBe(2.5);
  });

  it('hides the mask per primitive, including chunks added while it is hidden', () => {
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    layer.setVisibility(true, false);
    layer.addChunk(triangleSurfaceBuffers(1), maskedSupport(1));

    expect((layer.collection.get(1) as PrimitiveCollection).show).toBe(true);
    expect(childrenOf(layer, 1).map((primitive) => primitive.show)).toEqual([
      false,
      false,
      false,
      false,
    ]);
    expect(childrenOf(layer, 0).map((primitive) => primitive.show)).toEqual([
      true,
      true,
    ]);
    expect(layer.edges.collection.show).toBe(true);

    layer.setVisibility(true, true);
    expect(childrenOf(layer, 1).map((primitive) => primitive.show)).toEqual([
      true,
      true,
      true,
      true,
    ]);
  });

  it('gamma-corrects and closes extruded chunks', () => {
    const layer = group('extruded');
    layer.addChunk(triangleSurfaceBuffers(0), emptySupport(0));
    const appearance = childAt(layer, 0, 0)
      .appearance as ElevatedSurfaceAppearance;

    expect(appearance.uniforms.u_vertexColorGamma).toBe(1);
    expect(appearance.closed).toBe(true);
  });

  it('refuses a mask from another chunk before adding anything', () => {
    const layer = group();

    expect(() =>
      layer.addChunk(triangleSurfaceBuffers(3), maskedSupport(4)),
    ).toThrow('surface chunk 3 cannot take the mask of chunk 4');
    expect(layer.chunkCount()).toBe(0);
    expect(layer.totalCount()).toBe(0);
  });

  it('keeps raised chunks that Cesium re-bounds at the antimeridian out of culling', () => {
    expect(needsLongitudeSplit(triangleSurfaceBuffers(0).boundingSphere)).toBe(
      false,
    );
    expect(needsLongitudeSplit(seamSurfaceBuffers(1).boundingSphere)).toBe(
      true,
    );
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), emptySupport(0));
    layer.addChunk(seamSurfaceBuffers(1), maskedSupport(1));
    const culled = () =>
      childrenOf(layer, 0).map((primitive) => primitive.cull);

    // At rest Cesium's replacement sphere still bounds every drawn vertex.
    expect(culled()).toEqual([true, true]);
    layer.setElevationFactor(3);
    expect(culled()).toEqual([true, false]);
    layer.addChunk(seamSurfaceBuffers(2), emptySupport(2));
    expect(culled()).toEqual([true, false, false]);
    // Masks are never raised, so they keep culling.
    expect(childrenOf(layer, 1).map((primitive) => primitive.cull)).toEqual([
      true,
      true,
    ]);
    layer.setElevationFactor(0);
    expect(culled()).toEqual([true, true, true]);
  });

  it('keeps raised chunks out of culling off the globe, where the shader shears them', async () => {
    // In Columbus view Cesium culls against the ECEF sphere projected into the
    // map frame, which the sheared raised surface leaves; the pick and
    // translucent-depth passes then dropped chunks that were on screen.
    const layer = group();
    layer.addChunk(triangleSurfaceBuffers(0), maskedSupport(0));
    layer.addChunk(seamSurfaceBuffers(1), emptySupport(1));
    const culled = () =>
      childrenOf(layer, 0).map((primitive) => primitive.cull);

    await layer.setSceneMode('perspective');
    expect(culled(), 'at rest the bounds hold').toEqual([true, true]);
    layer.setElevationFactor(2);
    expect(culled()).toEqual([false, false]);
    layer.addChunk(triangleSurfaceBuffers(2), emptySupport(2));
    expect(culled()).toEqual([false, false, false]);
    expect(
      childrenOf(layer, 1).every((primitive) => primitive.cull),
      'masks are never raised',
    ).toBe(true);
    await layer.setSceneMode('globe');
    expect(culled()).toEqual([true, false, true]);
    await layer.setSceneMode('map');
    expect(culled()).toEqual([false, false, false]);
    layer.setElevationFactor(0);
    expect(culled()).toEqual([true, true, true]);
  });

  it('loses the raised extent only where Cesium splits at the antimeridian', () => {
    // scene3DOnly is false, so Primitive runs splitLongitude on every chunk;
    // past its early exit it re-bounds the geometry over the unraised positions.
    const splitLongitude = (
      GeometryPipeline as unknown as {
        splitLongitude(instance: GeometryInstance): GeometryInstance;
      }
    ).splitLongitude;
    for (const [buffers, splits] of [
      [triangleSurfaceBuffers(0), false],
      [seamSurfaceBuffers(1), true],
    ] as const) {
      const layer = group();
      layer.addChunk(buffers, emptySupport(buffers.chunk));
      const instance = childAt(layer, 0, 0)
        .geometryInstances as GeometryInstance;
      splitLongitude(instance);
      const sphere = instance.geometry.boundingSphere!;

      expect(
        raisedVertices(buffers).every(
          (vertex) =>
            Cartesian3.distance(vertex, sphere.center) <= sphere.radius,
        ),
        `chunk ${buffers.chunk}`,
      ).toBe(!splits);
    }
  });
});
