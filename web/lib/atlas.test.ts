/** Contract tests for P5 viewport behavior (design §11–§12). */

import {describe, expect, it} from "vitest";
import {resolutionForZoom, viewportSegments} from "./atlas";

describe("resolutionForZoom", () => {
  it("never requests a resolution that the artifact did not publish", () => {
    expect(resolutionForZoom([4], 12)).toBe(4);
    expect(resolutionForZoom([4, 6], 4)).toBe(6);
    expect(resolutionForZoom([4, 6], 12)).toBe(6);
  });
});

describe("viewportSegments", () => {
  it("uses bounded global reads at world scale", () => {
    const segments = viewportSegments({west: -180, south: -90, east: 180, north: 90}, 1);
    expect(segments).toHaveLength(8);
    expect(segments.every(({south, north}) => south >= -85 && north <= 85)).toBe(true);
  });

  it("splits a viewport that crosses the antimeridian", () => {
    expect(viewportSegments({west: 170, south: -10, east: 190, north: 10}, 4)).toEqual([
      {west: 170, south: -10, east: 180, north: 10},
      {west: -180, south: -10, east: -170, north: 10},
    ]);
  });
});
