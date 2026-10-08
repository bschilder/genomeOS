import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const dist = path.resolve(import.meta.dirname, '../dist');
const assets = path.join(dist, '_astro');
// Strings that survive minification in Cesium code. GLSL built-ins carry `czm_` in every shader
// source. `DeveloperError` is the error class behind Cesium's argument checks, which its ES source
// keeps, so every non-trivial Core value (Color, Cartesian3, Math, JulianDate, Event…) brings it
// along even when tree-shaken away from the renderer. Only constant-only modules (`defined`,
// `Frozen`, small enums) carry neither.
const CESIUM_MARKERS = ['czm_', 'DeveloperError'];
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

/** The Cesium markers present in a chunk's source. */
function cesiumMarkers(source: string): string[] {
  return CESIUM_MARKERS.filter((marker) => source.includes(marker));
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
      expect(cesiumMarkers(code(file)), file).toEqual([]);
    }
  });

  it('loads Cesium only through the lazy scene chunk', () => {
    const scene = sceneChunk();
    expect(existsSync(path.join(assets, scene))).toBe(true);
    // Every marker must occur in the scene graph, or it could never catch Cesium in the island.
    expect(
      new Set(staticGraph(scene).flatMap((file) => cesiumMarkers(code(file)))),
    ).toEqual(new Set(CESIUM_MARKERS));
  });

  it('bundles the data worker as a Cesium-free ES module referenced by the island', () => {
    const worker = readdirSync(assets).find((name) =>
      /^atlas-data\.worker[-.].+\.js$/.test(name),
    );
    expect(worker).toBeDefined();
    const source = code(worker!);
    expect(cesiumMarkers(source)).toEqual([]);
    expect(source).toContain('load-grid');
    expect(source.trimStart().startsWith('(function')).toBe(false);
    expect(
      staticGraph(islandChunk()).some((file) => code(file).includes(worker!)),
    ).toBe(true);
  });

  it('modulepreloads the lazy scene chunk and its static imports from the /app/ head', () => {
    const html = appHtml();
    const head = html.slice(0, html.indexOf('</head>'));
    const hrefs = [
      ...head.matchAll(/<link rel="modulepreload" href="([^"]+)">/g),
    ].map((match) => match[1]);
    const scene = sceneChunk();
    expect(hrefs[0]).toBe(`/_astro/${scene}`);
    expect(new Set(hrefs)).toEqual(
      new Set(staticGraph(scene).map((file) => `/_astro/${file}`)),
    );
    for (const href of hrefs)
      expect(existsSync(path.join(dist, href))).toBe(true);
  });
});
