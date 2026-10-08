import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Cartesian3,
  DeveloperError,
  PolylineCollection,
  PrimitiveCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  BORDER_CLEARANCE_METRES,
  ContextOverlay,
} from '../src/atlas/scene/context-overlay';
import { countryLabelHeight } from '../src/atlas/scene/geographic-overlay';
import type { ContextHeights } from '../src/atlas/worker/protocol';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';
import { flushTasks } from './helpers/scene-fakes';

const parsed = {
  labels: [{ lat: 47, lon: 2, minLabel: 2, text: 'France' }],
  lonLat: Float64Array.of(0, 0, 1, 0, 1, 1, 10, 10, 11, 10, 11, 11),
  ringOffsets: Uint32Array.of(0, 3, 6),
};

interface SetupOptions {
  context?: typeof parsed;
  /** Resolves the worker's heights; by default 1,000 m under every vertex and 500 m under every label. */
  heights?: () => Promise<ContextHeights>;
  now?: () => number;
  slice?: { sliceMs?: number; yieldFn: () => Promise<void> };
}

function setup(
  fetchBytes = async () => new ArrayBuffer(8),
  config: SetupOptions = {},
) {
  const context = config.context ?? parsed;
  const added: { position: Cartesian3; text: string }[] = [];
  const labels = {
    add(options: { position: Cartesian3; text: string }) {
      const label = { position: options.position, text: options.text };
      added.push(label);
      return label;
    },
    destroy() {},
    show: true,
  };
  let contextParsed = false;
  const worker = {
    // Like the data worker, which computes heights from the context it has parsed.
    contextHeights: vi.fn(async (): Promise<ContextHeights> => {
      if (!contextParsed)
        throw new Error('Natural Earth context is not parsed');
      if (config.heights) return config.heights();
      return {
        borderHeights: Float32Array.from(
          { length: context.lonLat.length / 2 },
          () => 1_000,
        ),
        labelHeights: Float32Array.from(context.labels, () => 500),
      };
    }),
    parseContext: vi.fn(async () => {
      contextParsed = true;
      return context;
    }),
  };
  const primitives = new PrimitiveCollection();
  const scene = {
    primitives,
    // A destroyed Cesium Scene throws here too; Viewer.destroy() destroys the primitives with it.
    requestRender: vi.fn(() => {
      if (primitives.isDestroyed())
        throw new DeveloperError('This object was destroyed');
    }),
  };
  const addCredit = vi.fn();
  const overlay = new ContextOverlay({
    addCredit,
    createLabels: () => labels as never,
    fetchBytes,
    now: config.now,
    scene,
    slice: config.slice ?? { yieldFn: () => Promise.resolve() },
    worker: worker as never,
  });
  return { added, addCredit, overlay, scene, worker };
}

function bufferOf(overlay: ContextOverlay): BufferPolylineCollection {
  for (let index = 0; index < overlay.collection.length; index += 1) {
    const child: unknown = overlay.collection.get(index);
    if (child instanceof BufferPolylineCollection) return child;
  }
  throw new Error('no border buffer');
}

function vertex(buffer: BufferPolylineCollection, ring: number): Cartesian3 {
  const line = new BufferPolyline();
  buffer.get(ring, line);
  const [x, y, z] = (line.toJSON() as { positions: number[] }).positions;
  return new Cartesian3(x, y, z);
}

