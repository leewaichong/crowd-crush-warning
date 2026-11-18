# Pamplona density change-point forecast

This is the completed, descriptive result of one exploratory forecast run on a published spatial-average density series. It is separate from a warning evaluation. An independent audit completed at `2026-11-18T06:09:35.866963+00:00`; all 21 checks passed and the findings list was empty. Maintainer review of the producer script, results, provenance, and audit is complete.

## Run record

The input was the density table from the CrowdDNA Zenodo record 14050598, with source-declared units m^-2 and timestamps in seconds relative to festival opening. The input SHA-256 was `cbc48912b51e1824017b046a6ee5f1d5eef19a529ba33d9aee361d21cd36561c`. The table's authors are François Gu, Benjamin Guiselin, and Denis Bartolo. The related Nature paper has five authors; see [CITATIONS.md](../../CITATIONS.md) for both attributions and the record's CC BY 4.0 terms.

The run used clean tracked Git SHA `345275100aaae31b9810a95a8eeec8cfe8a0a3b9`. It started at `2026-11-18T05:59:48.334012+00:00` and completed at `2026-11-18T06:00:03.203354+00:00`. The executed command was:

```sh
/Users/waichong/miniconda3/bin/python3 /Users/waichong/worktrees/crowd-m06-density/work/m06-density/run.py --run
```

The archived [executed script](executed_script.py) has SHA-256 `54b60edaafc693b8644a24628c048a30b307850a521865a9ae07d64f8112b5cc`. It is a byte-for-byte copy of the script used for the run. It contains workspace-specific paths and is evidence of the executed source, not a portable entry point. The start manifest records the frozen protocol SHA-256 `5472fb288821ab42054a39df80924285ec50176a93b63aefeb82cd66897b7071`.

## Forecast rule

Each forecast used the 30 seconds ending at its origin and predicted the next 30 seconds on the source-native 0.04-second grid. It used no observations after the origin. The candidate has either one constant segment or one split into two constant segments. Each segment must span at least five seconds.

The rule minimizes `n * log(SSE / n) + k * log(n)`, using `k=1` for no split and `k=3` for one split. Exact ties favor no split, then the earliest split. Zero SSE receives a score of negative infinity. This is a BIC-inspired heuristic, not standard BIC applied under a validated likelihood, a posterior probability, or a significance test. The density series is serially dependent, and the split location is searched. Frequent selected splits do not show that the underlying crowd experienced physically real change points.

The exact retained M04 schedule supplied 336 origins: 105 in 2022, 113 in 2023, and 118 in 2024. The audit checked every origin and target against the source, all output residuals, aggregate and per-year metrics, paired differences, 30-second causal history bounds, and retained controls. Persistence and AR(1) predictions exactly match the retained values. The run's causal local-trend predictions match the retained local-trend values on all 336 rows within `1e-10`; the maximum absolute difference was `1.0658141036401503e-14`, from equivalent algebraic expressions. Trailing mean and one-split forecasts were computed by the run. Independent split selection was recomputed with a separate `math.fsum` implementation on three sampled origins per year, nine rows total. The audit did not rerun all split fits. Its full report and executed audit script are included as `audit.json` and `audit_script.py`.

## Descriptive errors

Values are MAE / RMSE in source-declared m^-2. All five arms have coverage on the full 336-row schedule.

| Year | Origins | Persistence | Trailing mean | Local trend | Retained AR(1) | One split | Selected split / no split |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 105 | 0.0833 / 0.1119 | 0.0804 / 0.1078 | 0.1130 / 0.1919 | 0.4819 / 0.5474 | 0.0763 / 0.1106 | 105 / 0 |
| 2023 | 113 | 0.0660 / 0.0806 | 0.0605 / 0.0742 | 0.0747 / 0.1005 | 0.4897 / 0.6157 | 0.0561 / 0.0720 | 111 / 2 |
| 2024 | 118 | 0.0673 / 0.0914 | 0.0617 / 0.0787 | 0.0723 / 0.1011 | 0.4394 / 0.5534 | 0.0577 / 0.0749 | 115 / 3 |

Overall, one-split MAE / RMSE was 0.0630 / 0.0868; trailing mean was 0.0671 / 0.0875; persistence was 0.0719 / 0.0950. The split rule selected one split for 331 histories and no split for 5.

These are descriptive forecast errors on one venue's series. The 2024 data had already been inspected, so it is exploratory reuse, not a fresh confirmatory holdout. The results do not establish warning accuracy, change-onset accuracy, physical force, a crowd mechanism, safety, or generalization to other venues.

## Files and review status

`manifest.json`, `trail.jsonl`, `origins.jsonl`, `metrics.json`, and `comparison.json` are byte-for-byte copies of the completed run artifacts. The run manifest and event trail retain their original hashes. `origins.jsonl` contains derived forecasts and target density observations from the CC BY 4.0 source, with attribution in [CITATIONS.md](../../CITATIONS.md). The full source table is not included; target density observations remain in the derived per-origin outputs under the source's CC BY 4.0 terms and attribution. The audit found no discrepancies in the checks it performed. Its stated limits, including sampled rather than exhaustive independent split-fit recomputation, remain part of this result.
