/** Country label rules for the Natural Earth context overlay (Atlas design §11; spec 2026-10-07 §B.6.9). */

export {
  countryLabelText,
  type CountryProperties,
} from '../geometry/natural-earth';

const LABEL_CLEARANCE_METRES = 2_500;
const FRONT_HEMISPHERE_DEPTH_TEST_LIMIT_METRES = 8_000_000;

export function countryLabelHeight(
  surfaceHeight: number,
  elevationFactor: number,
): number {
  return (
    Math.max(0, surfaceHeight) * Math.max(0, elevationFactor) +
    LABEL_CLEARANCE_METRES
  );
}

export function countryLabelDistanceForScale(minLabel: number): number {
  const safeLabel = Number.isFinite(minLabel) ? Math.max(0, minLabel) : 7;
  return Math.max(800_000, 45_000_000 / 2 ** (safeLabel * 0.75));
}

export function countryLabelDepthTestDistance(minLabel: number): number {
  return Math.min(
    countryLabelDistanceForScale(minLabel),
    FRONT_HEMISPHERE_DEPTH_TEST_LIMIT_METRES,
  );
}
