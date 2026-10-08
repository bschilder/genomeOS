import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ArtifactRef } from '../src/atlas/contracts';
import {
  NATURAL_EARTH_BORDERS,
  NATURAL_EARTH_PLACES,
} from '../src/atlas/context-sources';
import {
  aggregateTransferProgress,
  createTransferProgressTracker,
  type TransferProgress,
} from '../src/atlas/progress';
import { StaticAtlasDataProvider } from '../src/atlas/static-provider';
import { artifactKeyFor, cellAt } from '../src/atlas/surface-columns';
import {
  AtlasWorkerClient,
  AtlasWorkerError,
  isArtifactValidationError,
} from '../src/atlas/worker/client';
import {
  goldenBytes,
  goldenCatalog,
  goldenCatalogRaw,
  goldenSurfaceJson,
  onlyGrid,
} from './support/gosa-builder';
import { InProcessWorker } from './support/in-process-worker';

const ORIGIN = 'http://test.invalid';
const BASE = '/genomeOS/data/atlas/';
const DOCUMENT = `${ORIGIN}/genomeOS/app/`;
const catalog = goldenCatalog();
const { entry } = onlyGrid(catalog);
const ref = catalog.artifacts[0];
const formatTwo = catalog.artifacts.find(
  (artifact) => artifact.artifact_format >= 2,
)!;

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function createProvider(
  options: { inlineCatalog?: unknown; stallMs?: number } = {},
) {
  return new StaticAtlasDataProvider({
    artifactDataBase: BASE,
    documentBase: () => DOCUMENT,
    inlineCatalog:
      'inlineCatalog' in options ? options.inlineCatalog : goldenCatalogRaw(),
    requestStallMs: options.stallMs,
    siteDataBase: BASE,
    worker: new AtlasWorkerClient(new InProcessWorker().asWorker()),
  });
}

function keyOf(url: unknown): string {
  const parsed = new URL(String(url));
  expect(parsed.origin).toBe(ORIGIN);
  expect(parsed.pathname.startsWith(BASE)).toBe(true);
  return parsed.pathname.slice(BASE.length);
}

function goldenFetch(overrides: Record<string, () => Response> = {}) {
  const fetchMock = vi.fn(
    async (url: string | URL | Request, _init?: RequestInit) => {
      const key = keyOf(url);
      return overrides[key]?.() ?? new Response(goldenBytes(key));
    },
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function callsTo(
  fetchMock: ReturnType<typeof goldenFetch>,
  key: string,
): number {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(`/${key}`))
    .length;
}

function initFor(
  fetchMock: ReturnType<typeof goldenFetch>,
  key: string,
): RequestInit | undefined {
  return fetchMock.mock.calls.find(([url]) =>
    String(url).endsWith(`/${key}`),
  )?.[1];
}

function flipped(bytes: Uint8Array): Uint8Array<ArrayBuffer> {
  const copy = bytes.slice();
  copy[copy.length - 1] ^= 0xff;
  return copy;
}

function observationsFixture(count: number) {
  const artifact = goldenSurfaceJson(ref).artifact;
  const payload = {
    artifact,
    observations: Array.from({ length: count }, (_, index) => ({
      ac: 3,
      an: 100,
      assay: 'genotype',
      citation_text: 'Fixture survey',
      cohort_id: `cohort-${index}`,
      disease_ascertainment_excluded: false,
      ingest_version: 'fixture',
      lat: 10,
      lon: 20,
      population_label: `Population ${index}`,
      radius_km: 25,
      sampling_design: 'population_random',
      source_locator: `row ${index}`,
      source_record_id: `fixture:${index}`,
      source_url: 'https://example.org/source',
      study_id: 'fixture-study',
      study_label: 'Fixture study',
    })),
    schema_version: 1,
  };
  const body = new TextEncoder().encode(JSON.stringify(payload));
  const observed = {
    ...ref,
    n_observations: count,
    observations_available: true,
    observations_bytes: body.byteLength,
    observations_sha256: 'e'.repeat(64),
    observations_url: 'fixture.observations.json',
  } as ArtifactRef;
  return { body, observed, payload };
}

function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start: (value) => {
      controller = value;
    },
  });
  return { controller, stream };
}

