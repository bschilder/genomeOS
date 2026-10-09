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
  PrimitiveType,
} from 'cesium';

import type { SurfaceCell } from '../../src/atlas/contracts';
import { SURFACE_CLEARANCE_METRES } from '../../src/atlas/geometry/surface-buffers';
import {
  colorAtPosition,
  heightForCell,
  type Metric,
  type MetricDomain,
  type PaletteId,
} from '../../src/atlas/visual-encoding';
export {
  elevatedSurfaceAppearance,
  HONMOON_CONTOUR_BANDS,
  honmoonModeForGeometry,
  type ElevatedSurfaceAppearance,
} from '../../src/atlas/scene/surface-appearance';

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

interface HeightAccumulator {
  count: number;
  sum: number;
}

function isSupported(cell: SurfaceCell): boolean {
  return cell.support === 'observed' || cell.support === 'interpolated';
}

export { SURFACE_CLEARANCE_METRES };
const CPU_EXTRUSION_EPSILON_METRES = 1;

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
