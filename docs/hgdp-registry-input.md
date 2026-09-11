# HGDP registry input

The HGDP adapter consumes a curated tab-separated file. It is not an importer for an untouched
vendor export. Before building the registry, the curator must establish what each coordinate
represents, what geographic support is justified, and which evidence supports both values.
Parsing checks the supplied representation; it does not inspect or qualify the cited sources.

## Required input

Every file must have these five columns:

| Column | Meaning |
|---|---|
| `population` | Source population label |
| `latitude` | Finite WGS84 latitude in `[-90, 90]` |
| `longitude` | Finite WGS84 longitude in `[-180, 180]` |
| `uncertainty_radius_km` | Finite, strictly positive spatial-support radius in kilometres |
| `provenance` | Locator identifying the supporting coordinate/support source and version |

Additional well-formed columns, such as `region`, are permitted. For example:

```tsv
population	latitude	longitude	uncertainty_radius_km	provenance
Example	1	2	2.5	synthetic:example-v1#row-1
```

Population labels and provenance are preserved literally, including leading zeros, strings such
as `NA`, and leading or trailing whitespace in a nonblank field. Multiple evidence locators may
share the existing `provenance` string field, provided the value identifies the sources and their
versions. The parser does not interpret or verify those locators.

The build refuses a missing or duplicate header, a blank column name, a missing required column,
a blank required value, a malformed or ragged record, a nonnumeric or nonfinite number, a radius
that is zero or negative, an out-of-range coordinate, or a population label that cannot produce a
unique canonical identifier. Rows are never silently dropped, repaired, or filled from defaults.

## Output contract

`genomeos.registry.sources.hgdp.load` still returns the canonical population and alias tables.
The population table contains `population_id`, `lat`, `lon`, `uncertainty_radius_km`,
`location_type`, `provenance`, `biocultural_notice`, and `registry_version`. The alias table
contains `population_id`, `source`, and the literal `label`. HGDP rows retain
`location_type="ancestral"` and the CARE-aligned biocultural notice. The frozen schemas and public
adapter signature are unchanged.

Schema-valid output does not certify the source review, population identity, coordinate meaning,
sampling footprint, residency, or eligibility for a scientific benchmark. Those qualifications
precede parsing and remain open scientific work under [#21](https://github.com/bschilder/genomeOS/issues/21)
and [#219](https://github.com/bschilder/genomeOS/issues/219).

## Migrating existing files

Existing four-column files now fail. Each row must be curated with evidence supporting its
coordinate and spatial extent, then supplied with explicit `uncertainty_radius_km` and
`provenance` values. There is intentionally no conversion command or default-fill recipe because
those values cannot be derived from the old fields.

The six-row file at `tests/fixtures/hgdp_populations.tsv` is synthetic test data. Its radii and
locators are hand-written values used only to verify parsing and serialization; they are not
measured or inferred extents of the named populations and do not satisfy the source-qualification
work tracked in #21 or #219.
