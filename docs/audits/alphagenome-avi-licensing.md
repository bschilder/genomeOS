# AlphaGenome AVI — licensing record for the external reference tab

Why the Atlas publishes the AVI score freely, and what has to happen before it publishes the
feature breakdown alongside it.
Every statement below was read from the primary source on 2026-09-10.

## The governing terms

Google DeepMind, *AlphaGenome Services Additional Terms of Service*, last modified 2026-09-08,
https://deepmind.google.com/science/alphagenome/terms

Two definitions decide this, quoted verbatim:

> "AVI Score" means the AlphaGenome Variant Impact score which is a single score reflecting variant
> impact, as further described here. For clarity, the AVI Score Feature Breakdown (defined below)
> does not form part of AVI Score. "AVI Score Feature Breakdown" means the breakdown showing
> features and inputs used to generate the AVI Score.

> Subject to your compliance with and without prejudice to the other provision of these Terms, AVI
> Scores and other artifacts that are made available for download within the "Permissive Use
> Downloadable Artifact" section of the AlphaGenome Services website ("Permissive Use Downloadable
> Artifacts for Commercial and Non-Commercial Use") may be used for commercial use and in connection
> with any commercial organisations.

The general restriction, with the AVI carve-out stated parenthetically:

> This means that only individuals and non-commercial organizations (universities, non-profit
> organizations and research institutes, educational and government bodies) may use the AlphaGenome
> Assets and only for non-commercial purposes (except for the AVI Score, which may be used for
> commercial purposes).

## What we publish, and what we do not

Published in the AVI card: `avi_phred`, `avi_raw_score`, `avi_tail_quantile`, `dominant_modality`,
`deep_link`, `model_version`, `prediction_class`. These are the AVI Score and the metadata that
identifies it.

Not currently published: the per-feature attribution breakdown. That is the AVI Score Feature
Breakdown, which the first definition places outside the AVI Score, and which DeepMind's own
download listing carries under "Downloadable artifacts for non-commercial use only". It is the
restricted half of a source that is otherwise permissively licensed, which is the same shape as
gnomAD shipping CC0 data with CC BY-NC SpliceAI annotations bundled in.

### It may be published, marked

genomeOS is a non-commercial open atlas, so the non-commercial grant covers publishing the
breakdown. The maintainer's ruling is that we may include it **provided it is marked clearly enough
that a future commercial component can extract all of it at once**. The mechanism for that is in
[`docs/non-commercial-data.md`](../non-commercial-data.md): the resource's `commercial_use` block
declares `finding: "restricted"` and names `top_attributions` in `restricted_fields`, and
`python scripts/check_commercial_use.py --list` then reports it as data a commercial build must
remove.

Adding it is a separate data change from the marking machinery, and it is gated on the acquisition
question below rather than on the licence.

Enforced in two places, so the two gates agree rather than one relying on convention:

- `KNOWN_NON_COMMERCIAL_FIELDS` in `scripts/export_atlas_web.py` refuses a cache payload carrying
  the field unless the declaration names it. Marked it may ship; unmarked it may not, whoever
  re-adds it to the JSON.
- The `record` object in `website/src/atlas/contracts.ts` is a strict object, so the browser
  contract rejects a field it does not know at parse time. Publishing the breakdown means adding it
  there deliberately, in the same change that declares it.

## Acquisition path, still to confirm

The commercial carve-out is worded against artifacts "made available for download within the
'Permissive Use Downloadable Artifact' section", not against the AVI value however it was obtained.
The committed payload records `AlphaGenome (Avsec et al. 2026); Atlas AVI, accessed 2026-09-09`,
which is a read through the Atlas interface rather than the bulk download. Sourcing the score from
the permissive download (`avi_scores_snvs...`) is the low-risk path and also settles the refresh
cadence question. `alphagenome@google.com` is the contact the terms name for it. This is a
maintainer call, tracked upstream rather than resolved here.

## Not a restriction

AlphaMissense predictions are licensed CC BY 4.0. Verified at
https://github.com/google-deepmind/alphamissense (`README.md`, "AlphaMissense predictions License")
and by the change that did it, commit `fe2dc845` on 2024-03-13, *"Update AlphaMissense predictions
database license."* The AlphaMissense contribution to `dominant_modality` therefore imposes no
non-commercial term downstream, and the earlier concern recorded in #193 is out of date.

## If a model-inference path is ever added

The AVI score is a lookup against a coordinate-keyed atlas. AlphaGenome the model is
sequence-to-function, so it could score an allele that carries no coordinate, and the Model Terms
govern the model parameters and general outputs with no AVI-style exception. That is why `method`
exists as a discriminator next to `source` in the external-resource contract: `source` names the
provider, `method` names how the value was obtained, and the coordinate requirement attaches to the
`atlas_lookup` method only.
