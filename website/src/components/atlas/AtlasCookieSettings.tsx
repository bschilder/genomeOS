/**
 * The cookie settings icon docked in the Atlas (#422), standing in for the site's corner icon
 * (CookieControl.astro) on /app/, where that corner belongs to the explorer. The site's cookie
 * control (src/lib/cookie-control.ts) opens its panel beside whichever copy is shown:
 *
 * - `corner`: desktop, in the explorer's bottom-left corner under the controls dock, which ends
 *   one icon higher to make room (atlas.css), clear of the legend, the credits and the right rail;
 * - `credit`: phones, at the end of the data credit row, which rides above the bottom sheet in
 *   every state, so it never covers the sheet, its handle, the legend or the credits.
 *
 * Renders nothing in a build without analytics.
 */

import { COOKIE_GLYPH_PATHS } from '../../lib/cookie-glyph';

export function AtlasCookieSettings({
  placement,
}: {
  placement: 'corner' | 'credit';
}) {
  if (!import.meta.env.PUBLIC_GA_MEASUREMENT_ID) return null;
  return (
    <button
      type="button"
      className={`atlas-cookie-settings atlas-cookie-settings--${placement}`}
      aria-label="Cookie settings"
      aria-controls="cookie-settings-panel"
      aria-expanded="false"
      data-cookie-settings=""
      data-cookie-dock=""
    >
      <svg className="cookie-glyph" viewBox="0 0 24 24" aria-hidden="true">
        {COOKIE_GLYPH_PATHS.map((d) => (
          <path key={d} d={d} />
        ))}
      </svg>
    </button>
  );
}
