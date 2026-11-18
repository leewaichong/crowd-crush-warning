# Pamplona 30-second density forecast benchmark

**Run completed:** 2026-11-18, at clean Git SHA `53c35c42087d76614e16d2b14bfd630acfb5e15b`.

This is a descriptive forecast benchmark on the published Pamplona spatial-average density table. The input reports source-declared density in m^-2. It is not an independent measurement-accuracy study or a crowd-crush warning evaluation. The dataset's preprocessing and causal interpretation have not been independently verified.

## Design

The run fitted the local-trend and discrete AR(1) forecasts using 2022 only. The persistence control carries forward the latest observed density. The 2023 check and 2024 same-venue holdout each forecast 30 seconds ahead from scheduled origins 30 seconds apart. Forecast errors use source-declared density units, m^-2. The 2022 training results are in `metrics.json` as an in-sample diagnostic and are not held-out performance.

| Year and split | Arm | Completed origins | MAE (m^-2) | RMSE (m^-2) |
| --- | --- | ---: | ---: | ---: |
| 2023 check | Persistence | 113 | 0.0660 | 0.0806 |
| 2023 check | Local trend | 113 | 0.0747 | 0.1005 |
| 2023 check | AR(1) | 113 | 0.4897 | 0.6157 |
| 2024 same-venue holdout | Persistence | 118 | 0.0673 | 0.0914 |
| 2024 same-venue holdout | Local trend | 118 | 0.0723 | 0.1011 |
| 2024 same-venue holdout | AR(1) | 118 | 0.4394 | 0.5534 |

All scheduled origins completed, with zero excluded origins in both years. The input table has 85,875 source observations for 2023, with 4,125 trailing padding rows excluded, and 90,000 source observations for 2024, with no trailing padding.

## Descriptive paired intervals

The following are 1,000 paired block-bootstrap intervals with block length 5. Each delta is the arm's error minus persistence error; positive values mean higher error than persistence. These intervals are descriptive, not significance tests.

| Year | Arm vs persistence | MAE delta interval (m^-2) | RMSE delta interval (m^-2) |
| --- | --- | ---: | ---: |
| 2023 | Local trend | [-0.0009, 0.0178] | [0.0061, 0.0323] |
| 2023 | AR(1) | [0.2841, 0.5877] | [0.3687, 0.6959] |
| 2024 | Local trend | [-0.0053, 0.0152] | [-0.0047, 0.0238] |
| 2024 | AR(1) | [0.2508, 0.5047] | [0.3314, 0.5822] |

The run does not establish venue generalization, statistical significance, promotion of an arm, sensor accuracy, or warning effectiveness. A density forecast is not a measurement of physical force or harm. Motion accuracy and warning effectiveness are **NOT RUN**. Raw metrics, origins, model, and configuration are included with checksums and run provenance in `provenance.json`.

The input table comes from the CrowdDNA release by François Gu, Benjamin Guiselin, and Denis Bartolo, Zenodo record [10.5281/zenodo.14050598](https://doi.org/10.5281/zenodo.14050598), which declares CC BY 4.0 at record scope. The original repository code is MIT licensed. See [CITATIONS.md](../../CITATIONS.md) for the distinct Nature-paper and dataset-record attributions.
