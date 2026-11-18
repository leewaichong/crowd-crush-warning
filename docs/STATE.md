# Project status

Snapshot date: 18 November 2026.

## Implemented

The offline CLI supports observation validation, causal temporal features, conditional proxy-crossing forecasts, diagnostic baselines, source-manifest integrity checks, and inspection and replay of the Pamplona temporal-density table. The parser checks the source's six-column tab-separated schema, increasing times, finite values, nonnegative densities, and trailing missing pairs. The viewer is self-contained HTML and makes no hazard classification.

The source-inspection additions include `inspect-video`, which requires local `ffprobe` and `ffmpeg`, reports actual presentation timestamps, and performs video-only null decoding. A completed inspection separates timing abstention from command failure; optional `--max-gap-s` is caller-declared and is not a safety threshold. The Lyon reader is a Python API for one exact nine-column TopView ZIP member and its summary. It preserves source time, excludes `id_global`, and does not provide a calibrated motion-field pipeline. Integrated local checks for these additions remain pending.

Baseline signals include current density, previous valid pressure proxy, and one-sided excess CUSUM against the causal past mean. Parameters are explicit research settings. They are not safety limits or calibrated warning thresholds. The CUSUM family is informed by Page (1954), not a calibrated reproduction.

Event matching and alarm-episode matching scope pooled data by recording identifier when present, otherwise event identifier, and by venue when supplied. Without identifiers, callers must partition inputs by recording. Episode matching expects selected alarm rows and does not automatically convert all forecasts to alarms.

The temporal-density source describes spatially averaged density in m^-2 against author-declared seconds relative to festival opening. It has 90,000 table rows and numeric counts of 80,025, 85,875, and 90,000 for 2022, 2023, and 2024. Trailing padding counts are 9,975, 4,125, and 0. It supplies no velocity, calibrated harm probability, or outcome labels. The original five selected CrowdDNA files total 4,697,499 bytes. The separately selected video is 51,275,828 bytes; the separate Lyon ZIP is 33,639,872 bytes. These are selected files, not complete record inventories. See the [video manifest](../sources/pamplona-video.json) and [Lyon manifest](../sources/lyon-topview.json). The full 1.22 GB CrowdDNA record was not fetched or audited.

## Local verification

Verification runs locally on the home Mac. This snapshot does not state an integrated test count. Software checks establish code behavior only; they do not establish empirical model performance.

## Evaluation

**Real crowd evaluation: NOT RUN. Warning effectiveness: NOT RUN.** The source inspection is technical only. No effectiveness experiment, validated warning, calibrated harm probability, or useful-warning result is claimed.

## Rights and evidence limits

The source verifier checks local file size and checksums against a manifest. It does not fetch files or determine rights clearance. The selected video and Lyon archive manifests record CC BY 4.0 at record scope; integrity checks do not provide blanket rights clearance. The Lyon archive homepage describes attributed research use. The controlled impulse archive permits attributed research use; only one trajectory ZIP and one member were inspected, with no pressure/video admission or importer. The Nature paper authors and CrowdDNA dataset-record authors are distinct. MIT covers original code only.
