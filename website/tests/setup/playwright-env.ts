/**
 * Opt-in local overrides shared by both Playwright configs (#411). CI sets neither variable, so
 * CI keeps one worker per shard and the test server on 127.0.0.1:4322.
 */
type Environment = Readonly<Record<string, string | undefined>>;

/** The `serve:test` port when `PLAYWRIGHT_PORT` is unset; package.json repeats it as the default. */
export const DEFAULT_PLAYWRIGHT_PORT = 4322;

function integerFromEnv(
  env: Environment,
  name: string,
  fallback: number,
  max: number,
): number {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  const value = /^[1-9]\d*$/.test(raw) ? Number(raw) : Number.NaN;
  if (!(value <= max))
    throw new Error(
      `${name} must be an integer from 1 to ${max}, got "${raw}"`,
    );
  return value;
}

/** `PLAYWRIGHT_WORKERS`: the Playwright worker count, default 1. */
export function playwrightWorkers(env: Environment = process.env): number {
  return integerFromEnv(env, 'PLAYWRIGHT_WORKERS', 1, Number.MAX_SAFE_INTEGER);
}

/** `PLAYWRIGHT_PORT`: the port `npm run serve:test` listens on, default 4322. */
export function playwrightPort(env: Environment = process.env): number {
  return integerFromEnv(
    env,
    'PLAYWRIGHT_PORT',
    DEFAULT_PLAYWRIGHT_PORT,
    65_535,
  );
}
