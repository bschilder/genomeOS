/** Batched H3 posterior and support geometry for Atlas design §11. */

import { cellToBoundary } from 'h3-js';
import {
  Cartesian3,
  Color,
  Material,
  MaterialAppearance,
  PolygonGeometry,
  PolygonHierarchy,
  Primitive,
  PrimitiveCollection,
  GeometryInstance,
} from 'cesium';

import type { SurfaceArtifact, SurfaceCell } from '../contracts';
import { heightForCell, type Metric } from '../visual-encoding';
import { materialForSupport, partitionSurfaceCells } from './support-material';

export type SurfacePick = { kind: 'surface'; h3Index: string };

export interface SurfaceLayerOptions {
  metric: Metric;
  elevation: boolean;
  exaggeration: number;
}

export interface ScientificPrimitiveGroup {
  collection: PrimitiveCollection;
  primitives: Primitive[];
  isReady(): boolean;
  setOpacity(opacity: number): void;
  setVisibility(surface: boolean, support: boolean): void;
}

type OpacityMaterial = {
  material: Material;
  colors: { key: 'color' | 'lightColor' | 'darkColor'; baseAlpha: number }[];
  cellAlpha?: number;
};

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

export function h3BoundaryDegrees(h3Index: string): [number, number][] {
  return cellToBoundary(h3Index).map(([lat, lon]) => [lon, lat]);
}

export function surfacePickId(cell: SurfaceCell): SurfacePick {
  return { h3Index: cell.h3_index, kind: 'surface' };
}

function geometryForCell(
  cell: SurfaceCell,
  domain: readonly [number, number],
  options: SurfaceLayerOptions,
): PolygonGeometry {
  const degrees = h3BoundaryDegrees(cell.h3_index).flat();
  const height = options.elevation
    ? heightForCell(cell, domain, options.exaggeration, options.metric)
    : 0;
  return new PolygonGeometry({
    closeBottom: height > 0,
    closeTop: true,
    extrudedHeight: height > 0 ? 0 : undefined,
    height,
    polygonHierarchy: new PolygonHierarchy(
      Cartesian3.fromDegreesArray(degrees),
    ),
    vertexFormat: MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat,
  });
}

function addPrimitive(
  collection: PrimitiveCollection,
  cells: readonly SurfaceCell[],
  material: Material,
  domain: readonly [number, number],
  options: SurfaceLayerOptions,
): Primitive {
  const primitive = new Primitive({
    appearance: new MaterialAppearance({
      closed: options.elevation,
      flat: true,
      material,
      translucent: true,
    }),
    asynchronous: true,
    geometryInstances: cells.map(
      (cell) =>
        new GeometryInstance({
          geometry: geometryForCell(cell, domain, options),
          id: surfacePickId(cell),
        }),
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
  collection.add(surfaceCollection);
  collection.add(supportCollection);
  const primitives: Primitive[] = [];
  const opacityMaterials: OpacityMaterial[] = [];
  const domain = artifact.artifact.metric_domains[options.metric];
  const partitions = partitionSurfaceCells(
    artifact.cells,
    options.metric,
    domain,
  );

  for (const group of partitions.surface) {
    const color = Color.fromCssColorString(group.color).withAlpha(0.9);
    const material = Material.fromType('Color', { color });
    opacityMaterials.push(opacityMaterial(material));
    primitives.push(
      addPrimitive(surfaceCollection, group.cells, material, domain, options),
    );
  }
  for (const support of ['unknown', 'prior_dominated'] as const) {
    const cells = partitions.support[support];
    if (cells.length === 0) continue;
    const material = materialForSupport(support);
    opacityMaterials.push(opacityMaterial(material));
    primitives.push(
      addPrimitive(supportCollection, cells, material, domain, {
        ...options,
        elevation: false,
      }),
    );
  }

  return {
    collection,
    primitives,
    isReady: () => primitives.every((primitive) => primitive.ready),
    setOpacity(opacity: number) {
      collection.show = opacity > 0;
      for (const { cellAlpha, colors, material } of opacityMaterials) {
        for (const { baseAlpha, key } of colors) {
          const color = material.uniforms[key];
          if (color instanceof Color) color.alpha = baseAlpha * opacity;
        }
        if (cellAlpha !== undefined)
          material.uniforms.cellAlpha = cellAlpha * opacity;
      }
    },
    setVisibility(surface: boolean, support: boolean) {
      surfaceCollection.show = surface;
      supportCollection.show = support;
    },
  };
}
