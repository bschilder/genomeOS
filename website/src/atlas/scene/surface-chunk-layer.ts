/** Worker-built surface chunks as Cesium primitives for Atlas design §11 (spec 2026-10-07 §B.6.5–§B.6.6).
 *
 * One primitive per chunk carries its supported cells; its masked cells
 * (`unknown` hatch, `prior_dominated` dots per palette bin) are added in the
 * same call, so a chunk is never visible without its mask. Every primitive is
 * built synchronously from the worker's typed arrays and picks as the chunk.
 * Child order of `collection` is surface (0), support (1), edges (2).
 */

import {
  BoundingSphere,
  Cartesian3,
  Color,
  ComponentDatatype,
  Geometry,
  GeometryAttribute,
  GeometryAttributes,
  GeometryInstance,
  Material,
  MaterialAppearance,
  Primitive,
  PrimitiveCollection,
  PrimitiveType,
} from 'cesium';

import type {
  FlatCellBuffers,
  SupportChunkBuffers,
} from '../geometry/support-buffers';
import type { SurfaceChunkBuffers } from '../geometry/surface-buffers';
import { needsLongitudeSplit } from '../geometry/wgs84';
import type { SurfaceGeometry } from '../url-state';
import { hexFromBytes } from '../visual-encoding';
import { createEdgeLayer, type EdgeLayer } from './edge-layer';
import { materialForSupport } from './support-material';
import {
  elevatedSurfaceAppearance,
  honmoonModeForGeometry,
  usesVertexColorGamma,
  type ElevatedSurfaceAppearance,
} from './surface-appearance';
import type { ScientificPrimitiveGroup, SurfaceChunkPick } from './types';

const SURFACE_MATERIAL_ALPHA = 0.9;
const EDGE_FADE_THRESHOLD = 0.05;

export interface SurfaceChunkGroupOptions {
  artifactKey: string;
  geometry: SurfaceGeometry;
  surfaceOpacity: number;
  elevationFactor: number;
  cellEdges: boolean;
  requestRender: () => void;
}

export interface SurfaceChunkGroup extends ScientificPrimitiveGroup {
  readonly artifactKey: string;
  readonly edges: EdgeLayer;
  addChunk(surface: SurfaceChunkBuffers, support: SupportChunkBuffers): void;
  chunkCount(): number;
  readyChunkCount(): number;
  opacity(): number;
}

interface OpacityMaterial {
  material: Material;
  colors: { key: 'color' | 'lightColor' | 'darkColor'; baseAlpha: number }[];
  cellAlpha?: number;
}

interface ChunkPrimitives {
  surface: Primitive | null;
  support: Primitive[];
}

type SphereBuffers = SurfaceChunkBuffers['boundingSphere'];

export function surfaceChunkPickId(
  artifactKey: string,
  chunk: number,
): SurfaceChunkPick {
  return { artifactKey, chunk, kind: 'surface-chunk' };
}

function opacityMaterial(material: Material): OpacityMaterial {
  const colors = (['color', 'lightColor', 'darkColor'] as const).flatMap(
    (key) => {
      const color = material.uniforms[key];
      return color instanceof Color ? [{ baseAlpha: color.alpha, key }] : [];
    },
  );
  const cellAlpha = material.uniforms.cellAlpha;
  return {
    cellAlpha: typeof cellAlpha === 'number' ? cellAlpha : undefined,
    colors,
    material,
  };
}

function boundingSphere(sphere: SphereBuffers): BoundingSphere {
  return new BoundingSphere(
    new Cartesian3(sphere.center[0], sphere.center[1], sphere.center[2]),
    sphere.radius,
  );
}

function floatAttribute(
  values: Float32Array,
  componentsPerAttribute: number,
): GeometryAttribute {
  return new GeometryAttribute({
    componentDatatype: ComponentDatatype.FLOAT,
    componentsPerAttribute,
    values,
  });
}

function positionAttribute(values: Float64Array): GeometryAttribute {
  return new GeometryAttribute({
    componentDatatype: ComponentDatatype.DOUBLE,
    componentsPerAttribute: 3,
    values,
  });
}

