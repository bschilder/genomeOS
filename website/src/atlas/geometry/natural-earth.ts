/** Natural Earth borders and country labels, parsed in the Atlas data worker
 * (fast-load spec 2026-10-07 §B.6.9).
 *
 * Reproduces what `GeoJsonDataSource` plus `GeographicOverlay.load` drew:
 * one ring per polygon outer boundary (holes are not drawn), closed by
 * repeating its first coordinate; one label per distinct country text at
 * LABEL_X/LABEL_Y, first occurrence wins. Context only, never science.
 */

import { gridDisk, latLngToCell } from 'h3-js';

import type { DecodedGrid } from '../gosa/types';
import { heightFor, type MetricDomain } from '../visual-encoding';
import { supportName } from './support-codes';
import { gridRowOf } from './topology';

export interface CountryProperties {
  ADMIN?: unknown;
  LABEL_X?: unknown;
  LABEL_Y?: unknown;
  MIN_LABEL?: unknown;
  NAME?: unknown;
  NAME_LONG?: unknown;
}

export interface NaturalEarthLabel {
  text: string;
  lon: number;
  lat: number;
  minLabel: number;
}

export interface NaturalEarthBuffers {
  ringOffsets: Uint32Array;
  /** Interleaved lon, lat in degrees. */
  lonLat: Float64Array;
  labels: NaturalEarthLabel[];
}

export function countryLabelText(properties: CountryProperties): string | null {
  for (const value of [properties.NAME_LONG, properties.ADMIN, properties.NAME])
    if (typeof value === 'string' && value.trim()) return value.trim();
  return null;
}

function isPosition(value: unknown): value is [number, number, ...number[]] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  );
}

function polygonsOf(geometry: unknown): unknown[][][] {
  if (!geometry || typeof geometry !== 'object') return [];
  const { type, coordinates } = geometry as {
    type?: unknown;
    coordinates?: unknown;
  };
  if (type === 'Polygon') return [coordinates as unknown[][]];
  if (type === 'MultiPolygon') return coordinates as unknown[][][];
  return [];
}

export function parseNaturalEarth(json: unknown): NaturalEarthBuffers {
  if (
    !json ||
    typeof json !== 'object' ||
    (json as { type?: unknown }).type !== 'FeatureCollection' ||
    !Array.isArray((json as { features?: unknown }).features)
  )
    throw new TypeError(
      'Natural Earth data must be a GeoJSON FeatureCollection',
    );
  const ringOffsets: number[] = [0];
  const lonLat: number[] = [];
  const labels: NaturalEarthLabel[] = [];
  const labelled = new Set<string>();
  for (const feature of (json as { features: unknown[] }).features) {
    const { geometry, properties } = (feature ?? {}) as {
      geometry?: unknown;
      properties?: CountryProperties | null;
    };
    for (const polygon of polygonsOf(geometry)) {
      if (!Array.isArray(polygon) || polygon.length === 0) continue;
      const outer = polygon[0];
      if (!Array.isArray(outer) || outer.length === 0) continue;
      if (!outer.every(isPosition))
        throw new TypeError('Natural Earth ring has a non-numeric position');
      if (outer.length > 1) {
        for (const [lon, lat] of [...outer, outer[0]]) lonLat.push(lon, lat);
        ringOffsets.push(lonLat.length / 2);
      }
      const text = properties ? countryLabelText(properties) : null;
      const lon = properties?.LABEL_X;
      const lat = properties?.LABEL_Y;
      if (
        !text ||
        labelled.has(text) ||
        typeof lon !== 'number' ||
        !Number.isFinite(lon) ||
        typeof lat !== 'number' ||
        !Number.isFinite(lat)
      )
        continue;
      labelled.add(text);
      labels.push({
        lat,
        lon,
        minLabel:
          typeof properties?.MIN_LABEL === 'number' ? properties.MIN_LABEL : 7,
        text,
      });
    }
  }
  return {
    labels,
    lonLat: Float64Array.from(lonLat),
    ringOffsets: Uint32Array.from(ringOffsets),
  };
}

export interface ContextSurface {
  grid: DecodedGrid;
  support: Uint8Array;
  values: Float32Array;
  domain: MetricDomain;
}

function supportedSurfaceHeight(
  lat: number,
  lon: number,
  surface: ContextSurface,
): number {
  const index = latLngToCell(lat, lon, surface.grid.resolution);
  let height = 0;
  for (const candidate of gridDisk(index, 1)) {
    const row = gridRowOf(surface.grid, candidate);
    if (row !== null)
      height = Math.max(
        height,
        heightFor(
          supportName(surface.support[row]),
          surface.values[row],
          surface.domain,
          1,
        ),
      );
  }
  return height;
}

/** Border and label heights at exaggeration 1 (legacy `#refreshSurfaceHeights`). */
export function naturalEarthHeights(
  buffers: Pick<NaturalEarthBuffers, 'lonLat' | 'labels'>,
  surface: ContextSurface,
): { borderHeights: Float32Array; labelHeights: Float32Array } {
  const borderHeights = new Float32Array(buffers.lonLat.length / 2);
  for (let vertex = 0; vertex < borderHeights.length; vertex += 1)
    borderHeights[vertex] = supportedSurfaceHeight(
      buffers.lonLat[vertex * 2 + 1],
      buffers.lonLat[vertex * 2],
      surface,
    );
  return {
    borderHeights,
    labelHeights: Float32Array.from(buffers.labels, (label) =>
      supportedSurfaceHeight(label.lat, label.lon, surface),
    ),
  };
}