function expectNear(actual: Cartesian3, expected: Cartesian3): void {
  expect(Cartesian3.distance(actual, expected)).toBeLessThan(1e-6);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Natural Earth context overlay', () => {
  it('draws worker rings and labels without touching surface heights at elevation 0', async () => {
    const { added, addCredit, overlay, scene, worker } = setup();

    await expect(
      overlay.load('/data/atlas/ne-50m-admin-0.geojson'),
    ).resolves.toBe('ready');

    expect(scene.primitives.contains(overlay.collection)).toBe(true);
    const buffer = bufferOf(overlay);
    expect(buffer.primitiveCount).toBe(2);
    expectNear(
      vertex(buffer, 0),
      Cartesian3.fromDegrees(0, 0, BORDER_CLEARANCE_METRES),
    );
    expectNear(
      vertex(buffer, 1),
      Cartesian3.fromDegrees(10, 10, BORDER_CLEARANCE_METRES),
    );
    expect(added.map(({ text }) => text)).toEqual(['France']);
    expectNear(
      added[0].position,
      Cartesian3.fromDegrees(2, 47, countryLabelHeight(0, 0)),
    );
    expect(addCredit).toHaveBeenCalledTimes(1);
    expect(addCredit.mock.calls[0][0].html).toContain('Natural Earth');
    expect(worker.contextHeights).not.toHaveBeenCalled();
    expect(overlay.isReady()).toBe(true);
  });

  it('loads once however often it is asked', async () => {
    const { overlay, worker } = setup();
    await Promise.all([overlay.load('/a.geojson'), overlay.load('/a.geojson')]);
    expect(worker.parseContext).toHaveBeenCalledTimes(1);
  });

  it('asks the worker for surface heights only on the first non-zero factor', async () => {
    const { added, overlay, worker } = setup();
    await overlay.load('/a.geojson');
    overlay.setSurface('hbs-rs334:v3:map-2026-08', 'post_mean');
    overlay.setElevationFactor(0, true);
    expect(worker.contextHeights).not.toHaveBeenCalled();

    overlay.setElevationFactor(2, true);
    expect(worker.contextHeights).toHaveBeenCalledWith({
      artifactKey: 'hbs-rs334:v3:map-2026-08',
      metric: 'post_mean',
    });
    await flushTasks();

    expectNear(
      vertex(bufferOf(overlay), 0),
      Cartesian3.fromDegrees(0, 0, 1_000 * 2 + BORDER_CLEARANCE_METRES),
    );
    expectNear(
      added[0].position,
      Cartesian3.fromDegrees(2, 47, countryLabelHeight(500, 2)),
    );
    overlay.setElevationFactor(3, true);
    expect(worker.contextHeights).toHaveBeenCalledTimes(1);
  });

  it('falls back quietly when the borders cannot be fetched', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { addCredit, overlay } = setup(async () => {
      throw new Error('offline');
    });
    await expect(overlay.load('/a.geojson')).resolves.toBe('fallback');
    expect(addCredit).not.toHaveBeenCalled();
    expect(overlay.isReady()).toBe(false);
  });

  it('applies visibility and border style to the drawn rings', async () => {
    const { overlay } = setup();
    await overlay.load('/a.geojson');
    overlay.setVisible(false);
    expect(overlay.collection.show).toBe(false);

    overlay.setBorderStyle('#ff0000', 0.25);
    const line = new BufferPolyline();
    const material = new BufferPolylineMaterial();
    bufferOf(overlay).get(1, line);
    line.getMaterial(material);
    expect(material.color.red).toBeCloseTo(1, 2);
    expect(material.color.alpha).toBeCloseTo(0.25, 2);
    expect(material.width).toBeCloseTo(1.65, 2);
  });

  it('switches to projected borders in the 2D map', async () => {
    stubCesiumBrowserImageTypes();
    const { overlay } = setup();
    await overlay.load('/a.geojson');
    await overlay.setSceneMode('map');

    const projected = [...Array(overlay.collection.length).keys()]
      .map((index) => overlay.collection.get(index) as unknown)
      .find(
        (child): child is PolylineCollection =>
          child instanceof PolylineCollection,
      );
    expect(projected?.length).toBe(2);
    expect(projected?.show).toBe(true);
    expect(bufferOf(overlay).show).toBe(false);
  });
});

const COUNTRIES = {
  labels: [
    { lat: 47, lon: 2, minLabel: 2, text: 'France' },
    { lat: 40, lon: -4, minLabel: 2, text: 'Spain' },
    { lat: 42, lon: 12, minLabel: 2, text: 'Italy' },
  ],
  // One triangle per country, with its corner at (c, c), (c + 1, c) and (c + 1, c + 1).
  lonLat: Float64Array.from(
    [0, 10, 20].flatMap((c) => [c, c, c + 1, c, c + 1, c + 1]),
  ),
  ringOffsets: Uint32Array.of(0, 3, 6, 9),
};
const SURFACE = 'hbs-rs334:v3:map-2026-08';
const RAISED = 1_000 * 2 + BORDER_CLEARANCE_METRES;

