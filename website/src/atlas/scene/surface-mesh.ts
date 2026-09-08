/** Triangulated H3 render mesh for Atlas design §11.
 *
 * This is a presentation-only bridge for cell-centred artifacts. Shared corner
 * heights average adjacent supported H3 predictions; unsupported cells never
 * contribute. Future artifact versions can replace these derived heights with
 * posterior summaries predicted directly at mesh vertices.
 */

import { cellToLatLng, cellToVertexes, vertexToLatLng } from 'h3-js';
import {
  BoundingSphere,
  Cartesian3,
  Color,
  ComponentDatatype,
  Geometry,
  GeometryAttribute,
  GeometryAttributes,
  Material,
  MaterialAppearance,
  PrimitiveType,
} from 'cesium';

import type { SurfaceCell } from '../contracts';
import type { SurfaceGeometry } from '../url-state';
import {
  colorAtPosition,
  heightForCell,
  type Metric,
  type MetricDomain,
  type PaletteId,
} from '../visual-encoding';

export interface SurfaceMeshVertex {
  height: number;
  lat: number;
  lon: number;
  value: number;
  vertexId: string | null;
}

export interface SurfaceCellMesh {
  indices: number[];
  vertices: SurfaceMeshVertex[];
}

export type ElevatedSurfaceAppearance = MaterialAppearance & {
  uniforms: { u_elevationFactor: number; u_honmoonMode: number };
};

interface HeightAccumulator {
  count: number;
  sum: number;
}

// Dense enough that a regional viewport still crosses several value isolines.
export const HONMOON_CONTOUR_BANDS = 36;

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
    material.diffuse *= v_surfaceColor;
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

function isSupported(cell: SurfaceCell): boolean {
  return cell.support === 'observed' || cell.support === 'interpolated';
}

export const SURFACE_CLEARANCE_METRES = 650;
const CPU_EXTRUSION_EPSILON_METRES = 1;

export function honmoonModeForGeometry(geometry: SurfaceGeometry): number {
  if (geometry === 'honmoon') return 1;
  if (geometry === 'honmoon-fill') return 2;
  return 0;
}

function normalizedSurfaceValue(value: number, domain: MetricDomain): number {
  if (domain[0] === domain[1]) return 0;
  return Math.min(
    1,
    Math.max(0, (value - domain[0]) / (domain[1] - domain[0])),
  );
}

function groundPosition(lon: number, lat: number): Cartesian3 {
  return Cartesian3.fromDegrees(lon, lat, SURFACE_CLEARANCE_METRES);
}

function cpuTopPosition(position: Cartesian3, extruded: boolean): Cartesian3 {
  if (!extruded) return position;
  const normal = Cartesian3.normalize(position, new Cartesian3());
  return Cartesian3.add(
    position,
    Cartesian3.multiplyByScalar(
      normal,
      CPU_EXTRUSION_EPSILON_METRES,
      new Cartesian3(),
    ),
    new Cartesian3(),
  );
}

export function surfaceVertexHeights(
  cells: readonly SurfaceCell[],
  domain: MetricDomain,
  metric: Metric,
): ReadonlyMap<string, number> {
  const accumulators = new Map<string, HeightAccumulator>();
  for (const cell of cells) {
    if (!isSupported(cell)) continue;
    const height = heightForCell(cell, domain, 1, metric);
    for (const vertexId of cellToVertexes(cell.h3_index)) {
      const value = accumulators.get(vertexId) ?? { count: 0, sum: 0 };
      value.count += 1;
      value.sum += height;
      accumulators.set(vertexId, value);
    }
  }
  return new Map(
    [...accumulators].map(([vertexId, value]) => [
      vertexId,
      value.sum / value.count,
    ]),
  );
}

export function surfaceVertexValues(
  cells: readonly SurfaceCell[],
  metric: Metric,
): ReadonlyMap<string, number> {
  const accumulators = new Map<string, HeightAccumulator>();
  for (const cell of cells) {
    if (!isSupported(cell)) continue;
    for (const vertexId of cellToVertexes(cell.h3_index)) {
      const value = accumulators.get(vertexId) ?? { count: 0, sum: 0 };
      value.count += 1;
      value.sum += cell[metric];
      accumulators.set(vertexId, value);
    }
  }
  return new Map(
    [...accumulators].map(([vertexId, value]) => [
      vertexId,
      value.sum / value.count,
    ]),
  );
}

