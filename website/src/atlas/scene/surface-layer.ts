/** Batched H3 posterior and support geometry for Atlas design §11. */

import { cellToBoundary, cellToLatLng } from 'h3-js';
import {
  BufferPolyline,
  BufferPolylineCollection,
  BufferPolylineMaterial,
  Cartesian3,
  Color,
  ComponentDatatype,
  Material,
  MaterialAppearance,
  PolygonGeometry,
  PolygonHierarchy,
  Polyline,
  PolylineCollection,
  Primitive,
  PrimitiveCollection,
  GeometryInstance,
} from 'cesium';

import type { SurfaceArtifact, SurfaceCell } from '../contracts';
import type {
  EdgeColorMode,
  ExplorerSceneMode,
  SurfaceGeometry,
} from '../url-state';
import { heightForCell, type Metric, type PaletteId } from '../visual-encoding';
import {
  elevatedSurfaceAppearance,
  geometryForExtrudedSurfaceCell,
  geometryForFlatSurfaceCell,
  geometryForSurfaceMesh,
  honmoonModeForGeometry,
  SURFACE_CLEARANCE_METRES,
  surfaceMeshForCell,
  surfaceVertexHeights,
  surfaceVertexValues,
  type ElevatedSurfaceAppearance,
} from './surface-mesh';
import {
  materialForSupport,
  paletteBinsForCells,
  partitionSurfaceCells,
} from './support-material';

export type SurfacePick = { kind: 'surface'; h3Index: string };

export interface SurfaceLayerOptions {
  metric: Metric;
  elevation: boolean;
  exaggeration: number;
  palette: PaletteId;
  opacity: number;
  cellEdges: boolean;
  edgeColorMode: EdgeColorMode;
  edgeFixedColor: string;
  geometry: SurfaceGeometry;
  mode: ExplorerSceneMode;
}

export function brighterEdgeColor(cssColor: string): string {
  const source = Color.fromCssColorString(cssColor);
  return Color.lerp(source, Color.WHITE, 0.46, new Color()).toCssHexString();
}

export function edgeColorForSurface(
  surfaceColor: string,
  mode: EdgeColorMode,
  fixedColor: string,
): string {
  return mode === 'matched' ? brighterEdgeColor(surfaceColor) : fixedColor;
}

export interface ScientificPrimitiveGroup {
  collection: PrimitiveCollection;
  primitives: Primitive[];
  isReady(): boolean;
  readyCount(): number;
  setOpacity(opacity: number): void;
  setSurfaceOpacity(opacity: number): void;
  setCellEdges(visible: boolean): Promise<void>;
  setElevationFactor(factor: number, force?: boolean): void;
  setSceneMode(mode: ExplorerSceneMode): Promise<void>;
  setVisibility(surface: boolean, support: boolean): void;
}

type OpacityMaterial = {
  applySurfaceOpacity: boolean;
  material: Material;
  colors: { key: 'color' | 'lightColor' | 'darkColor'; baseAlpha: number }[];
  cellAlpha?: number;
};

interface EdgeDefinition {
  baseHeights: Float64Array;
  basePositions: Float64Array;
  normals: Float64Array;
  positions: Float64Array;
}

interface EdgeInput {
  color: Color;
  definition: EdgeDefinition;
}

type EdgeRenderer = 'buffer' | 'projected';

// Cesium cannot tessellate a polygon whose edges collectively enclose a pole
// (https://github.com/CesiumGS/cesium/issues/4801). Only those two H3 cells are
// split into triangles, with a renderer-only seam kept just off the singularity.
const POLAR_SEAM_LONGITUDE = 179;
const POLE_EPSILON_DEGREES = 0.000001;
const EDGE_CLEARANCE_METRES = 1_050;

export function edgeRendererForMode(mode: ExplorerSceneMode): EdgeRenderer {
  return mode === 'globe' ? 'buffer' : 'projected';
}

async function yieldEdgeBuild(index: number): Promise<void> {
  if (index > 0 && index % 256 === 0)
    await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0));
}

function opacityMaterial(
  material: Material,
  applySurfaceOpacity = true,
): OpacityMaterial {
  const colors = (['color', 'lightColor', 'darkColor'] as const).flatMap(
    (key) => {
      const color = material.uniforms[key];
      return color instanceof Color ? [{ baseAlpha: color.alpha, key }] : [];
    },
  );
  const cellAlpha = material.uniforms.cellAlpha;
  return {
    applySurfaceOpacity,
    cellAlpha: typeof cellAlpha === 'number' ? cellAlpha : undefined,
    colors,
    material,
  };
}

