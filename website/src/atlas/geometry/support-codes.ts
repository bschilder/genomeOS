/** Numeric support codes for worker geometry (fast-load spec 2026-10-07 §B.3).
 *
 * Derived from the decoder's `SUPPORT_CODES` table so geometry never restates
 * the code order.
 */

import type { Support } from '../contracts';
import { SUPPORT_CODES } from '../gosa/decode';

export const OBSERVED_CODE = SUPPORT_CODES.indexOf('observed');
export const INTERPOLATED_CODE = SUPPORT_CODES.indexOf('interpolated');
export const PRIOR_DOMINATED_CODE = SUPPORT_CODES.indexOf('prior_dominated');
export const UNKNOWN_CODE = SUPPORT_CODES.indexOf('unknown');

export function supportName(code: number): Support {
  const name = SUPPORT_CODES[code];
  if (name === undefined) throw new Error(`unknown support code ${code}`);
  return name;
}

/** Observed and interpolated cells are meshed; the other two are masked. */
export function isSupportedCode(code: number): boolean {
  return code === OBSERVED_CODE || code === INTERPOLATED_CODE;
}
