/** Eligible-variant gnomAD and dbSNP cache explorer for Atlas design §11. */

import { useEffect, useRef, useState } from 'react';

import type { ArtifactRef, ExternalInfo } from '../../atlas/contracts';
import { InfoTip } from './InfoTip';

interface ExternalInfoPanelProps {
  artifact: ArtifactRef;
  load: (
    source: 'gnomad' | 'dbsnp',
    signal: AbortSignal,
  ) => Promise<ExternalInfo>;
}

function percent(value: number): string {
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 4 })}%`;
}

function Frequency({
  label,
  value,
}: {
  label: string;
  value: { ac: number; af: number; an: number } | null;
}) {
  if (!value) return null;
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {percent(value.af)} · AC {value.ac.toLocaleString()} / AN{' '}
        {value.an.toLocaleString()}
      </dd>
    </div>
  );
}

function ExternalRecord({ info }: { info: ExternalInfo }) {
  if (info.source === 'gnomad') {
    const consequence = info.record.canonical_consequence;
    return (
      <div className="atlas-external-info__result">
        <dl>
          <div>
            <dt>Variant</dt>
            <dd>{info.query.normalized_variant_id}</dd>
          </div>
          {consequence && (
            <div>
              <dt>Consequence</dt>
              <dd>
                {consequence.gene_symbol ?? 'Unknown gene'} ·{' '}
                {consequence.major_consequence?.replaceAll('_', ' ') ??
                  'Not reported'}
                {consequence.hgvsp ? ` · ${consequence.hgvsp}` : ''}
              </dd>
            </div>
          )}
          <Frequency label="Joint" value={info.record.joint} />
          <Frequency label="Exomes" value={info.record.exome} />
          <Frequency label="Genomes" value={info.record.genome} />
        </dl>
        <a href={info.record.source_url} target="_blank" rel="noreferrer">
          Open this variant in gnomAD ↗
        </a>
      </div>
    );
  }
  return (
    <div className="atlas-external-info__result">
      <dl>
        <div>
          <dt>RefSNP</dt>
          <dd>{info.record.rsid}</dd>
        </div>
        <div>
          <dt>GRCh38 allele</dt>
          <dd>{info.record.hgvs}</dd>
        </div>
        <div>
          <dt>dbSNP citations</dt>
          <dd>{info.record.citation_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Record updated</dt>
          <dd>{info.record.last_update_date}</dd>
        </div>
      </dl>
      <a href={info.record.source_url} target="_blank" rel="noreferrer">
        Open this record in dbSNP ↗
      </a>
    </div>
  );
}

export function ExternalInfoPanel({ artifact, load }: ExternalInfoPanelProps) {
  const [source, setSource] = useState<'gnomad' | 'dbsnp' | ''>('');
  const [info, setInfo] = useState<ExternalInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setSource('');
    setInfo(null);
    setError(null);
    setLoading(false);
    return () => activeRequest.current?.abort();
  }, [artifact.id, artifact.model_version, artifact.data_version]);

  const lookup = (next: 'gnomad' | 'dbsnp') => {
    activeRequest.current?.abort();
    setSource(next);
    setInfo(null);
    setError(null);
    setLoading(true);
    const controller = new AbortController();
    activeRequest.current = controller;
    void load(next, controller.signal)
      .then((loaded) => {
        if (activeRequest.current === controller) setInfo(loaded);
      })
      .catch((caught) => {
        if (
          activeRequest.current === controller &&
          (caught as Error).name !== 'AbortError'
        )
          setError(
            caught instanceof Error
              ? caught.message
              : `${next} information could not be loaded.`,
          );
      })
      .finally(() => {
        if (activeRequest.current === controller) {
          activeRequest.current = null;
          setLoading(false);
        }
      });
  };

  return (
    <details className="atlas-external-info">
      <summary>
        More info
        <InfoTip label="external variant information">
          Opens a reviewed, API-derived gnomAD or dbSNP cache. These sources are
          offered only when this map has an exact normalized variant identifier.
        </InfoTip>
      </summary>
      <div>
        {artifact.external_resources.length > 0 ? (
          <label className="atlas-field">
            <span>External resource</span>
            <select
              value={source}
              onChange={(event) =>
                lookup(event.target.value as 'gnomad' | 'dbsnp')
              }
            >
              <option value="" disabled>
                Choose a source…
              </option>
              {artifact.external_resources.map((resource) => (
                <option value={resource.source} key={resource.source}>
                  {resource.source === 'gnomad' ? 'gnomAD' : 'dbSNP'}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p>
            gnomAD and dbSNP lookup is unavailable because this map does not
            resolve to a reviewed normalized variant or rsID.
          </p>
        )}
        {loading && <p role="status">Loading {source} information…</p>}
        {error && <p role="alert">{error}</p>}
        {info && (
          <>
            <ExternalRecord info={info} />
            <p className="atlas-external-info__provenance">
              {info.source_release} · cached from the source API{' '}
              {new Date(info.retrieved_at).toLocaleDateString()}
            </p>
          </>
        )}
      </div>
    </details>
  );
}
