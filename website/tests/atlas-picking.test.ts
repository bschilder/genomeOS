import {
  cellToLatLng,
  cellsToDirectedEdge,
  directedEdgeToBoundary,
  gridDisk,
  latLngToCell,
} from 'h3-js';
import { Cartesian2, Cartesian3, type PolylineCollection } from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HighlightLayer } from '../src/atlas/scene/highlight-layer';
import { observationPickId } from '../src/atlas/scene/observation-layer';
import { preferredAtlasPick, sameAtlasPick } from '../src/atlas/scene/picking';
import { SURFACE_CLEARANCE_METRES } from '../src/atlas/scene/surface-appearance';
import { surfaceChunkPickId } from '../src/atlas/scene/surface-chunk-layer';
import { columnarHeightSource } from '../src/atlas/scene/surface-heights';
import {
  createSurfacePickResolver,
  type SurfacePickContext,
} from '../src/atlas/scene/surface-pick';
import type { SurfacePick } from '../src/atlas/scene/types';
import { rowForH3 } from '../src/atlas/surface-columns';
import { heightFor } from '../src/atlas/visual-encoding';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';
import { columnarSurface } from './helpers/columnar-surface';

const CELL = '83754efffffffff';
const OTHER = 'g6pd-deficiency:v3:map-2026-08';
const surface = columnarSurface([
  { h3: CELL, post_mean: 0.5, post_sd: 0.1, support: 'observed' },
]);
const KEY = surface.artifactKey;
const [LAT, LON] = cellToLatLng(CELL);
const WINDOW = new Cartesian2(320, 240);

