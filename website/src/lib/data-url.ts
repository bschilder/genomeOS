/** Data-key and data-base URL rules for Atlas design §11 and fast-load design §B.4. */

const DATA_KEY = /^[a-z0-9][a-z0-9._/-]*$/;
const LOCAL_HTTP_HOSTS: ReadonlySet<string> = new Set([
  'localhost',
  '127.0.0.1',
]);
// Root-relative bases are resolved against a fixed placeholder, never Astro.url or Astro.site.
const PLACEHOLDER_ORIGIN = 'http://x.invalid';

type DataBaseKind = 'root-relative' | 'absolute';

/**
 * `new URL(input, base)`, or null when it does not parse. This runs in the browser at fetch time,
 * so it avoids `URL.canParse`, which needs Safari 17, Chrome 120 or Firefox 115.
 */
function parseUrl(input: string, base?: string): URL | null {
  try {
    return new URL(input, base);
  } catch {
    return null;
  }
}

/**
 * Classify a base by parsing it, never by its prefix. The parser reads "/\host/" and "/<tab>/host/"
 * as "//host/", drops a query or fragment on resolution, and moves the host after "user@", so a
 * base is accepted only when the parsed URL is exactly the string written: a root-relative base
 * keeps the placeholder origin and is its own pathname, and an absolute base is its own href with
 * no credentials, query or fragment.
 */
function dataBaseKind(base: string): DataBaseKind {
  if (!base.endsWith('/')) {
    throw new Error(`Atlas data base must end in "/": ${JSON.stringify(base)}`);
  }
  if (base.startsWith('/')) {
    const url = parseUrl(base, PLACEHOLDER_ORIGIN);
    if (
      url !== null &&
      url.origin === PLACEHOLDER_ORIGIN &&
      url.pathname === base
    ) {
      return 'root-relative';
    }
  } else {
    const url = parseUrl(base);
    if (
      url !== null &&
      (url.protocol === 'https:' ||
        (url.protocol === 'http:' && LOCAL_HTTP_HOSTS.has(url.hostname))) &&
      url.username === '' &&
      url.password === '' &&
      url.search === '' &&
      url.hash === '' &&
      url.href === base
    ) {
      return 'absolute';
    }
  }
  throw new Error(
    'Atlas data base must be root-relative or an absolute https URL, written as the URL parser ' +
      `reads it, with no credentials, query, fragment or dot segment: ${JSON.stringify(base)}`,
  );
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
  dataBaseKind(base);
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
  const kind = dataBaseKind(base);
  const url = new URL(key, new URL(base, PLACEHOLDER_ORIGIN));
  return kind === 'absolute' ? url.href : url.pathname;
}

/** The origin a `<link rel="preconnect">` should name, or null for a same-origin base. */
export function dataOrigin(base: string): string | null {
  return dataBaseKind(base) === 'absolute' ? new URL(base).origin : null;
}
