# Crowd crush warning research prototype

This repository contains offline research code for studying crowd motion and density. It is not a validated crowd safety system. Its outputs do not measure physical force, provide calibrated harm probabilities, or establish useful warning lead time.

## Implemented

The command line accepts already-extracted zone observations, validates them, computes causal trailing-window features, and produces conditional stochastic proxy-crossing frequencies. It also provides causal diagnostic baselines, local source-manifest integrity checks, event and alarm-episode matching scoped by recording context, and a parser and offline viewer for the published Pamplona temporal-density table.

The baseline arms are density, lagged persistence, and one-sided excess CUSUM. CUSUM is included as a diagnostic family informed by Page's continuous inspection schemes. Its parameters are explicit research settings, not calibrated thresholds. It does not reproduce Page's industrial calibration or establish warning performance.

The optional `assess_motion_quality` and `project_motion_video` Python APIs bind caller-supplied visibility, camera, and calibration evidence to image-space motion results. Missing evidence abstains. The projection is conditional reference-plane image-pattern motion, not verified pedestrian velocity. The APIs do not independently validate supplied evidence or estimate motion accuracy. See the [offline research workflow](docs/offline-research-workflow.md) for their inputs and limits.

The Pamplona table contains 90,000 rows with author-declared time in seconds relative to festival opening and spatially averaged density in m^-2. The three series contain 80,025, 85,875, and 90,000 numeric observations for 2022, 2023, and 2024. Their remaining rows are trailing padding: 9,975, 4,125, and 0. The table contains no velocity, calibrated harm probability, or outcome labels. The viewer inspects source values; it does not define a hazard threshold or produce a warning.

**Density forecasting component: evaluated descriptively** on one published spatial-average density series. The [30-second benchmark](results/pamplona-density-30s-2026-11-18/README.md) and [exploratory change-point run](results/pamplona-change-point-2026-11-18/README.md) do not establish independent measurement accuracy, venue generalization, or warning effectiveness. The change-point results passed a 21-check independent audit and maintainer review; the audit's nine split-fit spot checks are not a full refit. **Motion accuracy: NOT RUN. Real crowd warning evaluation: NOT RUN.** See the [status snapshot](docs/STATE.md).

The [controlled-trial co-movement study](results/controlled-co-movement-2026-11-18/README.md) reports an independently audited, exploratory analysis of native-frame motion in one previously inspected trial. It describes correlations and common-mode sensitivity, without estimating propagation, physical response time, force, or warning accuracy.

The [Lyon switching-state result](results/lyon-switching-state-2026-11-18/README.md) reports one descriptive evaluation of chronological source-reported next-frame increments within supplied traces. It does not establish physical measurement accuracy, generalization, or warning effectiveness.

## Local commands

For the current source-integrity, timestamp/decode, pixel-motion, and density-replay workflow, see the [offline research workflow](docs/offline-research-workflow.md).

For source access, annotation limits, and reuse terms across real and synthetic crowd datasets, see the [crowd annotation source review](docs/annotation-source-review.md).

The commands use Python's standard library unless noted below. They read local files and do not connect to a camera or service, except for the explicit `curl` downloads shown here.

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

The original five-file CrowdDNA subset totals 4,697,499 bytes. The selected CrowdDNA video and Lyon archive are separate additions, recorded in [their manifests](sources/pamplona-video.json) and [Lyon manifest](sources/lyon-topview.json). These are selected files, not full-record inventories. Source-record licence metadata and file integrity checks do not establish measurement calibration or clear rights beyond the stated source terms.

### Inspect selected video timestamps and decoding