function surfaceGeometry(buffers: SurfaceChunkBuffers): Geometry {
  const attributes = new GeometryAttributes() as GeometryAttributes & {
    elevationNormal: GeometryAttribute;
    surfaceColor: GeometryAttribute;
    surfaceHeight: GeometryAttribute;
    surfaceValue: GeometryAttribute;
  };
  attributes.position = positionAttribute(buffers.positions);
  attributes.normal = floatAttribute(buffers.normals, 3);
  attributes.elevationNormal = floatAttribute(buffers.elevationNormals, 3);
  attributes.surfaceColor = floatAttribute(buffers.colors, 3);
  attributes.surfaceHeight = floatAttribute(buffers.heights, 1);
  attributes.surfaceValue = floatAttribute(buffers.values, 1);
  return new Geometry({
    attributes,
    boundingSphere: boundingSphere(buffers.boundingSphere),
    indices: buffers.indices,
    primitiveType: PrimitiveType.TRIANGLES,
  });
}

function flatCellGeometry(buffers: FlatCellBuffers): Geometry {
  const attributes = new GeometryAttributes();
  attributes.position = positionAttribute(buffers.positions);
  attributes.normal = floatAttribute(buffers.normals, 3);
  attributes.st = floatAttribute(buffers.st, 2);
  return new Geometry({
    attributes,
    boundingSphere: boundingSphere(buffers.boundingSphere),
    indices: buffers.indices,
    primitiveType: PrimitiveType.TRIANGLES,
  });
}

