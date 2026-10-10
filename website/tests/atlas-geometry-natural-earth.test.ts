import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { cellToLatLng, gridDisk, latLngToCell } from 'h3-js';
import { describe, expect, it } from 'vitest';

import {
  naturalEarthHeights,
  parseNaturalEarth,
  type NaturalEarthLabel,
} from '../src/atlas/geometry/natural-earth';
import { heightForCell } from '../src/atlas/visual-encoding';
import { GOLDEN_DIR, surfaceFixturesIn } from './helpers/atlas-geometry';

const COMMITTED_BORDERS = fileURLToPath(
  new URL('../public/data/atlas/ne-50m-admin-0.geojson', import.meta.url),
);

const SQUARE = [
  [0, 0],
  [1, 0],
  [1, 1],
  [0, 0],
];

function featureCollection(...features: unknown[]) {
  return { features, type: 'FeatureCollection' };
}

function polygonFeature(coordinates: unknown, properties: unknown = null) {
  return {
    geometry: { coordinates, type: 'Polygon' },
    properties,
    type: 'Feature',
  };
}

/** Each malformed shape, the feature it sits in, and the error it must raise. */
const MALFORMED: [string, unknown, string][] = [
  ['a null feature', null, 'feature 0 is not a GeoJSON Feature'],
  [
    'a feature without type Feature',
    { geometry: null, properties: null, type: 'Polygon' },
    'feature 0 is not a GeoJSON Feature',
  ],
  [
    'a missing geometry',
    { properties: null, type: 'Feature' },
    'feature 0 geometry must be a GeoJSON geometry or null',
  ],
  [
    'an unsupported geometry type',
    {
      geometry: { coordinates: SQUARE, type: 'LineString' },
      properties: null,
      type: 'Feature',
    },
    'feature 0 has unsupported geometry type "LineString"',
  ],
  [
    'MultiPolygon coordinates of null',
    {
      geometry: { coordinates: null, type: 'MultiPolygon' },
      properties: null,
      type: 'Feature',
    },
    'feature 0 MultiPolygon coordinates are not an array',
  ],
  [
    'a MultiPolygon polygon that is not an array',
    {
      geometry: { coordinates: [[SQUARE], 7], type: 'MultiPolygon' },
      properties: null,
      type: 'Feature',
    },
    'feature 0 MultiPolygon polygon 1 coordinates are not an array',
  ],
  [
    'Polygon coordinates of null',
    polygonFeature(null),
    'feature 0 Polygon coordinates are not an array',
  ],
  [
    'a ring that is not an array',
    polygonFeature([SQUARE, 'ring']),
    'feature 0 Polygon ring 1 is not an array',
  ],
  [
    'a non-numeric position in a hole',
    polygonFeature([
      SQUARE,
      [
        [0, 0],
        [0, null],
        [1, 1],
        [0, 0],
      ],
    ]),
    'feature 0 Polygon ring 1 has a non-numeric position',
  ],
  [
    'a position with one coordinate',
    polygonFeature([[[0], [1, 0], [1, 1], [0]]]),
    'feature 0 Polygon ring 0 has a non-numeric position',
  ],
  [
    'an empty outer ring',
    polygonFeature([[]]),
    'feature 0 Polygon ring 0 has fewer than four positions',
  ],
  [
    'a ring of three positions',
    polygonFeature([
      [
        [0, 0],
        [1, 0],
        [0, 0],
      ],
    ]),
    'feature 0 Polygon ring 0 has fewer than four positions',
  ],
  [
    'a ring that is not closed',
    polygonFeature([
      [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ],
    ]),
    'feature 0 Polygon ring 0 is not closed',
  ],
  [
    'properties that are not an object',
    polygonFeature([SQUARE], 'Alpha'),
    'feature 0 properties must be an object or null',
  ],
];

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

  it.each(MALFORMED)(
    'refuses %s with a TypeError instead of skipping it',
    (_name, feature, message) => {
      const parse = () => parseNaturalEarth(featureCollection(feature));
      expect(parse).toThrow(TypeError);
      expect(parse).toThrow(`Natural Earth ${message}`);
    },
  );

  it('names the malformed feature by its index', () => {
    expect(() =>
      parseNaturalEarth(
        featureCollection(polygonFeature([SQUARE]), polygonFeature([[]])),
      ),
    ).toThrow('Natural Earth feature 1 Polygon ring 0 has fewer than four');
  });

  it('labels an unlocated feature and draws nothing for empty geometries', () => {
    const parsed = parseNaturalEarth(
      featureCollection(
        {
          geometry: null,
          properties: { LABEL_X: 4, LABEL_Y: 2, NAME: 'Unlocated' },
          type: 'Feature',
        },
        {
          geometry: { coordinates: [], type: 'MultiPolygon' },
          properties: { LABEL_X: 5, LABEL_Y: 3, NAME: 'Empty multi' },
          type: 'Feature',
        },
        {
          geometry: { coordinates: [[], [SQUARE]], type: 'MultiPolygon' },
          properties: { LABEL_X: 6, LABEL_Y: 4, NAME: 'Partly empty' },
          type: 'Feature',
        },
        { geometry: null, properties: null, type: 'Feature' },
        { geometry: null, type: 'Feature' },
      ),
    );
    expect(Array.from(parsed.ringOffsets)).toEqual([0, 5]);
    expect(parsed.labels).toEqual([
      { lat: 2, lon: 4, minLabel: 7, text: 'Unlocated' },
      { lat: 4, lon: 6, minLabel: 7, text: 'Partly empty' },
    ]);
  });

  it('parses the committed Natural Earth borders', () => {
    const parsed = parseNaturalEarth(
      JSON.parse(readFileSync(COMMITTED_BORDERS, 'utf8')),
    );
    expect(parsed.ringOffsets.length - 1).toBe(1_620);
    expect(parsed.lonLat.length / 2).toBe(99_432 + 1_620);
    // 242 features, each with its own country text and a label point.
    expect(parsed.labels).toHaveLength(242);
    expect(new Set(parsed.labels.map(({ text }) => text)).size).toBe(242);
  });

  it('raises borders and labels to the tallest supported neighbour like the legacy overlay', () => {
    const [fixture] = surfaceFixturesIn(GOLDEN_DIR);
    const metric = 'post_mean';
    const domain = fixture.artifact.metric_domains[metric];
    const points: number[] = [];
    const labels: NaturalEarthLabel[] = [];
    fixture.cells.forEach((cell, index) => {
      const [lat, lon] = cellToLatLng(cell.h3_index);
      points.push(lon, lat, lon + 0.3, lat - 0.2);
      // Off the border vertices, so the labels' own lat/lon must be read.
      labels.push({
        lat: lat + 0.15,
        lon: lon - 0.25,
        minLabel: 7,
        text: `label ${index}`,
      });
    });
    const lonLat = Float64Array.from(points);
    const { borderHeights, labelHeights } = naturalEarthHeights(
      { labels, lonLat },
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
    const legacyHeight = (lat: number, lon: number) => {
      let height = 0;
      for (const candidate of gridDisk(
        latLngToCell(lat, lon, fixture.grid.resolution),
        1,
      )) {
        const cell = cells.get(candidate);
        if (cell)
          height = Math.max(height, heightForCell(cell, domain, 1, metric));
      }
      return Math.fround(height);
    };
    expect(borderHeights).toHaveLength(lonLat.length / 2);
    for (let vertex = 0; vertex < lonLat.length / 2; vertex += 1)
      expect(borderHeights[vertex]).toBe(
        legacyHeight(lonLat[vertex * 2 + 1], lonLat[vertex * 2]),
      );
    expect(labelHeights).toHaveLength(labels.length);
    labels.forEach(({ lat, lon }, index) =>
      expect(labelHeights[index]).toBe(legacyHeight(lat, lon)),
    );
    expect(labelHeights.some((height) => height > 0)).toBe(true);
  });
});