export function h3BoundaryDegrees(h3Index: string): [number, number][] {
  return cellToBoundary(h3Index).map(([lat, lon]) => [lon, lat]);
}

export function h3PolygonParts(h3Index: string): [number, number][][] {
  const boundary = h3BoundaryDegrees(h3Index);
  const longitudeSpan =
    Math.max(...boundary.map(([lon]) => lon)) -
    Math.min(...boundary.map(([lon]) => lon));
  const isPolar =
    longitudeSpan > 180 && boundary.some(([, lat]) => Math.abs(lat) > 89);
  if (!isPolar) return [boundary];

  const [centerLat, centerLon] = cellToLatLng(h3Index);
  const center: [number, number] = [centerLon, centerLat];
  const poleLatitude = Math.sign(centerLat) * (90 - POLE_EPSILON_DEGREES);
  const parts: [number, number][][] = [];
  for (let index = 0; index < boundary.length; index += 1) {
    const first = boundary[index];
    const second = boundary[(index + 1) % boundary.length];
    if (Math.abs(first[0] - second[0]) <= 180) {
      parts.push([center, first, second]);
      continue;
    }
    const firstSeam: [number, number] = [
      Math.sign(first[0]) * POLAR_SEAM_LONGITUDE,
      poleLatitude,
    ];
    const secondSeam: [number, number] = [
      Math.sign(second[0]) * POLAR_SEAM_LONGITUDE,
      poleLatitude,
    ];
    parts.push([center, first, firstSeam], [center, secondSeam, second]);
  }
  return parts;
}

export function surfacePickId(cell: SurfaceCell): SurfacePick {
  return { h3Index: cell.h3_index, kind: 'surface' };
}

function geometryForCell(cell: SurfaceCell): PolygonGeometry[] {
  return h3PolygonParts(cell.h3_index).map(
    (part) =>
      new PolygonGeometry({
        height: SURFACE_CLEARANCE_METRES,
        polygonHierarchy: new PolygonHierarchy(
          Cartesian3.fromDegreesArray(part.flat()),
        ),
        vertexFormat: MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat,
      }),
  );
}

function coordinateKey(lon: number, lat: number): string {
  return `${lon.toFixed(7)}:${lat.toFixed(7)}`;
}

function edgeDefinitionsForCell(
  cell: SurfaceCell,
  domain: readonly [number, number],
  metric: Metric,
  vertexHeights: ReadonlyMap<string, number>,
  initialFactor: number,
  geometry: SurfaceGeometry,
): EdgeDefinition[] {
  const mesh = surfaceMeshForCell(cell, vertexHeights, domain, metric);
  const heightByCoordinate = new Map(
    mesh.vertices.map(({ height, lat, lon }) => [
      coordinateKey(lon, lat),
      height,
    ]),
  );
  const centerHeight = heightForCell(cell, domain, 1, metric);
  return h3PolygonParts(cell.h3_index).map((part) => {
    const closed = [...part, part[0]];
    const baseHeights = new Float64Array(closed.length);
    const basePositions = new Float64Array(closed.length * 3);
    const normals = new Float64Array(closed.length * 3);
    const positions = new Float64Array(closed.length * 3);
    closed.forEach(([lon, lat], index) => {
      const ground = Cartesian3.fromDegrees(lon, lat);
      const normal = Cartesian3.normalize(ground, new Cartesian3());
      const base = Cartesian3.add(
        ground,
        Cartesian3.multiplyByScalar(
          normal,
          EDGE_CLEARANCE_METRES,
          new Cartesian3(),
        ),
        new Cartesian3(),
      );
      const baseHeight =
        geometry === 'triangles' ||
        geometry === 'honmoon' ||
        geometry === 'honmoon-fill'
          ? (heightByCoordinate.get(coordinateKey(lon, lat)) ?? centerHeight)
          : centerHeight;
      const offset = index * 3;
      baseHeights[index] = baseHeight;
      basePositions[offset] = base.x;
      basePositions[offset + 1] = base.y;
      basePositions[offset + 2] = base.z;
      normals[offset] = normal.x;
      normals[offset + 1] = normal.y;
      normals[offset + 2] = normal.z;
      for (let axis = 0; axis < 3; axis += 1)
        positions[offset + axis] =
          basePositions[offset + axis] +
          normals[offset + axis] * baseHeight * initialFactor;
    });
    return { baseHeights, basePositions, normals, positions };
  });
}

