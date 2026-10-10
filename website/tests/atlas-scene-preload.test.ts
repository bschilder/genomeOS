import { describe, expect, it } from 'vitest';

import {
  injectModulePreloads,
  sceneChunkFiles,
} from '../integrations/atlas-scene-preload.mjs';

const bundle = {
  'atlas-scene': {
    facadeModuleId: '/repo/website/src/atlas/scene/atlas-scene.ts',
    fileName: '_astro/atlas-scene.B2.js',
    imports: ['_astro/cesium.C3.js', '_astro/h3-js.es.D4.js'],
    type: 'chunk',
  },
  cesium: {
    facadeModuleId: null,
    fileName: '_astro/cesium.C3.js',
    imports: ['_astro/h3-js.es.D4.js'],
    type: 'chunk',
  },
  h3: {
    facadeModuleId: null,
    fileName: '_astro/h3-js.es.D4.js',
    imports: [],
    type: 'chunk',
  },
  island: {
    facadeModuleId: '/repo/website/src/components/atlas/AtlasExplorer.tsx',
    fileName: '_astro/AtlasExplorer.A1.js',
    imports: ['_astro/h3-js.es.D4.js'],
    type: 'chunk',
  },
  style: { fileName: '_astro/app.E5.css', type: 'asset' },
};

describe('sceneChunkFiles', () => {
  it('returns the scene chunk first, then its static-import closure', () => {
    expect(sceneChunkFiles(bundle)).toEqual([
      '_astro/atlas-scene.B2.js',
      '_astro/cesium.C3.js',
      '_astro/h3-js.es.D4.js',
    ]);
  });

  it('finds the scene module on Windows paths', () => {
    const windows = {
      ...bundle,
      'atlas-scene': {
        ...bundle['atlas-scene'],
        facadeModuleId: 'C:\\repo\\website\\src\\atlas\\scene\\atlas-scene.ts',
      },
    };
    expect(sceneChunkFiles(windows)?.[0]).toBe('_astro/atlas-scene.B2.js');
  });

  it('returns null when no scene chunk was emitted', () => {
    const { 'atlas-scene': _scene, ...rest } = bundle;
    expect(sceneChunkFiles(rest)).toBeNull();
  });
});

describe('injectModulePreloads', () => {
  it('adds base-aware modulepreload links before </head>', () => {
    expect(
      injectModulePreloads(
        '<html><head><title>x</title></head><body></body></html>',
        '/genomeOS',
        ['_astro/atlas-scene.B2.js'],
      ),
    ).toBe(
      '<html><head><title>x</title><link rel="modulepreload" fetchpriority="high" href="/genomeOS/_astro/atlas-scene.B2.js"></head><body></body></html>',
    );
  });

  it('refuses a page without a head', () => {
    expect(() =>
      injectModulePreloads('<body></body>', '/', ['_astro/x.js']),
    ).toThrow(/<\/head>/);
  });
});
