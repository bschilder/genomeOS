import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  atlasCatalogSchema,
  observationArtifactSchema,
  surfaceArtifactSchema,
} from '../src/atlas/contracts';
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

function readPayload(filename: string): { digest: string; value: unknown } {
  const bytes = readFileSync(`${dataDirectory}/${filename}`);
  return {
    digest: createHash('sha256').update(bytes).digest('hex'),
    value: JSON.parse(bytes.toString()),
  };
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
    }
  });
});
