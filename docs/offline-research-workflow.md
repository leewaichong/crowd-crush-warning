# Offline research workflow

This page describes the current local tools. They support source inspection and research review; they do not form a validated crowd safety system. Keep the downloaded source files outside Git. The manifests record the source URL, retrieval time, byte count, SHA-256, source checksum, and record-level terms. Verify every local source file before using it. Integrity is a byte check, not rights clearance or evidence of measurement accuracy.

## 1. Check source integrity

From the repository root, put a downloaded file at the path named in its manifest, then run the matching command. Paths below are examples; replace them with the actual local files.

```sh
PYTHONPATH=src python3 -m crowd_warning verify-source sources/pamplona-density.json --base-dir /example/local-data
PYTHONPATH=src python3 -m crowd_warning verify-source sources/pamplona-video.json --base-dir /example/local-data
```

Each manifest entry names a relative `path`, source `url`, `size_bytes`, `sha256`, `source_checksum`, `retrieved_at`, `purpose`, and `status`. `--base-dir` is the directory containing those relative paths. A successful result has `integrity_verified: true`; missing files or metadata or a byte mismatch makes verification fail with a nonzero exit. This command does not download anything. Keep raw source payloads external. Original repository code is MIT licensed; source material retains the terms and attribution recorded in its manifest. The Pamplona video manifest identifies CC BY 4.0 at record scope, which does not by itself settle rights for a particular use.

## 2. Inspect video timestamps and decode

`inspect-video` requires a local video file plus `ffprobe` and `ffmpeg` on `PATH`. It probes stream metadata and presentation timestamps, then decodes the video stream to a null output without audio.

```sh
PYTHONPATH=src python3 -m crowd_warning inspect-video /example/local-data/video_crowd.mov
```

The JSON includes the input byte count and SHA-256, tool versions, stream metadata, frame count, timestamp counts and intervals, decode status, and `timing_status`. A completed inspection can report `ok` or `abstain`; missing, duplicate, or decreasing timestamps cause abstention. Use `--max-gap-s SECONDS` only to report caller-selected timestamp intervals. Exceeding that value causes abstention; the command does not infer missing physical frames. A missing input, missing tool, failed probe, or failed decode is a command error, printed as JSON on stderr with a nonzero exit status. An abstention is a completed inspection, not a command failure.

## 3. Inspect image-space motion

`inspect-motion` requires the same video file and tools, plus NumPy. It samples grayscale frames at intervals based on actual presentation timestamps and reports integer-pixel block matches. The defaults are width 320 pixels and a one-second minimum sample interval.

```sh
PYTHONPATH=src python3 -m crowd_warning inspect-motion /example/local-data/video_crowd.mov
```

Options are `--width PIXELS` and `--sample-interval-s SECONDS`. The command rejects videos over 2,000 native frames or 60 seconds, and bounds decoded frame memory. A completed result reports `motion_status` as `ok` or `abstain`; invalid input, unavailable tools or NumPy, and probe or decode failures are command errors. The output describes image pixels only. Camera movement, visibility, calibration, and physical scale remain unknown. A block match or a unique minimum is not an accuracy or confidence measure and does not measure physical motion or force. Human review remains outside any operational claim.

### Python quality and calibration APIs

The optional Python APIs add a caller-evidence quality gate and a conditional projection. They do not add a CLI command or estimate camera stability, occlusion, or visibility. Supply evidence from outside these APIs. A reference string records where the caller's evidence came from; it does not mean the software checked that evidence.

```python
from crowd_warning.motion_quality import assess_motion_quality
from crowd_warning.calibration import project_motion_video

# Required caller-supplied inputs:
# camera_review describes the caller's camera review, with "stable" and "reference".
# visible_ids_by_pair contains an externally reviewed list of visible cell IDs per pair.
# visibility_review contains a nonempty evidence reference per pair.
# supplied_calibration is a caller-provided calibration mapping.
quality_by_pair = [
    assess_motion_quality(
        pair["motion"],
        camera_stable=camera_review["stable"],
        camera_reference=camera_review["reference"],
        visible_cell_ids=visible_ids_by_pair[index],
        visibility_reference=visibility_review[index],
    )
    for index, pair in enumerate(video_result["pairs"])
]

projected = project_motion_video(
    video_result,
    calibration=supplied_calibration,
    quality_by_pair=quality_by_pair,
)
```

The example requires real caller inputs and is not run with guessed labels or calibration values. `assess_motion_quality` binds each assessment to the exact motion field using its canonical SHA-256 digest. It admits only unique, finite, nonboundary displacements in the caller's visible-ID list. Camera stability must be explicitly `True`, and both evidence references must be nonempty. Missing evidence abstains. The returned eligible IDs and counts describe admitted coverage; malformed fields, duplicate or unknown IDs, and malformed flags raise `ValueError`.

`project_motion_video` requires a calibration marked `verified: True`, a nonempty reference, a source SHA-256 matching `video_result["input"]["sha256"]`, native dimensions matching the result, and a finite nonsingular `image_to_plane_m` 3 by 3 homography. This is a supplied calibration bound to that source and native image size. The matrix maps zero-based native pixel-center coordinates to metres on its supplied reference plane. The adapter accounts for the inspector's scaled dimensions and resize transform, uses the patch center, and maps both displacement endpoints. It retains the result's native/scaled dimensions, transform, and pair timing fields, including PTS. Missing calibration, quality, or usable timing abstains; malformed supplied context raises `ValueError`; a projection-horizon failure abstains for that cell.