function updateEdgePositions(
  definition: EdgeDefinition,
  factor: number,
): Float64Array {
  for (let index = 0; index < definition.positions.length; index += 1)
    definition.positions[index] =
      definition.basePositions[index] +
      definition.normals[index] *
        definition.baseHeights[Math.floor(index / 3)] *
        factor;
  return definition.positions;
}

function addSurfacePrimitive(
  collection: PrimitiveCollection,
  cells: readonly SurfaceCell[],
  material: Material,
  domain: readonly [number, number],
  options: SurfaceLayerOptions,
  vertexHeights: ReadonlyMap<string, number>,
  vertexValues: ReadonlyMap<string, number>,
  elevationAppearances: ElevatedSurfaceAppearance[],
): Primitive {
  const initialFactor = options.elevation ? options.exaggeration : 0;
  const appearance = elevatedSurfaceAppearance(
    material,
    initialFactor,
    options.geometry === 'extruded',
    honmoonModeForGeometry(options.geometry),
  );
  const primitive = new Primitive({
    appearance,
    // Custom vertex attributes cannot use Cesium's stock geometry workers.
    // Geometry is already prepared and batched by palette before this point.
    asynchronous: false,
    geometryInstances: cells.map(
      (cell) =>
        new GeometryInstance({
          geometry:
            options.geometry === 'extruded'
              ? geometryForExtrudedSurfaceCell(cell, domain, options.metric)
              : options.geometry === 'hexagons'
                ? geometryForFlatSurfaceCell(cell, domain, options.metric)
                : geometryForSurfaceMesh(
                    surfaceMeshForCell(
                      cell,
                      vertexHeights,
                      domain,
                      options.metric,
                      vertexValues,
                    ),
                    options.palette,
                    domain,
                  ),
          id: surfacePickId(cell),
        }),
    ),
  });
  collection.add(primitive);
  elevationAppearances.push(appearance);
  return primitive;
}

function addSupportPrimitive(
  collection: PrimitiveCollection,
  cells: readonly SurfaceCell[],
  material: Material,
): Primitive {
  const primitive = new Primitive({
    appearance: new MaterialAppearance({
      closed: false,
      flat: true,
      material,
      translucent: true,
    }),
    asynchronous: true,
    geometryInstances: cells.flatMap((cell) =>
      geometryForCell(cell).map(
        (geometry) =>
          new GeometryInstance({
            geometry,
            id: surfacePickId(cell),
          }),
      ),
    ),
  });
  collection.add(primitive);
  return primitive;
}

