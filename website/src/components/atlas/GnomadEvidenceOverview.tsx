/** Compact gnomAD variant overview for Atlas design §11. */

import type { ReactNode } from 'react';

import type { ExternalInfo } from '../../atlas/contracts';

type GnomadInfo = Extract<ExternalInfo, { source: 'gnomad' }>;

interface FrequencyValue {
  ac: number;
  ac_hemi?: number;
  ac_hom?: number;
  af: number;
  an: number;
}

function percent(value: number): string {
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 4 })}%`;
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function BooleanValue({ value }: { value: boolean | null }) {
  return <>{value === null ? 'Not reported' : value ? 'Yes' : 'No'}</>;
}

function FrequencyCard({
  label,
  value,
}: {
  label: string;
  value: FrequencyValue | null;
}) {
  return (
    <article className="atlas-external-frequency">
      <p>{label}</p>
      {value ? (
        <>
          <strong>{percent(value.af)}</strong>
          <dl>
            <Field label="Allele count" value={value.ac.toLocaleString()} />
            <Field label="Allele number" value={value.an.toLocaleString()} />
            {value.ac_hom !== undefined && (
              <Field
                label="Homozygous alternate"
                value={value.ac_hom.toLocaleString()}
              />
            )}
            {value.ac_hemi !== undefined && (
              <Field
                label="Hemizygous alternate"
                value={value.ac_hemi.toLocaleString()}
              />
            )}
          </dl>
        </>
      ) : (
        <span>No frequency record returned</span>
      )}
    </article>
  );
}

export function GnomadEvidenceOverview({
  info,
  navigator,
}: {
  info: GnomadInfo;
  navigator: ReactNode;
}) {
  const consequence = info.record.canonical_consequence;
  return (
    <>
      <section className="atlas-external-hero">
        <span>Normalized GRCh38 variant</span>
        <h3>{info.query.normalized_variant_id}</h3>
        <div className="atlas-external-badges">
          {info.record.rsids.map((rsid) => (
            <span key={rsid}>{rsid}</span>
          ))}
          <span>{info.query.dataset}</span>
        </div>
      </section>

      <section className="atlas-external-section">
        <h3>Allele frequency</h3>
        <div className="atlas-external-frequency-grid">
          <FrequencyCard label="Combined" value={info.record.joint} />
          <FrequencyCard label="Exomes" value={info.record.exome} />
          <FrequencyCard label="Genomes" value={info.record.genome} />
        </div>
      </section>

      {navigator}

      <section className="atlas-external-section">
        <h3>Variant identity</h3>
        <dl className="atlas-external-fields">
          <Field label="Chromosome" value={info.record.chrom} />
          <Field label="Position" value={info.record.pos.toLocaleString()} />
          <Field label="Reference allele" value={info.record.ref} />
          <Field label="Alternate allele" value={info.record.alt} />
          <Field
            label="rsID(s)"
            value={
              info.record.rsids.length
                ? info.record.rsids.join(', ')
                : 'None returned'
            }
          />
        </dl>
      </section>

      <section className="atlas-external-section">
        <h3>Canonical consequence</h3>
        {consequence ? (
          <dl className="atlas-external-fields">
            <Field
              label="Gene"
              value={consequence.gene_symbol ?? 'Not reported'}
            />
            <Field
              label="Gene ID"
              value={consequence.gene_id ?? 'Not reported'}
            />
            <Field
              label="Consequence"
              value={
                consequence.major_consequence?.replaceAll('_', ' ') ??
                'Not reported'
              }
            />
            <Field
              label="Coding change"
              value={consequence.hgvsc ?? 'Not reported'}
            />
            <Field
              label="Protein change"
              value={consequence.hgvsp ?? 'Not reported'}
            />
            <Field
              label="Canonical transcript"
              value={consequence.transcript_id ?? 'Not reported'}
            />
            <Field
              label="Canonical"
              value={<BooleanValue value={consequence.is_canonical} />}
            />
            <Field
              label="MANE Select"
              value={<BooleanValue value={consequence.is_mane_select} />}
            />
          </dl>
        ) : (
          <p>No canonical consequence was returned by this source.</p>
        )}
      </section>
    </>
  );
}
