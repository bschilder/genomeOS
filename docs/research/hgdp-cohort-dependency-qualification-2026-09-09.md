# Harmonized HGDP + 1KG: cohort and dependency qualification

September 9, 2026; advances [#189](https://github.com/bschilder/genomeOS/issues/189),
WP0/WP1 of the [global AF plan](../superpowers/plans/2026-09-09-global-af-modeling.md).
This is actual source-metadata evidence, not an allele-frequency performance result.

## Scientific contract

The objective is to establish which released participants and reported kinship links could
support a separately labeled reference-panel development benchmark. Acceptance evidence is
checksum-verified source bytes, exact identity joins, explicit QC exclusions and an aggregate
dependency audit. The engineering component at this stage is an isolated offline Hail reader;
there is no new public genomeOS interface, P1 admission or serving-path change.

Downstream count preparation and split manifests must consume a specified cohort and retain
source dependencies. Approximate population origins are not verified present-day residences or
sampling footprints. Missing dates, ascertainment evidence and independence remain unknown.
No genotype calls were read for this milestone. No benchmark, fitted surface, finer-resolution
claim or scientific release is admitted by these findings.

## Sources and reproducible identities

The full [Koenig et al. article](https://pmc.ncbi.nlm.nih.gov/articles/PMC11216312/) was read
through its body, methods, captions and data-access text; supplements were not inspected.
The authors' [QC notebook](https://github.com/atgu/hgdp_tgp/blob/50a1b8bc36dfc45b9fa1efa847c4e54018da722f/tutorials/nb1.ipynb)
and relevant [ancestry/relatedness notebook code](https://github.com/atgu/hgdp_tgp/blob/50a1b8bc36dfc45b9fa1efa847c4e54018da722f/tutorials/nb2.ipynb)
were inspected at commit `50a1b8bc36dfc45b9fa1efa847c4e54018da722f`, excluding output cells.

All Google Cloud access used the repository wrapper anonymously, with credentials disabled.
The complete sample-metadata Hail table was acquired locally, not a genome matrix:

```text
gs://gcp-public-data--gnomad/release/3.1.2/ht/genomes/gnomad.genomes.v3.1.2.hgdp_1kg_subset_sample_meta.ht
```

Its 478 unique objects total 3,654,644 bytes. Every acquired member matched its listed size and
MD5; individual SHA-256 hashes were also computed. The canonical source inventory SHA-256 is
`9b50144a77c381da8d72efcdf8ca7e1eaa4d6e3c51c1c6250c306fb519a115df`;
the verified local inventory SHA-256 is
`3a7e0fd11f9ba6af4dea20a86c7ad05d966a7736ca86da3d3db88f452f4b349c`.
The root `metadata.json.gz` has generation `1635558511736212`, 1,892 bytes and SHA-256
`619bf087a25c249fcbbd3f6bacbf499079812e024fad36447919f3afad6ccccb`.

Two additional objects were read at exact generations and verified by length and MD5 before
parsing. Both paths below are relative to
`gs://gcp-public-data--gnomad/release/3.1/secondary_analyses/hgdp_1kg_v2/`.

| Object | Generation | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `metadata_and_qc/gnomad_meta_updated.tsv` | `1714521690603290` | 6,158,624 | `e18e7a29d0567b8063edc1a714bd31e57dc422823ba51af2c63fecef0dbc3cf1` |
| `pca/pca_outliers.txt` | `1714521693311010` | 218 | `592772fff79086a6b55ce07693f2871c9e4fbe9bdeff1ff926d87fcba884994f` |

The temporary local reader used Python 3.12.13, Hail `0.2.139-5e5eedb87ff8`, PySpark 3.5.3,
Py4J 0.10.9.7 and Temurin JRE 11.0.32.1+1 on macOS ARM64. Spark used `local[2]`, a 2 GiB
driver, loopback binding, disabled UI and seed 42. The portable JRE archive matched the
vendor-provided SHA-256 `4fb215c85ab144e0bf34e28c6edd126a3d60af9c3e1db33406a3b1d3e8bcec5e`.
No genomeOS environment, dependency lock or global Java configuration was changed.

## Actual cohort reconciliation

The Hail reader collected 4,151 uniquely keyed metadata rows. An exact-ID join to the updated
TSV found 4,150 common IDs, no TSV-only IDs and one Hail-only ID: the authors' documented
synthetic control. This was checked by identity, not inferred from the one-row difference.

| Explicit selection | Remaining rows | Interpretation |
| --- | ---: | --- |
| Entire Hail sample metadata | 4,151 | Includes the synthetic control |
| Remove 31 hard-filtered samples, two named contamination exclusions and the control | 4,117 | Authors' technical-QC stage |
| Then remove the older Hail ancestry-outlier flags | 4,095 | 22 flagged exclusions; not the final paper cohort |
| Instead remove the release-specific text list | 4,094 | 23 unique exclusions; reproduces the paper's sample count |

All 23 text-list IDs exist within the 4,117-sample technical-QC stage. The list contains all
22 older flagged IDs and one additional ID. This resolves the discrepancy without inventing an
exclusion or silently changing the meaning of a metadata flag. It reproduces the cohort count,
not the paper's genotype filtering, unrelated subset, allele frequencies or analysis results.

The legacy `gnomad_high_quality` field selects 3,943 Hail rows versus 3,942 TSV rows; the Hail
`high_quality` field has 4,097 true, 53 false and one missing value. These are distinct source
fields, not interchangeable implementations of the final 4,094-person cohort. Technical QC and
ancestry-outlier exclusions must remain separately auditable; the latter are not a newly
endorsed genomeOS sampling policy.

## Actual reported-kinship audit

The Hail field descriptions identify PC-Relate estimates with `kin > 0.05`. Reading every
`related_samples` set found:

- 2,488 directed records representing 1,302 distinct unordered reported pairs.
- All endpoints present; no self-links or duplicate directed records.
- 116 directed records without a reverse record. Present reverse records agree numerically.
- No null sets; 2,302 empty sets. An empty set is not proof of universal unrelatedness.
- No missing or nonfinite kinship/IBD values. Kinship ranges from 0.05008813792050971 to
  0.4921968154148169. IBD estimates include negative IBD2 and IBD1 greater than one; they were
  preserved as estimates, not clipped or reinterpreted as a joint probability distribution.

Using the undirected union of reported links, component-size counts over all 4,151 rows are
`{1: 2302, 2: 69, 3: 515, 4: 8, 5: 1, 6: 14, 9: 3, 18: 1}`. This union is a conservative
dependency representation of the reported edges, not an invented reciprocal measurement or
a certified complete pedigree. A hand-specified four-node graph checked the component routine.

The TSV's `relatedness_inference.relationships` contains relationship-category sets, not
partner IDs; it cannot replace this edge source. The Hail `related` boolean denotes a pruning
decision, not simply whether any relative exists. The authors' later notebook uses a separate
KING-robust analysis and a pruned-ID artifact. Neither that selected-ID list nor this PC-Relate
graph alone certifies the final 3,400-person unrelated cohort or complete dependence coverage.

## Scope, access and next experiment

The [release annotation definitions](https://github.com/broadinstitute/gnomad-browser/blob/16e39929a8938c334a8eee4d7d0c7a67e6624153/browser/help/topics/hgdp-1kg-annotations.md)
describe approximate population origins. Both inspected age columns in the updated TSV contain
literal `NA` throughout; no explicitly named residence, recruitment or collection-date columns
were found. This is not an exhaustive interpretation of every free-text field. A biobank label
does not establish random sampling or disease-ascertainment exclusion.

The [source terms](https://github.com/broadinstitute/gnomad-browser/blob/16e39929a8938c334a8eee4d7d0c7a67e6624153/browser/about/policies/terms.md)
identify primary data as CC0 and prohibit participant reidentification; annotation-specific
restrictions remain separate. The owner's resolved [#66 decision](https://github.com/bschilder/genomeOS/issues/66#issuecomment-5565166083)
permits fitted-surface redistribution with attribution, biocultural notices, explicit distinction
between observations and estimates, and source restrictions honored. Earlier qualification
commentary that called #66 unresolved was stale. Conditional permission does not establish
scientific release eligibility. No participant rows, IDs or genomic data are committed here.

Next is a prespecified small autosomal genotype/count qualification, followed by a separately
labeled reference-panel development comparison. Prefer directly called genotype evidence over
jointly imputed/phased targets, and retain joint-calling, QC and variant-discovery dependencies.
The primary resident target, qualified spatial-footprint buffers, external sealed confirmation,
count calibration and unchanged scientific publication gates remain required. CuGen/LD is an
independent optional workstream, not a prerequisite for these AF experiments.

The subsequent [fixed-interval count pilot](hgdp-count-pilot-2026-09-09.md) records that next
acquisition separately; the no-genotype-read statements above describe this metadata milestone.

## Verification and limitations

The complete acquisition, actual-row kinship audit and exact outlier-list reconciliation each
exited successfully. The kinship audit's aggregate JSON SHA-256 is
`d9da9d58f1213c8de0eb61cfc48b9357ff8654c15ac8d3b363b305c6d2c47dc6`.
Raw inputs, member inventories and diagnostic logs remain local temporary research material;
this note is an aggregate research record, not a packaged production ingestion pipeline.

Two setup failures were resolved explicitly: Spark's local gateway needed sandbox permission
to bind loopback, and an inclusive byte-range endpoint initially requested one excess TSV byte.
The corrected exact range was rechecked against size, MD5 and SHA-256. PySpark was pinned from
3.5.9 to the Hail JAR's 3.5.3 build version. Remaining warnings were native-Hadoop fallback and
Spark local-directory override. Repository smoke passed all 40 tests after the diagnostic
correction; no full-suite or scientific performance result is claimed for this metadata audit.
