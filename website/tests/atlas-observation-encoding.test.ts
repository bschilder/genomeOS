import { describe, expect, it } from 'vitest';

import type { Observation } from '../src/atlas/contracts';
import {
  observationColor,
  observationDomains,
  observationSize,
  studyColor,
  validateObservationSizeRange,
} from '../src/atlas/observation-encoding';

const base: Observation = {
  ac: 25,
  an: 100,
  assay: 'genotype',
  citation_text: 'Example publication.',
  cohort_id: 'map-study-1',
  disease_ascertainment_excluded: true,
  ingest_version: 'map-2026-08',
  lat: 5,
  lon: -1,
  population_label: 'Example population',
  radius_km: 12,
  sampling_design: 'population_random',
  source_locator: 'MAP survey 1',
  source_record_id: 'map-surveys:1',
  source_url: 'https://example.org/source',
  study_id: 'map-study-1',
  study_label: 'Example study',
};

function observation(overrides: Partial<Observation> = {}): Observation {
  return { ...base, ...overrides };
}

describe('observation visual encoding', () => {
  it('never lets sampling radius influence symbol size', () => {
    const compact = observation({ radius_km: 1 });
    const broad = observation({ radius_km: 563.9 });
    expect(observationSize(compact, 'ac', [6, 18], [0, 100])).toBe(
      observationSize(broad, 'ac', [6, 18], [0, 100]),
    );
  });

  it('uses linear frequency and square-root count scaling', () => {
    expect(
      observationSize(
        observation({ ac: 25, an: 100 }),
        'frequency',
        [6, 18],
        [0, 1],
      ),
    ).toBe(9);
    expect(
      observationSize(observation({ ac: 25 }), 'ac', [6, 18], [0, 100]),
    ).toBe(12);
    expect(
      observationSize(observation({ an: 25 }), 'an', [6, 18], [0, 100]),
    ).toBe(12);
  });

  it('keeps a zero allele count visible at the selected minimum', () => {
    expect(
      observationSize(observation({ ac: 0 }), 'ac', [7, 19], [0, 100]),
    ).toBe(7);
  });

  it('refuses reversed and shape-incompatible display ranges', () => {
    expect(() => validateObservationSizeRange('circle', [20, 5])).toThrow(
      'minimum',
    );
    expect(() => validateObservationSizeRange('circle', [1, 20])).toThrow(
      '4..40 pixels',
    );
    expect(() => validateObservationSizeRange('hemisphere', [5, 200])).toThrow(
      '10..500 visual kilometres',
    );
  });

  it('assigns stable study colors and keeps white as the default', () => {
    expect(studyColor('map-study-1')).toBe(studyColor('map-study-1'));
    expect(studyColor('map-study-1')).not.toBe(studyColor('map-study-2'));
    expect(observationColor(base, 'white', [0, 100])).toBe('#f4fbff');
    expect(observationColor(base, 'study', [0, 100])).toBe(
      studyColor(base.study_id),
    );
    expect(observationColor(base, 'frequency', [0, 1])).not.toBe('#f4fbff');
    expect(observationColor(base, 'ac', [0, 100])).not.toBe('#f4fbff');
  });

  it('derives display domains only from source-backed observation fields', () => {
    expect(
      observationDomains([
        observation({ ac: 0, an: 20 }),
        observation({ ac: 30, an: 100 }),
      ]),
    ).toEqual({ ac: [0, 30], an: [20, 100], frequency: [0, 0.3] });
  });
});
