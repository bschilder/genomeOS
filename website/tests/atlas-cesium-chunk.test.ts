/** The Cesium bundle has one stable chunk name for long-frame attribution (fast-load design §B.1). */
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const astroDirectory = path.resolve(import.meta.dirname, '../dist/_astro');
const CESIUM_MARKER = 'approximateTerrainHeights';

describe('Cesium chunk', () => {
  it('emits all Cesium code in one cesium.<hash>.js chunk', () => {
    const scripts = readdirSync(astroDirectory).filter((name) =>
      name.endsWith('.js'),
    );
    const cesium = scripts.filter((name) => /^cesium\.[\w-]+\.js$/.test(name));
    expect(cesium).toHaveLength(1);
    const withCesium = scripts.filter((name) =>
      readFileSync(path.join(astroDirectory, name), 'utf8').includes(
        CESIUM_MARKER,
      ),
    );
    expect(withCesium).toEqual(cesium);
  });
});
