/** The Atlas data worker's complete handler registry (fast-load design §B.6.3); geometry tasks spread theirs in here. */

import { DATA_HANDLERS } from './data-handlers';
import type { HandlerRegistry } from './dispatcher';

export const ATLAS_WORKER_HANDLERS: HandlerRegistry = { ...DATA_HANDLERS };
