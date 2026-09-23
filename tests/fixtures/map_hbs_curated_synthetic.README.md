# Synthetic MAP spatial-support contract fixture

`map_hbs_curated_synthetic.csv` is wholly authored test data. It contains no real MAP survey ID,
location, spatial support, study, citation, or scientific claim. No real MAP support evidence was
reviewed or inferred to create it. `country=Synthetic` and the `SYNTHETIC-` study prefixes make
that boundary explicit.

The authored coordinate and bounding-disc radius pairs are:

| Survey ID | Latitude | Longitude | Radius (km) |
|---:|---:|---:|---:|
| 9001 | 10.0 | -20.0 | 73.25 |
| 9002 | 15.5 | -12.25 | 18.5 |
| 9003 | 2.0 | 5.0 | 4.0 |
| 9004 | -8.0 | 12.0 | 31.75 |
| 9005 | 22.0 | 30.0 | 9.25 |
| 9006 | -18.5 | 40.0 | 122.0 |
| 9007 | 35.0 | 48.0 | 15.0 |
| 9008 | -30.0 | 55.0 | 27.0 |
| 9009 | 42.0 | 65.0 | 6.5 |
| 9010 | not supplied | 72.0 | 88.0 |
| 9011 | 5.0 | 80.0 | 44.5 |

Every `coordinate_provenance` and `radius_provenance` value is an authored
`synthetic:map-support#...` test locator. These locators do not represent an external source,
independent verification, scientific review, or publication eligibility.
