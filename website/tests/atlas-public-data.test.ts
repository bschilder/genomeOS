import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  atlasCatalogSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
} from '../src/atlas/contracts';
import {
  decodeDetail,
  decodeGrid,
  decodeRender,
} from '../src/atlas/gosa/decode';
import { populatedPlaceCatalogSchema } from '../src/atlas/place-context';

const dataDirectory = fileURLToPath(
  new URL('../public/data/atlas/', import.meta.url),
);

const POPULATED_ISLAND_CELLS = {
  Azores: '84351b5ffffffff',
  'Cook Islands': '84b4c59ffffffff',
  Madeira: '843466bffffffff',
  Malta: '843f305ffffffff',
  Praia: '845494bffffffff',
  Tenerife: '84344cdffffffff',
} as const;

function readObject(key: string): { bytes: number; digest: string } {
  const bytes = readFileSync(`${dataDirectory}/${key}`);
  return {
    bytes: bytes.length,
    digest: createHash('sha256').update(bytes).digest('hex'),
  };
}

function readPayload(filename: string): {
  bytes: number;
  digest: string;
  value: unknown;
} {
  const bytes = readFileSync(`${dataDirectory}/${filename}`);
  return {
    bytes: bytes.length,
    digest: createHash('sha256').update(bytes).digest('hex'),
    value: JSON.parse(bytes.toString()),
  };
}

function readBuffer(key: string): ArrayBuffer {
  const bytes = readFileSync(`${dataDirectory}/${key}`);
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
}

/** SHA-256 of the little-endian u64 H3 column, as `encode_atlas_web.py` declares grids. */
function gridSha256(h3Indices: readonly string[]): string {
  const view = new DataView(new ArrayBuffer(h3Indices.length * 8));
  h3Indices.forEach((h3Index, row) =>
    view.setBigUint64(row * 8, BigInt(`0x${h3Index}`), true),
  );
  return createHash('sha256').update(new Uint8Array(view.buffer)).digest('hex');
}

describe('published Atlas data', () => {
  it('publishes validated public-domain city and region context', () => {
    const places = populatedPlaceCatalogSchema.parse(
      readPayload('ne-50m-populated-places.json').value,
    );
    expect(places.places.length).toBeGreaterThan(1_000);
    expect(places.places).toContainEqual(
      expect.objectContaining({
        country: 'Australia',
        name: 'Sydney',
        region: 'New South Wales',
      }),
    );
  });

  it('validates every allowlisted surface and measured-observation file', () => {
    const catalog = atlasCatalogSchema.parse(readPayload('catalog.json').value);

    expect(catalog.artifacts).toHaveLength(30);
    const [[sharedGridSha256, grid]] = Object.entries(catalog.grids);
    expect(readObject(grid.url)).toEqual({
      bytes: grid.bytes,
      digest: grid.sha256,
    });
    expect(grid.resolution).toBe(4);
    for (const reference of catalog.artifacts) {
      const surfacePayload = readPayload(reference.surface_url);
      const surface = surfaceArtifactSchema.parse(surfacePayload.value);
      expect(surfacePayload.digest, reference.id).toBe(
        reference.surface_sha256,
      );
      expect(surface.artifact.id, reference.id).toBe(reference.id);
      expect(surface.artifact.variant_id, reference.id).toBe(
        reference.variant_id,
      );
      expect(surface.artifact.resolution, reference.id).toBe(4);
      expect(surface.artifact.target_grid_source, reference.id).toBe(
        'worldpop-1km-unconstrained',
      );
      expect(surface.artifact.target_grid_version, reference.id).toContain(
        'Global_2000_2020/2020/0_Mosaicked',
      );
      expect(surface.cells, reference.id).toHaveLength(reference.n_cells);
      expect(reference.web.grid_sha256, reference.id).toBe(sharedGridSha256);
      expect(grid.n_cells, reference.id).toBe(reference.n_cells);
      expect(
        gridSha256(surface.cells.map((cell) => cell.h3_index)),
        `${reference.id}: surface h3 order equals the shared grid`,
      ).toBe(sharedGridSha256);
      for (const object of [reference.web.render, reference.web.detail])
        expect(readObject(object.url), object.url).toEqual({
          bytes: object.bytes,
          digest: object.sha256,
        });
      const surfaceCells = new Set(surface.cells.map((cell) => cell.h3_index));
      for (const [island, h3Index] of Object.entries(POPULATED_ISLAND_CELLS))
        expect(surfaceCells.has(h3Index), `${reference.id}: ${island}`).toBe(
          true,
        );

      expect(reference.observations_available, reference.id).toBe(true);
      expect(reference.observations_url, reference.id).not.toBeNull();
      expect(reference.observations_sha256, reference.id).not.toBeNull();
      const observationPayload = readPayload(reference.observations_url!);
      const observations = observationArtifactSchema.parse(
        observationPayload.value,
      );
      expect(observationPayload.digest, reference.id).toBe(
        reference.observations_sha256,
      );
      expect(observations.artifact.id, reference.id).toBe(reference.id);
      expect(observations.observations, reference.id).toHaveLength(
        reference.n_observations,
      );
      expect(observationPayload.bytes, reference.id).toBe(
        reference.observations_bytes,
      );
    }
  }, 60_000);

  it('decodes every staged grid, render and detail object with the TS GOSA decoder', () => {
    const catalog = atlasCatalogSchema.parse(readPayload('catalog.json').value);
    const [[gridSha256, entry]] = Object.entries(catalog.grids);
    const grid = decodeGrid(readBuffer(entry.url), { entry, gridSha256 });
    expect(grid.n).toBe(77_844);
    for (const ref of catalog.artifacts) {
      const render = decodeRender(readBuffer(ref.web.render.url), {
        grid,
        ref,
      });
      const detail = decodeDetail(readBuffer(ref.web.detail.url), {
        grid,
        ref,
        render,
      });
      expect(detail.post_mean, ref.id).toHaveLength(ref.n_cells);
    }
  }, 120_000);
});
