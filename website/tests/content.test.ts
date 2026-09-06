import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const dist = path.resolve(import.meta.dirname, '../dist');

function page(route: string): string {
  const filename = path.join(dist, route, 'index.html');
  return existsSync(filename) ? readFileSync(filename, 'utf8') : '';
}

const home = page('');
const project = page('project');
const groups = page('working-groups');
const contribute = page('contribute');
const preview = page('app');

describe('public site content', () => {
  it.each([
    ['home', home],
    ['project', project],
    ['working groups', groups],
    ['contribute', contribute],
    ['preview', preview],
  ])('renders one primary heading on the %s page', (_name, html) => {
    expect(html.match(/<h1(?:\s|>)/g) ?? []).toHaveLength(1);
  });

  it('labels current work, active work, and future ideas separately', () => {
    expect(home).toMatch(
      /Available now[\s\S]*In active development[\s\S]*Future exploration/,
    );
  });

  it('leads with the higher-order mission and concrete applications', () => {
    expect(home).toContain(
      'Make the world’s genetic diversity legible and useful',
    );
    expect(home).toMatch(
      /Potential applications[\s\S]*Screening programmes[\s\S]*Diagnostic context[\s\S]*Trial planning[\s\S]*The map of what we don’t know/,
    );
    expect(home).toContain(
      'https://github.com/bschilder/genomeOS/discussions/1',
    );
    expect(home).toMatch(/open source/i);
    expect(home).toMatch(/global community/i);
    expect(home).toMatch(/public good/i);
  });

  it('reports sourced corpus metrics with an auditable definition', () => {
    expect(home).toMatch(
      /4,392[\s\S]*Genetic variants &amp; alleles[\s\S]*6\.69M[\s\S]*People represented[\s\S]*2[\s\S]*Diseases represented/,
    );
    expect(home).toContain('How these counts are defined');
    expect(home).toContain('fc17bc1c1d96a0d0766746dcf26277ccdc669717');
    expect(home).not.toContain('Measured here.');
  });

  it('defines all three forming working groups and modeling breadth', () => {
    expect(groups).toMatch(
      /Data[\s\S]*Modeling[\s\S]*Product &amp; Experience/,
    );
    expect(groups).toContain('geometric deep learning');
    expect(groups).toContain('Brian');
    expect(groups).toMatch(
      /Future exploration[\s\S]*privacy[\s\S]*consent[\s\S]*governance/,
    );
    expect(groups).toContain('Groups are forming');
  });

  it('teaches the repository contribution workflow', () => {
    expect(contribute).toContain('Discussion #76');
    expect(contribute).toContain('mention the original issue author');
    expect(contribute).toContain('Ready');
    expect(contribute).toContain('needs-human-decision');
    expect(contribute).toContain('wants-expert-review');
    expect(contribute).toContain(
      'https://github.com/users/bschilder/projects/8',
    );
  });

  it('states the scientific publication bar', () => {
    expect(project).toMatch(/HbS[\s\S]*G6PD[\s\S]*screening/);
    expect(project).toMatch(/population-location registry/i);
    expect(project).toMatch(/interactive public map/i);
  });

  it('frames the live application as a sample-data WIP diagnostic', () => {
    expect(preview).toContain('Work-in-progress preview');
    expect(preview).toContain('Sample data for testing');
    expect(preview).toContain(
      'https://genomeos-api-357876699511.us-east1.run.app/preview',
    );
    expect(preview).toContain(
      'title="genomeOS diagnostic application preview"',
    );
    expect(preview).not.toMatch(/\bP[0-9]+\b/);
    expect(preview).toContain('sample data created for software testing');
  });

  it('does not expose unexplained internal project codes on introduction pages', () => {
    expect(home).not.toMatch(/\bP[0-9]+\b/);
    expect(project).not.toMatch(/\bP[0-9]+\b/);
  });
});
