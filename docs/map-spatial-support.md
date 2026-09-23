# MAP HbS explicit spatial support

The MAP HbS adapter accepts an observation only when its curated input declares where the sample
was recruited and supplies a radius that bounds that sampling support. This contract prevents an
area label from silently becoming geographic precision. It implements the no-default spatial
uncertainty requirement in Atlas design §§6–7 and the hard-error behavior in §12.

Every curated CSV has these columns:

| Field | Contract |
|---|---|
| `radius_km` | Finite, positive radius in kilometres, measured from the row's WGS84 coordinate. |
| `support_kind` | Exactly `sampling_bounding_disc`. |
| `coordinate_provenance` | Nonblank locator for the interpretation and source of the coordinate. |
| `radius_provenance` | Nonblank locator for the bounding radius evidence or reviewed derivation. |

An equal-area radius answers how large a circle has the same area as a footprint. It does not
bound distance from the coordinate: a narrow 100 km² polygon may extend much farther than the
radius of a 100 km² circle. Administrative area, original MAP area class, presumed catchment and
ancestral location therefore do not satisfy `sampling_bounding_disc`. The original `area_type`
remains in the curated source evidence, but it never changes the emitted radius.

The adapter first applies the existing count, coordinate and Piel-subset refusals. It validates
spatial support for every row that would otherwise enter P1. A missing required column, duplicate
support header, invalid support kind, blank provenance locator, or nonpositive/nonfinite radius is
a hard error for the whole input. No partial observation frame is returned. A row already refused
from P1 need not have per-row support values, but the four columns must exist so the file's
contract is explicit.

Untouched vendor exports contain area classes without these evidence fields and now intentionally
fail. Keep the raw export unchanged. A real curated input is a separate immutable, versioned
evidence asset; updates publish a new version rather than rewriting an input used by an existing
artifact. Structural parser acceptance does not establish that the supplied evidence is true,
independently reviewed, representative of residents, or eligible for publication.

Coordinate and radius provenance remain in the retained curated source evidence. The unchanged P1
schema and web export carry the accepted observation and exact declared radius; they do not claim
to carry or verify the entire evidence ledger. Likelihood support for spatially extended samples is
separate work tracked in issue #37. This boundary also leaves the existing genotype reconstruction,
typed-denominator threshold, study-cohort construction, population-screening designation and
ascertainment limitations unchanged.

The review figure uses wholly synthetic data and performs no fitting:

```bash
python scripts/plot_map_support_contract.py --out docs/figures/map_support_contract.png
```

It labels accepted survey points with their exact authored radii and hatches all other space as
unqualified. Its second panel calls the real loader on an area-only copy and records the refusal.
