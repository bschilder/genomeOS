/** Deterministic measured-observation encodings for Atlas design §11. */

import type { Observation } from './contracts';
import {
  colorAtPosition,
  colorAtStops,
  type MetricDomain,
} from './visual-encoding';

export type ObservationSizeVariable = 'fixed' | 'frequency' | 'ac' | 'an';
export type ObservationColorVariable = 'solid' | 'gradient' | 'study' | 'ac';
export type ObservationShape = 'circle' | 'hemisphere' | 'sphere' | 'pin';
export type ObservationSizeRange = readonly [number, number];

export const MIN_OBSERVATION_MARKER_SIZE = 12;
export const MAX_OBSERVATION_MARKER_SIZE = 96;
export const DEFAULT_OBSERVATION_SIZE_RANGE: ObservationSizeRange = [12, 32];

export interface ObservationDomains {
  ac: MetricDomain;
  an: MetricDomain;
  frequency: MetricDomain;
}

export interface ObservationColorEncoding {
  color: string;
  label: 'Allele count (AC)' | 'Observed frequency' | 'Study' | null;
  value: number | string | null;
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

export const DEFAULT_OBSERVATION_SOLID_COLOR = '#f4fbff';
export const DEFAULT_OBSERVATION_GRADIENT = [
  '#24144b',
  '#ad8bff',
  '#f4c86a',
] as const;
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function validateColor(color: string): string {
  if (!HEX_COLOR.test(color)) throw new Error(`invalid marker color ${color}`);
  return color.toLowerCase();
}

function validateDomain([lower, upper]: MetricDomain): void {
  if (!Number.isFinite(lower) || !Number.isFinite(upper) || lower > upper) {
    throw new Error('observation encoding domain must be finite and ordered');
  }
}

function fraction(
  value: number,
  domain: MetricDomain,
  scale: 'linear' | 'logarithmic' | 'square-root',
): number {
  validateDomain(domain);
  const [lower, upper] = domain;
  if (lower === upper) return 0.5;
  const bounded = Math.min(upper, Math.max(lower, value));
  if (scale === 'square-root') {
    return (
      (Math.sqrt(bounded) - Math.sqrt(lower)) /
      (Math.sqrt(upper) - Math.sqrt(lower))
    );
  }
  if (scale === 'logarithmic') {
    return (
      (Math.log1p(bounded) - Math.log1p(lower)) /
      (Math.log1p(upper) - Math.log1p(lower))
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
  _shape: ObservationShape,
  [minimum, maximum]: ObservationSizeRange,
): void {
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) {
    throw new Error('observation size range must be finite');
  }
  if (minimum > maximum) {
    throw new Error('observation size minimum must not exceed maximum');
  }
  if (
    minimum < MIN_OBSERVATION_MARKER_SIZE ||
    maximum > MAX_OBSERVATION_MARKER_SIZE
  )
    throw new Error(
      `marker size must stay within ${MIN_OBSERVATION_MARKER_SIZE}..${MAX_OBSERVATION_MARKER_SIZE} pixels`,
    );
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
    variable === 'ac' || variable === 'an' ? 'square-root' : 'linear',
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

export function observationColorEncoding(
  observation: Observation,
  variable: ObservationColorVariable,
  domain: MetricDomain,
  solidColor = DEFAULT_OBSERVATION_SOLID_COLOR,
  gradient: readonly string[] = DEFAULT_OBSERVATION_GRADIENT,
): ObservationColorEncoding {
  if (variable === 'solid')
    return { color: validateColor(solidColor), label: null, value: null };
  if (variable === 'study')
    return {
      color: studyColor(observation.study_id),
      label: 'Study',
      value: observation.study_label,
    };
  if (variable === 'gradient') {
    const colors = gradient.map(validateColor);
    const value = observedFrequency(observation);
    return {
      color: colorAtStops(colors, fraction(value, domain, 'linear')),
      label: 'Observed frequency',
      value,
    };
  }
  return {
    color: colorAtPosition(
      'signal',
      fraction(observation.ac, domain, 'logarithmic'),
    ),
    label: 'Allele count (AC)',
    value: observation.ac,
  };
}

export function observationColor(
  observation: Observation,
  variable: ObservationColorVariable,
  domain: MetricDomain,
  solidColor = DEFAULT_OBSERVATION_SOLID_COLOR,
  gradient: readonly string[] = DEFAULT_OBSERVATION_GRADIENT,
): string {
  return observationColorEncoding(
    observation,
    variable,
    domain,
    solidColor,
    gradient,
  ).color;
}