The original motion fields remain in pixel units. Projected fields use the separate `plane_vx_mps` and `plane_vy_mps` names and are conditional reference-plane image-pattern velocity. They are not pedestrian velocity or physical force. The visible-ID masks come from external evidence supplied by the caller; neither API independently checks visibility or estimates occlusion.

## 4. Inspect and replay the temporal-density table

`inspect-density` parses the exact six-column tab-separated Pamplona table. It checks the expected description and header, finite values, nonnegative densities, strictly increasing times, and paired trailing missing values. It reports counts and ranges by year.

```sh
PYTHONPATH=src python3 -m crowd_warning inspect-density /example/local-data/data_density_over_time.txt
```

To make the standalone viewer, give `replay-density` a new output path. It refuses to overwrite an existing file.

```sh
PYTHONPATH=src python3 -m crowd_warning replay-density /example/local-data/data_density_over_time.txt --output /example/review/pamplona-density-viewer.html
```

The command prints JSON with `status: written`, the resolved output path, and `input_sha256`. Retain that digest with the review so the viewed table can be tied to the exact input bytes. The viewer identifies the source and terms, reports missing trailing padding, and may decimate displayed points while retaining endpoints and bucket extrema. It does not interpolate missing rows, set a hazard threshold, or make a forecast. Unknown camera scale and source gaps stay unknown.

## Reading results and review limits

Separate these cases when reviewing output:

- **Data checks:** `verify-source` checks manifest metadata and local bytes. The density parser checks its stated file schema and numeric consistency. Passing these checks does not establish that measurements are accurate or calibrated.
- **Completed abstention:** `inspect-video` may complete with `timing_status: abstain`; `inspect-motion` may complete with `motion_status: abstain`. Read the reason and counts. Do not treat abstention as a warning or as evidence that conditions are safe.
- **Command failure:** nonzero exit and JSON error on stderr means the requested operation did not complete. Resolve the missing input, dependency, or processing error before interpreting any result.
- **Independent accuracy:** these tools do not compare motion estimates with independent ground truth. Independent measurement accuracy has not been established by successful parsing, decoding, or replay.
- **Warning effectiveness:** these source-inspection tools do not evaluate warnings. Do not infer warning effectiveness, safety thresholds, calibrated probabilities, or physical force from their outputs.

Camera calibration and visibility remain unknown unless supported by separate evidence. Human review can check whether files and outputs are internally consistent, but it does not supply a trained safety-operator study or authorize operational use.

## Existing density forecast result

The [published Pamplona density benchmark bundle](../results/pamplona-density-30s-2026-11-18/README.md) records a completed descriptive run at clean Git SHA `53c35c42087d76614e16d2b14bfd630acfb5e15b`, completed at `2026-11-18T04:19:21.269627+00:00`. Its input was the 4,636,050-byte source table with SHA-256 `cbc48912b51e1824017b046a6ee5f1d5eef19a529ba33d9aee361d21cd36561c`. The bundle retains `origins.jsonl`, `metrics.json`, model and configuration files, run provenance, and figure checksums. The comparison control is persistence, which carries forward the latest observed density.

Only the global discrete AR(1) fit uses 2022 training observations. At each origin, local trend is refit on the causal trailing 30 seconds of available history, including later years, without future values. Persistence uses the latest value at that origin. The 2023 check contains 113 completed origins; the 2024 same-venue holdout contains 118. The bundle reports MAE and RMSE against source-declared density in m^-2. This is a descriptive forecast evaluation on one spatial-average series, not independent measurement accuracy or warning effectiveness. Motion accuracy and warning effectiveness are **NOT RUN**.

## Review evidence

The integrated suite passed 133 tests at clean Git SHA `53c35c42087d76614e16d2b14bfd630acfb5e15b`, as recorded in [project status](STATE.md). Prior real-input replay and browser checks are recorded in local release evidence. The [published density result bundle](../results/pamplona-density-30s-2026-11-18/README.md) retains the separate benchmark run and its provenance. These checks establish software behavior for the recorded inputs. They do not establish independent measurement accuracy or warning effectiveness.

This checklist supports a developer/research review; it is not a trained safety-operator study. No safety-operator study is claimed.

## Developer and research acceptance checklist

For a bounded local review of these existing tools:

1. Confirm each source file is external and matches its selected-file manifest, including recorded byte count and checksums.
2. Run timestamp inspection and record the JSON status, tool versions, frame count, and any timestamp defects or configured gap check.
3. If reviewing motion, confirm NumPy is available, inspect the reported image dimensions and sample intervals, and record abstentions or boundary matches without treating them as accuracy.
4. Parse and replay the temporal-density table. Retain the `input_sha256` from the replay JSON and inspect the viewer's source labels, counts, and missing padding.
5. Record command failures separately from completed abstentions and data validation failures. State explicitly what each check establishes and what remains unknown.
6. Have a research reviewer check the local artifacts and evidence limits. Record this as a developer/research acceptance review only. No trained safety-operator acceptance study or warning-effectiveness evaluation is claimed.

This checklist is a review of existing offline behavior, not a protocol for an effectiveness experiment.
