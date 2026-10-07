/**
 * Request dispatch, cancellation by id and error mapping for the Atlas data worker (fast-load
 * design §B.6.3). Cesium-free and Worker-free so vitest drives it directly.
 */

import { GosaError } from '../gosa/container';
import type {
  StepName,
  WorkerErrorCode,
  WorkerInbound,
  WorkerOutbound,
  WorkerRequest,
  WorkerRequestOf,
  WorkerRequestType,
} from './protocol';
import { createWorkerState, type WorkerState } from './state';

export interface WorkerPort {
  post(message: WorkerOutbound, transfer: Transferable[]): void;
}

export interface HandlerContext {
  readonly id: number;
  readonly signal: AbortSignal;
  readonly state: WorkerState;
  post(message: WorkerOutbound, transfer?: Transferable[]): void;
  /** `start`/`end` are `performance.now()` values of the worker realm. */
  timing(
    step: StepName,
    start: number,
    end: number,
    scope?: { artifactKey?: string | null; chunk?: number | null },
  ): void;
}

export type RequestHandler<K extends WorkerRequestType> = (
  request: WorkerRequestOf<K>,
  context: HandlerContext,
) => Promise<void> | void;

/** Every request type must have a handler; B3 adds geometry handlers here. */
export type HandlerRegistry = { [K in WorkerRequestType]: RequestHandler<K> };

export function errorCodeFor(
  error: unknown,
  signal: AbortSignal,
): WorkerErrorCode {
  if (signal.aborted) return 'cancelled';
  if (error instanceof GosaError) {
    return error.code === 'container_sha256' ? 'checksum' : 'validation';
  }
  return 'internal';
}

type AnyRequestHandler = (
  request: WorkerRequest,
  context: HandlerContext,
) => Promise<void> | void;

/**
 * The registry's own handler for `type`. An inherited lookup would resolve `toString` or
 * `constructor` to Object.prototype's, which return without throwing and so would leave the
 * request with no terminal message.
 */
function handlerFor(
  handlers: HandlerRegistry,
  type: string,
): AnyRequestHandler | undefined {
  if (!Object.hasOwn(handlers, type)) return undefined;
  const handler: unknown = (handlers as Record<string, unknown>)[type];
  return typeof handler === 'function'
    ? (handler as AnyRequestHandler)
    : undefined;
}

async function run(
  request: WorkerRequest,
  handlers: HandlerRegistry,
  context: HandlerContext,
): Promise<void> {
  const handler = handlerFor(handlers, request.type);
  if (!handler) {
    throw new Error(
      `Atlas data worker has no handler for ${String(request.type)}`,
    );
  }
  await handler(request, context);
}

export function createDispatcher(
  port: WorkerPort,
  handlers: HandlerRegistry,
  state: WorkerState = createWorkerState(),
): (message: WorkerInbound) => void {
  const running = new Map<number, AbortController>();
  const epoch = (time: number) => performance.timeOrigin + time;
  return (message) => {
    if (message.type === 'cancel') {
      running.get(message.id)?.abort();
      return;
    }
    const controller = new AbortController();
    running.set(message.id, controller);
    const context: HandlerContext = {
      id: message.id,
      post: (outbound, transfer = []) => port.post(outbound, transfer),
      signal: controller.signal,
      state,
      timing: (step, start, end, scope = {}) =>
        port.post(
          {
            artifactKey: scope.artifactKey ?? null,
            chunk: scope.chunk ?? null,
            endEpochMs: epoch(end),
            id: message.id,
            startEpochMs: epoch(start),
            step,
            type: 'step-timing',
          },
          [],
        ),
    };
    void run(message, handlers, context)
      .catch((error: unknown) => {
        port.post(
          {
            code: errorCodeFor(error, controller.signal),
            gosaCode: error instanceof GosaError ? error.code : null,
            id: message.id,
            message: error instanceof Error ? error.message : String(error),
            type: 'error',
          },
          [],
        );
      })
      .finally(() => running.delete(message.id));
  };
}
