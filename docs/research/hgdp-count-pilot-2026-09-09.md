# Original-callset allele-count qualification pilot

September 9, 2026; advances [#189](https://github.com/bschilder/genomeOS/issues/189).
This follows the [cohort/dependency qualification](hgdp-cohort-dependency-qualification-2026-09-09.md).
It establishes real count-preparation evidence, not an AF prediction improvement.

## Scientific contract

The objective is to determine whether exact released genotype calls can produce traceable
population-level AC/AN for a reference-panel development experiment. Acceptance requires a
prespecified interval, immutable source identities, exact sample joins, explicit missing-call
and QC rules, distinct population identities, and an independent count cross-check.

The engineering component is a local research-only acquisition/count diagnostic using
generation-pinned repository GCP-wrapper reads and bcftools/htslib 1.23.1. There is no new public
genomeOS interface, production schema, P1 admission, model fit or serving change. Downstream
research contracts must retain the counts' cohort, source, QC, ascertainment, geographic-support
and dependency limitations. Neither sampled chromosomes nor source populations are claimed to
be independent or representative of present-day residents.

## Frozen source and interval

The interval was fixed before genotype/count inspection: **GRCh38 chr22:20,000,001–20,010,000**,
one-based inclusive, or `[20,000,000, 20,010,000)` in zero-based half-open notation. Its purpose
is a count-preparation pilot, not a selected favorable test region or a sealed confirmation set.

The [official download definition](https://github.com/broadinstitute/gnomad-browser/blob/16e39929a8938c334a8eee4d7d0c7a67e6624153/browser/src/DataPage/GnomadV3Downloads.tsx)
identifies individual genotypes in the original HGDP + 1KG callset:

```text
gs://gcp-public-data--gnomad/release/3.1.2/vcf/genomes/gnomad.genomes.v3.1.2.hgdp_tgp.chr22.vcf.bgz
```

- VCF generation `1635563729614310`; full-object size 59,465,212,964 bytes. Its published
  whole-object MD5 was recorded, **not verified by this partial acquisition**.
- Corresponding `.tbi` generation `1635563729351334`; all 41,840 bytes acquired and MD5 checked.
  Index SHA-256: `db6231c43135b597998d1b97985c4199ff5003e1ffb518fcca6a10f8dd0220e1`.
- Fixed 1,048,576-byte prefix SHA-256:
  `49bdd82aeb1c783b8d610638abbd2f26b4bb3ef6aeffa92c24c1b2a240d47a3f`.
- Complete decoded header: 187,500 bytes, SHA-256
  `881895b5d4f027f2639d5f9be23d29d1aea69e6bf1d8b4a269b1dd21cd0663b2`.
  It declares VCF 4.2, 4,151 unique samples and `gnomAD_GRCh38` contig assembly metadata.
- Indexed compressed byte range `[14,688,742,454, 14,731,998,299]`, inclusive:
  43,255,846 bytes, SHA-256
  `bd901eb377e87dc942d9c386f822e1c95824d50e2081bd6d7dfbefd58cddccda`.
  The source's final BGZF EOF marker was separately checked.

The Tabix index and BGZF block offsets were interpreted using the
[Tabix](https://samtools.github.io/hts-specs/tabix.pdf) and
[SAM/BGZF specifications, §4.1](https://samtools.github.io/hts-specs/SAMv1.pdf).
An explicitly incomplete local sparse staging file held only the header prefix, needed blocks
and EOF marker. Its allocated size was 44,331,008 bytes; its 59 GB logical size is not a full
download. Native bcftools performed indexed extraction with `--regions-overlap 0`, retaining
records whose POS is inside the fixed interval. Local genotype records were not printed or
uploaded. Source annotations were not used as predictive covariates.

The compact BCF contains **616 records**, is 8,523,987 bytes, and has SHA-256
`1f483d54f2b043406d525ad7551941e991d6aa6a37078fc43cc875583c52abb8`.
This is an original-callset extraction, not the separately phased reference resource. It still
inherits joint calling, source QC and variant-discovery dependencies.

## Count rules and identity correction

The acquired BCF sample IDs exactly match the qualified 4,150-person metadata plus the
documented synthetic control. Two explicit sample stages were retained: technical QC (4,117)
and the paper's additional ancestry exclusions (4,094). Variant selection is PASS, biallelic,
single-nucleotide A/C/G/T alleles. Alternate dosage is counted only from complete diploid GT;
phase delimiters do not change dosage. Missing genotypes reduce AN and never become reference
calls. Partial, non-diploid, invalid or out-of-range genotype encodings are refused.

Called counts and quality-filtered counts are separate. The prespecified quality sensitivity
requires GQ ≥20, DP ≥10 and, for heterozygotes, each reported AD divided by DP ≥0.2. Missing
required quality fields exclude that call from quality-filtered counts with an explicit reason.
This is the pilot's explicit QC rule, not a claim to reproduce every upstream gnomAD adjustment.
Native bcftools `+fill-tags` recomputed AC/AN after sample/site selection; the separate Python
count routine's population sums were compared with those totals at every selected variant.

The first diagnostic incorrectly used `hgdp_tgp_meta.Population` as a grouping key: that
display-label column has 78 groups. An exact metadata audit found two collisions:

| Display label | Distinct source `population` identities |
| --- | --- |
| Han | Han; NorthernHan |
| Papuan | PapuanHighlands; PapuanSepik |

Adding project identity does not resolve these collisions. The corrected diagnostic uses the
literal source `population` field, retaining all 80 identities. A regression hand control
requires all four colliding identities to remain distinct. The original 78-group run and its
count tables remain locally preserved as superseded diagnostics. The interval, cohort, site
selection and genotype QC did not change; this was an identity correction before any fitting.

The initial acquisition/count contract SHA-256 was
`0e1173595b310b58877eb70fef335958c0a5f77ca401999a8441859e2a82f61e`.
The corrected source-identity contract references that parent and has SHA-256
`b9ef8cfbfc0c4879ba27b6d0cda335c4248bb1b2e45efa9f47a0e3c5a154cc2c`.

## Verified aggregate result

Both cohort stages retain 510 PASS biallelic SNPs and 80 populations, yielding 40,800
population/variant cells per stage. Population sample sizes range from 6 to 176. All 510
variant totals match the independent native AC/AN calculation in each stage.

| Quantity | Technical QC, 4,117 samples | Additional ancestry exclusions, 4,094 samples |
| --- | ---: | ---: |
| Sum of called AN across SNPs | 4,167,968 | 4,144,750 |
| Sum of quality-filtered AN | 4,161,146 | 4,137,954 |
| Missing genotype entries | 15,686 | 15,565 |
| Low-GQ entries | 3,277 | 3,265 |
| Low-DP entries after the GQ check | 103 | 102 |
| Low-heterozygote-balance entries after earlier checks | 31 | 31 |
| Population/variant cells with quality-filtered AN = 0 | 3 | 3 |

The QC reasons are mutually exclusive sequential dispositions, not marginal counts of every
possible failure. AN sums count chromosome calls repeatedly across variants, not independent
people. Zero-AN cells are retained as unavailable counts; they are not zero allele frequency.

Corrected local count-table SHA-256 hashes:

- Technical QC: `cac845d4710724d45ff63a8814f9f7703f677e3d8c4e33b38aa50fcdb795c6ea`.
- Additional ancestry exclusions: `c940be8697ce4d6ec021a7fa317a1d68ff807f613ac5a37419854c92be10bd84`.
- Aggregate audit JSON: `0d21d84a8fd8c2757c032fa536f112139436542e77a8d38d981d00b8fd925b28`.

## Meaning, remaining work and verification

This is usable evidence that exact reference-panel allele counts can be prepared and checked.
It is not an independently validated model benchmark: **510 nearby SNPs are one short genomic
block, not 510 independent locus replicates**. No performance-selected filtering, model tuning,
inference or accuracy comparison has occurred. Geography remains approximate origin information;
recruitment footprints, present-day residence and collection dates are not established.

Next, package the research count contract and preparation diagnostics into reviewed reproducible
interfaces, then freeze a separately labeled within-resource development comparison. Explicitly
audit cross-population reported-kinship dependencies before splitting. A genome-wide experiment
needs prespecified additional blocks, unchanged count targets and separate population/locus
holdouts. The primary resident, 300 km footprint-buffer, independent external confirmation,
calibration and scientific release gates are not waived. CuGen remains optional and independent.

The acquisition and both count diagnostics exited successfully. Seven final hand-control tests
passed, after recorded missing-implementation failures; they cover genotype/missingness/QC
boundaries and population identity. The independent native count checks are actual-data checks,
not fixture results. Smoke passed all 40 tests after the last diagnostic correction.

The tracked AF branch's full CI commands also passed: Ruff, contract drift, module size, privacy,
smoke and **838 pytest tests**, with 11 skips and 15 rasterio `PendingDeprecationWarning`s.
This verifies the unchanged production code; ignored research diagnostics are outside that
pytest suite. Raw source slices, participant lists, count tables and diagnostic scripts remain
local research material, not a packaged or reviewed production ingestion implementation.
No genotype/count dataset or scientific surface is published by this documentation milestone.
