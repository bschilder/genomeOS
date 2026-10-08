/**
 * The Atlas data worker's complete handler registry (fast-load design §B.6.3): the data-tier
 * handlers plus the geometry handlers, which share the dispatcher's state, port and cancellation.
 * The grid's topology is warmed right after `grid-ready` (§B.6 "topology as soon as the grid arrives").
 */

import { DATA_HANDLERS } from './data-handlers';
import type {
  HandlerContext,
  HandlerRegistry,
  RequestHandler,
} from './dispatcher';
import {
  createGeometryWorker,
  messageChannelYield,
  type GeometryWorker,
} from './geometry-handlers';
import type { GeometryRequestType } from './protocol';
import type { WorkerState } from './state';

interface GeometryRuntime {
  signals: Map<number, AbortSignal>;
  worker: GeometryWorker;
}

const runtimes = new WeakMap<WorkerState, GeometryRuntime>();

/** The geometry worker bound to this dispatcher's state and port. */
export function geometryRuntime(context: HandlerContext): GeometryRuntime {
  let runtime = runtimes.get(context.state);
  if (!runtime) {
    const { state } = context;
    const post = context.post;
    const signals = new Map<number, AbortSignal>();
    runtime = {
      signals,
      worker: createGeometryWorker({
        grid: (gridSha256) => state.grids.get(gridSha256),
        gridFor: (artifactKey) => {
          const gridSha256 = state.renderGrids.get(artifactKey);
          return gridSha256 === undefined
            ? undefined
            : state.grids.get(gridSha256);
        },
        isCancelled: (id) => signals.get(id)?.aborted ?? false,
        now: () => performance.timeOrigin + performance.now(),
        post: (message, transfer) => post(message, transfer),
        render: (artifactKey) => state.renders.get(artifactKey),
        yieldToEventLoop: messageChannelYield(),
      }),
    };
    runtimes.set(state, runtime);
  }
  return runtime;
}

function geometry<K extends GeometryRequestType>(type: K): RequestHandler<K> {
  return async (request, context) => {
    const runtime = geometryRuntime(context);
    runtime.signals.set(context.id, context.signal);
    try {
      const handler = runtime.worker.handlers[type] as unknown as (
        message: typeof request,
      ) => Promise<void>;
      await handler(request);
    } finally {
      runtime.signals.delete(context.id);
    }
  };
}

export const ATLAS_WORKER_HANDLERS: HandlerRegistry = {
  ...DATA_HANDLERS,
  'build-chunks': geometry('build-chunks'),
  'build-edges': geometry('build-edges'),
  'context-heights': geometry('context-heights'),
  'load-grid': async (request, context) => {
    await DATA_HANDLERS['load-grid'](request, context);
    geometryRuntime(context).worker.warmGrid(
      request.id,
      request.expect.gridSha256,
    );
  },
  'parse-context': geometry('parse-context'),
  recolour: geometry('recolour'),
};
