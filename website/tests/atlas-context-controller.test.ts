import type { Viewer } from 'cesium';
import { describe, expect, it, vi } from 'vitest';

import { ContextController } from '../src/atlas/scene/context-controller';

function fakeViewer() {
  return {
    imageryLayers: { add: vi.fn(), remove: vi.fn() },
    scene: { requestRender: vi.fn() },
  };
}

function controllerFor(viewer = fakeViewer(), token = '') {
  const warnings = vi.fn();
  const controller = new ContextController(
    viewer as unknown as Viewer,
    token,
    'https://tiles.example.org/{z}/{x}/{y}.png',
    warnings,
  );
  return { controller, viewer, warnings };
}

describe('ContextController.setBasemap', () => {
  it('treats a request for the requested basemap as a no-op', async () => {
    const { controller, viewer } = controllerFor();
    const first = controller.setBasemap('dark-streets');
    expect(controller.setBasemap('dark-streets')).toBe(first);
    await expect(first).resolves.toBe(true);
    await expect(controller.setBasemap('dark-streets')).resolves.toBe(true);
    expect(viewer.imageryLayers.add).toHaveBeenCalledTimes(1);
  });

  it('still switches away from and back to a basemap', async () => {
    const { controller, viewer } = controllerFor();
    await controller.setBasemap('dark-streets');
    await controller.setBasemap('openstreetmap');
    await controller.setBasemap('dark-streets');
    expect(viewer.imageryLayers.add).toHaveBeenCalledTimes(3);
    expect(viewer.imageryLayers.remove).toHaveBeenCalledTimes(2);
  });

  it('keeps the active basemap a no-op after a failed switch away from it', async () => {
    const { controller, viewer } = controllerFor();
    const active = controller.setBasemap('dark-streets');
    await expect(active).resolves.toBe(true);
    await expect(controller.setBasemap('aerial')).resolves.toBe(false);
    const again = controller.setBasemap('dark-streets');
    await expect(again).resolves.toBe(true);
    expect(viewer.imageryLayers.add).toHaveBeenCalledTimes(1);
    expect(viewer.imageryLayers.remove).not.toHaveBeenCalled();
    expect(again).toBe(active);
  });

  it('retries a basemap whose previous request failed', async () => {
    const { controller, warnings } = controllerFor();
    await expect(controller.setBasemap('aerial')).resolves.toBe(false);
    await expect(controller.setBasemap('aerial')).resolves.toBe(false);
    expect(warnings).toHaveBeenCalledTimes(2);
  });
});