/** One item per slice, so every build of two or more items yields between them. `atYield(when, action)`
 * runs `action` at the first yield at which `when()` holds, while borders or labels are being added. */
function slicedLoad() {
  const hooks: { action: () => void; when: () => boolean }[] = [];
  return {
    atYield(when: () => boolean, action: () => void) {
      hooks.push({ action, when });
    },
    slice: {
      sliceMs: 0,
      yieldFn: async () => {
        const index = hooks.findIndex(({ when }) => when());
        if (index >= 0) hooks.splice(index, 1)[0].action();
      },
    },
  };
}

function childOf<T>(
  overlay: ContextOverlay,
  type: abstract new (...args: never[]) => T,
): T | undefined {
  for (let index = 0; index < overlay.collection.length; index += 1) {
    const child: unknown = overlay.collection.get(index);
    if (child instanceof type) return child;
  }
  return undefined;
}

const projectedOf = (overlay: ContextOverlay) =>
  childOf(overlay, PolylineCollection);
const bufferRingCount = (overlay: ContextOverlay): number =>
  childOf(overlay, BufferPolylineCollection)?.primitiveCount ?? 0;
const projectedRingCount = (overlay: ContextOverlay): number =>
  projectedOf(overlay)?.length ?? 0;

function bufferRings(overlay: ContextOverlay): Cartesian3[][] {
  const buffer = bufferOf(overlay);
  const line = new BufferPolyline();
  return Array.from({ length: buffer.primitiveCount }, (_, ring) => {
    buffer.get(ring, line);
    const values = (line.toJSON() as { positions: number[] }).positions;
    return Array.from(
      { length: values.length / 3 },
      (_, vertex) =>
        new Cartesian3(
          values[vertex * 3],
          values[vertex * 3 + 1],
          values[vertex * 3 + 2],
        ),
    );
  });
}

function projectedRings(overlay: ContextOverlay): Cartesian3[][] {
  const projected = projectedOf(overlay)!;
  return Array.from(
    { length: projected.length },
    (_, ring) => projected.get(ring).positions,
  );
}

/** Every vertex of every COUNTRIES ring sits `height` metres above the ellipsoid. */
function expectRingsAt(rings: Cartesian3[][], height: number): void {
  const { lonLat, ringOffsets } = COUNTRIES;
  expect(rings).toHaveLength(ringOffsets.length - 1);
  rings.forEach((ring, index) => {
    expect(ring).toHaveLength(ringOffsets[index + 1] - ringOffsets[index]);
    ring.forEach((position, offset) => {
      const vertex = ringOffsets[index] + offset;
      expectNear(
        position,
        Cartesian3.fromDegrees(
          lonLat[vertex * 2],
          lonLat[vertex * 2 + 1],
          height,
        ),
      );
    });
  });
}

function expectLabelsAt(
  added: { position: Cartesian3 }[],
  surfaceHeight: number,
  factor: number,
): void {
  expect(added).toHaveLength(COUNTRIES.labels.length);
  added.forEach(({ position }, index) => {
    const { lat, lon } = COUNTRIES.labels[index];
    expectNear(
      position,
      Cartesian3.fromDegrees(
        lon,
        lat,
        countryLabelHeight(surfaceHeight, factor),
      ),
    );
  });
}

