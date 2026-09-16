# gnomAD and dbSNP — commercial-use checks

## TL;DR

Both sources allow commercial use of the data we publish. gnomAD says so with an explicit licence;
NCBI says it imposes no restrictions but stops short of granting permission, because it does not
hold the rights to grant. Neither is a blocker.

One thing to carry forward: gnomAD warns that *some* of its bundled annotations carry separate
restrictions and names SpliceAI only as an example. That list is not closed, so a new field arriving
in a gnomAD payload needs its own check rather than inheriting this one.

Both terms pages were read on **2026-09-15**. Resolves
[#294](https://github.com/bschilder/genomeOS/issues/294).

---

## gnomAD — `explicitly_open`

Read 2026-09-15 from https://gnomad.broadinstitute.org/policies. The rendered page is a JavaScript
application, so the text below was taken from its source of truth,
`browser/about/policies/terms.md` in `broadinstitute/gnomad-browser`, which is what that page
renders.

> The primary data from the gnomAD exomes and genomes are available free of restrictions under the
> Creative Commons Zero Public Domain Dedication. This means that you can use it for any purpose
> without legally having to give attribution.

That is an explicit licence permitting commercial use, so the finding is `explicitly_open` rather
than `no_restriction_found`.

### The part that constrains future payloads

> Some annotations may have restrictions on usage. For instance, SpliceAI annotations have been
> computed by Illumina and are provided with permission under a CC BY NC 4.0 license for academic
> and non-commercial use. It is the responsibility of users to abide by all relevant licensing
> requirements.

Note the wording: **"some annotations"** and **"for instance"**. gnomAD is not publishing a closed
list of restricted annotations, and it places the burden of checking on the user. So
`KNOWN_NON_COMMERCIAL_FIELDS["gnomad"]` in `scripts/export_atlas_web.py` should be read as the
restrictions we happen to know about, never as a complete set. Adding a field to a gnomAD payload
requires checking that field, not relying on the tripwire.

### What our payload actually carries

Checked against the committed record: `alt`, `canonical_consequence`, `chrom`, `clinvar`, `exome`,
`genetic_ancestry_group_frequencies`, `genome`, `genomic_constraint`, `joint`, `pos`, `ref`,
`rsids`, `source_url`.

No SpliceAI field is present. The frequency fields are the primary data the Creative Commons Zero
dedication names. The annotations present are ClinVar (NCBI, covered below), the consequence
prediction, and gnomAD's own constraint metric. None of these is a known non-commercial annotation.

### Not a commercial restriction, but binding anyway

> All users of gnomAD data agree to not attempt to reidentify participants.

A use restriction that has nothing to do with commerce, and one this project has no reason to
approach. Recorded so it is not lost.

There is also a trademark request: acknowledge gnomAD where possible, do not put "gnomAD" or
"Genome Aggregation Database" in the name of a tool, and do not use the logo without permission.
Trademark, not licence.

## dbSNP — `no_restriction_found`

Read 2026-09-15 from https://www.ncbi.nlm.nih.gov/home/about/policies/, section "Copyright Status
of Webpages", the paragraph covering the molecular databases. dbSNP is the molecular-variation
database named there.

> Databases of molecular data on the NCBI Web site include such examples as nucleotide sequences
> (GenBank), protein sequences, macromolecular structures, molecular variation, gene expression, and
> mapping data. [...] Therefore, NCBI itself places no restrictions on the use or distribution of
> the data contained therein. Nor do we accept data when the submitter has requested restrictions on
> reuse or redistribution. However, some submitters of the original data (or the country of origin
> of such data) may claim patent, copyright, or other intellectual property rights in all or a
> portion of the data (that has been submitted). NCBI is not in a position to assess the validity of
> such claims and since there is no transfer of rights from submitters to NCBI, NCBI has no rights
> to transfer to a third party. Therefore, NCBI cannot provide comment or unrestricted permission
> concerning the use, copying, or distribution of the information contained in the molecular
> databases.

### Why this is `no_restriction_found` and not `explicitly_open`

The two findings mean different things and the distinction matters here.

NCBI states it places no restrictions, and strengthens that by refusing submissions that come with
restrictions attached. But it explicitly declines to grant permission, because it holds no rights
to transfer. That is the definition of a completed check that found no restriction, not of an
explicit licence granting commercial use.

Recording it as `explicitly_open` would claim a grant that the source says in plain words it cannot
give.

### What our payload carries

`citation_count`, `hgvs`, `last_update_date`, `rsid`, `source_url`, and the `spdi` coordinate. These
are identifiers and coordinates, the least likely category to attract a submitter's intellectual
property claim.

## What a reviewer should confirm

An agent read these pages and recorded what they say. The reading is straightforward in both cases
and the text is quoted above so it can be checked without revisiting the sites. What a person may
want to confirm:

- that `no_restriction_found` is the right call for dbSNP rather than something weaker, given
  NCBI's explicit refusal to grant permission;
- that the gnomAD Creative Commons Zero dedication is understood to cover the aggregated frequency
  fields we publish, which is how the phrase "primary data from the gnomAD exomes and genomes"
  reads, rather than only the raw callset.
