# Climate covariates: qualify decoding before testing predictive value

Status: `automated_proposal` / `pending`, 2026-09-10. Advances
[#189](https://github.com/bschilder/genomeOS/issues/189) WP3, Atlas design §§4–9,
12 and the [global modeling plan](../superpowers/plans/2026-09-09-global-af-modeling.md).
This note admits no source or feature and claims no allele-frequency improvement.

## Scientific contract

Objective: test whether present-day, historical and ancient climate information
improves withheld allele-count prediction after the strongest eligible genetic/
spatial baseline, terrain and population covariates. The first bounded candidate
is temperature and precipitation normals, not the whole temporal program. The
output now is a traceable candidate and decoding checklist; the eventual
interface is an immutable offline space-time-support feature artifact. Raster/
network I/O never enters fitters or serving.

Climate is modeled environmental information, not genetic observations or proof
of selection. Missing sample dates, footprints, uncertainty and support remain
missing. A fine climate grid does not establish fine genetic resolution. Modern
normals are not an evolutionary exposure history or a paleoclimate reconstruction.

## Three temporal tracks, not interchangeable climate labels

The owner's September 10 clarification includes ancient climate spanning human
divergence from non-human primates to the present, not merely the last glacial
cycle. Keep that full research scope even where qualified data are unavailable.

| Track | Intended information | Required distinction |
|---|---|---|
| Present-day | Climate associated with a declared contemporary target or sampling period, including normals and separately tested anomalies/extremes | A 1981–2010 normal is a fixed modern reference, not current weather or an observation made today. |
| Historical | Dated recent-past conditions along qualified population histories | Climate at a current residence is not ancestral exposure; calendar support and migration uncertainty remain explicit. |
| Ancient | Reconstructions across the requested evolutionary interval, including deep-time and more recent paleoclimate | Time slices, proxy records and model ensembles are distinct evidence; do not invent continuous fine-resolution global coverage or a single exact divergence date. |

These are scientific tracks, not an arbitrary universal date cutoff. Record each
source's actual interval, calendar/age convention, time step, spatial support,
available date, proxy/model lineage and uncertainty. A gap stays unavailable;
interpolation or downscaling is a separately tested model, not newly observed
climate. Ancient sea level, ice sheets, coastlines and land configuration require
time-appropriate support rather than blindly sampling today's terrain grid.

Audit present-day/reanalysis, historical and deep-time sources independently.
Test each family and its incremental contribution on the same eligible evaluation
rows before combinations. Separate retrospective reconstruction using later
information from prediction constrained to information available at the cutoff.
For temporal prediction, retain forward-time holdouts; for retrospective history,
retain independent ancient sites/time windows. Neither random year splitting nor
leaving nearby, source-dependent reconstructions in training establishes temporal
generalization. The resident target remains primary; origin and historical
allele-frequency outputs require their own validation under WP7.

## Candidate and reuse boundary

Prioritize **CHELSA-climatologies V2.1, 1981–2010**, monthly `tas` and
`pr`, from the provider-linked current delivery for further qualification as a
modern reference normal. The provider lists CC0 for this dataset, distinct
from the model code's GPLv3. Its catalogue also includes future periods; only the
exact historical assets belong to this candidate. The landing page's publication
date is June 2021, not a claim that the data were available during 1981–2010.
[Dataset metadata and terms](https://www.chelsa-climate.org/datasets/chelsa_climatologies),
[model metadata](https://www.chelsa-climate.org/models/chelsa).

WorldClim V2.1, 1970–2000, is a possible scientific comparator, but its terms
require permission for commercial use or redistribution. Do not assume genomeOS
research is noncommercial or that public download links grant those rights.
It is not admitted here. Different normal periods also confound a simple
WorldClim-versus-CHELSA comparison. [WorldClim release](https://www.worldclim.org/data/worldclim21.html),
[WorldClim terms](https://www.worldclim.org/about.html).

## Exact delivery changes the decoder

The EnviDat catalogue explicitly names resource
`ee935f48-b3da-432d-961d-f815289e476f` as **CHELSA V2.1 (current)** and links the
`os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/` delivery. The
catalogue reports version 2.1 and CC0-1.0; this is provider linkage, not a guess
from matching filenames. [Provider catalogue API](https://www.envidat.ch/api/3/action/package_show?id=chelsa-climatologies).

Only January `tas` and `pr` were sampled from each delivery: four retained 1 MiB
prefixes in total, not complete rasters. Current-object responses were HTTP 206,
bytes 0–1048575, against full sizes 149,078,236 and 346,942,826 respectively.
Such segments can contain compressed pixel payload; no pixel array was decoded,
valid mask established or global coverage tested.
[Current January temperature](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/tas/1981-2010/CHELSA_tas_01_1981-2010_V.2.1.tif),
[current January precipitation](https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/climatologies/pr/1981-2010/CHELSA_pr_01_1981-2010_V.2.1.tif),
[legacy temperature](https://os.zhdk.cloud.switch.ch/chelsav2/GLOBAL/climatologies/1981-2010/tas/CHELSA_tas_01_1981-2010_V.2.1.tif),
[legacy precipitation](https://os.zhdk.cloud.switch.ch/chelsav2/GLOBAL/climatologies/1981-2010/pr/CHELSA_pr_01_1981-2010_V.2.1.tif).

| Inspected base-directory metadata | Legacy January files | Current January files |
|---|---|---|
| Temperature scale / offset | `0.1 / -273.15`; no unit item retained in header | `0.1 / 0`; header unit `K` |
| Precipitation scale / offset | `0.1 / 0` | `0.1 / 0`; header unit `kg m-2 month-1` |
| UInt16 nodata | `-2147483647`, outside the type's range | `65535`, representable |
| Layout | Deflate, one-row strips | LZW, 512 × 512 tiles and seven overview directories |
| Grid | 43,200 × 20,880, EPSG:4326 | Same inspected grid and GeoKeys |

The captured prefixes differ. This resolves a metadata difference, not decoded
cell equivalence. Do not reuse the legacy Celsius offset on the current kelvin
delivery or apply an extra conversion. Technical specification §7.1 describes
the former Celsius transform; §4 prints 20,800 rows, unlike all four inspected
headers. Native spacing is approximately 1/120 degree with a half-arcsecond grid
offset and northern edge near 84°N. Use exact inspected geometry, not a guessed
standard grid. Representable nodata does not prove correct masks, and valid zero
precipitation must remain distinct from missingness. Full-file checksums, decoded
values, the other 22 current assets, land/ocean support and full COG compliance
remain unverified. The complete specification was read; its grid and climatology
tables were also visually inspected. [CHELSA V2.1 technical specification,
document v1.2, §§3–4 and 7.1](https://www.envidat.ch/dataset/2adb0c83-4653-4337-af28-f75c63ab7c74/resource/61fff0a7-6abb-45f7-a5f6-48f6e2c24851/download/chelsa_file_specification.pdf).

The current precipitation header also declares
`cf_standard_name=precipitation_flux`, whose CF canonical units are `kg m-2 s-1`,
alongside `variable_unit=kg m-2 month-1`; the CHELSA climatology specification
describes a precipitation amount in `kg m-2`. Record this semantic mismatch and
resolve the calendar-month support explicitly in decoder qualification. A generic
CF converter must not silently reinterpret monthly accumulations as an
instantaneous flux or assume a fixed month length. The proposed sum below remains
conditional on establishing monthly-amount semantics for the selected assets.
[CF Standard Name Table v81, precipitation_flux](https://cfconventions.org/Data/cf-standard-names/81/build/cf-standard-name-table.html#precipitation_flux).

## Extraction and falsifiable comparison

Before extraction, pin all 24 assets, terms, strong checksums, available date,
normal period, native geometry, units, packing and mask behavior. Test known land,
ocean, coastline, dry-zero and high-latitude cases with the intended reader. Header
consistency is insufficient: inspect decoded values and documented support before
admission. A failed check is a refusal, not permission to choose a plausible default.

Use reviewed footprints; label physical-area overlap weighting as a uniform-area
exposure assumption, not measured recruitment geography. For radius-only support,
compare uniform-area and population-weighted assumptions as WP2 requires; neither
is recruitment truth. A WorldPop-weighted sensitivity is source-dependent, not
independent validation of climate's effect. Retain valid/excluded support and test
grid offsets, dateline crossings and partial coverage. Start with
two proposed summaries: day-count-weighted monthly temperature normals and the
sum of monthly precipitation amounts. For 1981–2010, month weights are
`930,847,930,900,930,900,930,930,900,930,900,930`, totaling 10,957 days. This defines
a feature from monthly normals, not a reconstruction of daily or yearwise climate.
Precipitation includes water in liquid and solid phases; preserve amount/time
support rather than treating a monthly accumulation as an instantaneous rate.

CHELSA uses atmospheric forcing and terrain-aware downscaling; WorldPop also
incorporates climate and terrain information. Their inclusion is not independent
confirmation. Exact upstream release/cell relationships still need qualification.
See the companion [terrain](terrain-covariate-qualification-2026-09-10.md) and
[demographic](demographic-covariate-qualification-2026-09-10.md) notes.

Freeze the same outcome rows, folds and scoring weights across baseline, added
climate, missingness-only and spatially structured controls. Test climate's
incremental value after terrain, population and genomic structure. Fit scaling,
selection and any explicitly permitted missing-value strategy only within training
partitions. Retain failed folds and unchanged evaluation coverage; report paired
uncertainty, calibration and regional/rare-allele strata. Reserve independent final
confirmation. Modern available-date violations permit only retrospective labeling,
not prediction-time claims. No sampled climate data, features, genetic observations,
production schema, denominator or serving behavior is changed by this note.
