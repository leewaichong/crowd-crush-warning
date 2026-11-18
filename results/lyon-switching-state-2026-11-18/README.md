# Lyon switching-state result

**EXPLORATORY.** This is one chronological, within-recording forecast of the next native-frame reported `x_RGF,y_RGF` increment for existing supplied traces. At each origin, the model used already observed consecutive increments ending at or before that frame. It did not track new identities.

The source archive is Dufour et al.'s Lyon trajectory dataset, Zenodo record 13830435, which declares CC BY 4.0 at record scope. This bundle includes no source archive, image, video, trace IDs, coordinates, or per-origin forecasts. The source record permits readers to obtain the data and reproduce the admitted member. Archive and member SHA-256 values, which matched before and after the run, appear in [provenance](provenance.json).

The experiment ran once at tracked SHA `6b51f744684fa71c55e91bec452a3072f55087eb`, with a clean tracked worktree. Command: `python3 work/m07-model/runner.py`. It ran from `2026-11-18T07:03:52.776337Z` to `2026-11-18T07:11:40.913821Z`. The statistical model was a local NumPy float64 two-state diagonal-Gaussian HMM with no model endpoint. It converged after 20 of at most 30 EM updates, without degeneracy or a nonmonotonic likelihood. The [provenance extract](provenance.json) records source, runtime, code, and private artifact hashes.

## Forecast errors

Mean vector error and vector RMSE use source-declared projected-coordinate units per native frame. Training is in-sample. Validation and test are descriptive chronological partitions of this same recording. The full partition table is in [aggregate-summary.json](aggregate-summary.json).

| Partition | Eligible origins | HMM mean / RMSE | Latest mean / RMSE | Trailing mean of 5 mean / RMSE | Memoryless mean / RMSE |
|---|---:|---:|---:|---:|---:|
| Train | 160,143 | 0.012326 / 0.015331 | 0.011093 / 0.015542 | 0.008440 / 0.011599 | 0.015323 / 0.019307 |
| Validation | 48,621 | 0.012330 / 0.015377 | 0.011802 / 0.016355 | 0.008990 / 0.012289 | 0.015824 / 0.019218 |
| Test | 46,699 | 0.012580 / 0.015626 | 0.011650 / 0.016174 | 0.008836 / 0.012071 | 0.016457 / 0.019528 |

These numbers describe forecasts of source-reported increments, not independently measured physical velocity or ground truth. The source preprocessing is unknown and may use smoothing that is noncausal. On test, the trailing mean of five wins both reported metrics, mean vector error and RMSE. The HMM RMSE is lower than latest-increment persistence, but its mean error is higher. The HMM remains an archived experiment with no production integration. This single-record comparison establishes no effectiveness or generalization.

## Model and audit

The [model summary](model-summary.json) contains final fitted parameters and training likelihoods. Filtered-state occupancy is reported in the aggregate and model summaries. The two states are statistical clusters; they have no danger or physical meaning.

The [corrected numerical-audit extract](numerical-audit.json) records a reconciled pass. It matched source-derived keys and controls for all 255,463 eligible origins, recomputed aggregate metrics, checked nine causal-filter anchors, and recomputed final training likelihood once without refitting. It did not independently refit the HMM or replay every HMM forecast. An earlier audit attempt was aborted after a first-observation transition bug; the corrected v2 audit starts with `pi` times the first emission, then applies transitions between observations. The v2 report's completion-status finding was reconciled against the completed run record and attempt status.

The frozen initialization wording was ambiguous. The executed code selected the axis with greatest raw training-coordinate variance, then stably sorted standardized values on that axis. The audit verified this operational rule. This clarification is not an exact claim that the protocol wording was unambiguous.

Independent measurement accuracy, online performance, warning effectiveness, safety, and venue generalization are **NOT RUN**. Do not promote this exploratory result automatically.

## Reproduction files and terms

`hmm.py`, `config.json`, `tests/test_hmm.py`, and `audit_helpers_v2.py` are archived source copies. `runner.py` is a public reproduction copy of the executed runner with only the `profile` and `model_identity` metadata entries removed. Its SHA-256 differs from the executed runner; both are recorded in provenance. The software check log records the two previously run analytic checks. No test suite was rerun for publication. The runner is a workspace-specific research helper, not a production CLI.

Original code is MIT licensed; see [LICENSE](LICENSE). Dataset terms remain separate. Sources: Dufour et al., [Scientific Data paper](https://doi.org/10.1038/s41597-025-04732-3) and [Zenodo record 13830435](https://doi.org/10.5281/zenodo.13830435). HMM background: Rabiner (1989), [DOI 10.1109/5.18626](https://doi.org/10.1109/5.18626). The citations are background and source attribution, not endorsement.
