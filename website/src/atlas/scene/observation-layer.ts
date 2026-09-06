/** Measured-sample rings and centres for Atlas design §11. */

import {
  Cartesian3,
  Color,
  GeometryInstance,
  GroundPolylineGeometry,
  GroundPolylinePrimitive,
  Material,
  PointPrimitiveCollection,
  PolylineMaterialAppearance,
  PrimitiveCollection,
} from 'cesium';

import type { Observation, ObservationArtifact } from '../contracts';

export type ObservationPick = { kind: 'observation'; sourceRecordId: string };

export interface ObservationPrimitiveGroup {
  collection: PrimitiveCollection;
  ring: GroundPolylinePrimitive;
  points: PointPrimitiveCollection;
  isReady(): boolean;
  setOpacity(opacity: number): void;
}

export function observationPickId(sourceRecordId: string): ObservationPick {
  return { kind: 'observation', sourceRecordId };
}

function radiusRing(observation: Observation, segments = 36): Cartesian3[] {
  const angularDistance = observation.radius_km / 6_371.0088;
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
    return Cartesian3.fromRadians(lon2, lat2, 750);
  });
}

function denominatorQuartiles(
  observations: readonly Observation[],
): [number, number, number] {
  const sorted = observations
    .map(({ an }) => an)
    .sort((left, right) => left - right);
  const at = (fraction: number) =>
    sorted[Math.floor((sorted.length - 1) * fraction)] ?? 1;
  return [at(0.25), at(0.5), at(0.75)];
}

function pointSize(an: number, [q25, q50, q75]: readonly number[]): number {
  if (an <= q25) return 6;
  if (an <= q50) return 8;
  if (an <= q75) return 10;
  return 12;
}

export function buildObservationLayer(
  artifact: ObservationArtifact,
): ObservationPrimitiveGroup {
  const collection = new PrimitiveCollection();
  const ringColor = Color.fromCssColorString('#9af9e2').withAlpha(0.94);
  const ringMaterial = Material.fromType('Color', { color: ringColor });
  const ring = new GroundPolylinePrimitive({
    appearance: new PolylineMaterialAppearance({ material: ringMaterial }),
    asynchronous: true,
    geometryInstances: artifact.observations.map(
      (observation) =>
        new GeometryInstance({
          geometry: new GroundPolylineGeometry({
            loop: true,
            positions: radiusRing(observation),
            width: 1.6,
          }),
          id: observationPickId(observation.source_record_id),
        }),
    ),
  });
  collection.add(ring);

  const points = new PointPrimitiveCollection();
  const quartiles = denominatorQuartiles(artifact.observations);
  for (const observation of artifact.observations) {
    points.add({
      color: Color.fromCssColorString('#e8fffa').withAlpha(0.96),
      id: observationPickId(observation.source_record_id),
      outlineColor: Color.fromCssColorString('#28d4df'),
      outlineWidth: 2,
      pixelSize: pointSize(observation.an, quartiles),
      position: Cartesian3.fromDegrees(observation.lon, observation.lat, 1_200),
    });
  }
  collection.add(points);

  return {
    collection,
    isReady: () => ring.ready,
    points,
    ring,
    setOpacity(opacity: number) {
      ringColor.alpha = 0.94 * opacity;
      for (let index = 0; index < points.length; index += 1) {
        points.get(index).color.alpha = 0.96 * opacity;
      }
    },
  };
}
