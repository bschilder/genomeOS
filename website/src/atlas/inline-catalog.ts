/** The `/app/` inline catalog element, shared by the page, the head script and the provider (fast-load design §B.6.1). */

export const INLINE_CATALOG_ID = 'atlas-catalog';

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
