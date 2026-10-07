/**
 * Typed messages of the Atlas data worker for Atlas design §11 and fast-load design §B.6.3. Geometry
 * tasks extend `WorkerRequestMap`, `WorkerResponseMap` and `TERMINAL_RESPONSES`.
 */

import type { ArtifactRef, GridEntry } from '../contracts';
import type { GosaErrorCode } from '../gosa/container';
import type { DecodedDetail, DecodedGrid, DecodedRender } from '../gosa/types';

export interface GridExpect {
  entry: GridEntry;
  gridSha256: string;
}

export interface WorkerRequestMap {
  'load-detail': { buf: ArrayBuffer; ref: ArtifactRef; render: DecodedRender };
  'load-grid': { buf: ArrayBuffer; expect: GridExpect };
  'load-render': { buf: ArrayBuffer; ref: ArtifactRef };
}

export interface WorkerResponseMap {
  'detail-ready': { detail: DecodedDetail };
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

/** Responses that settle their request; any other response type is intermediate. */
export const TERMINAL_RESPONSES: ReadonlySet<WorkerResponseType> =
  new Set<WorkerResponseType>(['detail-ready', 'grid-ready', 'render-ready']);