describe('StaticAtlasDataProvider catalog', () => {
  it('resolves the inline catalog without a network request', async () => {
    const fetchMock = goldenFetch();
    const provider = createProvider();
    const progress = vi.fn();
    const first = await provider.getCatalog(undefined, progress);
    expect(first).toEqual(catalog);
    await expect(provider.getCatalog()).resolves.toBe(first);
    expect(progress).toHaveBeenCalledWith({ loadedBytes: 1, totalBytes: 1 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports a page without a usable inline catalog', async () => {
    await expect(
      createProvider({ inlineCatalog: undefined }).getCatalog(),
    ).rejects.toThrow(
      'The Atlas catalog is missing from this page or is not valid JSON.',
    );
    await expect(
      createProvider({ inlineCatalog: {} }).getCatalog(),
    ).rejects.toThrow();
  });

  it('resolves catalog context sources against the site data base', async () => {
    const provider = createProvider();
    expect(provider.contextSourceUrl(catalog, NATURAL_EARTH_BORDERS)).toBe(
      `${ORIGIN}${BASE}${catalog.context_sources.find(({ id }) => id === NATURAL_EARTH_BORDERS)!.url}`,
    );
    expect(provider.contextSourceUrl(catalog, NATURAL_EARTH_PLACES)).toMatch(
      /^http:\/\/test\.invalid\//,
    );
    expect(() => provider.contextSourceUrl(catalog, 'missing-source')).toThrow(
      'The Atlas catalog declares no context source "missing-source"',
    );
  });

  it('refuses data bases that cannot be resolved safely', () => {
    const worker = new AtlasWorkerClient(new InProcessWorker().asWorker());
    expect(
      () =>
        new StaticAtlasDataProvider({
          artifactDataBase:
            'https://storage.googleapis.com/example-bucket/atlas/web',
          inlineCatalog: goldenCatalogRaw(),
          siteDataBase: BASE,
          worker,
        }),
    ).toThrow('Atlas data base must end in "/"');
    expect(
      () =>
        new StaticAtlasDataProvider({
          artifactDataBase: BASE,
          inlineCatalog: goldenCatalogRaw(),
          siteDataBase: 'data/atlas/',
          worker,
        }),
    ).toThrow(/root-relative or an absolute https URL/);
  });
});

describe('StaticAtlasDataProvider surface tiers', () => {
  it('loads the columnar grid and render tiers from the artifact base', async () => {
    const fetchMock = goldenFetch();
    const provider = createProvider();
    const surface = await provider.getSurface(ref);
    expect(surface.artifactKey).toBe(artifactKeyFor(ref));
    expect(surface.grid.n).toBe(ref.n_cells);
    expect(surface.support.length).toBe(ref.n_cells);
    expect(surface.detail).toBeNull();
    await expect(provider.getSurface(ref)).resolves.toBe(surface);
    expect(callsTo(fetchMock, entry.url)).toBe(1);
    expect(callsTo(fetchMock, ref.web.render.url)).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      `${ORIGIN}${BASE}${ref.web.render.url}`,
      expect.objectContaining({
        credentials: 'same-origin',
        mode: 'cors',
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it('fetches the shared grid once for every artifact', async () => {
    const fetchMock = goldenFetch();
    const provider = createProvider();
    await Promise.all(
      catalog.artifacts.map((artifact) => provider.getSurface(artifact)),
    );
    expect(callsTo(fetchMock, entry.url)).toBe(1);
    for (const artifact of catalog.artifacts) {
      expect(callsTo(fetchMock, artifact.web.render.url)).toBe(1);
    }
  });

  it('passes caller cancellation to its render fetch but keeps the shared grid fetch', async () => {
    const fetchMock = vi.fn(
      (_url: string | URL | Request, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(init.signal?.reason),
          );
        }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const provider = createProvider({ stallMs: 1_000 });
    const controller = new AbortController();
    const request = provider.getSurface(ref, controller.signal);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    const renderInit = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith(ref.web.render.url),
    )?.[1];
    const gridInit = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith(entry.url),
    )?.[1];
    expect(renderInit?.signal?.aborted).toBe(true);
    expect(gridInit?.signal?.aborted).toBe(false);
  });

  it('retries a failed tier from the network instead of caching the failure', async () => {
    let renderAttempts = 0;
    let gridAttempts = 0;
    const fetchMock = goldenFetch({
      [entry.url]: () =>
        gridAttempts++ === 0
          ? new Response('busy', { status: 503 })
          : new Response(goldenBytes(entry.url)),
      [ref.web.render.url]: () =>
        renderAttempts++ < 2
          ? new Response('busy', { status: 503 })
          : new Response(goldenBytes(ref.web.render.url)),
    });
    const provider = createProvider();
    await expect(provider.getSurface(ref)).rejects.toThrow(
      /Atlas request failed with HTTP 503/,
    );
    await expect(provider.getSurface(ref)).rejects.toThrow(
      `Atlas request failed with HTTP 503: ${ref.web.render.url}`,
    );
    await expect(provider.getSurface(ref)).resolves.toMatchObject({
      artifactKey: artifactKeyFor(ref),
    });
    expect(callsTo(fetchMock, entry.url)).toBe(2);
    expect(callsTo(fetchMock, ref.web.render.url)).toBe(3);
  });

  it('rejects a corrupted render object as a validation failure and caches nothing', async () => {
    let corrupt = true;
    goldenFetch({
      [ref.web.render.url]: () =>
        new Response(
          corrupt
            ? flipped(goldenBytes(ref.web.render.url))
            : goldenBytes(ref.web.render.url),
        ),
    });
    const provider = createProvider();
    const failure = await provider
      .getSurface(ref)
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(AtlasWorkerError);
    expect(failure).toMatchObject({ code: 'checksum' });
    expect(isArtifactValidationError(failure)).toBe(true);
    corrupt = false;
    await expect(provider.getSurface(ref)).resolves.toMatchObject({
      artifactKey: artifactKeyFor(ref),
    });
  });

  it('loads the detail tier at low priority and attaches it to the cached surface', async () => {
    const fetchMock = goldenFetch();
    const provider = createProvider();
    const surface = await provider.getSurface(ref);
    const detail = await provider.getSurfaceDetail(ref);
    expect(surface.detail).toBe(detail);
    expect(initFor(fetchMock, ref.web.detail.url)).toMatchObject({
      credentials: 'same-origin',
      mode: 'cors',
      priority: 'low',
    });
    expect(cellAt(surface, 0)).toEqual(goldenSurfaceJson(ref).cells[0]);
    await expect(provider.getSurfaceDetail(ref)).resolves.toBe(detail);
    expect(callsTo(fetchMock, ref.web.detail.url)).toBe(1);
  });

  it('rejects a detail tier that fails its checksum without attaching it', async () => {
    goldenFetch({
      [ref.web.detail.url]: () =>
        new Response(flipped(goldenBytes(ref.web.detail.url))),
    });
    const provider = createProvider();
    const surface = await provider.getSurface(ref);
    await expect(provider.getSurfaceDetail(ref)).rejects.toMatchObject({
      code: 'checksum',
    });
    expect(surface.detail).toBeNull();
  });

  it('reports HTTP failures instead of falling back', async () => {
    goldenFetch({
      [ref.web.render.url]: () => new Response('missing', { status: 404 }),
    });
    await expect(createProvider().getSurface(ref)).rejects.toThrow(/404/);
  });
});

describe('StaticAtlasDataProvider transfer rules', () => {
  it('fails a transfer only after the stall window passes without a new chunk', async () => {
    vi.useFakeTimers();
    const { body, observed } = observationsFixture(4);
    const { controller, stream } = controlledStream();
    // A real fetch errors its body stream when the request signal aborts; the mock must too.
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
        init?.signal?.addEventListener('abort', () =>
          controller.error(init.signal?.reason),
        );
        return new Response(stream);
      }),
    );
    const provider = createProvider({ stallMs: 25 });
    let outcome: string | null = null;
    void provider.getObservations(observed).then(
      () => (outcome = 'resolved'),
      (error: Error) => (outcome = error.message),
    );
    await vi.advanceTimersByTimeAsync(0);
    const quarter = Math.ceil(body.byteLength / 4);
    for (let index = 0; index < 3; index += 1) {
      controller.enqueue(body.subarray(index * quarter, (index + 1) * quarter));
      await vi.advanceTimersByTimeAsync(20);
    }
    expect(outcome).toBeNull();
    await vi.advanceTimersByTimeAsync(5);
    expect(outcome).toBe(
      'Atlas request stalled: no data for 25 ms: fixture.observations.json',
    );
  });

  it('lets a slow but steady transfer finish after more than the stall window', async () => {
    vi.useFakeTimers();
    const { body, observed } = observationsFixture(4);
    const { controller, stream } = controlledStream();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(stream)),
    );
    const provider = createProvider({ stallMs: 25 });
    const request = provider.getObservations(observed);
    await vi.advanceTimersByTimeAsync(0);
    const quarter = Math.ceil(body.byteLength / 4);
    for (let index = 0; index < 4; index += 1) {
      controller.enqueue(body.subarray(index * quarter, (index + 1) * quarter));
      await vi.advanceTimersByTimeAsync(20);
    }
    controller.close();
    await expect(request).resolves.toMatchObject({
      observations: expect.any(Array),
    });
  });

  it('stalls when response headers never arrive', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string | URL | Request, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(init.signal?.reason),
            );
          }),
      ),
    );
    const { observed } = observationsFixture(1);
    const request = createProvider({ stallMs: 25 }).getObservations(observed);
    const rejection = expect(request).rejects.toThrow(
      'Atlas request stalled: no data for 25 ms: fixture.observations.json',
    );
    await vi.advanceTimersByTimeAsync(25);
    await rejection;
  });

  it('takes totals only from catalog-declared decoded bytes, never from headers', async () => {
    const { body, observed } = observationsFixture(40);
    const { controller, stream } = controlledStream();
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(stream, {
            headers: {
              'Content-Length': String(Math.ceil(body.byteLength / 10)),
            },
          }),
      ),
    );
    const seen: TransferProgress[] = [];
    const request = createProvider().getObservations(
      observed,
      undefined,
      (progress) => seen.push(progress),
    );
    const half = Math.ceil(body.byteLength / 2);
    controller.enqueue(body.subarray(0, half));
    await vi.waitFor(() => expect(seen.at(-1)?.loadedBytes).toBe(half));
    expect(aggregateTransferProgress([seen.at(-1)!])).toBeLessThan(1);
    controller.enqueue(body.subarray(half));
    controller.close();
    await request;
    expect(seen.every(({ totalBytes }) => totalBytes === body.byteLength)).toBe(
      true,
    );
    expect(seen.at(-1)).toEqual({
      loadedBytes: body.byteLength,
      totalBytes: body.byteLength,
    });
  });

  it('reports surface progress against the declared grid and render sizes', async () => {
    goldenFetch({
      [entry.url]: () =>
        new Response(goldenBytes(entry.url), {
          headers: { 'Content-Length': '17' },
        }),
    });
    const seen: TransferProgress[] = [];
    await createProvider().getSurface(ref, undefined, (progress) =>
      seen.push(progress),
    );
    const declared = entry.bytes + ref.web.render.bytes;
    expect(seen.every(({ totalBytes }) => totalBytes === declared)).toBe(true);
    expect(seen.at(-1)).toEqual({
      loadedBytes: declared,
      totalBytes: declared,
    });
  });

  it('keeps the load aggregate below one until observations finish', async () => {
    const { body, observed } = observationsFixture(40);
    const { controller, stream } = controlledStream();
    goldenFetch({ 'fixture.observations.json': () => new Response(stream) });
    const values: (number | null)[] = [];
    const track = createTransferProgressTracker(
      ['surface', 'observations'],
      (value) => values.push(value),
    );
    const provider = createProvider();
    const observations = provider.getObservations(
      observed,
      undefined,
      track('observations'),
    );
    await provider.getSurface(ref, undefined, track('surface'));
    controller.enqueue(body.subarray(0, 10));
    await vi.waitFor(() => expect(values.length).toBeGreaterThan(2));
    expect(
      Math.max(...values.filter((value): value is number => value !== null)),
    ).toBeLessThan(1);
    controller.enqueue(body.subarray(10));
    controller.close();
    await observations;
    expect(values.at(-1)).toBe(1);
  });

  it('reports indeterminate progress when no size is declared', async () => {
    const resource = {
      cache_sha256: 'd'.repeat(64),
      cache_url: 'external/gnomad/chr11-5227002-t-a.json',
      commercial_use: {
        finding: 'not_checked' as const,
        restricted_fields: [],
      },
      dataset: 'gnomad_r4',
      normalized_variant_id: ref.variant_id,
      source: 'gnomad' as const,
    };
    const cached = {
      query: { dataset: 'gnomad_r4', normalized_variant_id: ref.variant_id },
      record: {
        alt: 'A',
        canonical_consequence: null,
        chrom: '11',
        clinvar: null,
        exome: null,
        genetic_ancestry_group_frequencies: [],
        genome: null,
        genomic_constraint: null,
        joint: { ac: 4, af: 0.04, an: 100 },
        pos: 5227002,
        ref: 'T',
        rsids: ['rs334'],
        source_url: 'https://gnomad.broadinstitute.org/variant/11-5227002-T-A',
      },
      retrieved_at: '2026-09-07T00:00:00Z',
      schema_version: 2,
      source: 'gnomad',
      source_release: 'gnomad_r4',
    };
    const fetchMock = goldenFetch({
      [resource.cache_url]: () => new Response(JSON.stringify(cached)),
    });
    const provider = createProvider();
    const progress = vi.fn();
    const eligible = { ...ref, external_resources: [resource] } as ArtifactRef;
    await expect(
      provider.getExternalInfo(eligible, 'gnomad', undefined, progress),
    ).resolves.toMatchObject({
      source: 'gnomad',
    });
    expect(
      progress.mock.calls.every(([value]) => value.totalBytes === null),
    ).toBe(true);
    await expect(
      provider.getExternalInfo(
        { ...ref, external_resources: [] } as ArtifactRef,
        'gnomad',
      ),
    ).rejects.toThrow(/no reviewed identifier/);
    expect(callsTo(fetchMock, resource.cache_url)).toBe(1);
  });
});