export function buildSurfaceLayer(
  artifact: SurfaceArtifact,
  options: SurfaceLayerOptions,
): ScientificPrimitiveGroup {
  const collection = new PrimitiveCollection();
  const surfaceCollection = new PrimitiveCollection();
  const supportCollection = new PrimitiveCollection();
  const edgeCollection = new PrimitiveCollection();
  collection.add(surfaceCollection);
  collection.add(supportCollection);
  collection.add(edgeCollection);
  const primitives: Primitive[] = [];
  const opacityMaterials: OpacityMaterial[] = [];
  const elevationAppearances: ElevatedSurfaceAppearance[] = [];
  let fadeOpacity = 1;
  let surfaceOpacity = options.opacity;
  let edgesVisible = options.cellEdges;
  let surfaceVisible = true;
  let elevationFactor = options.elevation ? options.exaggeration : 0;
  let lastElevationUpdate = Number.NEGATIVE_INFINITY;
  const domain = artifact.artifact.metric_domains[options.metric];
  const partitions = partitionSurfaceCells(
    artifact.cells,
    options.metric,
    domain,
    options.palette,
  );
  const supportedCells = partitions.surface.flatMap(({ cells }) => cells);
  const vertexHeights = surfaceVertexHeights(
    supportedCells,
    domain,
    options.metric,
  );
  const vertexValues = surfaceVertexValues(supportedCells, options.metric);

  for (const group of partitions.surface) {
    const smoothGeometry =
      options.geometry === 'triangles' ||
      options.geometry === 'honmoon' ||
      options.geometry === 'honmoon-fill';
    const color = Color.fromCssColorString(
      smoothGeometry ? '#ffffff' : group.color,
    ).withAlpha(0.9);
    const material = Material.fromType('Color', { color });
    opacityMaterials.push(opacityMaterial(material));
    primitives.push(
      addSurfacePrimitive(
        surfaceCollection,
        group.cells,
        material,
        domain,
        options,
        vertexHeights,
        vertexValues,
        elevationAppearances,
      ),
    );
  }

  const edgeDefinitions: EdgeDefinition[] = [];
  let edgeBuffer: BufferPolylineCollection | null = null;
  let edgeBufferPromise: Promise<void> | null = null;
  let projectedEdges: PolylineCollection | null = null;
  let projectedEdgesPromise: Promise<void> | null = null;
  let projectedLines: Polyline[] = [];
  let edgeInputs: EdgeInput[] | null = null;
  let edgeInputsPromise: Promise<EdgeInput[]> | null = null;
  let edgeMode = options.mode;
  const ensureEdgeInputs = (): Promise<EdgeInput[]> => {
    if (edgeInputs) return Promise.resolve(edgeInputs);
    if (edgeInputsPromise) return edgeInputsPromise;
    const edgeGroups =
      options.edgeColorMode === 'matched'
        ? partitions.surface.map(({ cells, color }) => ({
            cells,
            color: edgeColorForSurface(
              color,
              options.edgeColorMode,
              options.edgeFixedColor,
            ),
          }))
        : [{ cells: supportedCells, color: options.edgeFixedColor }];
    edgeInputsPromise = (async () => {
      const inputs: EdgeInput[] = [];
      let index = 0;
      for (const group of edgeGroups) {
        const color = Color.fromCssColorString(group.color).withAlpha(0.92);
        for (const cell of group.cells) {
          for (const definition of edgeDefinitionsForCell(
            cell,
            domain,
            options.metric,
            vertexHeights,
            0,
            options.geometry,
          ))
            inputs.push({ color, definition });
          index += 1;
          await yieldEdgeBuild(index);
        }
      }
      edgeDefinitions.push(...inputs.map(({ definition }) => definition));
      edgeInputs = inputs;
      return inputs;
    })();
    return edgeInputsPromise;
  };
  const ensureEdgeBuffer = (): Promise<void> => {
    if (edgeBufferPromise) return edgeBufferPromise;
    if (supportedCells.length === 0) return Promise.resolve();
    edgeBufferPromise = (async () => {
      const inputs = await ensureEdgeInputs();
      edgeBuffer = new BufferPolylineCollection({
        allowPicking: false,
        positionDatatype: ComponentDatatype.DOUBLE,
        primitiveCountMax: inputs.length,
        vertexCountMax: inputs.reduce(
          (total, { definition }) => total + definition.positions.length / 3,
          0,
        ),
      });
      edgeCollection.add(edgeBuffer);
      const polyline = new BufferPolyline();
      for (let index = 0; index < inputs.length; index += 1) {
        const { color, definition } = inputs[index];
        updateEdgePositions(definition, elevationFactor);
        edgeBuffer.add(
          {
            material: new BufferPolylineMaterial({ color, width: 2 }),
            positions: definition.positions,
          },
          polyline,
        );
        await yieldEdgeBuild(index);
      }
    })();
    return edgeBufferPromise;
  };
  const projectedPositions = (definition: EdgeDefinition): Cartesian3[] => {
    const positions: Cartesian3[] = [];
    for (let index = 0; index < definition.positions.length; index += 3)
      positions.push(
        Cartesian3.fromElements(
          definition.positions[index],
          definition.positions[index + 1],
          definition.positions[index + 2],
        ),
      );
    return positions;
  };
  const ensureProjectedEdges = (): Promise<void> => {
    if (projectedEdgesPromise) return projectedEdgesPromise;
    if (supportedCells.length === 0) return Promise.resolve();
    projectedEdgesPromise = (async () => {
      const inputs = await ensureEdgeInputs();
      const materials = new Map<string, Material>();
      projectedEdges = new PolylineCollection();
      edgeCollection.add(projectedEdges);
      for (let index = 0; index < inputs.length; index += 1) {
        const { color, definition } = inputs[index];
        const key = color.toCssHexString();
        let material = materials.get(key);
        if (!material) {
          material = Material.fromType('Color', { color });
          materials.set(key, material);
        }
        updateEdgePositions(definition, elevationFactor);
        projectedLines.push(
          projectedEdges.add({
            material,
            positions: projectedPositions(definition),
            width: 2,
          }),
        );
        await yieldEdgeBuild(index);
      }
    })();
    return projectedEdgesPromise;
  };
  const updateEdgeRenderer = async (): Promise<void> => {
    const renderer = edgeRendererForMode(edgeMode);
    if (edgesVisible) {
      if (renderer === 'buffer') await ensureEdgeBuffer();
      else await ensureProjectedEdges();
    }
    const currentRenderer = edgeRendererForMode(edgeMode);
    if (edgeBuffer) edgeBuffer.show = currentRenderer === 'buffer';
    if (projectedEdges) projectedEdges.show = currentRenderer === 'projected';
  };
  if (options.cellEdges) void updateEdgeRenderer();
  const unknownCells = partitions.support.unknown;
  if (unknownCells.length > 0) {
    const material = materialForSupport('unknown');
    opacityMaterials.push(opacityMaterial(material));
    primitives.push(
      addSupportPrimitive(supportCollection, unknownCells, material),
    );
  }
  const priorBins = paletteBinsForCells(
    partitions.support.prior_dominated,
    options.metric,
    domain,
    options.palette,
  );
  for (const group of priorBins) {
    const material = materialForSupport('prior_dominated', group.color);
    opacityMaterials.push(opacityMaterial(material));
    primitives.push(
      addSupportPrimitive(supportCollection, group.cells, material),
    );
  }

  return {
    collection,
    primitives,
    isReady: () => primitives.every((primitive) => primitive.ready),
    readyCount: () => primitives.filter((primitive) => primitive.ready).length,
    setOpacity(opacity: number) {
      fadeOpacity = opacity;
      edgeCollection.show = surfaceVisible && edgesVisible && opacity > 0.05;
      for (const {
        applySurfaceOpacity,
        cellAlpha,
        colors,
        material,
      } of opacityMaterials) {
        for (const { baseAlpha, key } of colors) {
          const color = material.uniforms[key];
          if (color instanceof Color)
            color.alpha =
              baseAlpha * opacity * (applySurfaceOpacity ? surfaceOpacity : 1);
        }
        if (cellAlpha !== undefined)
          material.uniforms.cellAlpha = cellAlpha * opacity;
      }
    },
    setSurfaceOpacity(opacity: number) {
      surfaceOpacity = opacity;
      this.setOpacity(fadeOpacity);
    },
    async setCellEdges(visible: boolean) {
      edgesVisible = visible;
      if (visible) await updateEdgeRenderer();
      edgeCollection.show = surfaceVisible && visible && fadeOpacity > 0.05;
    },
    setElevationFactor(factor: number, force = false) {
      const safeFactor = Math.max(0, factor);
      if (safeFactor === elevationFactor) return;
      elevationFactor = safeFactor;
      for (const appearance of elevationAppearances)
        appearance.uniforms.u_elevationFactor = safeFactor;
      if (!edgeBuffer && !projectedEdges) return;
      const now = performance.now();
      if (!force && safeFactor !== 0 && now - lastElevationUpdate < 50) return;
      lastElevationUpdate = now;
      for (const definition of edgeDefinitions)
        updateEdgePositions(definition, safeFactor);
      if (edgeBuffer) {
        const polyline = new BufferPolyline();
        for (let index = 0; index < edgeBuffer.primitiveCount; index += 1) {
          const definition = edgeDefinitions[index];
          edgeBuffer.get(index, polyline);
          polyline.setPositions(definition.positions);
        }
      }
      if (projectedEdges)
        projectedLines.forEach((line, index) => {
          const definition = edgeDefinitions[index];
          line.positions = projectedPositions(definition);
        });
    },
    async setSceneMode(mode: ExplorerSceneMode) {
      edgeMode = mode;
      await updateEdgeRenderer();
      edgeCollection.show =
        surfaceVisible && edgesVisible && fadeOpacity > 0.05;
    },
    setVisibility(surface: boolean, support: boolean) {
      surfaceVisible = surface;
      surfaceCollection.show = surface;
      supportCollection.show = support;
      edgeCollection.show = surface && edgesVisible && fadeOpacity > 0.05;
    },
  };
}
