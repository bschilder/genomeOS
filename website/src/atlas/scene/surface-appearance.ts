/** Elevated surface shading for Atlas design §11 (spec 2026-10-07 §B.6.5).
 *
 * Smooth modes carry their sRGB colour per vertex and multiply it into a
 * white material unchanged. Hexagon and extruded modes carry the sRGB
 * palette-bin colour per vertex and gamma-correct it in the fragment shader,
 * which reproduces the former per-bin material colour under high dynamic
 * range and is the identity without it.
 */

import { Material, MaterialAppearance } from 'cesium';

import { SURFACE_CLEARANCE_METRES } from '../geometry/surface-buffers';
import type { SurfaceGeometry } from '../url-state';

// One owner: the Cesium-free constant from Task 44 (B3.5), re-exported for the scene modules.
export { SURFACE_CLEARANCE_METRES };

// Dense enough that a regional viewport still crosses several value isolines.
export const HONMOON_CONTOUR_BANDS = 36;

export type ElevatedSurfaceAppearance = MaterialAppearance & {
  uniforms: {
    u_elevationFactor: number;
    u_honmoonMode: number;
    u_vertexColorGamma: number;
  };
};

const ELEVATED_SURFACE_VERTEX_SHADER = `
in vec3 position3DHigh;
in vec3 position3DLow;
in vec3 normal;
in vec3 elevationNormal;
in vec3 surfaceColor;
in float surfaceHeight;
in float surfaceValue;
in float batchId;

uniform float u_elevationFactor;

out vec3 v_positionEC;
out vec3 v_normalEC;
out vec3 v_surfaceColor;
out float v_surfaceValue;

void main()
{
    vec4 p = czm_computePosition();
    p.xyz += elevationNormal * surfaceHeight * u_elevationFactor;

    v_positionEC = (czm_modelViewRelativeToEye * p).xyz;
    v_normalEC = czm_normal * normal;
    v_surfaceColor = surfaceColor;
    v_surfaceValue = surfaceValue;
    gl_Position = czm_modelViewProjectionRelativeToEye * p;
}
`;

const ELEVATED_SURFACE_FRAGMENT_SHADER = `
in vec3 v_positionEC;
in vec3 v_normalEC;
in vec3 v_surfaceColor;
in float v_surfaceValue;

uniform float u_honmoonMode;
uniform float u_vertexColorGamma;

void main()
{
    vec3 positionToEyeEC = -v_positionEC;
    vec3 normalEC = normalize(v_normalEC);
#ifdef FACE_FORWARD
    normalEC = faceforward(normalEC, vec3(0.0, 0.0, 1.0), -normalEC);
#endif
    czm_materialInput materialInput;
    materialInput.normalEC = normalEC;
    materialInput.positionToEyeEC = positionToEyeEC;
    czm_material material = czm_getMaterial(materialInput);
    vec3 surfaceColor = u_vertexColorGamma > 0.5
        ? czm_gammaCorrect(v_surfaceColor)
        : v_surfaceColor;
    material.diffuse *= surfaceColor;
    if (u_honmoonMode > 0.5) {
        float contourCoordinate = v_surfaceValue * ${HONMOON_CONTOUR_BANDS.toFixed(1)};
        float distanceToLine = abs(fract(contourCoordinate + 0.5) - 0.5);
        float screenDerivative = clamp(fwidth(contourCoordinate), 0.006, 0.22);
        float pixelsFromLine = distanceToLine / screenDerivative;
        float core = 1.0 - smoothstep(0.45, 1.15, pixelsFromLine);
        float halo = 1.0 - smoothstep(0.7, 4.5, pixelsFromLine);
        vec3 luminous = mix(v_surfaceColor, vec3(1.0), 0.2 + core * 0.3);
        float fillAlpha = u_honmoonMode > 1.5 ? material.alpha * 0.28 : 0.0;
        float lineAlpha = material.alpha * max(core, halo * 0.42);
        vec3 fillColor = v_surfaceColor * 0.55;
        out_FragColor = vec4(
            mix(fillColor, luminous * 1.35, max(core, halo * 0.62)),
            max(fillAlpha, lineAlpha)
        );
        return;
    }
#ifdef FLAT
    out_FragColor = vec4(material.diffuse + material.emission, material.alpha);
#else
    out_FragColor = czm_phong(normalize(positionToEyeEC), material, czm_lightDirectionEC);
#endif
}
`;

export function honmoonModeForGeometry(geometry: SurfaceGeometry): number {
  if (geometry === 'honmoon') return 1;
  if (geometry === 'honmoon-fill') return 2;
  return 0;
}

export function usesVertexColorGamma(geometry: SurfaceGeometry): boolean {
  return geometry === 'hexagons' || geometry === 'extruded';
}

export function elevatedSurfaceAppearance(
  material: Material,
  initialFactor: number,
  extruded = false,
  honmoonMode = 0,
  vertexColorGamma = false,
): ElevatedSurfaceAppearance {
  const appearance = new MaterialAppearance({
    closed: extruded,
    flat: !extruded,
    material,
    materialSupport: MaterialAppearance.MaterialSupport.BASIC,
    translucent: true,
    fragmentShaderSource: ELEVATED_SURFACE_FRAGMENT_SHADER,
    vertexShaderSource: ELEVATED_SURFACE_VERTEX_SHADER,
  }) as ElevatedSurfaceAppearance;
  appearance.uniforms = {
    u_elevationFactor: initialFactor,
    u_honmoonMode: honmoonMode,
    u_vertexColorGamma: vertexColorGamma ? 1 : 0,
  };
  return appearance;
}