function context(
  factor: number,
  hidden: { show: boolean }[] = [],
): SurfacePickContext {
  return {
    factor: () => factor,
    geometry: () => 'triangles',
    metric: () => 'post_mean',
    target: () => ({ artifactKey: KEY, hidden, surface }),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('keyed pick arbitration', () => {
  it('drops other artifacts before choosing, so an incoming chunk never wins', () => {
    const picks = [
      { id: surfaceChunkPickId(OTHER, 1) },
      { id: surfaceChunkPickId(KEY, 4) },
    ];
    expect(preferredAtlasPick(picks, KEY)).toEqual(surfaceChunkPickId(KEY, 4));
    expect(preferredAtlasPick(picks, null)).toBeNull();
  });

  it('lets a displayed observation win and ignores an incoming observation', () => {
    const picks = [
      { id: surfaceChunkPickId(KEY, 4) },
      { id: observationPickId('map-surveys:1', OTHER) },
      { id: observationPickId('map-surveys:2', KEY) },
    ];
    expect(preferredAtlasPick(picks, KEY)).toEqual(
      observationPickId('map-surveys:2', KEY),
    );
  });

  it('keeps legacy arbitration when no displayed key is given', () => {
    const legacy = { h3Index: CELL, kind: 'surface' as const };
    expect(preferredAtlasPick([{ id: legacy }])).toEqual(legacy);
    expect(preferredAtlasPick([{ id: surfaceChunkPickId(KEY, 0) }])).toBeNull();
  });

  it('compares artifact and row when de-duplicating hover', () => {
    const first: SurfacePick = {
      artifactKey: KEY,
      h3Index: CELL,
      kind: 'surface',
      row: 0,
    };
    expect(sameAtlasPick(first, { ...first })).toBe(true);
    expect(sameAtlasPick(first, { ...first, artifactKey: OTHER })).toBe(false);
    // Row and cell each on their own, so neither clause hides behind the other.
    expect(sameAtlasPick(first, { ...first, row: 1 })).toBe(false);
    expect(sameAtlasPick(first, { ...first, h3Index: '83754bfffffffff' })).toBe(
      false,
    );
    expect(
      sameAtlasPick(
        observationPickId('map-surveys:1', KEY),
        observationPickId('map-surveys:1', OTHER),
      ),
    ).toBe(false);
  });
});

describe('surface-chunk cell resolution', () => {
  it('uses the ellipsoid at elevation 0 and never renders a depth pass', () => {
    const scene = {
      camera: { pickEllipsoid: vi.fn(() => Cartesian3.fromDegrees(LON, LAT)) },
      pickPosition: vi.fn(),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(scene as never, context(0));

    expect(resolve([{ id: surfaceChunkPickId(KEY, 0) }], WINDOW)).toEqual({
      artifactKey: KEY,
      h3Index: CELL,
      kind: 'surface',
      row: rowForH3(surface, CELL),
    });
    expect(scene.camera.pickEllipsoid).toHaveBeenCalledWith(
      WINDOW,
      expect.anything(),
    );
    expect(scene.pickPosition).not.toHaveBeenCalled();
    expect(scene.pickTranslucentDepth).toBe(false);
  });

  it('turns translucent depth on only around the depth pick and hides the incoming group', () => {
    const incoming = { show: true };
    const seen: { depth: boolean; incoming: boolean }[] = [];
    const scene = {
      camera: { pickEllipsoid: vi.fn() },
      pickPosition: vi.fn(() => {
        seen.push({
          depth: scene.pickTranslucentDepth,
          incoming: incoming.show,
        });
        return Cartesian3.fromDegrees(LON, LAT, 40_650);
      }),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(
      scene as never,
      context(2, [incoming]),
    );

    expect(resolve([{ id: surfaceChunkPickId(KEY, 0) }], WINDOW)).toMatchObject(
      {
        artifactKey: KEY,
        h3Index: CELL,
        kind: 'surface',
      },
    );
    expect(seen).toEqual([{ depth: true, incoming: false }]);
    expect(scene.pickTranslucentDepth).toBe(false);
    expect(incoming.show).toBe(true);
    expect(scene.camera.pickEllipsoid).not.toHaveBeenCalled();
  });

  it('keeps the translucent hit out of the camera pivot cache entry for the pointer', () => {
    // Cesium (@cesium/engine 26.3.0, Picking.js `pickPositionWorldCoordinates`)
    // caches `pickPosition` results by `windowPosition.toString()` alone,
    // whatever `pickTranslucentDepth` was, until the next `Scene.render`. The
    // next tick's camera controller picks its zoom pivot at the same pointer
    // position before that render.
    const surfaceTop = Cartesian3.fromDegrees(LON, LAT, 40_650);
    const globe = Cartesian3.fromDegrees(LON, LAT);
    const cache = new Map<string, Cartesian3>();
    const passes: boolean[] = [];
    const queried: Cartesian2[] = [];
    const scene = {
      camera: { pickEllipsoid: vi.fn() },
      pickPosition: vi.fn((position: Cartesian2) => {
        queried.push(position);
        const key = position.toString();
        let hit = cache.get(key);
        if (!hit) {
          passes.push(scene.pickTranslucentDepth);
          hit = scene.pickTranslucentDepth ? surfaceTop : globe;
          cache.set(key, hit);
        }
        return Cartesian3.clone(hit);
      }),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(scene as never, context(2));
    const hover = () =>
      resolve([{ id: surfaceChunkPickId(KEY, 0) }], WINDOW.clone());

    // Hover frame, after Cesium's tick: the translucent depth pick.
    expect(hover()).toMatchObject({ artifactKey: KEY, h3Index: CELL });
    // Next tick, before render: the controller's pivot is the globe point.
    expect(scene.pickPosition(WINDOW.clone())).toEqual(globe);
    expect(passes).toEqual([true, false]);
    // The depth pick reads the pointer's own pixel under a key of its own.
    expect(Cartesian2.equals(queried[0], WINDOW)).toBe(true);
    expect(queried[0].toString()).not.toBe(WINDOW.toString());

    // Render clears the cache. An opaque pivot entry cached at the pointer
    // never answers a translucent pick either.
    cache.clear();
    passes.length = 0;
    scene.pickPosition(WINDOW.clone());
    hover();
    expect(passes).toEqual([false, true]);
    expect(scene.pickTranslucentDepth).toBe(false);
  });

  it("misses the depth pick's entry in Cesium's own cache at the raw pointer", async () => {
    // Cesium's private Picking is exported at runtime but untyped. Running its
    // real cache lookup pins the keying the depth pick relies on.
    const { Picking } = (await import('cesium')) as unknown as {
      Picking: {
        prototype: {
          pickPositionWorldCoordinates(
            this: object,
            scene: object,
            position: Cartesian2,
          ): Cartesian3 | undefined;
        };
      };
    };
    const surfaceTop = Cartesian3.fromDegrees(LON, LAT, 40_650);
    const queried: Cartesian2[] = [];
    const resolve = createSurfacePickResolver(
      {
        camera: { pickEllipsoid: vi.fn() },
        pickPosition: (position: Cartesian2) => {
          queried.push(position);
          return surfaceTop;
        },
        pickTranslucentDepth: false,
      } as never,
      context(2),
    );
    resolve([{ id: surfaceChunkPickId(KEY, 0) }], WINDOW.clone());

    // The hover's translucent hit as Cesium stores it, and just enough scene
    // for an opaque depth read that finds no depth.
    const picking = {
      _pickPositionCache: { [queried[0].toString()]: surfaceTop },
      _pickPositionCacheDirty: false,
    };
    const scene = {
      camera: { frustum: { clone: () => ({}), fov: 1 } },
      canvas: { clientHeight: 480, clientWidth: 640 },
      context: {
        depthTexture: true,
        uniformState: { update() {}, updateFrustum() {} },
      },
      defaultView: { frustumCommandsList: [] },
      drawingBufferHeight: 480,
      drawingBufferWidth: 640,
      frameState: {},
      pickTranslucentDepth: false,
      updateEnvironment() {},
      updateFrameState() {},
      useDepthPicking: true,
    };
    const pickAt = (position: Cartesian2) =>
      Picking.prototype.pickPositionWorldCoordinates.call(
        picking,
        scene,
        position,
      );

    expect(pickAt(queried[0])).toEqual(surfaceTop);
    // The camera controller's pivot pick at the pointer reads depth afresh.
    expect(pickAt(WINDOW.clone())).toBeUndefined();
  });

  it('restores translucent depth even when the depth pick throws', () => {
    const scene = {
      camera: { pickEllipsoid: vi.fn() },
      pickPosition: vi.fn(() => {
        throw new Error('context lost');
      }),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(scene as never, context(2));
    expect(() => resolve([{ id: surfaceChunkPickId(KEY, 0) }], WINDOW)).toThrow(
      'context lost',
    );
    expect(scene.pickTranslucentDepth).toBe(false);
  });

  it('resolves cells only for chunk picks of the displayed artifact', () => {
    const scene = {
      camera: { pickEllipsoid: vi.fn() },
      pickPosition: vi.fn(),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(scene as never, context(0));

    expect(
      resolve([{ id: observationPickId('map-surveys:1', KEY) }], WINDOW),
    ).toEqual(observationPickId('map-surveys:1', KEY));
    expect(resolve([{ id: surfaceChunkPickId(OTHER, 0) }], WINDOW)).toBeNull();
    expect(resolve([{ id: 'context' }], WINDOW)).toBeNull();
    expect(scene.camera.pickEllipsoid).not.toHaveBeenCalled();
    expect(scene.pickPosition).not.toHaveBeenCalled();
  });

  it('resolves nothing while no artifact is pickable', () => {
    const scene = {
      camera: { pickEllipsoid: vi.fn() },
      pickPosition: vi.fn(),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(scene as never, {
      ...context(0),
      target: () => null,
    });
    expect(resolve([{ id: surfaceChunkPickId(KEY, 0) }], WINDOW)).toBeNull();
  });

  it('gives an extruded wall hit at exaggeration 5 to the taller cell', () => {
    // The resolver applies the factor to heights given at exaggeration 1, so
    // heights already raised by the factor would lift the short top above
    // this wall hit and hand it to the short cell.
    const [short] = gridDisk(CELL, 1).filter((h3) => h3 !== CELL);
    const disk = columnarSurface(
      gridDisk(CELL, 1).map((h3) => ({
        h3,
        post_mean: h3 === CELL ? 0.9 : 0.2,
        post_sd: 0.1,
        support: 'interpolated' as const,
      })),
    );
    // Over the short cell, 3% short of its edge with the tall one, halfway
    // between the two tops as drawn at factor 5.
    const [[firstLat, firstLon], [secondLat, secondLon]] =
      directedEdgeToBoundary(cellsToDirectedEdge(short, CELL));
    const [shortLat, shortLon] = cellToLatLng(short);
    const lat = shortLat + ((firstLat + secondLat) / 2 - shortLat) * 0.97;
    const lon = shortLon + ((firstLon + secondLon) / 2 - shortLon) * 0.97;
    expect(latLngToCell(lat, lon, 3), 'precondition').toBe(short);
    const altitude =
      (heightFor('interpolated', 0.2, [0, 1], 5) +
        heightFor('interpolated', 0.9, [0, 1], 5)) /
      2;
    const ground = Cartesian3.fromDegrees(lon, lat);
    const hit = Cartesian3.multiplyByScalar(
      ground,
      1 + (SURFACE_CLEARANCE_METRES + altitude) / Cartesian3.magnitude(ground),
      new Cartesian3(),
    );
    const scene = {
      camera: { pickEllipsoid: vi.fn() },
      pickPosition: vi.fn(() => hit),
      pickTranslucentDepth: false,
    };
    const resolve = createSurfacePickResolver(scene as never, {
      ...context(5),
      geometry: () => 'extruded',
      target: () => ({
        artifactKey: disk.artifactKey,
        hidden: [],
        surface: disk,
      }),
    });

    expect(
      resolve([{ id: surfaceChunkPickId(disk.artifactKey, 0) }], WINDOW),
    ).toEqual({
      artifactKey: disk.artifactKey,
      h3Index: CELL,
      kind: 'surface',
      row: rowForH3(disk, CELL),
    });
  });
});

describe('keyed selection highlight', () => {
  it('hides a selection that belongs to another artifact', () => {
    stubCesiumBrowserImageTypes();
    const layer = new HighlightLayer({ requestRender: vi.fn() } as never);
    layer.setArtifacts(
      columnarHeightSource(surface),
      null,
      'post_mean',
      false,
      0,
    );
    const lines = layer.collection.get(0) as PolylineCollection;

    layer.setSelection({
      artifactKey: OTHER,
      h3Index: CELL,
      kind: 'surface',
      row: 0,
    });
    expect(lines.get(1).show).toBe(false);
    layer.setSelection({
      artifactKey: KEY,
      h3Index: CELL,
      kind: 'surface',
      row: 0,
    });
    expect(lines.get(1).show).toBe(true);
  });
});
