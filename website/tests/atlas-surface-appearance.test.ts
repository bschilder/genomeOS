import { Color, Material } from 'cesium';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  elevatedSurfaceAppearance,
  HONMOON_CONTOUR_BANDS,
  honmoonModeForGeometry,
  SURFACE_CLEARANCE_METRES,
  usesVertexColorGamma,
} from '../src/atlas/scene/surface-appearance';
import * as legacyMesh from './legacy/surface-mesh';
import { stubCesiumBrowserImageTypes } from './helpers/cesium-stubs';

afterEach(() => vi.unstubAllGlobals());

function whiteMaterial(): Material {
  return Material.fromType('Color', { color: Color.WHITE.withAlpha(0.9) });
}

describe('elevated surface appearance', () => {
  it('gamma-corrects vertex colours only for per-cell bin geometries', () => {
    expect(usesVertexColorGamma('hexagons')).toBe(true);
    expect(usesVertexColorGamma('extruded')).toBe(true);
    expect(usesVertexColorGamma('triangles')).toBe(false);
    expect(usesVertexColorGamma('honmoon')).toBe(false);
    expect(usesVertexColorGamma('honmoon-fill')).toBe(false);
  });

  it('exposes the gamma switch as a uniform that defaults off', () => {
    stubCesiumBrowserImageTypes();
    const smooth = elevatedSurfaceAppearance(whiteMaterial(), 0);
    const binned = elevatedSurfaceAppearance(whiteMaterial(), 2, true, 0, true);

    expect(smooth.uniforms).toEqual({
      u_elevationFactor: 0,
      u_honmoonMode: 0,
      u_vertexColorGamma: 0,
    });
    expect(binned.uniforms).toEqual({
      u_elevationFactor: 2,
      u_honmoonMode: 0,
      u_vertexColorGamma: 1,
    });
    expect(binned.closed).toBe(true);
  });

  it('multiplies the gamma-corrected vertex colour into the material diffuse', () => {
    stubCesiumBrowserImageTypes();
    const source = elevatedSurfaceAppearance(
      whiteMaterial(),
      0,
    ).fragmentShaderSource;

    expect(source).toContain('uniform float u_vertexColorGamma;');
    expect(source).toContain('czm_gammaCorrect(v_surfaceColor)');
    expect(source).toContain('material.diffuse *= surfaceColor;');
    expect(source).not.toContain('material.diffuse *= v_surfaceColor;');
  });

  it('keeps the legacy surface-mesh exports as the same functions', () => {
    expect(legacyMesh.elevatedSurfaceAppearance).toBe(
      elevatedSurfaceAppearance,
    );
    expect(legacyMesh.honmoonModeForGeometry).toBe(honmoonModeForGeometry);
    expect(legacyMesh.HONMOON_CONTOUR_BANDS).toBe(HONMOON_CONTOUR_BANDS);
    expect(legacyMesh.SURFACE_CLEARANCE_METRES).toBe(SURFACE_CLEARANCE_METRES);
    expect(SURFACE_CLEARANCE_METRES).toBe(650);
  });
});
