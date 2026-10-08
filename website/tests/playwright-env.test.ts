/** Opt-in local Playwright overrides (docs-website design §7, #411). */
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PLAYWRIGHT_PORT,
  playwrightPort,
  playwrightWorkers,
} from './setup/playwright-env';

describe('Playwright environment overrides', () => {
  it('keeps the CI defaults when neither variable is set', () => {
    expect(playwrightWorkers({})).toBe(1);
    expect(playwrightPort({})).toBe(DEFAULT_PLAYWRIGHT_PORT);
    expect(DEFAULT_PLAYWRIGHT_PORT).toBe(4322);
    expect(playwrightWorkers({ PLAYWRIGHT_WORKERS: '' })).toBe(1);
    expect(playwrightPort({ PLAYWRIGHT_PORT: '' })).toBe(4322);
  });

  it('accepts any TCP port and any positive worker count', () => {
    expect(playwrightPort({ PLAYWRIGHT_PORT: '1' })).toBe(1);
    expect(playwrightPort({ PLAYWRIGHT_PORT: '4352' })).toBe(4352);
    expect(playwrightPort({ PLAYWRIGHT_PORT: '65535' })).toBe(65_535);
    expect(playwrightWorkers({ PLAYWRIGHT_WORKERS: '12' })).toBe(12);
  });

  it('refuses a malformed or out-of-range value instead of falling back', () => {
    for (const raw of [
      '0',
      '65536',
      '70000',
      '-1',
      '04322',
      ' 4322',
      '1.5',
      'x',
    ])
      expect(() => playwrightPort({ PLAYWRIGHT_PORT: raw }), raw).toThrow(
        `PLAYWRIGHT_PORT must be an integer from 1 to 65535, got "${raw}"`,
      );
    for (const raw of ['0', '2.0', 'four', '99999999999999999999'])
      expect(() => playwrightWorkers({ PLAYWRIGHT_WORKERS: raw }), raw).toThrow(
        /^PLAYWRIGHT_WORKERS must be an integer from 1 to \d+, got "/,
      );
  });
});
