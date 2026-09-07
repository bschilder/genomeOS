/** Measured-observation symbols and source-supported footprints for Atlas design §11. */

import { latLngToCell } from 'h3-js';
import {
  BillboardCollection,
  Cartesian3,
  Color,
  EllipsoidGeometry,
  Material,
  MaterialAppearance,
  Matrix4,
  PinBuilder,
  PointPrimitiveCollection,
  PolylineCollection,
  Primitive,
  PrimitiveCollection,
  GeometryInstance,
  Transforms,
  VerticalOrigin,
} from 'cesium';

import type {
  Observation,
  ObservationArtifact,
  SurfaceArtifact,
  SurfaceCell,
} from '../contracts';
import {
  observationColor,
  observationDomains,
  observationSize,
  validateObservationSizeRange,
  type ObservationColorVariable,
  type ObservationShape,
  type ObservationSizeRange,
  type ObservationSizeVariable,
} from '../observation-encoding';
import { heightForCell, type Metric } from '../visual-encoding';

export type ObservationPick = { kind: 'observation'; sourceRecordId: string };

export interface ObservationLayerOptions {
  colorVariable: ObservationColorVariable;
  elevation: boolean;
  exaggeration: number;
  hemisphereRange: ObservationSizeRange;
  metric: Metric;
  pointRange: ObservationSizeRange;
  samplingAreas: boolean;
  shape: ObservationShape;
  sizeVariable: ObservationSizeVariable;
  surface: SurfaceArtifact;
}

export interface ObservationPrimitiveGroup {
  collection: PrimitiveCollection;
  isReady(): boolean;
  setOpacity(opacity: number): void;
  setVisibility(symbols: boolean, samplingAreas: boolean): void;
}

interface GeographicPoint {
  lat: number;
  lon: number;
}

interface SymbolEncoding {
  color: string;
  observation: Observation;
  size: number;
  topHeight: number;
}

const EARTH_RADIUS_KM = 6_371.0088;
const SYMBOL_CLEARANCE_METRES = 4_000;

export function observationPickId(sourceRecordId: string): ObservationPick {
  return { kind: 'observation', sourceRecordId };
}

function samplingAreaMaterial(): Material {
  return Material.fromType('Color', {
    color: Color.fromCssColorString('#9af9e2').withAlpha(0.9),
  });
}

function surfaceCellMap(surface: SurfaceArtifact): Map<string, SurfaceCell> {
  return new Map(surface.cells.map((cell) => [cell.h3_index, cell]));
}

export function surfaceHeightAt(
  point: GeographicPoint,
  surface: SurfaceArtifact,
  metric: Metric,
  elevation: boolean,
  exaggeration: number,
  cells = surfaceCellMap(surface),
): number {
  if (!elevation) return 0;
  const h3Index = latLngToCell(
    point.lat,
    point.lon,
    surface.artifact.resolution,
  );
  const cell = cells.get(h3Index);
  if (!cell) return 0;
  return heightForCell(
    cell,
    surface.artifact.metric_domains[metric],
    exaggeration,
    metric,
  );
}

function radiusRing(
  observation: Observation,
  heightAt: (point: GeographicPoint) => number,
  segments = 48,
): Cartesian3[] {
  const angularDistance = observation.radius_km / EARTH_RADIUS_KM;
  const lat1 = (observation.lat * Math.PI) / 180;
  const lon1 = (observation.lon * Math.PI) / 180;
  return Array.from({ length: segments }, (_, index) => {
    const bearing = (index / segments) * Math.PI * 2;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(angularDistance) +
        Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing),
    );
    const lon2 =
      lon1 +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
        Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2),
      );
    const point = {
      lat: (lat2 * 180) / Math.PI,
      lon: (lon2 * 180) / Math.PI,
    };
    return Cartesian3.fromRadians(
      lon2,
      lat2,
      heightAt(point) + SYMBOL_CLEARANCE_METRES,
    );
  });
}

function encodings(
  artifact: ObservationArtifact,
  options: ObservationLayerOptions,
): SymbolEncoding[] {
  const domains = observationDomains(artifact.observations);
  const range =
    options.shape === 'hemisphere'
      ? options.hemisphereRange
      : options.pointRange;
  validateObservationSizeRange(options.shape, range);
  const sizeDomain =
    options.sizeVariable === 'fixed'
      ? ([0, 1] as const)
      : domains[options.sizeVariable];
  const colorDomain =
    options.colorVariable === 'white' || options.colorVariable === 'study'
      ? ([0, 1] as const)
      : domains[options.colorVariable];
  const cells = surfaceCellMap(options.surface);
  return artifact.observations.map((observation) => ({
    color: observationColor(observation, options.colorVariable, colorDomain),
    observation,
    size: observationSize(observation, options.sizeVariable, range, sizeDomain),
    topHeight:
      surfaceHeightAt(
        observation,
        options.surface,
        options.metric,
        options.elevation,
        options.exaggeration,
        cells,
      ) + SYMBOL_CLEARANCE_METRES,
  }));
}

