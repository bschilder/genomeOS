import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { surfaceArtifactSchema } from '../src/atlas/contracts';
import {
  colorAtPosition,
  normalizedValue,
  quantizeMetric,
  type PaletteId,
} from '../src/atlas/visual-encoding';
import { publishedSurfaces } from './helpers/atlas-geometry';

/** Every surface the tree's catalog lists (Plan ruling R23): empty without data, never partial. */
const SURFACES = publishedSurfaces();
const PALETTES: readonly PaletteId[] = [
  'genome',
  'signal',
  'viridis',
  'cividis',
  'plasma',
  'rainbow',
  'golden',
];
const HEIGHT_SCALE_METRES = 180_000;
/** The f32 render tier moves exactly one 32-bin assignment across all layers. */
const EXPECTED_FLIPS = ['cyt-il-10-819-t post_sd 84194e9ffffffff 4->5'];

describe.skipIf(SURFACES.length === 0)(
  'f32 render tier against the f64 artifacts (fast-load §B.1)',
  () => {
    it('stays inside the analytic bound and flips exactly the reported bins', () => {
      expect(SURFACES).toHaveLength(30);
      const flips: string[] = [];
      const firstCellChanges: string[] = [];
      const report: string[] = [];
      for (const ref of SURFACES) {
        const surface = surfaceArtifactSchema.parse(
          JSON.parse(readFileSync(ref.path, 'utf8')),
        );
        for (const metric of ['post_mean', 'post_sd'] as const) {
          const domain = surface.artifact.metric_domains[metric];
          for (const group of [
            ['observed', 'interpolated'],
            ['prior_dominated'],
          ] as const) {
            const cells = surface.cells.filter((cell) =>
              (group as readonly string[]).includes(cell.support),
            );
            if (cells.length === 0) continue;
            let maxAbs = 0;
            let maxDelta = 0;
            const first64 = new Map<number, (typeof cells)[number]>();
            const first32 = new Map<number, (typeof cells)[number]>();
            for (const cell of cells) {
              const value = cell[metric];
              const rendered = Math.fround(value);
              maxAbs = Math.max(maxAbs, Math.abs(value));
              maxDelta = Math.max(
                maxDelta,
                Math.abs(
                  normalizedValue(value, domain) -
                    normalizedValue(rendered, domain),
                ),
              );
              const bin = quantizeMetric(value, domain);
              const renderedBin = quantizeMetric(rendered, domain);
              if (bin !== renderedBin)
                flips.push(
                  `${ref.id} ${metric} ${cell.h3_index} ${bin}->${renderedBin}`,
                );
              if (!first64.has(bin)) first64.set(bin, cell);
              if (!first32.has(renderedBin)) first32.set(renderedBin, cell);
            }
            const bound = (2 ** -24 * maxAbs) / (domain[1] - domain[0]);
            expect(maxDelta, `${ref.id} ${metric}`).toBeLessThanOrEqual(bound);
            for (const [bin, cell] of first32) {
              const source = first64.get(bin);
              if (source?.h3_index !== cell.h3_index) {
                firstCellChanges.push(`${ref.id} ${metric} bin ${bin}`);
                continue;
              }
              for (const palette of PALETTES)
                if (
                  colorAtPosition(
                    palette,
                    normalizedValue(cell[metric], domain),
                  ) !==
                  colorAtPosition(
                    palette,
                    normalizedValue(Math.fround(cell[metric]), domain),
                  )
                )
                  firstCellChanges.push(
                    `${ref.id} ${metric} bin ${bin} ${palette}`,
                  );
            }
            report.push(
              `${ref.id} ${metric} ${group.join('|')}: max |Δnormalised| ${maxDelta.toExponential(2)} ≤ ${bound.toExponential(2)}, height ≤ ${(bound * HEIGHT_SCALE_METRES).toFixed(3)} m`,
            );
          }
        }
      }
      console.info(report.join('\n'));
      expect(flips).toEqual(EXPECTED_FLIPS);
      expect(firstCellChanges).toEqual([]);
    }, 300_000);
  },
);
