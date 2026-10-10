/** The `/app/` inline catalog element, shared by the page, the head script and the provider (fast-load design §B.6.1). */

export const INLINE_CATALOG_ID = 'atlas-catalog';

/**
 * Set by the head script (`preload-script.ts`) on the catalog element when the connection is slow
 * and the render tier waits for the scene chunk (fast-load design §B.1, ruling R84-slow4g).
 */
export const SURFACE_DOWNLOADS_ATTRIBUTE = 'data-surface-downloads';
export const SURFACE_DOWNLOADS_AFTER_SCENE = 'after-scene';
/** Each tier's fetch priority, shared by the preload links and the provider's fetches. */
export const OBSERVATIONS_PRIORITY: RequestPriority = 'high';
export const SURFACE_PRIORITY: RequestPriority = 'low';

/** True when the head script left the render tier for after the scene chunk. */
export function surfaceDownloadsAfterScene(
  doc: Pick<Document, 'getElementById'>,
): boolean {
  return (
    doc
      .getElementById(INLINE_CATALOG_ID)
      ?.getAttribute(SURFACE_DOWNLOADS_ATTRIBUTE) ===
    SURFACE_DOWNLOADS_AFTER_SCENE
  );
}

/** JSON text safe inside a <script> element: every "<" becomes the JSON escape \u003c. */
export function escapeInlineJson(json: string): string {
  return json.replace(/</g, '\\u003c');
}

/** The parsed inline catalog, or undefined when the element is missing or is not JSON. */
export function readInlineCatalog(
  doc: Pick<Document, 'getElementById'>,
): unknown {
  const text = doc.getElementById(INLINE_CATALOG_ID)?.textContent;
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