function buildHemispheres(symbols: readonly SymbolEncoding[]): {
  collection: PrimitiveCollection;
  materials: Material[];
  primitives: Primitive[];
} {
  const collection = new PrimitiveCollection();
  const materials: Material[] = [];
  const primitives: Primitive[] = [];
  const byColor = new Map<string, SymbolEncoding[]>();
  for (const symbol of symbols)
    byColor.set(symbol.color, [...(byColor.get(symbol.color) ?? []), symbol]);
  for (const [cssColor, group] of byColor) {
    const color = Color.fromCssColorString(cssColor).withAlpha(0.9);
    const material = Material.fromType('Color', { color });
    const primitive = new Primitive({
      appearance: new MaterialAppearance({
        closed: false,
        faceForward: true,
        flat: true,
        material,
        translucent: true,
      }),
      asynchronous: true,
      geometryInstances: group.map(({ observation, size, topHeight }) => {
        const centre = Cartesian3.fromDegrees(
          observation.lon,
          observation.lat,
          topHeight,
        );
        const radiusMetres = size * 1_000;
        return new GeometryInstance({
          geometry: new EllipsoidGeometry({
            maximumCone: Math.PI / 2,
            radii: new Cartesian3(radiusMetres, radiusMetres, radiusMetres),
            stackPartitions: 16,
            slicePartitions: 24,
            vertexFormat:
              MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat,
          }),
          id: observationPickId(observation.source_record_id),
          modelMatrix: Transforms.eastNorthUpToFixedFrame(
            centre,
            undefined,
            new Matrix4(),
          ),
        });
      }),
    });
    materials.push(material);
    primitives.push(primitive);
    collection.add(primitive);
  }
  return { collection, materials, primitives };
}

export function buildObservationLayer(
  artifact: ObservationArtifact,
  options: ObservationLayerOptions,
): ObservationPrimitiveGroup {
  const collection = new PrimitiveCollection();
  const rings = new PolylineCollection();
  const points = new PointPrimitiveCollection();
  const pins = new BillboardCollection();
  const symbols = encodings(artifact, options);
  const cells = surfaceCellMap(options.surface);
  const heightAt = (point: GeographicPoint) =>
    surfaceHeightAt(
      point,
      options.surface,
      options.metric,
      options.elevation,
      options.exaggeration,
      cells,
    );
  const ringBaseColors: Color[] = [];
  for (const observation of artifact.observations) {
    const material = samplingAreaMaterial();
    const color = material.uniforms.color as Color;
    ringBaseColors.push(color.clone());
    rings.add({
      id: observationPickId(observation.source_record_id),
      loop: true,
      material,
      positions: radiusRing(observation, heightAt),
      width: 2,
    });
  }
  rings.show = options.samplingAreas;
  collection.add(rings);

  const hemisphere = buildHemispheres(
    options.shape === 'hemisphere' ? symbols : [],
  );
  collection.add(hemisphere.collection);

  const pinBuilder = new PinBuilder();
  const pointBaseColors: Color[] = [];
  const pinBaseColors: Color[] = [];
  for (const symbol of symbols) {
    const { color, observation, size, topHeight } = symbol;
    const cesiumColor = Color.fromCssColorString(color).withAlpha(0.97);
    const position = Cartesian3.fromDegrees(
      observation.lon,
      observation.lat,
      topHeight,
    );
    if (options.shape === 'circle') {
      pointBaseColors.push(cesiumColor.clone());
      points.add({
        color: cesiumColor,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        id: observationPickId(observation.source_record_id),
        outlineColor: Color.fromCssColorString('#071426').withAlpha(0.92),
        outlineWidth: 2,
        pixelSize: size,
        position,
      });
    } else if (options.shape === 'pin') {
      pinBaseColors.push(cesiumColor.clone());
      pins.add({
        color: cesiumColor,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        id: observationPickId(observation.source_record_id),
        image: pinBuilder.fromColor(Color.WHITE, Math.round(size * 1.7)),
        position,
        verticalOrigin: VerticalOrigin.BOTTOM,
      });
    }
  }
  collection.add(points);
  collection.add(pins);

  const symbolCollections = [hemisphere.collection, points, pins];
  return {
    collection,
    isReady: () => hemisphere.primitives.every((primitive) => primitive.ready),
    setOpacity(opacity: number) {
      for (let index = 0; index < rings.length; index += 1) {
        const material = rings.get(index).material;
        const color = material.uniforms.color;
        if (color instanceof Color)
          color.alpha = ringBaseColors[index].alpha * opacity;
      }
      for (let index = 0; index < points.length; index += 1) {
        points.get(index).color.alpha = pointBaseColors[index].alpha * opacity;
      }
      for (let index = 0; index < pins.length; index += 1) {
        pins.get(index).color.alpha = pinBaseColors[index].alpha * opacity;
      }
      for (const material of hemisphere.materials) {
        const color = material.uniforms.color;
        if (color instanceof Color) color.alpha = 0.9 * opacity;
      }
    },
    setVisibility(symbolsVisible: boolean, samplingAreas: boolean) {
      rings.show = symbolsVisible && samplingAreas;
      for (const symbolCollection of symbolCollections)
        symbolCollection.show = symbolsVisible;
    },
  };
}
