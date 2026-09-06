import { describe, expect, it } from 'vitest';

import { corpusMetrics, metricTotal } from '../src/data/corpusMetrics';

describe('corpus metrics snapshot', () => {
  it('derives every headline from named source components', () => {
    expect(metricTotal(corpusMetrics.variants)).toBe(4_392);
    expect(metricTotal(corpusMetrics.people)).toBe(6_690_875);
    expect(metricTotal(corpusMetrics.diseases)).toBe(2);
  });

  it('pins an immutable Hugging Face revision', () => {
    expect(corpusMetrics.sourceRevision).toMatch(/^[0-9a-f]{40}$/);
    expect(corpusMetrics.sourceRevision).toBe(
      'fc17bc1c1d96a0d0766746dcf26277ccdc669717',
    );
  });

  it('records participant components separately to expose overlap risk', () => {
    expect(corpusMetrics.people.components).toEqual({
      afndPopulationRecords: 657_287,
      hbsTypedParticipants: 5_717_140,
      g6pdHemizygousMaleParticipants: 316_448,
    });
    expect(corpusMetrics.people.isDeduplicated).toBe(false);
  });
});
