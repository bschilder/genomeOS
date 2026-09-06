import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

describe('Cesium static runtime', () => {
  it.each(['Assets', 'ThirdParty', 'Widgets', 'Workers'])(
    'copies %s into the production build',
    (directory) => {
      expect(existsSync(resolve('dist/cesium', directory))).toBe(true);
    },
  );
});
