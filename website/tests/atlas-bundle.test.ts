import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const dist = path.resolve(import.meta.dirname, '../dist');
const assets = path.join(dist, '_astro');
// GLSL built-ins carry this prefix in every Cesium shader source string; minification keeps it.
const CESIUM_MARKER = 'czm_';
const STATIC_IMPORT =
  /(?:\bimport|\bexport)\s*(?:[^"'()]*?\bfrom\s*)?["'](\.\.?\/[^"']+\.js)["']/g;
// The Vite 8 Oxc minifier writes string literals, dynamic-import specifiers included, as
// template literals (import(`./atlas-scene.<hash>.js`)), so backticks are accepted here.
const DYNAMIC_IMPORT = /\bimport\(\s*["'`](\.\.?\/[^"'`]+\.js)["'`]\s*\)/g;

function appHtml(): string {
  return readFileSync(path.join(dist, 'app', 'index.html'), 'utf8');
}

function code(file: string): string {
  return readFileSync(path.join(assets, file), 'utf8');
}

function islandChunk(): string {
  const match = appHtml().match(
    /component-url="[^"]*\/_astro\/(AtlasExplorer\.[^"/]+\.js)"/,
  );
  if (!match) throw new Error('the /app/ page has no AtlasExplorer island');
  return match[1];
}

/** The chunk and everything it imports statically (dynamic imports excluded). */
export function staticGraph(entry: string): string[] {
  const seen = new Set<string>();
  const queue = [entry];
  while (queue.length > 0) {
    const file = queue.pop()!;
    if (seen.has(file)) continue;
    seen.add(file);
    for (const match of code(file).matchAll(STATIC_IMPORT)) {
      queue.push(path.posix.join(path.posix.dirname(file), match[1]));
    }
  }
  return [...seen];
}

export function sceneChunk(): string {
  const island = islandChunk();
  const graph = staticGraph(island);
  const targets = graph.flatMap((file) =>
    [...code(file).matchAll(DYNAMIC_IMPORT)].map((match) =>
      path.posix.join(path.posix.dirname(file), match[1]),
    ),
  );
  const scene = targets.find((file) =>
    path.posix.basename(file).startsWith('atlas-scene.'),
  );
  if (!scene)
    throw new Error(`no lazy atlas-scene chunk among ${targets.join(', ')}`);
  return scene;
}

describe('Atlas client bundle', () => {
  it('keeps Cesium out of the explorer island and its static imports', () => {
    for (const file of staticGraph(islandChunk())) {
      expect(code(file).includes(CESIUM_MARKER), file).toBe(false);
    }
  });

  it('loads Cesium only through the lazy scene chunk', () => {
    const scene = sceneChunk();
    expect(existsSync(path.join(assets, scene))).toBe(true);
    expect(
      staticGraph(scene).some((file) => code(file).includes(CESIUM_MARKER)),
    ).toBe(true);
  });

  it('bundles the data worker as a Cesium-free ES module referenced by the island', () => {
    const worker = readdirSync(assets).find((name) =>
      /^atlas-data\.worker[-.].+\.js$/.test(name),
    );
    expect(worker).toBeDefined();
    const source = code(worker!);
    expect(source.includes(CESIUM_MARKER)).toBe(false);
    expect(source).toContain('load-grid');
    expect(source.trimStart().startsWith('(function')).toBe(false);
    expect(
      staticGraph(islandChunk()).some((file) => code(file).includes(worker!)),
    ).toBe(true);
  });
});