export function surfaceMeshForCell(
  cell: SurfaceCell,
  vertexHeights: ReadonlyMap<string, number>,
  domain: MetricDomain,
  metric: Metric,
  vertexValues?: ReadonlyMap<string, number>,
): SurfaceCellMesh {
  const [centerLat, centerLon] = cellToLatLng(cell.h3_index);
  const vertexIds = cellToVertexes(cell.h3_index);
  const vertices: SurfaceMeshVertex[] = [
    {
      height: heightForCell(cell, domain, 1, metric),
      lat: centerLat,
      lon: centerLon,
      value: cell[metric],
      vertexId: null,
    },
    ...vertexIds.map((vertexId) => {
      const [lat, lon] = vertexToLatLng(vertexId);
      const height = vertexHeights.get(vertexId);
      if (height === undefined)
        throw new Error(
          `supported H3 vertex has no render height: ${vertexId}`,
        );
      return {
        height,
        lat,
        lon,
        value: vertexValues?.get(vertexId) ?? cell[metric],
        vertexId,
      };
    }),
  ];
  const indices = vertexIds.flatMap((_, index) => [
    0,
    index + 1,
    ((index + 1) % vertexIds.length) + 1,
  ]);
  return { indices, vertices };
}

export function geometryForSurfaceMesh(
  mesh: SurfaceCellMesh,
  palette: PaletteId,
  domain: MetricDomain,
): Geometry {
  const positions = new Float64Array(mesh.vertices.length * 3);
  const normals = new Float32Array(mesh.vertices.length * 3);
  const colors = new Float32Array(mesh.vertices.length * 3);
  const heights = new Float32Array(mesh.vertices.length);
  const values = new Float32Array(mesh.vertices.length);
  mesh.vertices.forEach((vertex, index) => {
    const position = groundPosition(vertex.lon, vertex.lat);
    const normal = Cartesian3.normalize(position, new Cartesian3());
    const offset = index * 3;
    positions[offset] = position.x;
    positions[offset + 1] = position.y;
    positions[offset + 2] = position.z;
    normals[offset] = normal.x;
    normals[offset + 1] = normal.y;
    normals[offset + 2] = normal.z;
    const positionInDomain = normalizedSurfaceValue(vertex.value, domain);
    const color = Color.fromCssColorString(
      colorAtPosition(palette, positionInDomain),
    );
    colors[offset] = color.red;
    colors[offset + 1] = color.green;
    colors[offset + 2] = color.blue;
    heights[index] = vertex.height;
    values[index] = positionInDomain;
  });
  const attributes = new GeometryAttributes() as GeometryAttributes & {
    elevationNormal: GeometryAttribute;
    surfaceColor: GeometryAttribute;
    surfaceHeight: GeometryAttribute;
    surfaceValue: GeometryAttribute;
  };
  attributes.normal = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: normals,
  });
  attributes.position = new GeometryAttribute({
    componentDatatype: ComponentDatatype.DOUBLE,
    componentsPerAttribute: 3,
    values: positions,
  });
  attributes.elevationNormal = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: normals,
  });
  attributes.surfaceColor = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: colors,
  });
  attributes.surfaceHeight = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 1,
    values: heights,
  });
  attributes.surfaceValue = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 1,
    values,
  });
  return new Geometry({
    attributes,
    boundingSphere: BoundingSphere.fromVertices(positions),
    indices: new Uint16Array(mesh.indices),
    primitiveType: PrimitiveType.TRIANGLES,
  });
}

