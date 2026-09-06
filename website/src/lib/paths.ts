/** Join an internal site path to Astro's deployment base without double slashes. */
export function sitePath(
  path: string,
  base = import.meta.env.BASE_URL,
): string {
  const normalizedBase = base.replace(/^\/+|\/+$/g, '');
  const normalizedPath = path.replace(/^\/+/, '');
  const prefix = normalizedBase ? `/${normalizedBase}/` : '/';

  return `${prefix}${normalizedPath}`;
}
