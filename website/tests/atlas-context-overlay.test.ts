import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Cartesian3,
  PolylineCollection,
  PrimitiveCollection,
} from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  BORDER_CLEARANCE_METRES,
  ContextOverlay,
} from '../src/atlas/scene/context-overlay';
import { countryLabelHeight } from '../src/atlas/scene/geographic-overlay';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';
import { flushTasks } from './helpers/scene-fakes';

const parsed = {
  labels: [{ lat: 47, lon: 2, minLabel: 2, text: 'France' }],
  lonLat: Float64Array.of(0, 0, 1, 0, 1, 1, 10, 10, 11, 10, 11, 11),
  ringOffsets: Uint32Array.of(0, 3, 6),
};

function setup(fetchBytes = async () => new ArrayBuffer(8)) {
  const added: { position: Cartesian3; text: string }[] = [];
  const labels = {
    add(options: { position: Cartesian3; text: string }) {
      const label = { position: options.position, text: options.text };
      added.push(label);
      return label;
    },
    show: true,
  };
  const worker = {
    contextHeights: vi.fn(async () => ({
      borderHeights: Float32Array.from({ length: 6 }, () => 1_000),
      labelHeights: Float32Array.of(500),
    })),
    parseContext: vi.fn(async () => parsed),
  };
  const scene = {
    primitives: new PrimitiveCollection(),
    requestRender: vi.fn(),
  };
  const addCredit = vi.fn();
  const overlay = new ContextOverlay({
    addCredit,
    createLabels: () => labels as never,
    fetchBytes,
    scene,
    slice: { yieldFn: () => Promise.resolve() },
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
