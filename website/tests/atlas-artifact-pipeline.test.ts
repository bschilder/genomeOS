import { describe, expect, it } from 'vitest';

import type { ArtifactRef, ObservationArtifact } from '../src/atlas/contracts';
import {
  attachObservations,
  classifyDetailFailure,
  createLoadedArtifact,
  detailStatusFor,
  withoutKey,
} from '../src/components/atlas/artifact-pipeline';
import { columnarSurface } from './helpers/columnar-surface';

const cells = [
  {
    h3: '83754efffffffff',
    post_mean: 0.5,
    post_sd: 0.1,
    support: 'observed' as const,
  },
];

function coded(code: string): Error {
  return Object.assign(new Error(`worker ${code}`), { code });
}

describe('detail-tier state rules', () => {
  it('reports ready only when the detail tier is attached', () => {
    expect(detailStatusFor(null, undefined)).toBe('loading');
    expect(detailStatusFor(columnarSurface(cells), undefined)).toBe('loading');
    expect(
      detailStatusFor(columnarSurface(cells, { withDetail: true }), undefined),
    ).toBe('ready');
    expect(detailStatusFor(columnarSurface(cells), 'unavailable')).toBe(
      'unavailable',
    );
    expect(
      detailStatusFor(columnarSurface(cells, { withDetail: true }), 'invalid'),
    ).toBe('invalid');
  });

  it('separates corrupt detail from a slow or missing one', () => {
    expect(classifyDetailFailure(coded('checksum'))).toBe('invalid');
    expect(classifyDetailFailure(coded('validation'))).toBe('invalid');
    expect(
      classifyDetailFailure(
        Object.assign(new Error('bad column'), { name: 'GosaError' }),
      ),
    ).toBe('invalid');
    expect(classifyDetailFailure(coded('internal'))).toBe('unavailable');
    expect(
      classifyDetailFailure(new Error('Atlas request stalled for 15000 ms')),
    ).toBe('unavailable');
    expect(classifyDetailFailure('offline')).toBe('unavailable');
    expect(classifyDetailFailure(coded('cancelled'))).toBe('aborted');
    expect(
      classifyDetailFailure(new DOMException('aborted', 'AbortError')),
    ).toBe('aborted');
  });

  it('indexes observations of the loaded artifact by source record', () => {
    const entry = createLoadedArtifact('hbs-rs334:v3:map-2026-08', {
      id: 'hbs-rs334',
    } as ArtifactRef);
    attachObservations(entry, {
      observations: [{ source_record_id: 'map-surveys:1' }],
    } as unknown as ObservationArtifact);
    expect(entry.observationMap.get('map-surveys:1')).toEqual({
      source_record_id: 'map-surveys:1',
    });
    attachObservations(entry, null);
    expect(entry.observationMap.size).toBe(0);
  });

  it('removes one failure without touching the others', () => {
    expect(withoutKey({ a: 'invalid', b: 'unavailable' }, 'a')).toEqual({
      b: 'unavailable',
    });
  });
});
