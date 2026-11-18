# Crowd crush warning research prototype

This repository contains offline research code for studying crowd motion and density. It is not a validated crowd safety system. Its outputs do not measure physical force, provide calibrated harm probabilities, or establish useful warning lead time.

## Implemented

The command line accepts already-extracted zone observations, validates them, computes causal trailing-window features, and produces conditional stochastic proxy-crossing frequencies. It also provides causal diagnostic baselines, local source-manifest integrity checks, event and alarm-episode matching scoped by recording context, and a parser and offline viewer for the published Pamplona temporal-density table.

The baseline arms are density, lagged persistence, and one-sided excess CUSUM. CUSUM is included as a diagnostic family informed by Page's continuous inspection schemes. Its parameters are explicit research settings, not calibrated thresholds. It does not reproduce Page's industrial calibration or establish warning performance.

The Pamplona table contains 90,000 rows with author-declared time in seconds relative to festival opening and spatially averaged density in m^-2. The three series contain 80,025, 85,875, and 90,000 numeric observations for 2022, 2023, and 2024. Their remaining rows are trailing padding: 9,975, 4,125, and 0. The table contains no velocity, calibrated harm probability, or outcome labels. The viewer inspects source values; it does not define a hazard threshold or produce a warning.

**Real crowd evaluation: NOT RUN. Warning effectiveness: NOT RUN.** Source inspection and software checks do not establish predictive or safety performance. The [status snapshot](docs/STATE.md) records these limits.

## Local commands

The commands use Python's standard library. They read local files and do not connect to a camera or service, except for the explicit `curl` download shown below.

```sh
PYTHONPATH=src python3 -m crowd_warning validate observations.jsonl
PYTHONPATH=src python3 -m crowd_warning features observations.jsonl --window-s 5
PYTHONPATH=src python3 -m crowd_warning forecast observations.jsonl --threshold 1.0 --horizon-s 30
PYTHONPATH=src python3 -m crowd_warning baselines observations.jsonl \
  --density-threshold 2 --proxy-threshold 2 --change-threshold 2
```

The forecast threshold and baseline parameters are model inputs, not safety limits. Forecast outputs are conditional proxy-crossing calculations. Commands write JSON to stdout; input or calculation errors produce JSON on stderr and a nonzero exit status.

### Inspect the published temporal-density table

Download the source file from the Zenodo record, verify it against the selected-file manifest, inspect its counts, and write a new standalone HTML viewer:

```sh
mkdir -p data
curl --fail --location \
  'https://zenodo.org/records/14050598/files/data_density_over_time.txt?download=1' \
  --output data/data_density_over_time.txt
PYTHONPATH=src python3 -m crowd_warning verify-source sources/pamplona-density.json --base-dir data
PYTHONPATH=src python3 -m crowd_warning inspect-density data/data_density_over_time.txt
PYTHONPATH=src python3 -m crowd_warning replay-density data/data_density_over_time.txt \
  --output pamplona-density-viewer.html
```

The parser accepts this exact tab-separated source schema and rejects partial or non-trailing missing pairs, non-finite values, negative densities, and non-increasing time. The viewer runs offline, uses a light-only display, and does not interpolate across missing rows. It refuses to overwrite an existing output file. The data file is not included in this repository.

The reviewed subset contains five selected source files totaling 4,697,499 bytes, checked against official source checksums. That inspection did not fetch or audit the full 1.22 GB Zenodo record. Source-file integrity does not establish rights clearance, label validity, or measurement calibration.

## Observation schema

JSON Lines (`.jsonl` or `.ndjson`) and CSV (`.csv`) inputs contain `timestamp_s`, `zone_id`, `density_per_m2`, `vx_mps`, `vy_mps`, `quality`, and `calibrated`. These are supplied measurements. The code does not derive them from video or independently verify calibration. Feature windows need at least two adequate observations per zone. Forecasting abstains when a zone lacks sufficient history or has gaps, poor quality, or unknown calibration.

Event matching uses recording identifiers when present, then event identifiers as a fallback, and includes venue context when supplied. Pooled rows without those identifiers must be partitioned by recording before matching. Alarm-episode matching expects selected alarm rows and matches episode starts within the requested horizon; it does not turn every forecast into an alarm.

## Data terms and attribution

MIT applies to original code in this repository only. Papers, datasets, videos, and other third-party material retain their own terms. The Zenodo record declares record-level CC BY 4.0; that declaration does not by itself settle file-level rights. Keep downloaded data external and review applicable terms before use. The [research references](CITATIONS.md) distinguish the five-author Nature paper from the three-author dataset record.