export function createSurfaceChunkGroup(
  options: SurfaceChunkGroupOptions,
): SurfaceChunkGroup {
  const collection = new PrimitiveCollection();
  const surfaceCollection = new PrimitiveCollection();
  const supportCollection = new PrimitiveCollection();
  const edges = createEdgeLayer({ requestRender: options.requestRender });
  collection.add(surfaceCollection);
  collection.add(supportCollection);
  collection.add(edges.collection);
  const primitives: Primitive[] = [];
  const surfacePrimitives: Primitive[] = [];
  const supportPrimitives: Primitive[] = [];
  const chunks: ChunkPrimitives[] = [];
  const opacityMaterials: OpacityMaterial[] = [];
  const appearances: ElevatedSurfaceAppearance[] = [];
  const reboundedSurfaces: Primitive[] = [];
  let fadeOpacity = 1;
  let surfaceOpacity = options.surfaceOpacity;
  let edgesVisible = options.cellEdges;
  let surfaceVisible = true;
  let supportVisible = true;
  let elevationFactor = Math.max(0, options.elevationFactor);

  const applyEdgeVisibility = () => {
    edges.collection.show =
      surfaceVisible && edgesVisible && fadeOpacity > EDGE_FADE_THRESHOLD;
  };
  const applyOpacity = (entries: readonly OpacityMaterial[]) => {
    for (const { cellAlpha, colors, material } of entries) {
      for (const { baseAlpha, key } of colors) {
        const color = material.uniforms[key];
        if (color instanceof Color)
          color.alpha = baseAlpha * fadeOpacity * surfaceOpacity;
      }
      if (cellAlpha !== undefined)
        material.uniforms.cellAlpha = cellAlpha * fadeOpacity;
    }
  };
  const track = (material: Material): OpacityMaterial => {
    const entry = opacityMaterial(material);
    opacityMaterials.push(entry);
    applyOpacity([entry]);
    return entry;
  };
  const addSurface = (
    buffers: SurfaceChunkBuffers,
    chunk: number,
  ): Primitive | null => {
    if (buffers.indices.length === 0) return null;
    const material = Material.fromType('Color', {
      color: Color.WHITE.withAlpha(SURFACE_MATERIAL_ALPHA),
    });
    track(material);
    const appearance = elevatedSurfaceAppearance(
      material,
      elevationFactor,
      options.geometry === 'extruded',
      honmoonModeForGeometry(options.geometry),
      usesVertexColorGamma(options.geometry),
    );
    appearances.push(appearance);
    // The viewer is not scene3DOnly, so Primitive runs splitLongitude on every
    // chunk. Past its early exit, Cesium replaces the worker sphere (which
    // covers the fully raised cells) with one over the unraised positions, so
    // culling against it would drop raised cells near the limb or the frustum
    // edge. Those chunks are drawn unculled while the surface is raised.
    const rebounded = needsLongitudeSplit(buffers.boundingSphere);
    const primitive = new Primitive({
      appearance,
      // Custom vertex attributes cannot use Cesium's stock geometry workers;
      // the data worker already built every array.
      asynchronous: false,
      cull: !(rebounded && elevationFactor > 0),
      geometryInstances: new GeometryInstance({
        geometry: surfaceGeometry(buffers),
        id: surfaceChunkPickId(options.artifactKey, chunk),
      }),
      show: surfaceVisible,
    });
    if (rebounded) reboundedSurfaces.push(primitive);
    surfaceCollection.add(primitive);
    surfacePrimitives.push(primitive);
    primitives.push(primitive);
    return primitive;
  };
  const addSupport = (
    buffers: FlatCellBuffers,
    material: Material,
    chunk: number,
  ): Primitive | null => {
    if (buffers.indices.length === 0) return null;
    track(material);
    const primitive = new Primitive({
      appearance: new MaterialAppearance({
        closed: false,
        flat: true,
        material,
        translucent: true,
      }),
      asynchronous: false,
      geometryInstances: new GeometryInstance({
        geometry: flatCellGeometry(buffers),
        id: surfaceChunkPickId(options.artifactKey, chunk),
      }),
      show: supportVisible,
    });
    supportCollection.add(primitive);
    supportPrimitives.push(primitive);
    primitives.push(primitive);
    return primitive;
  };

  applyEdgeVisibility();
  return {
    artifactKey: options.artifactKey,
    collection,
    edges,
    primitives,
    addChunk(surface, support) {
      const chunk = surface.chunk;
      if (support.chunk !== chunk)
        throw new Error(
          `surface chunk ${chunk} cannot take the mask of chunk ${support.chunk}`,
        );
      const entry: ChunkPrimitives = {
        support: [],
        surface: addSurface(surface, chunk),
      };
      if (support.unknown) {
        const primitive = addSupport(
          support.unknown,
          materialForSupport('unknown'),
          chunk,
        );
        if (primitive) entry.support.push(primitive);
      }
      for (const bin of support.priorDominated) {
        const primitive = addSupport(
          bin.buffers,
          materialForSupport('prior_dominated', hexFromBytes(bin.color)),
          chunk,
        );
        if (primitive) entry.support.push(primitive);
      }
      chunks.push(entry);
    },
    chunkCount: () => chunks.length,
    readyChunkCount: () =>
      chunks.filter(
        ({ support, surface }) =>
          (surface?.ready ?? true) &&
          support.every((primitive) => primitive.ready),
      ).length,
    opacity: () => fadeOpacity,
    isReady: () => primitives.every((primitive) => primitive.ready),
    readyCount: () => primitives.filter((primitive) => primitive.ready).length,
    totalCount: () => primitives.length,
    setOpacity(opacity: number) {
      fadeOpacity = opacity;
      applyEdgeVisibility();
      applyOpacity(opacityMaterials);
    },
    setSurfaceOpacity(opacity: number) {
      surfaceOpacity = opacity;
      applyOpacity(opacityMaterials);
    },
    async setCellEdges(visible: boolean) {
      edgesVisible = visible;
      applyEdgeVisibility();
    },
    setElevationFactor(factor: number, force = false) {
      const safeFactor = Math.max(0, factor);
      if (safeFactor !== elevationFactor) {
        elevationFactor = safeFactor;
        for (const appearance of appearances)
          appearance.uniforms.u_elevationFactor = safeFactor;
        for (const primitive of reboundedSurfaces)
          primitive.cull = safeFactor === 0;
      }
      edges.setElevationFactor(safeFactor, force);
    },
    async setSceneMode(mode) {
      await edges.setMode(mode);
      applyEdgeVisibility();
    },
    setVisibility(surface: boolean, support: boolean) {
      surfaceVisible = surface;
      supportVisible = support;
      for (const primitive of surfacePrimitives) primitive.show = surface;
      for (const primitive of supportPrimitives) primitive.show = support;
      applyEdgeVisibility();
    },
  };
}
