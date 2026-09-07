/** Deterministic measured-observation encodings for Atlas design §11. */

import type { Observation } from './contracts';
import { colorAtPosition, type MetricDomain } from './visual-encoding';

export type ObservationSizeVariable = 'fixed' | 'frequency' | 'ac' | 'an';
export type ObservationColorVariable = 'white' | 'study' | 'frequency' | 'ac';
export type ObservationShape = 'circle' | 'hemisphere' | 'pin';
export type ObservationSizeRange = readonly [number, number];

export interface ObservationDomains {
  ac: MetricDomain;
  an: MetricDomain;
  frequency: MetricDomain;
}

const STUDY_COLORS = [
  '#72e7c1',
  '#70e6ff',
  '#f4c86a',
  '#ad8bff',
  '#ff8fb8',
  '#7dd3fc',
  '#f9a86f',
  '#a7f3d0',
] as const;

function validateDomain([lower, upper]: MetricDomain): void {
  if (!Number.isFinite(lower) || !Number.isFinite(upper) || lower > upper) {
    throw new Error('observation encoding domain must be finite and ordered');
  }
}

function fraction(
  value: number,
  domain: MetricDomain,
  squareRoot: boolean,
): number {
  validateDomain(domain);
  const [lower, upper] = domain;
  if (lower === upper) return 0.5;
  const bounded = Math.min(upper, Math.max(lower, value));
  if (squareRoot) {
    return (
      (Math.sqrt(bounded) - Math.sqrt(lower)) /
      (Math.sqrt(upper) - Math.sqrt(lower))
    );
  }
  return (bounded - lower) / (upper - lower);
}

function observedFrequency(observation: Observation): number {
  if (
    !Number.isInteger(observation.ac) ||
    !Number.isInteger(observation.an) ||
    observation.ac < 0 ||
    observation.an <= 0 ||
    observation.ac > observation.an
  ) {
    throw new Error('observation requires integer 0 <= ac <= an with an > 0');
  }
  return observation.ac / observation.an;
}

function extent(values: readonly number[]): MetricDomain {
  if (values.length === 0)
    throw new Error('observation domains require at least one observation');
  return [Math.min(...values), Math.max(...values)];
}

export function observationDomains(
  observations: readonly Observation[],
): ObservationDomains {
  for (const observation of observations) observedFrequency(observation);
  return {
    ac: extent(observations.map(({ ac }) => ac)),
    an: extent(observations.map(({ an }) => an)),
    frequency: extent(observations.map(observedFrequency)),
  };
}

export function validateObservationSizeRange(
  shape: ObservationShape,
  [minimum, maximum]: ObservationSizeRange,
): void {
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) {
    throw new Error('observation size range must be finite');
  }
  if (minimum > maximum) {
    throw new Error('observation size minimum must not exceed maximum');
  }
  if (shape === 'hemisphere') {
    if (minimum < 10 || maximum > 500) {
      throw new Error(
        'hemisphere size must stay within 10..500 visual kilometres',
      );
    }
  } else if (minimum < 4 || maximum > 40) {
    throw new Error(`${shape} size must stay within 4..40 pixels`);
  }
}

export function observationSize(
  observation: Observation,
  variable: ObservationSizeVariable,
  [minimum, maximum]: ObservationSizeRange,
  domain: MetricDomain,
): number {
  if (
    !Number.isFinite(minimum) ||
    !Number.isFinite(maximum) ||
    minimum > maximum
  ) {
    throw new Error('observation size range must be finite and ordered');
  }
  if (variable === 'fixed') return (minimum + maximum) / 2;
  const value =
    variable === 'frequency'
      ? observedFrequency(observation)
      : observation[variable];
  const position = fraction(
    value,
    domain,
    variable === 'ac' || variable === 'an',
  );
  return minimum + position * (maximum - minimum);
}

export function studyColor(studyId: string): string {
  if (!studyId.trim()) throw new Error('study_id must be non-empty');
  let hash = 2_166_136_261;
  for (const character of studyId) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16_777_619);
  }
  return STUDY_COLORS[(hash >>> 0) % STUDY_COLORS.length];
}

export function observationColor(
  observation: Observation,
  variable: ObservationColorVariable,
  domain: MetricDomain,
): string {
  if (variable === 'white') return '#f4fbff';
  if (variable === 'study') return studyColor(observation.study_id);
  const value =
    variable === 'frequency' ? observedFrequency(observation) : observation.ac;
  const position = fraction(value, domain, variable === 'ac');
  return colorAtPosition(
    variable === 'frequency' ? 'genome' : 'signal',
    position,
  );
}
