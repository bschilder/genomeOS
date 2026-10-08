import {
  Color,
  GeometryInstance,
  Primitive,
  PrimitiveCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { animateSwap, fadeTogether } from '../src/atlas/scene/scene-transition';
import {
  createSurfaceChunkGroup,
  surfaceChunkPickId,
} from '../src/atlas/scene/surface-chunk-layer';
import type { ElevatedSurfaceAppearance } from '../src/atlas/scene/surface-appearance';
import {
  emptySupport,
  maskedSupport,
  triangleSurfaceBuffers,
} from './helpers/chunk-buffers';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';

const KEY = 'hbs-rs334:v3:map-2026-08';

function group(geometry: 'triangles' | 'hexagons' = 'triangles') {
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
});
