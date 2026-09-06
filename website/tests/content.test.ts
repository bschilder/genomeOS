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

describe('public site content', () => {
  it.each([
    ['home', home],
    ['project', project],
    ['working groups', groups],
    ['contribute', contribute],
  ])('renders one primary heading on the %s page', (_name, html) => {
    expect(html.match(/<h1(?:\s|>)/g) ?? []).toHaveLength(1);
  });

  it('labels current work, active work, and future ideas separately', () => {
    expect(home).toMatch(
      /Available now[\s\S]*In active development[\s\S]*Future exploration/,
    );
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
    expect(project).toContain('P0');
    expect(project).toContain('P5');
  });
});
