import { afterEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

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
// Tiers come from a cross-origin bucket (the Part C deployment) and site data from the page's own
// origin, so a request resolved against the wrong base reaches no fixture and fails its test.
const ARTIFACT_BASE = 'https://atlas-bucket.test.invalid/atlas/web/';
const SITE_BASE = '/genomeOS/data/atlas/';
const SITE_ROOT = `${ORIGIN}${SITE_BASE}`;
const DOCUMENT = `${ORIGIN}/genomeOS/app/`;
const catalog = goldenCatalog();
const { entry, gridSha256 } = onlyGrid(catalog);
const ref = catalog.artifacts[0];
// A second artifact on the same shared grid.
const sibling = catalog.artifacts[1];
const STALL_MESSAGE = 'Atlas request stall timeout must be positive and finite';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function createProvider(
  options: { inlineCatalog?: unknown; stallMs?: number } = {},
) {
  return new StaticAtlasDataProvider({
    artifactDataBase: ARTIFACT_BASE,
    documentBase: () => DOCUMENT,
    inlineCatalog:
      'inlineCatalog' in options ? options.inlineCatalog : goldenCatalogRaw(),
    requestStallMs: options.stallMs,
    siteDataBase: SITE_BASE,
    worker: new AtlasWorkerClient(new InProcessWorker().asWorker()),
  });
}

/**
 * Golden objects are served from the artifact base only; `overrides` replaces artifact-base keys
 * and `site` serves site-base keys, which have no default. Any other URL rejects the fetch.
 */
function goldenFetch(
  overrides: Record<string, () => Response> = {},
  site: Record<string, () => Response> = {},
) {
  const fetchMock = vi.fn(
    async (url: string | URL | Request, _init?: RequestInit) => {
      const href = String(url);
      if (href.startsWith(ARTIFACT_BASE)) {
        const key = href.slice(ARTIFACT_BASE.length);
        return overrides[key]?.() ?? new Response(goldenBytes(key));
      }
      const respond = href.startsWith(SITE_ROOT)
        ? site[href.slice(SITE_ROOT.length)]
        : undefined;
      if (!respond) throw new Error(`No fixture is served at ${href}`);
      return respond();
    },
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function requestedUrls(fetchMock: ReturnType<typeof goldenFetch>): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url)).sort();
}

function lastByteMarks(): string[] {
  return performance
    .getEntriesByType('mark')
    .map(({ name }) => name)
    .filter((name) => name.startsWith('atlas:last-byte:'))
    .sort();
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

/** A body the test feeds chunk by chunk; `cancel` records the provider releasing it. */
function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const stream = new ReadableStream<Uint8Array>({
    cancel,
    start: (value) => {
      controller = value;
    },
  });
  return { cancel, controller, stream };
}

/** A reviewed gnomAD resource and the cached record it names; external caches live on the site base. */
function gnomadFixture() {
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
  const body = new TextEncoder().encode(JSON.stringify(cached));
  const eligible = { ...ref, external_resources: [resource] } as ArtifactRef;
  return { body, eligible, resource };
}