Download the selected video from the [CrowdDNA Zenodo record](https://doi.org/10.5281/zenodo.14050598), then check the local file against its selected-file manifest:

```sh
mkdir -p data
curl --fail --location \
  'https://zenodo.org/api/records/14050598/files/video_crowd.mov/content' \
  --output data/video_crowd.mov
PYTHONPATH=src python3 -m crowd_warning verify-source sources/pamplona-video.json --base-dir data
PYTHONPATH=src python3 -m crowd_warning inspect-video data/video_crowd.mov
```

`inspect-video` requires local `ffprobe` and `ffmpeg`. It reports stream metadata and actual presentation timestamps, then decodes the video stream to a null output without audio. A completed command reports timing status `ok` or `abstain`; missing, duplicate, or non-monotonic timestamps can cause abstention. Tool, probe, decode, or input failures produce a nonzero command status. Optional `--max-gap-s` reports caller-declared timestamp gaps and marks timing `abstain` when a gap exceeds that value. It is not a safety threshold and does not infer missing physical frames. Nominal frame rate is metadata, not a substitute for decoded timestamps.

`inspect-motion` uses the same local `ffprobe` and `ffmpeg` tools and also requires NumPy. NumPy is imported only for this command; the other commands above do not need it. The command resizes grayscale frames to width 320 by default and samples at one-second intervals by actual decoder presentation timestamps, not nominal frame rate. It reports integer-pixel, mean-SSD block matches. It does not reproduce Gu et al.'s method or a PIV method. The block matcher is an image-space baseline. The resize is specified in pixels, but physical scale and physical motion remain unknown. Camera motion and visibility are not assessed. A unique SSD minimum is not a confidence score, an accuracy measure, or visibility clearance. `at_search_boundary` means the selected minimum reaches the configured search limit, so the match may be truncated by that limit. The optional caller-supplied background summary does not independently verify that those cells are background.

```sh
PYTHONPATH=src python3 -m crowd_warning inspect-motion data/video_crowd.mov
```

At clean SHA `5c1d268c4060798701f6a1be3ec1ba2704537f35`, a real-input software check completed successfully on the selected CrowdDNA video on 18 November 2026. It bound 251 decoded frames to native timestamps and selected 10 pairs, each with 190 blocks at 320 by 180 pixels. Between 17 and 32 block matches per pair reached a search boundary. This verifies software operation on that input only. It does not establish motion beyond the search window, camera stability, or people motion. Independent motion accuracy and warning effectiveness are **NOT RUN**.

### Read one Lyon TopView trajectory member

The [Lyon Zenodo record](https://doi.org/10.5281/zenodo.13830435) contains the separately admitted `Data_Madras.zip` archive and declares CC BY 4.0 at record scope. Manifest verification checks file integrity; it does not determine rights for every use. Check the selected archive before reading it:

```sh
curl --fail --location \
  'https://zenodo.org/api/records/13830435/files/Data_Madras.zip/content' \
  --output data/Data_Madras.zip
PYTHONPATH=src python3 -m crowd_warning verify-source sources/lyon-topview.json --base-dir data
```

The Lyon reader is a Python API, not a command-line subcommand. It reads one exact nine-column TopView ZIP member and can produce a summary while preserving the source clock. It excludes `id_global` from trajectory rows. This is not a calibrated motion-field pipeline.

```python
from crowd_warning.lyon import read_lyon_topview, summarize_lyon_topview

table = read_lyon_topview("data/Data_Madras.zip")
summary = summarize_lyon_topview(table)
```

## Observation schema

JSON Lines (`.jsonl` or `.ndjson`) and CSV (`.csv`) inputs contain `timestamp_s`, `zone_id`, `density_per_m2`, `vx_mps`, `vy_mps`, `quality`, and `calibrated`. These are supplied measurements. The code does not derive them from video or independently verify calibration. Feature windows need at least two adequate observations per zone. Forecasting abstains when a zone lacks sufficient history or has gaps, poor quality, or unknown calibration.

Event matching uses recording identifiers when present, then event identifiers as a fallback, and includes venue context when supplied. Pooled rows without those identifiers must be partitioned by recording before matching. Alarm-episode matching expects selected alarm rows and matches episode starts within the requested horizon; it does not turn every forecast into an alarm.

## Data terms and attribution

MIT applies to original code in this repository only. Papers, datasets, videos, and other third-party material retain their own terms. The selected CrowdDNA video and Lyon ZIP are identified under record-level CC BY 4.0 terms in their manifests. Integrity verification checks bytes against those manifests; it does not grant rights clearance. Keep downloaded data external. The [research references](CITATIONS.md) distinguish the five-author Nature paper from the three-author CrowdDNA dataset record and cite the Lyon paper and archive separately.