function geometryForHexagonalSurfaceCell(
  cell: SurfaceCell,
  domain: MetricDomain,
  metric: Metric,
  extruded: boolean,
): Geometry {
  const [centerLat, centerLon] = cellToLatLng(cell.h3_index);
  const center = groundPosition(centerLon, centerLat);
  const corners = cellToVertexes(cell.h3_index).map((vertexId) => {
    const [lat, lon] = vertexToLatLng(vertexId);
    return { lat, lon, position: groundPosition(lon, lat) };
  });
  const height = heightForCell(cell, domain, 1, metric);
  const positions: number[] = [];
  const normals: number[] = [];
  const elevationNormals: number[] = [];
  const heights: number[] = [];
  const colors: number[] = [];
  const values: number[] = [];
  const indices: number[] = [];

  const addVertex = (
    position: Cartesian3,
    surfaceHeight: number,
    shadingNormal: Cartesian3,
  ): number => {
    const elevationNormal = Cartesian3.normalize(position, new Cartesian3());
    positions.push(position.x, position.y, position.z);
    normals.push(shadingNormal.x, shadingNormal.y, shadingNormal.z);
    elevationNormals.push(
      elevationNormal.x,
      elevationNormal.y,
      elevationNormal.z,
    );
    heights.push(surfaceHeight);
    colors.push(1, 1, 1);
    values.push(normalizedSurfaceValue(cell[metric], domain));
    return heights.length - 1;
  };

  const centerNormal = Cartesian3.normalize(center, new Cartesian3());
  const topCenter = addVertex(
    cpuTopPosition(center, extruded),
    height,
    centerNormal,
  );
  const topCorners = corners.map(({ position }) =>
    addVertex(
      cpuTopPosition(position, extruded),
      height,
      Cartesian3.normalize(position, new Cartesian3()),
    ),
  );
  for (let index = 0; index < corners.length; index += 1)
    indices.push(
      topCenter,
      topCorners[index],
      topCorners[(index + 1) % corners.length],
    );

  for (let index = 0; extruded && index < corners.length; index += 1) {
    const first = corners[index].position;
    const second = corners[(index + 1) % corners.length].position;
    const edge = Cartesian3.subtract(second, first, new Cartesian3());
    const radial = Cartesian3.normalize(
      Cartesian3.add(first, second, new Cartesian3()),
      new Cartesian3(),
    );
    const sideNormal = Cartesian3.normalize(
      Cartesian3.cross(edge, radial, new Cartesian3()),
      new Cartesian3(),
    );
    const midpoint = Cartesian3.multiplyByScalar(
      Cartesian3.add(first, second, new Cartesian3()),
      0.5,
      new Cartesian3(),
    );
    const outward = Cartesian3.subtract(midpoint, center, new Cartesian3());
    if (Cartesian3.dot(sideNormal, outward) < 0)
      Cartesian3.negate(sideNormal, sideNormal);
    const bottomFirst = addVertex(first, 0, sideNormal);
    const bottomSecond = addVertex(second, 0, sideNormal);
    const topFirst = addVertex(cpuTopPosition(first, true), height, sideNormal);
    const topSecond = addVertex(
      cpuTopPosition(second, true),
      height,
      sideNormal,
    );
    indices.push(
      bottomFirst,
      bottomSecond,
      topSecond,
      bottomFirst,
      topSecond,
      topFirst,
    );
  }

  const positionValues = new Float64Array(positions);
  const attributes = new GeometryAttributes() as GeometryAttributes & {
    elevationNormal: GeometryAttribute;
    surfaceColor: GeometryAttribute;
    surfaceHeight: GeometryAttribute;
    surfaceValue: GeometryAttribute;
  };
  attributes.position = new GeometryAttribute({
    componentDatatype: ComponentDatatype.DOUBLE,
    componentsPerAttribute: 3,
    values: positionValues,
  });
  attributes.normal = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: new Float32Array(normals),
  });
  attributes.elevationNormal = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: new Float32Array(elevationNormals),
  });
  attributes.surfaceHeight = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 1,
    values: new Float32Array(heights),
  });
  attributes.surfaceColor = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 3,
    values: new Float32Array(colors),
  });
  attributes.surfaceValue = new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute: 1,
    values: new Float32Array(values),
  });
  return new Geometry({
    attributes,
    boundingSphere: BoundingSphere.fromVertices(positionValues),
    indices: new Uint16Array(indices),
    primitiveType: PrimitiveType.TRIANGLES,
  });
}

export function geometryForFlatSurfaceCell(
  cell: SurfaceCell,
  domain: MetricDomain,
  metric: Metric,
): Geometry {
  return geometryForHexagonalSurfaceCell(cell, domain, metric, false);
}

export function geometryForExtrudedSurfaceCell(
  cell: SurfaceCell,
  domain: MetricDomain,
  metric: Metric,
): Geometry {
  return geometryForHexagonalSurfaceCell(cell, domain, metric, true);
}

export function elevatedSurfaceAppearance(
  material: Material,
  initialFactor: number,
  extruded = false,
  honmoonMode = 0,
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
  };
  return appearance;
}