/** Golden fetches with the shared grid fed by the test, and the grid's golden bytes to feed. */
function heldGridFetch() {
  const grid = controlledStream();
  const fetchMock = goldenFetch({
    [entry.url]: () => new Response(grid.stream),
  });
  return { bytes: goldenBytes(entry.url), fetchMock, grid };
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
    for (const inlineCatalog of [undefined, null]) {
      await expect(
        createProvider({ inlineCatalog }).getCatalog(),
      ).rejects.toThrow(
        'The Atlas catalog is missing from this page or is not valid JSON.',
      );
    }
    const invalid = await createProvider({ inlineCatalog: {} })
      .getCatalog()
      .catch((error: unknown) => error);
    expect(invalid).toBeInstanceOf(ZodError);
    expect((invalid as ZodError).issues).toContainEqual(
      expect.objectContaining({ path: ['artifacts'] }),
    );
  });

  it('resolves catalog context sources against the site data base', async () => {
    const provider = createProvider();
    const keyOf = (id: string) =>
      catalog.context_sources.find((source) => source.id === id)!.url;
    expect(provider.contextSourceUrl(catalog, NATURAL_EARTH_BORDERS)).toBe(
      `${SITE_ROOT}${keyOf(NATURAL_EARTH_BORDERS)}`,
    );
    expect(provider.contextSourceUrl(catalog, NATURAL_EARTH_PLACES)).toBe(
      `${SITE_ROOT}${keyOf(NATURAL_EARTH_PLACES)}`,
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
          siteDataBase: SITE_BASE,
          worker,
        }),
    ).toThrow('Atlas data base must end in "/"');
    expect(
      () =>
        new StaticAtlasDataProvider({
          artifactDataBase: ARTIFACT_BASE,
          inlineCatalog: goldenCatalogRaw(),
          siteDataBase: 'data/atlas/',
          worker,
        }),
    ).toThrow(/root-relative or an absolute https URL/);
  });

  it('defaults to a 15 s stall timeout and refuses one that is not positive and finite', () => {
    expect(StaticAtlasDataProvider.defaultRequestStallMs).toBe(15_000);
    expect(() => createProvider({ stallMs: 1 })).not.toThrow();
    for (const stallMs of [0, -25, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => createProvider({ stallMs })).toThrow(STALL_MESSAGE);
    }
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
    for (const key of [entry.url, ref.web.render.url]) {
      expect(fetchMock).toHaveBeenCalledWith(
        `${ARTIFACT_BASE}${key}`,
        expect.objectContaining({
          credentials: 'same-origin',
          mode: 'cors',
          signal: expect.any(AbortSignal),
        }),
      );
    }
  });

  it('routes tiers and observations to the artifact base and external caches to the site base', async () => {
    const { body, observed } = observationsFixture(2);
    const gnomad = gnomadFixture();
    const fetchMock = goldenFetch(
      { [observed.observations_url!]: () => new Response(body) },
      { [gnomad.resource.cache_url]: () => new Response(gnomad.body) },
    );
    const provider = createProvider();
    await provider.getSurfaceDetail(ref);
    await provider.getObservations(observed);
    await provider.getExternalInfo(gnomad.eligible, 'gnomad');
    expect(requestedUrls(fetchMock)).toEqual(
      [
        `${ARTIFACT_BASE}${entry.url}`,
        `${ARTIFACT_BASE}${ref.web.render.url}`,
        `${ARTIFACT_BASE}${ref.web.detail.url}`,
        `${ARTIFACT_BASE}${observed.observations_url}`,
        `${SITE_ROOT}${gnomad.resource.cache_url}`,
      ].sort(),
    );
  });

  it('refuses a surface whose grid the catalog does not declare, before any request', async () => {
    const fetchMock = goldenFetch();
    const undeclared = 'f'.repeat(64);
    const orphan = {
      ...ref,
      web: { ...ref.web, grid_sha256: undeclared },
    } as ArtifactRef;
    await expect(createProvider().getSurface(orphan)).rejects.toThrow(
      `Atlas grid ${undeclared} for ${ref.id} is not declared in the catalog`,
    );
    expect(fetchMock).not.toHaveBeenCalled();
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

  it('counts the in-flight shared grid for a caller that joins it', async () => {
    const { bytes, fetchMock, grid } = heldGridFetch();
    const provider = createProvider();
    const half = Math.ceil(bytes.byteLength / 2);
    const first = provider.getSurface(ref, undefined, () => undefined);
    grid.controller.enqueue(bytes.subarray(0, half));
    await vi.waitFor(() => expect(callsTo(fetchMock, entry.url)).toBe(1));
    const seen: TransferProgress[] = [];
    const joined = provider.getSurface(sibling, undefined, (progress) =>
      seen.push(progress),
    );
    const declared = entry.bytes + sibling.web.render.bytes;
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({
        loadedBytes: half + sibling.web.render.bytes,
        totalBytes: declared,
      }),
    );
    expect(aggregateTransferProgress([seen.at(-1)!])).toBeLessThan(1);
    grid.controller.enqueue(bytes.subarray(half));
    grid.controller.close();
    await Promise.all([first, joined]);
    expect(seen.every(({ totalBytes }) => totalBytes === declared)).toBe(true);
    expect(seen.at(-1)).toEqual({
      loadedBytes: declared,
      totalBytes: declared,
    });
    expect(callsTo(fetchMock, entry.url)).toBe(1);
  });

  it('stops reporting to a caller once it aborts, while the shared grid finishes for a retry', async () => {
    const { bytes, fetchMock, grid } = heldGridFetch();
    const provider = createProvider();
    const third = Math.ceil(bytes.byteLength / 3);
    const controller = new AbortController();
    const abandoned = vi.fn();
    const request = provider.getSurface(ref, controller.signal, abandoned);
    grid.controller.enqueue(bytes.subarray(0, third));
    await vi.waitFor(() =>
      expect(abandoned).toHaveBeenLastCalledWith({
        loadedBytes: third + ref.web.render.bytes,
        totalBytes: entry.bytes + ref.web.render.bytes,
      }),
    );
    controller.abort();
    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    const reported = abandoned.mock.calls.length;
    const retried = vi.fn();
    const retry = provider.getSurface(ref, undefined, retried);
    grid.controller.enqueue(bytes.subarray(third));
    grid.controller.close();
    await expect(retry).resolves.toMatchObject({
      artifactKey: artifactKeyFor(ref),
    });
    expect(abandoned).toHaveBeenCalledTimes(reported);
    expect(retried).toHaveBeenLastCalledWith({
      loadedBytes: entry.bytes + ref.web.render.bytes,
      totalBytes: entry.bytes + ref.web.render.bytes,
    });
    expect(callsTo(fetchMock, entry.url)).toBe(1);
  });

  it("fails only the caller whose progress listener throws, not the grid's other callers", async () => {
    const { bytes, fetchMock, grid } = heldGridFetch();
    const provider = createProvider();
    const failure = new Error('progress listener failed');
    let armed = false;
    const throwing = vi.fn(() => {
      if (armed) throw failure;
    });
    const failing = provider.getSurface(ref, undefined, throwing);
    const joined = provider.getSurface(sibling, undefined, () => undefined);
    await vi.waitFor(() =>
      expect(throwing).toHaveBeenLastCalledWith({
        loadedBytes: ref.web.render.bytes,
        totalBytes: entry.bytes + ref.web.render.bytes,
      }),
    );
    armed = true;
    grid.controller.enqueue(bytes);
    grid.controller.close();
    await expect(failing).rejects.toBe(failure);
    await expect(joined).resolves.toMatchObject({
      artifactKey: artifactKeyFor(sibling),
    });
    expect(callsTo(fetchMock, entry.url)).toBe(1);
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
    const { body, eligible, resource } = gnomadFixture();
    const fetchMock = goldenFetch(
      {},
      { [resource.cache_url]: () => new Response(body) },
    );
    const provider = createProvider();
    const progress = vi.fn();
    await expect(
      provider.getExternalInfo(eligible, 'gnomad', undefined, progress),
    ).resolves.toMatchObject({
      source: 'gnomad',
    });
    expect(progress).toHaveBeenCalledWith({ loadedBytes: 0, totalBytes: null });
    expect(progress).toHaveBeenLastCalledWith({
      loadedBytes: body.byteLength,
      totalBytes: null,
    });
    for (const [value] of progress.mock.calls) {
      expect(value).toMatchObject({ totalBytes: null });
    }
    await expect(
      provider.getExternalInfo(
        { ...ref, external_resources: [] } as ArtifactRef,
        'gnomad',
      ),
    ).rejects.toThrow(/no reviewed identifier/);
    expect(callsTo(fetchMock, resource.cache_url)).toBe(1);
  });

  it('cancels a request that fails with an HTTP error instead of leaving its body downloading', async () => {
    const { observed } = observationsFixture(1);
    const { cancel, stream } = controlledStream();
    let init: RequestInit | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string | URL | Request, requestInit?: RequestInit) => {
        init = requestInit;
        return new Response(stream, { status: 503 });
      }),
    );
    await expect(createProvider().getObservations(observed)).rejects.toThrow(
      'Atlas request failed with HTTP 503: fixture.observations.json',
    );
    expect(init?.signal?.aborted).toBe(true);
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('cancels a request whose progress listener throws, rejecting with its error', async () => {
    const { body, observed } = observationsFixture(4);
    const { cancel, controller, stream } = controlledStream();
    let init: RequestInit | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string | URL | Request, requestInit?: RequestInit) => {
        init = requestInit;
        return new Response(stream);
      }),
    );
    const failure = new Error('progress listener failed');
    const request = createProvider().getObservations(
      observed,
      undefined,
      ({ loadedBytes }) => {
        if (loadedBytes > 0) throw failure;
      },
    );
    controller.enqueue(body.subarray(0, 10));
    await expect(request).rejects.toBe(failure);
    expect(init?.signal?.aborted).toBe(true);
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it('makes no request for a caller that has already aborted', async () => {
    const fetchMock = goldenFetch();
    const { observed } = observationsFixture(1);
    const controller = new AbortController();
    controller.abort();
    const provider = createProvider();
    await expect(
      provider.getObservations(observed, controller.signal),
    ).rejects.toBe(controller.signal.reason);
    await expect(provider.getSurface(ref, controller.signal)).rejects.toBe(
      controller.signal.reason,
    );
    expect(controller.signal.reason).toMatchObject({ name: 'AbortError' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('marks the last byte of every tier it receives and of no failed request', async () => {
    performance.clearMarks();
    const { body, observed } = observationsFixture(2);
    goldenFetch({
      [observed.observations_url!]: () => new Response(body),
      [sibling.web.render.url]: () => new Response('busy', { status: 503 }),
    });
    const provider = createProvider();
    await provider.getSurfaceDetail(ref);
    await provider.getObservations(observed);
    await expect(provider.getSurface(sibling)).rejects.toThrow(/HTTP 503/);
    const key = artifactKeyFor(ref);
    expect(lastByteMarks()).toEqual(
      [
        `atlas:last-byte:detail:${key}`,
        `atlas:last-byte:grid:${gridSha256}`,
        `atlas:last-byte:observations:${key}`,
        `atlas:last-byte:render:${key}`,
      ].sort(),
    );
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
