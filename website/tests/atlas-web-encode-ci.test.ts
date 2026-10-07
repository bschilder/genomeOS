import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const repositoryRoot = path.resolve(import.meta.dirname, '../..');
const read = (relative: string) =>
  readFileSync(path.join(repositoryRoot, relative), 'utf8');
const pagesWorkflow = read('.github/workflows/pages.yml');
const [validateJob, buildJob] = pagesWorkflow
  .split('\n  build:\n')
  .map((part, index) =>
    index === 0 ? part.split('\n  validate:\n')[1] : part,
  );

const INSTALL = "run: python -m pip install -c requirements.lock '.[read]'";
const ENCODE = 'run: python scripts/encode_atlas_web.py';
const GUARD =
  'run: git diff --exit-code website/public/data/atlas/catalog.json';

describe('Atlas web-object encoding in the Pages workflow (fast-load spec §B.5)', () => {
  it('encodes and guards the committed catalog before validate tests and builds', () => {
    // `-c requirements.lock` pins h3-py to the lock's h3==4.5.0, the same H3 core as h3-js 4.5.0
    // (spec §B.3: both decoders pinned to the same H3 core).
    for (const step of [INSTALL, ENCODE, GUARD])
      expect(validateJob).toContain(step);
    expect(validateJob.indexOf(ENCODE)).toBeLessThan(
      validateJob.indexOf(GUARD),
    );
    expect(validateJob.indexOf(GUARD)).toBeLessThan(
      validateJob.indexOf('run: npm test'),
    );
  });

  it('pins h3-py to the H3 core of the website h3-js', () => {
    const lock = read('requirements.lock')
      .split('\n')
      .find((line) => line.startsWith('h3=='));
    const h3js = (
      JSON.parse(read('website/package.json')) as {
        dependencies: Record<string, string>;
      }
    ).dependencies['h3-js'];
    expect(lock).toBe(`h3==${h3js}`);
  });

  it('encodes before the production build', () => {
    expect(buildJob).toContain(INSTALL);
    expect(buildJob).toContain(ENCODE);
    expect(buildJob).toContain(GUARD);
    expect(buildJob.indexOf(ENCODE)).toBeLessThan(
      buildJob.indexOf('run: npm run build'),
    );
  });

  it('runs when the encoder, codec, Python package metadata or lock change', () => {
    // Both jobs install with `-c requirements.lock`, and the h3 pin test above reads it, so a
    // lock-only change (e.g. an h3 bump) must re-run this workflow.
    for (const filter of [
      '"genomeos/publication/**"',
      '"scripts/encode_atlas_web.py"',
      '"pyproject.toml"',
      '"requirements.lock"',
    ])
      expect(pagesWorkflow.split(filter)).toHaveLength(3); // push and pull_request
  });

  it('keeps generated objects out of git and documents the prerequisite', () => {
    const ignored = read('.gitignore').split('\n');
    expect(ignored).toContain('website/public/data/atlas/grids/');
    expect(ignored).toContain('website/public/data/atlas/surfaces/');
    const sentence =
      '`export_atlas_web.py` output is an intermediate; the site build fails until `encode_atlas_web.py`';
    for (const doc of [
      'website/src/content/docs/docs/local-development.md',
      'docs/data-store.md',
    ]) {
      const text = read(doc).replace(/\s+/g, ' ');
      expect(text, doc).toContain(sentence);
      expect(text, doc).toContain('python scripts/encode_atlas_web.py');
    }
  });
});
