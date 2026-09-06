import { describe, expect, it } from 'vitest';

import { sitePath } from '../src/lib/paths';

describe('sitePath', () => {
  it('keeps a root deployment rooted once', () => {
    expect(sitePath('/working-groups/', '/')).toBe('/working-groups/');
  });

  it('prefixes a project-site deployment exactly once', () => {
    expect(sitePath('/working-groups/', '/genomeOS/')).toBe('/genomeOS/working-groups/');
  });

  it('preserves query strings and fragments', () => {
    expect(sitePath('/contribute/?status=ready#start', '/genomeOS/')).toBe(
      '/genomeOS/contribute/?status=ready#start',
    );
  });
});
