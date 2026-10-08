/**
 * Typed messages of the Atlas data worker for Atlas design §11 and fast-load design §B.6.3, §B.6.5,
 * §B.6.9. A request is `{ id, type } & WorkerRequestMap[type]`, a response
 * `{ id, type } & WorkerResponseMap[type]`. Responses in `TERMINAL_RESPONSES` settle their request;
 * `chunk` and `edges-chunk` are intermediate. Callers build bodies (`*Body`); handlers receive the
 * full requests (`*Request`).
 */

import type { ArtifactRef, GridEntry } from '../contracts';
import type { ObservationAnchors } from '../geometry/anchors';
import type { EdgeChunkBuffers, EdgeColorSpec } from '../geometry/edge-buffers';
import type { NaturalEarthBuffers } from '../geometry/natural-earth';
import type { SupportChunkBuffers } from '../geometry/support-buffers';
import type { SurfaceChunkBuffers } from '../geometry/surface-buffers';
import type { GosaErrorCode } from '../gosa/container';
import type { DecodedDetail, DecodedGrid, DecodedRender } from '../gosa/types';
import type { SurfaceGeometry } from '../url-state';
import type { Metric, PaletteId } from '../visual-encoding';

export type { NaturalEarthBuffers } from '../geometry/natural-earth';

/** Observation anchor heights (one per point) and triangles (9 per point), first chunk only. */
export type ObservationAnchorBuffers = ObservationAnchors;

export interface GridExpect {
  entry: GridEntry;
  gridSha256: string;
}

export interface LookAt {
  lat: number;
  lon: number;
}

/** Surface + support chunks in camera order; anchors ride on index 0. */
export interface BuildChunksBody {
  artifactKey: string;
  geometry: SurfaceGeometry;
  gridSha256: string;
  lookAt: LookAt;
  metric: Metric;
  /** Interleaved lon, lat (degrees) of each observation in ObservationArtifact order, or null. */
  observationPoints: Float64Array | null;
  palette: PaletteId;
}

/** Every chunk again, in plan order, from cached topology and vertex means (§B.6.13). */
export interface RecolourBody {
  artifactKey: string;
  geometry: SurfaceGeometry;
  gridSha256: string;
  metric: Metric;
  palette: PaletteId;
}

export interface BuildEdgesBody {
  artifactKey: string;
  edgeColor: EdgeColorSpec;
  /** Elevation factor the returned `positions` are raised to; the scene asks for 1. */
  factor: number;
  geometry: SurfaceGeometry;
  gridSha256: string;
  lookAt: LookAt;
  metric: Metric;
  palette: PaletteId;
}

/** Border and label heights over the last parsed context; the worker finds the render tier's grid. */
export interface ContextHeightsBody {
  artifactKey: string;
  metric: Metric;
}

export interface ContextHeights {
  borderHeights: Float32Array;
  labelHeights: Float32Array;
}

export interface WorkerRequestMap {
  'build-chunks': BuildChunksBody;
  'build-edges': BuildEdgesBody;
  'context-heights': ContextHeightsBody;
  'load-detail': { buf: ArrayBuffer; ref: ArtifactRef; render: DecodedRender };
  'load-grid': { buf: ArrayBuffer; expect: GridExpect };
  'load-render': { buf: ArrayBuffer; ref: ArtifactRef };
  'parse-context': { json: ArrayBuffer };
  recolour: RecolourBody;
}

export interface WorkerResponseMap {
  chunk: {
    anchors: ObservationAnchorBuffers | null;
    artifactKey: string;
    /** The chunk's id in the plan (`surface.chunk`). */
    chunk: number;
    /** Position in send order (camera order for build-chunks, plan order for recolour). */
    index: number;
    /** True for the dedicated ±180° seam chunks, which the scheduler budgets as costly. */
    seam: boolean;
    support: SupportChunkBuffers;
    surface: SurfaceChunkBuffers;
    total: number;
  };
  'chunks-done': { artifactKey: string; total: number };
  'context-heights-ready': ContextHeights;
  'context-ready': { buffers: NaturalEarthBuffers };
  'detail-ready': { detail: DecodedDetail };
  'edges-chunk': {
    artifactKey: string;
    edges: EdgeChunkBuffers;
    index: number;
    /** Exact BufferPolylineCollection capacity over every chunk of the request. */
    primitiveCountMax: number;
    total: number;
    vertexCountMax: number;
  };
  'edges-done': { artifactKey: string; total: number };
  'grid-ready': { grid: DecodedGrid };
  'render-ready': { render: DecodedRender };
}

