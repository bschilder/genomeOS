import { readFileSync } from 'node:fs';

import { cellToLatLng, gridDisk, latLngToCell } from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  naturalEarthHeights,
  parseNaturalEarth,
} from '../src/atlas/geometry/natural-earth';
import { heightForCell } from '../src/atlas/visual-encoding';
import { GOLDEN_DIR, surfaceFixturesIn } from './helpers/atlas-geometry';

const COLLECTION = {
  features: [
    {
      geometry: {
        coordinates: [
          [
            [0, 0],
            [10, 0],
            [10, 10],
            [0, 0],
          ],
          [
            [2, 2],
            [3, 2],
            [3, 3],
            [2, 2],
          ],
        ],
        type: 'Polygon',
      },
      properties: {
        LABEL_X: 10,
        LABEL_Y: 5,
        MIN_LABEL: 3,
        NAME_LONG: ' Alpha ',
      },
      type: 'Feature',
    },
    {
      geometry: {
        coordinates: [
          [
            [
              [20, 0],
              [21, 0],
              [21, 1],
              [20, 0],
            ],
          ],
          [
            [
              [22, 0],
              [23, 0],
              [23, 1],
              [22, 0],
            ],
          ],
        ],
        type: 'MultiPolygon',
      },
      properties: { ADMIN: 'Beta', LABEL_X: 20, LABEL_Y: 0 },
      type: 'Feature',
    },
    {
      geometry: {
        coordinates: [
          [
            [30, 0],
            [31, 0],
            [31, 1],
            [30, 0],
          ],
        ],
        type: 'Polygon',
      },
      properties: { LABEL_X: 30, LABEL_Y: 0, NAME: 'Alpha' },
      type: 'Feature',
    },
    {
      geometry: {
        coordinates: [
          [
            [40, 0],
            [41, 0],
            [41, 1],
            [40, 0],
          ],
        ],
        type: 'Polygon',
      },
      properties: { NAME_LONG: 'Gamma' },
      type: 'Feature',
    },
    {
      geometry: { coordinates: [], type: 'Polygon' },
      properties: { LABEL_X: 50, LABEL_Y: 0, NAME_LONG: 'Delta' },
      type: 'Feature',
    },
  ],
  type: 'FeatureCollection',
};

describe('Natural Earth parsing in the worker (fast-load §B.6.9)', () => {
  it('draws outer rings closed on their first point and ignores holes', () => {
    const parsed = parseNaturalEarth(COLLECTION);
    expect(Array.from(parsed.ringOffsets)).toEqual([0, 5, 10, 15, 20, 25]);
    expect(Array.from(parsed.lonLat.subarray(0, 10))).toEqual([
      0, 0, 10, 0, 10, 10, 0, 0, 0, 0,
    ]);
    expect(Array.from(parsed.lonLat.subarray(10, 20))).toEqual([
      20, 0, 21, 0, 21, 1, 20, 0, 20, 0,
    ]);
  });

  it('labels each distinct country text once at LABEL_X/LABEL_Y', () => {
    expect(parseNaturalEarth(COLLECTION).labels).toEqual([
      { lat: 5, lon: 10, minLabel: 3, text: 'Alpha' },
      { lat: 0, lon: 20, minLabel: 7, text: 'Beta' },
    ]);
  });

  it('rejects data that is not a FeatureCollection of numeric rings', () => {
    expect(() => parseNaturalEarth({ type: 'Feature' })).toThrow(TypeError);
    expect(() =>
      parseNaturalEarth({
        features: [
          {
            geometry: {
              coordinates: [
                [
                  [0, 'x'],
                  [1, 1],
                ],
              ],
              type: 'Polygon',
            },
            type: 'Feature',
          },
        ],
        type: 'FeatureCollection',
      }),
    ).toThrow('non-numeric position');
  });

  it('parses the committed Natural Earth borders', () => {
    const parsed = parseNaturalEarth(
      JSON.parse(
        readFileSync('public/data/atlas/ne-50m-admin-0.geojson', 'utf8'),
      ),
    );
    expect(parsed.ringOffsets.length - 1).toBe(1_620);
    expect(parsed.lonLat.length / 2).toBe(99_432 + 1_620);
    expect(new Set(parsed.labels.map(({ text }) => text)).size).toBe(
      parsed.labels.length,
    );
  });

  it('raises borders to the tallest supported neighbour like the legacy overlay', () => {
    const [fixture] = surfaceFixturesIn(GOLDEN_DIR);
    const metric = 'post_mean';
    const domain = fixture.artifact.metric_domains[metric];
    const points: number[] = [];
    for (const cell of fixture.cells) {
      const [lat, lon] = cellToLatLng(cell.h3_index);
      points.push(lon, lat, lon + 0.3, lat - 0.2);
    }
    const lonLat = Float64Array.from(points);
    const { borderHeights } = naturalEarthHeights(
      { labels: [], lonLat },
      {
        domain,
        grid: fixture.grid,
        support: fixture.support,
        values: fixture.post_mean,
      },
    );
    const cells = new Map(
      fixture.froundCells.map((cell) => [cell.h3_index, cell]),
    );
    for (let vertex = 0; vertex < lonLat.length / 2; vertex += 1) {
      const index = latLngToCell(
        lonLat[vertex * 2 + 1],
        lonLat[vertex * 2],
        fixture.grid.resolution,
      );
      let expected = 0;
      for (const candidate of gridDisk(index, 1)) {
        const cell = cells.get(candidate);
        if (cell)
          expected = Math.max(expected, heightForCell(cell, domain, 1, metric));
      }
      expect(borderHeights[vertex]).toBe(Math.fround(expected));
    }
  });
});
