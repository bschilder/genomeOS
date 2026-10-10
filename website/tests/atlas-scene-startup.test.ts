import { describe, expect, it, vi } from 'vitest';

import { hideSkyUntilReady } from '../src/atlas/scene/scene-policy';

describe('scene start-up policy', () => {
  it('hides the sky box until revealed, once', () => {
    const scene = { requestRender: vi.fn(), skyBox: { show: true } };
    const reveal = hideSkyUntilReady(scene);
    expect(scene.skyBox.show).toBe(false);

    reveal();
    reveal();
    expect(scene.skyBox.show).toBe(true);
    expect(scene.requestRender).toHaveBeenCalledTimes(1);
  });

  it('tolerates a scene without a sky box', () => {
    expect(() => hideSkyUntilReady({ requestRender: vi.fn() })()).not.toThrow();
  });
});
