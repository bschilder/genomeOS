import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import { StaticAtlasDataProvider } from '../src/atlas/static-provider';

const ref: ArtifactRef = {
  artifact_format: 1,
  assumptions: ['fixture'],
  correlation_range_km: 400,
  data_version: 'map-2026-08',
  entity_type: 'variant',
  hf_dataset: 'bschilder/genomeos-data',
  hf_revision: 'fc17bc1c1d96a0d0766746dcf26277ccdc669717',
  id: 'hbs-rs334',
  label: 'HbS (rs334)',
  likelihood: 'beta_binomial',
  measurement: 'allele_frequency',
  metric_domains: { post_mean: [0.01, 0.2], post_sd: [0.001, 0.08] },
  model_version: 'v1',
  n_cells: 1,
  n_observations: 0,
  observations_available: true,
  observations_sha256: 'b'.repeat(64),
  observations_url: 'hbs-rs334.observations.json',
  registry_version: 'map-survey-coordinates-v1',
  resolution: 3,
  support_counts: { observed: 1 },
  surface_sha256: 'a'.repeat(64),
  surface_url: 'hbs-rs334.surface.json',
  variant_id: 'chr11-5227002-T-A',
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('StaticAtlasDataProvider', () => {
  it('fails a stalled request at the configured deadline', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: URL, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(init.signal?.reason);
          });
        });
      }),
    );
    const provider = new StaticAtlasDataProvider('/data/atlas/', 25);

    const request = provider.getCatalog();
    const rejection = expect(request).rejects.toThrow(
      'Atlas request timed out after 25 ms: catalog.json',
    );
    await vi.advanceTimersByTimeAsync(25);

    await rejection;
    vi.useRealTimers();
  });

  it('passes cancellation through to fetch', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: URL, init?: RequestInit) => {
        if (init?.signal?.aborted) {
          return Promise.reject(new DOMException('Aborted', 'AbortError'));
        }
        return Promise.resolve(new Response('{}'));
      }),
    );
    const provider = new StaticAtlasDataProvider('/genomeOS/data/atlas/');
    const controller = new AbortController();
    controller.abort();

    await expect(provider.getCatalog(controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    });
  });

  it('resolves deployment-aware URLs and validates identity', async () => {
    const response = {
      artifact: {
        artifact_format: ref.artifact_format,
        data_version: ref.data_version,
        entity_type: ref.entity_type,
        hf_dataset: ref.hf_dataset,
        hf_revision: ref.hf_revision,
        id: ref.id,
        label: ref.label,
        measurement: ref.measurement,
        metric_domains: ref.metric_domains,
        model_version: ref.model_version,
        registry_version: ref.registry_version,
        resolution: ref.resolution,
        variant_id: ref.variant_id,
      },
      cells: [
        {
          dist_nearest_obs_km: 10,
          h3_index: '83754efffffffff',
          post_mean: 0.1,
          post_sd: 0.02,
          posterior_contraction: 0.8,
          q025: 0.06,
          q975: 0.14,
          support: 'observed',
        },
      ],
      schema_version: 1,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(response), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const provider = new StaticAtlasDataProvider('/genomeOS/data/atlas/');
    const first = await provider.getSurface(ref);
    await expect(provider.getSurface(ref)).resolves.toBe(first);
    expect(first).toMatchObject({
      artifact: { id: ref.id },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/genomeOS/data/atlas/hbs-rs334.surface.json',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...response,
          artifact: { ...response.artifact, id: 'wrong' },
        }),
      ),
    );
    const invalidProvider = new StaticAtlasDataProvider(
      '/genomeOS/data/atlas/',
    );
    await expect(invalidProvider.getSurface(ref)).rejects.toThrow(/identity/i);
  });

  it('reports HTTP failures instead of falling back', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('missing', { status: 404 })),
    );
    const provider = new StaticAtlasDataProvider('/data/atlas/');

    await expect(provider.getSurface(ref)).rejects.toThrow(/404/);
  });

  it('does not request an observation payload declared unavailable', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const surfaceOnly = {
      ...ref,
      observations_available: false,
      observations_sha256: null,
      observations_url: null,
    } as unknown as ArtifactRef;
    const provider = new StaticAtlasDataProvider('/data/atlas/');

    await expect(provider.getObservations(surfaceOnly)).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