describe('Natural Earth context built across several slices', () => {
  it('releases projected borders that share a material when the scene is torn down', async () => {
    stubCesiumBrowserImageTypes();
    const { overlay, scene, worker } = setup(undefined, { context: COUNTRIES });
    await overlay.load('/a.geojson');
    await overlay.setSceneMode('map');
    const projected = projectedOf(overlay)!;
    expect(projected.length).toBe(3);
    expect(projected.get(2).material).toBe(projected.get(0).material);

    expect(() => scene.primitives.destroy()).not.toThrow();
    expect(overlay.collection.isDestroyed()).toBe(true);

    // Calls that reach a torn-down overlay change nothing and do not throw.
    overlay.setVisible(false);
    overlay.setBorderStyle('#ff0000', 0.25);
    overlay.setSurface(SURFACE, 'post_mean');
    overlay.setElevationFactor(2, true);
    await expect(overlay.setSceneMode('globe')).resolves.toBeUndefined();
    expect(worker.contextHeights).not.toHaveBeenCalled();
  });

  it.each(['borders', 'labels'] as const)(
    'shows projected borders when the view switches to map while the %s are added',
    async (phase) => {
      stubCesiumBrowserImageTypes();
      const { atYield, slice } = slicedLoad();
      const { added, overlay } = setup(undefined, {
        context: COUNTRIES,
        slice,
      });
      atYield(
        phase === 'borders'
          ? () => bufferRingCount(overlay) > 0
          : () => added.length > 0,
        () => void overlay.setSceneMode('map'),
      );

      await expect(overlay.load('/a.geojson')).resolves.toBe('ready');

      expect(projectedOf(overlay)?.length).toBe(3);
      expect(projectedOf(overlay)?.show).toBe(true);
      expect(bufferOf(overlay).show).toBe(false);
      expect(added).toHaveLength(3);
    },
  );

  it('shows the renderer of the last view when two switches overlap', async () => {
    stubCesiumBrowserImageTypes();
    const { atYield, slice } = slicedLoad();
    const { overlay } = setup(undefined, { context: COUNTRIES, slice });
    await overlay.load('/a.geojson');
    let back: Promise<void> | undefined;
    atYield(
      () => projectedRingCount(overlay) > 0,
      () => {
        back = overlay.setSceneMode('globe');
      },
    );

    await overlay.setSceneMode('map');
    await back;

    expect(back).toBeDefined();
    expect(projectedOf(overlay)?.length).toBe(3);
    expect(bufferOf(overlay).show).toBe(true);
    expect(projectedOf(overlay)?.show).toBe(false);
  });

  it('asks for surface heights once the worker has parsed the context', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { added, overlay, worker } = setup(undefined, { context: COUNTRIES });
    overlay.setSurface(SURFACE, 'post_mean');
    overlay.setElevationFactor(2, true);
    expect(worker.contextHeights).not.toHaveBeenCalled();

    await expect(overlay.load('/a.geojson')).resolves.toBe('ready');
    await flushTasks();

    expect(worker.contextHeights).toHaveBeenCalledTimes(1);
    expect(worker.contextHeights).toHaveBeenCalledWith({
      artifactKey: SURFACE,
      metric: 'post_mean',
    });
    expect(console.warn).not.toHaveBeenCalled();
    expectRingsAt(bufferRings(overlay), RAISED);
    expectLabelsAt(added, 500, 2);
  });

  it.each(['globe', 'map'] as const)(
    'raises every %s border and label when surface heights arrive during the load',
    async (mode) => {
      stubCesiumBrowserImageTypes();
      const { atYield, slice } = slicedLoad();
      let release = () => {};
      const arrived = new Promise<void>((resolve) => {
        release = resolve;
      });
      const { added, overlay } = setup(undefined, {
        context: COUNTRIES,
        heights: async () => {
          await arrived;
          return {
            borderHeights: new Float32Array(9).fill(1_000),
            labelHeights: new Float32Array(3).fill(500),
          };
        },
        slice,
      });
      await overlay.setSceneMode(mode);
      overlay.setSurface(SURFACE, 'post_mean');
      overlay.setElevationFactor(2, true);
      atYield(
        () => bufferRingCount(overlay) + projectedRingCount(overlay) > 0,
        release,
      );

      await expect(overlay.load('/a.geojson')).resolves.toBe('ready');

      expectRingsAt(
        mode === 'globe' ? bufferRings(overlay) : projectedRings(overlay),
        RAISED,
      );
      expectLabelsAt(added, 500, 2);
    },
  );

  it('raises every projected ring when the elevation changes while they are added', async () => {
    stubCesiumBrowserImageTypes();
    const { atYield, slice } = slicedLoad();
    const { overlay } = setup(undefined, { context: COUNTRIES, slice });
    await overlay.load('/a.geojson');
    overlay.setSurface(SURFACE, 'post_mean');
    overlay.setElevationFactor(2, true);
    await flushTasks();
    overlay.setElevationFactor(0, true);
    atYield(
      () => projectedRingCount(overlay) > 0,
      () => overlay.setElevationFactor(2, true),
    );

    await overlay.setSceneMode('map');

    expectRingsAt(projectedRings(overlay), RAISED);
    expectRingsAt(bufferRings(overlay), RAISED);
  });

  it('keeps one height when a throttled elevation change lands while projected rings are added', async () => {
    stubCesiumBrowserImageTypes();
    const { atYield, slice } = slicedLoad();
    const { overlay } = setup(undefined, {
      context: COUNTRIES,
      now: () => 0,
      slice,
    });
    await overlay.load('/a.geojson');
    overlay.setSurface(SURFACE, 'post_mean');
    overlay.setElevationFactor(1, true);
    await flushTasks();
    // Within the 50 ms throttle: recorded, not yet drawn.
    atYield(
      () => projectedRingCount(overlay) > 0,
      () => overlay.setElevationFactor(2),
    );

    await overlay.setSceneMode('map');
    expectRingsAt(projectedRings(overlay), 1_000 + BORDER_CLEARANCE_METRES);

    overlay.setElevationFactor(2, true);
    expectRingsAt(projectedRings(overlay), RAISED);
    expectRingsAt(bufferRings(overlay), RAISED);
  });

  it.each([
    ['an elevation change', true, 2],
    ['a throttled elevation change', false, 1],
  ] as const)(
    'keeps the labels at one height when %s lands while they are added',
    async (_, force, factor) => {
      const { atYield, slice } = slicedLoad();
      const { added, overlay } = setup(undefined, {
        context: COUNTRIES,
        now: () => 0,
        slice,
      });
      overlay.setSurface(SURFACE, 'post_mean');
      overlay.setElevationFactor(1, true);
      // Opens the 50 ms throttle window once the borders are drawn.
      atYield(
        () => bufferRingCount(overlay) > 0,
        () => overlay.setElevationFactor(1, true),
      );
      atYield(
        () => added.length === 1,
        () => overlay.setElevationFactor(2, force),
      );
      let midLoad: Cartesian3[] = [];
      atYield(
        () => added.length === 2,
        () => {
          midLoad = added.map(({ position }) => position);
        },
      );

      await expect(overlay.load('/a.geojson')).resolves.toBe('ready');

      expect(midLoad).toHaveLength(2);
      midLoad.forEach((position, index) => {
        const { lat, lon } = COUNTRIES.labels[index];
        expectNear(
          position,
          Cartesian3.fromDegrees(lon, lat, countryLabelHeight(500, factor)),
        );
      });
      // The load ends by drawing everything at the current elevation.
      expectLabelsAt(added, 500, 2);
      expectRingsAt(bufferRings(overlay), RAISED);
    },
  );

  it('colours every ring with a border style set while the borders are added', async () => {
    const { atYield, slice } = slicedLoad();
    const { overlay } = setup(undefined, { context: COUNTRIES, slice });
    atYield(
      () => bufferRingCount(overlay) > 0,
      () => overlay.setBorderStyle('#ff0000', 0.25),
    );

    await overlay.load('/a.geojson');

    const buffer = bufferOf(overlay);
    const line = new BufferPolyline();
    const material = new BufferPolylineMaterial();
    expect(buffer.primitiveCount).toBe(3);
    for (let ring = 0; ring < buffer.primitiveCount; ring += 1) {
      buffer.get(ring, line);
      line.getMaterial(material);
      expect(material.color.red).toBeCloseTo(1, 2);
      expect(material.color.green).toBeCloseTo(0, 2);
      expect(material.color.alpha).toBeCloseTo(0.25, 2);
      expect(material.width).toBeCloseTo(1.65, 2);
    }
  });

  it('draws projected borders in the chosen style and restyles them', async () => {
    stubCesiumBrowserImageTypes();
    const { overlay } = setup(undefined, { context: COUNTRIES });
    await overlay.load('/a.geojson');
    overlay.setBorderStyle('#00ff00', 0.4);
    await overlay.setSceneMode('map');
    const projected = projectedOf(overlay)!;
    for (let ring = 0; ring < projected.length; ring += 1) {
      const line = projected.get(ring);
      expect(line.width).toBeCloseTo(1.65, 2);
      expect(line.material.uniforms.color.green).toBeCloseTo(1, 2);
      expect(line.material.uniforms.color.alpha).toBeCloseTo(0.4, 2);
    }

    overlay.setBorderStyle('#ff0000', 0.25);
    for (let ring = 0; ring < projected.length; ring += 1) {
      const { color } = projected.get(ring).material.uniforms;
      expect(color.red).toBeCloseTo(1, 2);
      expect(color.green).toBeCloseTo(0, 2);
      expect(color.alpha).toBeCloseTo(0.25, 2);
    }
  });

  it.each(['vertices', 'borders', 'labels'] as const)(
    'stops quietly at the next yield when the scene is torn down while the %s are prepared',
    async (phase) => {
      vi.spyOn(console, 'warn').mockImplementation(() => {});
      const { atYield, slice } = slicedLoad();
      const { added, overlay, scene } = setup(undefined, {
        context: COUNTRIES,
        slice,
      });
      let rendersAtTeardown = -1;
      atYield(
        {
          borders: () => bufferRingCount(overlay) > 0,
          labels: () => added.length > 0,
          vertices: () => true,
        }[phase],
        () => {
          scene.primitives.destroy();
          rendersAtTeardown = scene.requestRender.mock.calls.length;
        },
      );

      await expect(overlay.load('/a.geojson')).resolves.toBe('fallback');

      // No slice ran on the destroyed scene: a slice ends by requesting a render.
      expect(scene.requestRender).toHaveBeenCalledTimes(rendersAtTeardown);
      expect(console.warn).not.toHaveBeenCalled();
      expect(overlay.isReady()).toBe(false);
    },
  );

  it('stays quiet when the worker stops with a torn-down scene', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { addCredit, overlay, scene, worker } = setup(undefined, {
      context: COUNTRIES,
    });
    worker.parseContext.mockImplementationOnce(async () => {
      scene.primitives.destroy();
      throw new Error('Atlas data worker terminated');
    });

    await expect(overlay.load('/a.geojson')).resolves.toBe('fallback');

    expect(addCredit).not.toHaveBeenCalled();
    expect(console.warn).not.toHaveBeenCalled();
  });

  it.each(['arrive', 'fail'] as const)(
    'leaves a torn-down scene alone when pending surface heights %s',
    async (outcome) => {
      vi.spyOn(console, 'warn').mockImplementation(() => {});
      const { overlay, scene, worker } = setup(undefined, {
        context: COUNTRIES,
      });
      await overlay.load('/a.geojson');
      let settle: () => void = () => {};
      worker.contextHeights.mockImplementationOnce(
        () =>
          new Promise<ContextHeights>((resolve, reject) => {
            settle = () =>
              outcome === 'arrive'
                ? resolve({
                    borderHeights: new Float32Array(9).fill(1_000),
                    labelHeights: new Float32Array(3).fill(500),
                  })
                : reject(new Error('Atlas data worker terminated'));
          }),
      );
      overlay.setSurface(SURFACE, 'post_mean');
      overlay.setElevationFactor(2, true);
      expect(worker.contextHeights).toHaveBeenCalledTimes(1);

      scene.primitives.destroy();
      const rendersAtTeardown = scene.requestRender.mock.calls.length;
      settle();
      await flushTasks();

      expect(scene.requestRender).toHaveBeenCalledTimes(rendersAtTeardown);
      expect(console.warn).not.toHaveBeenCalled();
    },
  );
});
