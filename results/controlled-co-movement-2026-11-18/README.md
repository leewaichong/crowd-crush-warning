# Controlled co-movement result bundle

Prepared for maintainer review. Independent review in the calibration lane is underway; its result is pending. This bundle does not claim an independent pass or approval for public release.

## Study

This is an exploratory descriptive analysis of one previously viewed controlled trial. It compares the bag's x/y step magnitude with each head's step magnitude over native frame indices. It does not estimate a physical response time.

The run contains 101 consecutive frame steps. It reports the full Pearson correlation profiles at fixed lags -10 through +10. Every lag uses the same 81 anchors, step indices 10 through 90 inclusive. Positive lag means the head series is later. The bundle retains every per-head profile and the head common-mode profile, along with lag-zero controls, unavailable-series flags, maximum-absolute-correlation locations, and ties. Constant series are null with a reason, never filled with zero.

Three descriptions are included. Raw head step magnitude keeps shared motion. Common-mode magnitude is the magnitude of the mean x/y step vector across the ten heads. Residual head magnitude comes from subtracting that mean vector from each head step vector before taking its magnitude. The subtraction also removes real shared motion. It is not an independent camera or background control. All three measures use scalar magnitudes, which discard direction.

Some maximum-absolute correlations occur at -10 or +10, the edges of the searched lag range. Those are boundary sensitivities, not arrival estimates. The full profiles are included so readers can inspect the shape and ties directly.

At lag zero, raw head correlations range from 0.0761 to 0.6678 across the ten ordinal profiles. Residual head correlations range from 0.1273 to 0.5273. The common-mode lag-zero correlation is 0.4844. All computed profile correlations were available in this run. These are descriptive values from one trial, with no uncertainty estimate or independent-sample interpretation.

## Data and credits

The source dataset is [Impulse propagation through a small standing crowd, DOI 10.34735/ped.2022.6](https://doi.org/10.34735/ped.2022.6). Dataset metadata credits Sina Feldmann, Alica Kandler, Armin Seyfried, and Maik Boltes.

The [archive record](https://ped.fz-juelich.de/da/doku.php?id=impulse_crowd) describes the dataset. Its [research-use terms](https://ped.fz-juelich.de/da/doku.php?id=start) permit further research with attribution. Those terms do not grant commercial use or permission to redistribute the source data. Preserve the source attribution and terms in any later permitted use.

Related primary work is Sina Feldmann, Juliane Adrian, Maik Boltes et al. (2024), “Impulse propagation through a small standing crowd,” [DOI 10.17815/CD.2024.148](https://doi.org/10.17815/CD.2024.148). This analysis does not reproduce that paper or validate its findings.

The project code is MIT licensed. That code license does not change the source dataset's terms. The derived correlations are research outputs; this bundle contains no source coordinates, source rows, trace identifiers, identity map, pressure matrices, or raw source payload.

## Limits

This result describes one previously viewed trial. It is not representative sampling, replication, or evidence of transfer to other crowds. The calculations use x/y and consecutive frame order only. They do not convert nominal FPS to physical time, join pressure data, or estimate speed, force, harm, or a mechanism. They make no causal, propagation, or warning-performance claim.

## Run record

- Status: executed once, exit code 0.
- Tracked Git SHA: `345275100aaae31b9810a95a8eeec8cfe8a0a3b9`; clean at freeze and run start.
- Command: `python3 work/m06-controlled/v2r1/controlled_head_lag_v2r1.py`.
- UTC start: `2026-11-18T06:07:46.754679+00:00`.
- UTC end: `2026-11-18T06:07:47.010757+00:00`.
- Python: 3.9.12, standard library only. Model endpoint: none.
- Archive SHA-256 before and after: `1a197b0fd068f7b9bea3ac53118a31f7fc698f90167d871bb44b8de34b10030f`.
- Selected member SHA-256 before and after: `3f5bfdaf2d9c4a07b22b489f8cef3c7d8b3fdc16c9d5a37a32e74ed8b6f627a1`.
- Executed script SHA-256: `497e0eba205dc5eee077031d4a22f1625f14e2c988777eb99ec4aaf15f625940`.
- Frozen protocol SHA-256: `66f9715c8c67f19ad27dd1782d2e703f8739f14b6e219c853e18db3c81a55315`.

The exact protocol remains in the ignored planning area and is not included here. The recorded script path is specific to the original worktree. `executed_script.py` is retained as run evidence, not a portable entry point.

The earlier v1 invocation stopped at a parser gate before calculation. The first v2 software smoke also failed before any source calculation. Both records remain preserved privately. The successful v2r1 run is distinct from those attempts.

## Files

- `lag_profiles.json`: full derived profiles and run execution details.
- `descriptive-summary.json`: per-head ordinal summary, lag-zero ranges, maxima, ties, and unavailable counts.
- `executed_script.py`: byte-for-byte copy of the frozen script used for the successful run.
- `freeze-manifest.json`, `start-manifest.json`, and `run-record.json`: frozen inputs and execution record.
- `events.jsonl`, stdout/stderr, and smoke logs: retained run evidence.
- `artifact-hashes.json`: source run's artifact hash inventory.
- `bundle-manifest.json`: hashes of the package copies.
