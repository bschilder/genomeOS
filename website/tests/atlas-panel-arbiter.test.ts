import { describe, expect, it, vi } from 'vitest';

import {
  createPanelArbiter,
  type PanelKind,
} from '../src/components/atlas/panel-arbiter';

function arbiter(exclusive: boolean) {
  const changes: (PanelKind | null)[] = [];
  const panels = createPanelArbiter({
    exclusive: () => exclusive,
    onChange: (open) => changes.push(open),
  });
  return { changes, panels };
}

describe('inspector and external panel arbitration (mobile sheets design §A.1.6)', () => {
  it('closes the other panel on phones so the latest one is shown', () => {
    const { changes, panels } = arbiter(true);
    const closeInspector = vi.fn();
    const releaseInspector = panels.present('inspector', closeInspector);
    const closeExternal = vi.fn();
    panels.present('external', closeExternal);
    expect(closeInspector).toHaveBeenCalledTimes(1);
    expect(closeExternal).not.toHaveBeenCalled();
    releaseInspector();
    expect(panels.open()).toBe('external');
    expect(changes).toEqual(['inspector', 'external', 'external']);
  });

  it('keeps both panels on desktop and falls back to the earlier one', () => {
    const { panels } = arbiter(false);
    const closeInspector = vi.fn();
    panels.present('inspector', closeInspector);
    const releaseExternal = panels.present('external', vi.fn());
    expect(closeInspector).not.toHaveBeenCalled();
    expect(panels.open()).toBe('external');
    releaseExternal();
    expect(panels.open()).toBe('inspector');
  });

  it('reports no panel once every panel has closed', () => {
    const { changes, panels } = arbiter(true);
    panels.present('inspector', vi.fn())();
    expect(panels.open()).toBeNull();
    expect(changes.at(-1)).toBeNull();
  });

  it('enforces exclusion when the layout becomes a phone', () => {
    let phone = false;
    const panels = createPanelArbiter({
      exclusive: () => phone,
      onChange: () => {},
    });
    const closeInspector = vi.fn();
    panels.present('inspector', closeInspector);
    panels.present('external', vi.fn());
    phone = true;
    panels.enforce();
    expect(closeInspector).toHaveBeenCalledTimes(1);
  });
});