describe('StaticAtlasDataProvider observations', () => {
  it('validates observation identity and count', async () => {
    const { body, observed, payload } = observationsFixture(2);
    goldenFetch({
      'fixture.observations.json': () => new Response(body),
      'wrong-identity.observations.json': () =>
        new Response(
          JSON.stringify({
            ...payload,
            artifact: { ...payload.artifact, id: 'wrong' },
          }),
        ),
    });
    const provider = createProvider();
    await expect(provider.getObservations(observed)).resolves.toMatchObject({
      observations: expect.any(Array),
    });
    await expect(
      provider.getObservations({
        ...observed,
        observations_url: 'wrong-identity.observations.json',
      } as ArtifactRef),
    ).rejects.toThrow(/identity/i);
    await expect(
      createProvider().getObservations({
        ...observed,
        n_observations: 3,
      } as ArtifactRef),
    ).rejects.toThrow(
      'Atlas observation count mismatch: expected 3, received 2',
    );
  });

  it('does not request an observation payload declared unavailable', async () => {
    const fetchMock = goldenFetch();
    const surfaceOnly = {
      ...ref,
      observations_available: false,
      observations_bytes: null,
      observations_sha256: null,
      observations_url: null,
    } as unknown as ArtifactRef;
    await expect(
      createProvider().getObservations(surfaceOnly),
    ).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('StaticAtlasDataProvider transitional JSON surface', () => {
  it('loads and validates the canonical JSON surface from the artifact base', async () => {
    const fetchMock = goldenFetch();
    const provider = createProvider();
    const surface = await provider.getSurfaceJson(ref);
    expect(surface.cells).toHaveLength(ref.n_cells);
    await expect(provider.getSurfaceJson(ref)).resolves.toBe(surface);
    expect(callsTo(fetchMock, ref.surface_url)).toBe(1);
  });

  it('keeps the identity and target-grid checks', async () => {
    const json = goldenSurfaceJson(formatTwo);
    goldenFetch({
      [formatTwo.surface_url]: () =>
        new Response(
          JSON.stringify({
            ...json,
            artifact: {
              ...json.artifact,
              target_grid_version: 'wrong-grid-version',
            },
          }),
        ),
    });
    await expect(createProvider().getSurfaceJson(formatTwo)).rejects.toThrow(
      /target_grid_version/,
    );
  });
});
