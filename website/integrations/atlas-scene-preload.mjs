/**
 * Emit <link rel="modulepreload" fetchpriority="high"> for the lazy Atlas scene chunk on /app/
 * (Atlas design §11; fast-load design §B.6; §B.1 ruling R84-slow4g puts the scene chunk and Cesium
 * ahead of the grid and render tiers). The hashed chunk names come from the client build's bundle
 * and are injected into the generated HTML in astro:build:done.
 */

import { readFile, writeFile } from 'node:fs/promises';

const SCENE_MODULE = /\/src\/atlas\/scene\/atlas-scene\.ts$/;

/** The scene chunk followed by its static-import closure, or null when it was not emitted. */
export function sceneChunkFiles(bundle) {
  const chunks = new Map(
    Object.values(bundle)
      .filter((item) => item.type === 'chunk')
      .map((chunk) => [chunk.fileName, chunk]),
  );
  const entry = [...chunks.values()].find(
    (chunk) =>
      typeof chunk.facadeModuleId === 'string' &&
      SCENE_MODULE.test(chunk.facadeModuleId.replaceAll('\\', '/')),
  );
  if (!entry) return null;
  const files = [];
  const seen = new Set();
  const visit = (fileName) => {
    if (seen.has(fileName)) return;
    seen.add(fileName);
    files.push(fileName);
    for (const next of chunks.get(fileName)?.imports ?? []) visit(next);
  };
  visit(entry.fileName);
  return files;
}

export function injectModulePreloads(html, base, files) {
  if (!html.includes('</head>'))
    throw new Error('the /app/ page has no </head>');
  const prefix = base.endsWith('/') ? base : `${base}/`;
  const links = files
    .map(
      (file) =>
        `<link rel="modulepreload" fetchpriority="high" href="${prefix}${file}">`,
    )
    .join('');
  return html.replace('</head>', `${links}</head>`);
}

export default function atlasScenePreload({ page = 'app/index.html' } = {}) {
  let base = '/';
  let files = null;
  return {
    name: 'genomeos-atlas-scene-preload',
    hooks: {
      'astro:config:setup': ({ updateConfig }) => {
        updateConfig({
          vite: {
            plugins: [
              {
                name: 'genomeos-atlas-scene-chunks',
                applyToEnvironment: (environment) =>
                  environment.name === 'client',
                generateBundle(_options, bundle) {
                  files = sceneChunkFiles(bundle);
                },
              },
            ],
          },
        });
      },
      'astro:config:done': ({ config }) => {
        base = config.base;
      },
      'astro:build:done': async ({ dir }) => {
        if (!files) {
          throw new Error(
            'Atlas scene chunk was not emitted: AtlasExplorer must import scene/atlas-scene lazily',
          );
        }
        const root = dir.href.endsWith('/') ? dir : new URL(`${dir.href}/`);
        const target = new URL(page, root);
        await writeFile(
          target,
          injectModulePreloads(await readFile(target, 'utf8'), base, files),
        );
      },
    },
  };
}
