import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import * as productionSymbols from '../src/atlas/scene/observation-symbols';
import * as productionSupport from '../src/atlas/scene/support-material';
import * as legacyAnchors from './legacy/observation-anchors';
import * as legacyLayer from './legacy/surface-layer';
import * as legacyMesh from './legacy/surface-mesh';
import * as legacySupport from './legacy/support-material';

/** [production module or null when the file left src, legacy module, legacy-only exports]. */
const LEGACY_ONLY: readonly [object | null, object, readonly string[]][] = [
  [
    null,
    legacyMesh,
    [
      'surfaceVertexHeights',
      'surfaceVertexValues',
      'surfaceMeshForCell',
      'geometryForSurfaceMesh',
      'geometryForFlatSurfaceCell',
      'geometryForExtrudedSurfaceCell',
    ],
  ],
  [null, legacyLayer, ['buildSurfaceLayer', 'surfacePickId']],
  [
    productionSupport,
    legacySupport,
    ['partitionSurfaceCells', 'paletteBinsForCells'],
  ],
  [
    productionSymbols,
    legacyAnchors,
    ['observationSurfaceAnchor', 'observationSurfaceContext'],
  ],
];

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx|astro)$/.test(entry) ? [path] : [];
  });
}

describe('the legacy builder lives only in the test oracle (fast-load §B.1)', () => {
  it('removes the main-thread mesh and layer modules from src', () => {
    expect(
      existsSync(
        resolve(import.meta.dirname, '../src/atlas/scene/surface-mesh.ts'),
      ),
    ).toBe(false);
    expect(
      existsSync(
        resolve(import.meta.dirname, '../src/atlas/scene/surface-layer.ts'),
      ),
    ).toBe(false);
  });

  it.each(
    LEGACY_ONLY.flatMap(([production, legacy, names]) =>
      names.map((name) => [name, production, legacy] as const),
    ),
  )(
    '%s is exported by tests/legacy and not by src',
    (name, production, legacy) => {
      if (production) expect(Object.keys(production)).not.toContain(name);
      expect(typeof (legacy as Record<string, unknown>)[name]).toBe('function');
    },
  );

  it('keeps every src module independent of the oracle', () => {
    for (const file of sourceFiles(resolve(import.meta.dirname, '../src')))
      expect(readFileSync(file, 'utf8'), file).not.toMatch(/tests\/legacy/);
  });
});
