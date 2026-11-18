# Crowd crush warning research prototype

## Research question

Can changes in observed crowd motion provide a reproducible basis for studying how hazardous crowd dynamics develop? This repository is an offline research prototype for exploring that question. It is not a validated crowd safety system, and its outputs are not evidence of physical force, injury risk, or useful warning lead time.

## What the code currently does

The current input begins after video analysis: each record describes a zone observation with a timestamp, a density value, two velocity components, quality, and a calibration flag. The code validates those records, computes causal trailing-window features for each zone, and can simulate conditional proxy-crossing frequencies under a selected stochastic model. It does not ingest camera footage, estimate these fields from pixels, fit a propagation model from crowd data, or issue a validated warning.

The temporal zone-average velocity variance in this prototype is variance across successive observations for a zone. It differs from the local spatial variance around a local velocity field used in Helbing, Johansson, and Al-Abideen's 2007 analysis. The prototype's global mean-reversion model also does not represent measured spatial propagation between people or zones. See the [literature review and research questions](docs/exploration.md) and [source citations](CITATIONS.md) for context and attribution.

## Current status

Implemented code includes offline observation ingestion, temporal zone-motion features, conditional stochastic proxy-crossing forecasts, evaluation helpers, and a command-line interface. Forecasting abstains when any observed zone lacks two complete adequate observations. Forecast output records its origin and input cutoff, seed, effective model parameters, and time discretization. Evaluation helpers include alarm-episode matching for preselected alarm rows, disjoint valid timeline exposure accounting, venue/event splitting, and chronology checks. The legacy row-matching helper remains available; callers must select episode matching when they need episode-level accounting.

**Real crowd evaluation: NOT RUN. Warning effectiveness: NOT RUN.** No real crowd dataset has been admitted, no harm probability is calibrated, and there is no evidence of useful warning performance. The [status snapshot](docs/STATE.md) records the integrated implementation and remaining evidence limits.

## Offline use

The commands below run against a local observations file. They do not contact a service or load video.

```sh
PYTHONPATH=src python3 -m crowd_warning validate observations.jsonl
PYTHONPATH=src python3 -m crowd_warning features observations.jsonl --window-s 5
PYTHONPATH=src python3 -m crowd_warning forecast observations.jsonl --threshold 1.0 --horizon-s 30
```

The forecast command requires an explicit threshold. That is a model input for conditional proxy-crossing calculations, not a safety threshold. The commands write JSON to stdout. Input, integration, or non-finite output errors produce a JSON error on stderr and a nonzero exit status.

## Input schema

The loader accepts JSON Lines (`.jsonl` or `.ndjson`) and CSV (`.csv`). Each record has:

| Field | Meaning |
| --- | --- |
| `timestamp_s` | Observation time in seconds |
| `zone_id` | Zone identifier |
| `density_per_m2` | Supplied density value per square metre |
| `vx_mps`, `vy_mps` | Supplied velocity components in metres per second |
| `quality` | Supplied observation quality value |
| `calibrated` | Whether the supplied observation is marked calibrated |

The code does not derive these fields from video or independently verify the calibration. Feature windows require at least two observations for a zone before variance is available. Forecasting abstains if any observed zone lacks two complete adequate feature observations, or if observations have gaps, poor quality, or unknown calibration. The response enumerates incomplete zones and records forecast origin, input cutoff, seed, effective parameters, and discretization.

## Research limits and data terms

The [research review](docs/exploration.md) separates published findings from hypotheses and this prototype's implementation. It summarizes mechanism evidence, camera limits, candidate models, prior work, dataset records, and open research questions. No experiment is run by these commands.

MIT applies to original code in this repository. It does not grant rights to papers, video, datasets, images, or other third-party material. Check each source's own licence and terms before obtaining or using it. The Zenodo record linked to Gu et al. is open under record-level CC BY 4.0 and lists 46 files totalling 1,217,698,331 bytes. No payload files were fetched or audited, so labels, calibration, and whether record-level terms apply to each file remain unchecked. Keep payloads external and inspect rights and contents before use. Public records reviewed here still do not establish a dataset pairing camera observations with independently adjudicated crush outcomes and matched non-event periods. See the research review for access distinctions.

## Licence and attribution

The original code is licensed under the [MIT License](LICENSE), copyright 2026 Lee Wai Chong. Research methods and findings remain attributed to their authors; references are listed in [CITATIONS.md](CITATIONS.md). Those references motivated questions explored here. They are not evidence that this code reproduces the papers or works empirically.