export type WorkerRequestType = keyof WorkerRequestMap;
export type WorkerResponseType = keyof WorkerResponseMap;

export type WorkerRequestOf<K extends WorkerRequestType> = {
  id: number;
  type: K;
} & WorkerRequestMap[K];
export type WorkerRequest = {
  [K in WorkerRequestType]: WorkerRequestOf<K>;
}[WorkerRequestType];

export type WorkerResponseOf<K extends WorkerResponseType> = {
  id: number;
  type: K;
} & WorkerResponseMap[K];
export type WorkerResponse = {
  [K in WorkerResponseType]: WorkerResponseOf<K>;
}[WorkerResponseType];

export type BuildChunksRequest = WorkerRequestOf<'build-chunks'>;
export type RecolourRequest = WorkerRequestOf<'recolour'>;
export type BuildEdgesRequest = WorkerRequestOf<'build-edges'>;
export type ParseContextRequest = WorkerRequestOf<'parse-context'>;
export type ContextHeightsRequest = WorkerRequestOf<'context-heights'>;
export type ChunkMessage = WorkerResponseOf<'chunk'>;
export type ChunksDoneMessage = WorkerResponseOf<'chunks-done'>;
export type EdgesChunkMessage = WorkerResponseOf<'edges-chunk'>;
export type EdgesDoneMessage = WorkerResponseOf<'edges-done'>;
export type ContextReadyMessage = WorkerResponseOf<'context-ready'>;
export type ContextHeightsReadyMessage =
  WorkerResponseOf<'context-heights-ready'>;

/** Cancels the in-flight request with this id. */
export interface CancelRequest {
  id: number;
  type: 'cancel';
}

export type WorkerInbound = CancelRequest | WorkerRequest;

export type WorkerErrorCode =
  'cancelled' | 'checksum' | 'internal' | 'validation';

export interface WorkerErrorMessage {
  code: WorkerErrorCode;
  gosaCode: GosaErrorCode | null;
  id: number;
  message: string;
  type: 'error';
}

export type DataStepName =
  | 'decode-detail'
  | 'decode-grid'
  | 'decode-render'
  | 'verify-detail'
  | 'verify-grid'
  | 'verify-render';
export type GeometryStepName = 'mesh' | 'support' | 'topology';
export type StepName = DataStepName | GeometryStepName;

/** A worker step on the epoch clock; the client converts it to the page time origin. */
export interface StepTimingMessage {
  /** The artifact the step worked on; null for grid steps. */
  artifactKey: string | null;
  /** The chunk id for `mesh` and `support`; null otherwise. */
  chunk: number | null;
  endEpochMs: number;
  id: number;
  startEpochMs: number;
  step: StepName;
  type: 'step-timing';
}

export type WorkerOutbound =
  StepTimingMessage | WorkerErrorMessage | WorkerResponse;

export type GeometryRequestType =
  | 'build-chunks'
  | 'build-edges'
  | 'context-heights'
  | 'parse-context'
  | 'recolour';

export type GeometryResponse =
  | ChunkMessage
  | ChunksDoneMessage
  | ContextHeightsReadyMessage
  | ContextReadyMessage
  | EdgesChunkMessage
  | EdgesDoneMessage
  | StepTimingMessage
  | WorkerErrorMessage;

/** Responses that settle their request; any other response type is intermediate. */
export const TERMINAL_RESPONSES: ReadonlySet<WorkerResponseType> =
  new Set<WorkerResponseType>([
    'chunks-done',
    'context-heights-ready',
    'context-ready',
    'detail-ready',
    'edges-done',
    'grid-ready',
    'render-ready',
  ]);
