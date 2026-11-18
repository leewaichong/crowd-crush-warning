# Lyon coupled-proxy comparison

**Actual descriptive result.** The comparison completed at clean tracked SHA `982b145e43f3e1c6f15729861a594f993a396155`. The independent v2 numerical consistency audit passed with exit status 0. The earlier v1 audit failed at its timestamp validator before numerical checks. Both outcomes and their original report hashes are retained in [numerical-audit.json](numerical-audit.json). This archive records a completed analysis, not an effectiveness result or production promotion.

## Comparison

Each row is one recording and chronological partition. Positive and negative counts are eligible proxy-crossing origins, not crowd-event counts. Every partition has only one target class. This makes discrimination and calibration conclusions unavailable from these scores. Origins overlap in time and are not independent cases.

| Record | Partition | Eligible origins | Positive | Negative |
| --- | --- | ---: | ---: | ---: |
| TopView 1A | Validation | 359 | 359 | 0 |
| TopView 1A | Test | 360 | 360 | 0 |
| TopView 2A | Validation | 66 | 0 | 66 |
| TopView 2A | Test | 66 | 66 | 0 |

Brier scores by arm are listed as replicate 0 / 1 / 2, followed by the descriptive mean and the minimum to maximum across the three replicates. No values are pooled across records or partitions. No confidence intervals or significance tests were calculated. Three Monte Carlo replicates reflect simulation variation, not independent data samples.

| Record | Partition | Arm | Brier 0 / 1 / 2; mean [min, max] |
| --- | --- | --- | --- |
| TopView 1A | Validation | coupled | 0.015170636615381268 / 0.015905821223776984 / 0.01615115194931668; 0.015742536596158308 [0.015170636615381268, 0.01615115194931668] |
| TopView 1A | Validation | uncoupled | 0.00088394717585741646 / 0.00089359549094707516 / 0.00097430980969272283; 0.00091728415883240478 [0.00088394717585741646, 0.00097430980969272283] |
| TopView 1A | Validation | persistence | 1 / 1 / 1; 1 [1, 1] |
| TopView 1A | Test | coupled | 0.023917134602864584 / 0.023726781209309895 / 0.02289403279622396; 0.023512649536132812 [0.02289403279622396, 0.023917134602864584] |
| TopView 1A | Test | uncoupled | 0.0014391581217447916 / 0.0014001634385850694 / 0.0013503180609809027; 0.0013965465404369212 [0.0013503180609809027, 0.0014391581217447916] |
| TopView 1A | Test | persistence | 1 / 1 / 1; 1 [1, 1] |
| TopView 2A | Validation | coupled | 0.7167873960552793 / 0.72075375643643469 / 0.7256000403201941; 0.72104706427063603 [0.7167873960552793, 0.7256000403201941] |
| TopView 2A | Validation | uncoupled | 0.93154167406486743 / 0.93589921431107959 / 0.9343777280865293; 0.93393953882082548 [0.93154167406486743, 0.93589921431107959] |
| TopView 2A | Validation | persistence | 0 / 0 / 0; 0 [0, 0] |
| TopView 2A | Test | coupled | 0.015347798665364584 / 0.014548561789772728 / 0.015198216293797348; 0.01503152558297822 [0.014548561789772728, 0.015347798665364584] |
| TopView 2A | Test | uncoupled | 0.0007862900242660985 / 0.00077380556048768938 / 0.00067762895063920451; 0.00074590817846433087 [0.00067762895063920451, 0.0007862900242660985] |
| TopView 2A | Test | persistence | 1 / 1 / 1; 1 [1, 1] |

The predeclared test condition required the coupled arm to have a strictly lower mean Brier score than both uncoupled diffusion and persistence. It failed on both test partitions. For TopView 1A, coupled scored worse than uncoupled and better than persistence. TopView 2A had the same test ordering. On TopView 2A validation, coupled beat uncoupled but lost to persistence, so the validation comparison was mixed. No tuning, retry, or promotion followed.

## Setup and limits

The source gate admitted TopView 1A and 2A. TopView 1C was excluded because 136 training cells were missing. Splits are chronological within each recording, using floor(0.6*N) and floor(0.8*N). The existing proxy is trajectory-row density multiplied by variance of source-coordinate rates. Its units follow the source declarations: reported-track-record m^-2 times source-declared (m/s)^2. It is a statistical proxy, not physical pressure or force. Fitted marginal drift and diffusion, and each record's training q95 boundary, are in [comparison-summary.json](comparison-summary.json); exact tile bounds are withheld.

The existing one-second Euler forecast used no nonnegative clamp, coupling 0.15, and 256 paths for each of three fixed replicates. The uncoupled arm used coupling 0. Persistence predicted no new crossing. The boundary was the nearest-rank 95th percentile of finite training q. No jump model ran. Jump rate and scale were zero in the frozen setup, so there is no jump effectiveness comparison.

This analysis derives its proxy from supplied trajectories as trajectory-row density multiplied by variance of source-coordinate rates. Source preprocessing causality remains unverified. The final paper describes geometric correction and interpolation without smoothing or filtering. Its Data Records section reports 10 Hz, while the released TopView headers and observed `t/s` cadence indicate 30 fps. TopView 1A also has an unresolved 210-second disagreement between the paper's recording time and the file header. The analysis used source `t/s`; these conflicts rule out a physical-clock interpretation. No online, calibrated-risk, or warning claim follows. This is a within-recording comparison and says nothing about event or venue generalization.

The v2 audit recomputed retained metrics, fit coefficients from retained training q, denominators, exclusions and control ordering, then replayed 12 selected origins across all three replicates and 256 paths per replicate. Its scope is numerical consistency of retained outputs. It did not independently reconstruct source q, verify source measurements, or test warning effectiveness. The v1 timestamp-guard failure remains recorded and unchanged.

## Provenance and reuse

[Provenance](provenance.json) records the actual command, UTC times, runtime, local runner identity, null endpoint, clean before/after state, input hashes, method and source terms. [Artifact hashes](artifact-hashes.json) records the byte-identical runner, launcher and v2 audit script copies and raw-safe logs. The scripts are included for inspection. They expect the original repository layout and private run inputs; this archive does not provide a standalone one-command replay.

The paper is Oscar Dufour et al., *Scientific Data* 12, 718 (2025), [DOI 10.1038/s41597-025-04732-3](https://doi.org/10.1038/s41597-025-04732-3). The data are from [Zenodo record 13830435](https://doi.org/10.5281/zenodo.13830435), which declares CC BY 4.0 at record scope. MIT applies to original repository code only. Dataset and paper terms remain separate. See [CITATIONS.md](../../CITATIONS.md).
