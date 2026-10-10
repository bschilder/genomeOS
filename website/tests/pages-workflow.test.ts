/** The sharded browser job of the Pages workflow and its test server (docs-website design §7, #411). */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { DEFAULT_PLAYWRIGHT_PORT } from './setup/playwright-env';

const repositoryRoot = path.resolve(import.meta.dirname, '../..');
const read = (relative: string) =>
  readFileSync(path.join(repositoryRoot, relative), 'utf8');
const pagesWorkflow = read('.github/workflows/pages.yml');

/** One job's text, from its key up to the next job's key. */
function job(name: string): string {
  const start = pagesWorkflow.indexOf(`\n  ${name}:\n`);
  expect(start, `job ${name}`).toBeGreaterThan(-1);
  const rest = pagesWorkflow.slice(start + 1);
  const next = rest.search(/\n {2}[a-z][\w-]*:\n/);
  return next < 0 ? rest : rest.slice(0, next);
}

/** A job's run defaults and its steps before the named step: how it prepares the workspace. */
function preparation(jobText: string, stepName: string): string {
  const start = jobText.search(/\n {4}(defaults|steps):\n/);
  const end = jobText.indexOf(`\n      - name: ${stepName}\n`);
  expect(start, 'defaults or steps').toBeGreaterThan(-1);
  expect(end, `step "${stepName}"`).toBeGreaterThan(start);
  return jobText.slice(start, end);
}

describe('Pages workflow browser shards', () => {
  it('prepares each shard exactly as validate prepares its checks', () => {
    // `npm run test:e2e` builds the site in every shard, so whatever validate sets up before it
    // checks and builds (a toolchain, an encoder for generated data) each shard needs too. A step
    // added to validate alone merges without a conflict and fails only in the shards.
    expect(preparation(job('e2e'), 'Install browser runtime')).toBe(
      preparation(job('validate'), 'Check formatting'),
    );
  });

  it('runs every shard from 1 to the matrix total, with the total written once', () => {
    const e2e = job('e2e');
    const shards = /\n {8}shard: \[([\d, ]+)\]\n/.exec(e2e)?.[1] ?? '';
    const total = Number(/\n {8}total: \[(\d+)\]\n/.exec(e2e)?.[1]);
    expect(total).toBeGreaterThan(0);
    expect(shards.split(',').map(Number)).toEqual(
      Array.from({ length: total }, (_, index) => index + 1),
    );
    const shard = '${{ matrix.shard }}/${{ matrix.total }}';
    expect(e2e).toContain(`name: e2e (shard ${shard})`);
    expect(e2e).toContain(
      `run: npm run test:e2e -- --fully-parallel --shard=${shard}`,
    );
    expect(e2e).toContain('fail-fast: false');
  });

  it('runs the browser contracts only in the shards and deploys only after all pass', () => {
    expect(pagesWorkflow.split('npm run test:e2e')).toHaveLength(2);
    expect(job('build')).toContain('needs: [validate, e2e]');
  });

  it('passes the GA Measurement ID to the production build step only (#422)', () => {
    const variable = 'PUBLIC_GA_MEASUREMENT_ID: ${{ vars.GA_MEASUREMENT_ID }}';
    expect(pagesWorkflow.split('PUBLIC_GA_MEASUREMENT_ID')).toHaveLength(2);
    expect(pagesWorkflow.split('GA_MEASUREMENT_ID')).toHaveLength(3);
    const build = job('build');
    const step = build.slice(
      build.indexOf('      - name: Build production site\n'),
      build.indexOf('      - name: Refuse broken production links\n'),
    );
    expect(step).toContain('run: npm run build\n');
    expect(step).toContain(variable);
    for (const name of ['validate', 'e2e', 'deploy'])
      expect(job(name), name).not.toContain('GA_MEASUREMENT_ID');
    expect(pagesWorkflow).not.toMatch(/goatcounter/i);
  });

  it('serves both Playwright suites through serve:test on PLAYWRIGHT_PORT', () => {
    const scripts = (
      JSON.parse(read('website/package.json')) as {
        scripts: Record<string, string>;
      }
    ).scripts;
    expect(scripts['serve:test']).toContain(
      'tcp://127.0.0.1:${PLAYWRIGHT_PORT:-' + DEFAULT_PLAYWRIGHT_PORT + '}',
    );
    for (const config of [
      'website/playwright.config.ts',
      'website/playwright.performance.config.ts',
    ]) {
      const text = read(config);
      expect(text, config).toContain("command: 'npm run serve:test'");
      expect(text, config).toContain('env: { PLAYWRIGHT_PORT: String(port) }');
      expect(text, config).not.toMatch(/\bserve dist\b/);
    }
  });
});
