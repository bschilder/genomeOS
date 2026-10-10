/** Data-tier handlers: verify, decode and validate grid, render and detail (fast-load design §B.2–§B.3, §B.6.3). */

import { decodeDetail, decodeGrid, decodeRender } from '../gosa/decode';
import type { DecodedDetail, DecodedGrid, DecodedRender } from '../gosa/types';
import { artifactKeyFor } from '../surface-columns';
import type { HandlerContext, HandlerRegistry } from './dispatcher';
import type { DataStepName } from './protocol';

type DataHandlers = Pick<
  HandlerRegistry,
  'load-detail' | 'load-grid' | 'load-render'
>;

function stepTimer(
  context: HandlerContext,
  tier: 'detail' | 'grid' | 'render',
  artifactKey: string | null = null,
) {
  return (phase: 'decode' | 'verify', start: number, end: number) =>
    context.timing(`${phase}-${tier}` as DataStepName, start, end, {
      artifactKey,
    });
}

/** Copies are transferred; the worker keeps its own arrays for later geometry requests. */
export function copyGrid(grid: DecodedGrid): DecodedGrid {
  return { ...grid, h3Hi: grid.h3Hi.slice(), h3Lo: grid.h3Lo.slice() };
}

export function copyRender(render: DecodedRender): DecodedRender {
  return {
    artifact: render.artifact,
    post_mean: render.post_mean.slice(),
    post_sd: render.post_sd.slice(),
    support: render.support.slice(),
  };
}

function detailTransfer(detail: DecodedDetail): ArrayBuffer[] {
  return [
    detail.post_mean.buffer,
    detail.post_sd.buffer,
    detail.q025.buffer,
    detail.q975.buffer,
    detail.posterior_contraction.buffer,
    detail.dist_nearest_obs_km.buffer,
  ];
}

function residentGrid(
  context: HandlerContext,
  gridSha256: string,
  id: string,
): DecodedGrid {
  const grid = context.state.grids.get(gridSha256);
  if (!grid) {
    throw new Error(
      `Atlas worker has no grid ${gridSha256} for ${id}; load the grid first`,
    );
  }
  return grid;
}

export const DATA_HANDLERS: DataHandlers = {
  'load-detail': (request, context) => {
    const grid = residentGrid(
      context,
      request.ref.web.grid_sha256,
      request.ref.id,
    );
    const detail = decodeDetail(
      request.buf,
      { grid, ref: request.ref, render: request.render },
      stepTimer(context, 'detail', artifactKeyFor(request.ref)),
    );
    context.post(
      { detail, id: request.id, type: 'detail-ready' },
      detailTransfer(detail),
    );
  },
  'load-grid': (request, context) => {
    const grid = decodeGrid(
      request.buf,
      request.expect,
      stepTimer(context, 'grid'),
    );
    context.state.grids.set(grid.gridSha256, grid);
    const copy = copyGrid(grid);
    context.post({ grid: copy, id: request.id, type: 'grid-ready' }, [
      copy.h3Lo.buffer,
      copy.h3Hi.buffer,
    ]);
  },
  'load-render': (request, context) => {
    const grid = residentGrid(
      context,
      request.ref.web.grid_sha256,
      request.ref.id,
    );
    const key = artifactKeyFor(request.ref);
    const render = decodeRender(
      request.buf,
      { grid, ref: request.ref },
      stepTimer(context, 'render', key),
    );
    context.state.renders.set(key, render);
    context.state.renderGrids.set(key, request.ref.web.grid_sha256);
    const copy = copyRender(render);
    context.post({ id: request.id, render: copy, type: 'render-ready' }, [
      copy.support.buffer,
      copy.post_mean.buffer,
      copy.post_sd.buffer,
    ]);
  },
};
