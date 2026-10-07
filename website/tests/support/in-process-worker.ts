/**
 * In-process stand-in for the Atlas data worker (fast-load design §B.6.3): the real dispatcher
 * behind structured-clone transfer semantics, so client and provider tests run without a Worker.
 */

import {
  createDispatcher,
  type HandlerRegistry,
} from '../../src/atlas/worker/dispatcher';
import { ATLAS_WORKER_HANDLERS } from '../../src/atlas/worker/handlers';
import type { WorkerInbound } from '../../src/atlas/worker/protocol';

export class InProcessWorker extends EventTarget {
  readonly received: WorkerInbound[] = [];
  terminated = false;
  readonly #dispatch: (message: WorkerInbound) => void;

  constructor(handlers: HandlerRegistry = ATLAS_WORKER_HANDLERS) {
    super();
    this.#dispatch = createDispatcher(
      {
        post: (message, transfer) => {
          const data = structuredClone(message, { transfer });
          queueMicrotask(() => {
            if (!this.terminated) {
              this.dispatchEvent(new MessageEvent('message', { data }));
            }
          });
        },
      },
      handlers,
    );
  }

  postMessage(
    message: WorkerInbound,
    options: StructuredSerializeOptions = {},
  ): void {
    const data = structuredClone(message, options);
    this.received.push(data);
    queueMicrotask(() => {
      if (!this.terminated) this.#dispatch(data);
    });
  }

  crash(message: string): void {
    this.dispatchEvent(Object.assign(new Event('error'), { message }));
  }

  terminate(): void {
    this.terminated = true;
  }

  asWorker(): Worker {
    return this as unknown as Worker;
  }
}
