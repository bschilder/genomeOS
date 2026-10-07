/** Data-key and data-base URL rules for Atlas design §11 and fast-load design §B.4. */

const DATA_KEY = /^[a-z0-9][a-z0-9._/-]*$/;
const LOCAL_HTTP_BASE = /^http:\/\/(?:localhost|127\.0\.0\.1)(?::[0-9]+)?\//;
// Root-relative bases are resolved against a fixed placeholder, never Astro.url or Astro.site.
const PLACEHOLDER_ORIGIN = 'http://x.invalid';

function isAbsoluteBase(base: string): boolean {
  return !base.startsWith('/');
}

/** A catalog key is a relative, lowercase path that cannot leave its base. */
export function assertDataKey(key: string): void {
  if (!DATA_KEY.test(key) || key.split('/').includes('..')) {
    throw new Error(
      `Atlas data key must be a relative lowercase path inside its base: ${JSON.stringify(key)}`,
    );
  }
}

/** A base is root-relative, or absolute https (or a local http dev origin), and ends in "/". */
export function assertDataBase(base: string): void {
  const rootRelative = base.startsWith('/') && !base.startsWith('//');
  const absolute =
    (base.startsWith('https://') || LOCAL_HTTP_BASE.test(base)) &&
    URL.canParse(base);
  if (!rootRelative && !absolute) {
    throw new Error(
      `Atlas data base must be root-relative or an absolute https URL: ${JSON.stringify(base)}`,
    );
  }
  if (!base.endsWith('/')) {
    throw new Error(`Atlas data base must end in "/": ${JSON.stringify(base)}`);
  }
}

/** The absolute URL a fetch uses. Call it at fetch time with `document.baseURI`. */
export function resolveDataUrl(
  key: string,
  base: string,
  docBase: string,
): string {
  assertDataKey(key);
  assertDataBase(base);
  return new URL(key, new URL(base, docBase)).href;
}

/** The string emitted in HTML: absolute for an absolute base, root-relative otherwise. */
export function dataHref(key: string, base: string): string {
  assertDataKey(key);
  assertDataBase(base);
  const url = new URL(key, new URL(base, PLACEHOLDER_ORIGIN));
  return isAbsoluteBase(base) ? url.href : url.pathname;
}

/** The origin a `<link rel="preconnect">` should name, or null for a same-origin base. */
export function dataOrigin(base: string): string | null {
  assertDataBase(base);
  return isAbsoluteBase(base) ? new URL(base).origin : null;
}
