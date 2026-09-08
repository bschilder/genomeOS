import { describe, expect, it } from 'vitest';

import {
  aggregateTransferProgress,
  createTransferProgressTracker,
} from '../src/atlas/progress';

describe('aggregateTransferProgress', () => {
  it('combines concurrent byte transfers only when every size is known', () => {
    expect(
      aggregateTransferProgress([
        { loadedBytes: 50, totalBytes: 100 },
        { loadedBytes: 25, totalBytes: null },
      ]),
    ).toBeNull();
    expect(
      aggregateTransferProgress([
        { loadedBytes: 50, totalBytes: 100 },
        { loadedBytes: 25, totalBytes: 50 },
      ]),
    ).toBe(0.5);
  });

  it('clamps malformed transport counters without overstating completion', () => {
    expect(
      aggregateTransferProgress([{ loadedBytes: 120, totalBytes: 100 }]),
    ).toBe(1);
    expect(aggregateTransferProgress([])).toBeNull();
  });

  it('keeps a concurrent transfer indeterminate until every header arrives', () => {
    const values: (number | null)[] = [];
    const track = createTransferProgressTracker(
      ['surface', 'observations'],
      (value) => values.push(value),
    );

    track('surface')({ loadedBytes: 50, totalBytes: 100 });
    track('observations')({ loadedBytes: 25, totalBytes: 50 });

    expect(values).toEqual([null, 0.5]);
  });
});
