/** AlphaGenome AVI predicted-impact card for Atlas design §11 (external reference). */

import type { ReactNode } from 'react';

import type { ExternalInfo } from '../../atlas/contracts';
import '../../styles/alphagenome-evidence.css';

type AlphagenomeInfo = Extract<ExternalInfo, { source: 'alphagenome' }>;

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function AlphagenomeEvidence({ info }: { info: AlphagenomeInfo }) {
  const record = info.record;
  const tailPercent = (record.avi_tail_quantile * 100).toLocaleString(
    undefined,
    { maximumFractionDigits: 2 },
  );
  return (
    <>
      <section className="atlas-external-hero">
        <span className="atlas-alphagenome-tag">Predicted impact</span>
        <h3>AlphaGenome AVI</h3>
        <div className="atlas-external-badges">
          <span>{info.query.normalized_variant_id}</span>
          <span>{info.source_release}</span>
        </div>
      </section>

      <section className="atlas-external-section">
        <h3>Impact readout</h3>
        <dl className="atlas-external-fields">
          <Field label="AVI Phred" value={record.avi_phred.toFixed(2)} />
          <Field
            label="Genome-wide rank"
            value={`top ${tailPercent}% of all possible single-letter changes (tail quantile ${record.avi_tail_quantile})`}
          />
          <Field label="Dominant modality" value={record.dominant_modality} />
          <Field label="Model version" value={record.model_version} />
          <Field
            label="Retrieved"
            value={new Date(info.retrieved_at).toLocaleDateString(undefined, {
              dateStyle: 'medium',
            })}
          />
        </dl>
      </section>

      <a
        className="atlas-external-source-link"
        href={record.deep_link}
        target="_blank"
        rel="noreferrer"
      >
        Open this variant in the AlphaGenome Atlas{' '}
        <span aria-hidden="true">↗</span>
      </a>

      <section className="atlas-alphagenome-note">
        <p>
          AVI is a model prediction of molecular impact. It is not a measured
          allele frequency and not a clinical classification. Predictions never
          qualify or disqualify a measured source.
        </p>
      </section>
    </>
  );
}
