# Lyon training-only proxy fit

**Fitted exploratory package.** The fit used one Lyon recording's training portion. No forecast or effectiveness evaluation ran. The raw independent audit exited 1 and recorded `passed=false` after three provenance assertions. A separate root maintainer reconciliation checked the preserved launcher, freeze, and child-run records, then accepted the numerical and provenance evidence. Both records are summarized in [audit-summary.json](audit-summary.json); the reconciliation does not change the raw audit's exit code or pass field.

The fit computed marginal statistical proxy drift and residual diffusion once. It computed a statistical percentile boundary once. Coupling `0.15` was fixed, not estimated; jump parameters were disabled. The fit did not estimate joint causal coupling, test on held-out events, or invoke the calibrated production forecast interface. These quantities do not establish physical force, danger, or calibrated probability validity. There is no baseline or score because this was fit-only.

The reported proxy is trajectory rows per fixed training tile area multiplied by the population variance of available tile-mean source-coordinate rates in the inclusive trailing one source-clock second. The variance uses no future data. Its units follow source declarations; it is not persons per square metre or pressure. Four equal-area tiles came from training-only bounds. The public summary withholds those bounds.

| Tile | Marginal drift per source second | Residual diffusion per square-root source second |
|---:|---:|---:|
| 0 | 0.00013604735400043227 | 0.004255466675814542 |
| 1 | 0.00008068883988034143 | 0.005708907038464851 |
| 2 | 0.00004795276578940277 | 0.002519202662849646 |
| 3 | 0.00005618780644703064 | 0.004163191797640135 |

The nearest-rank training 95th-percentile proxy boundary was computed once as `0.017703076301339493` over 11,500 q values. It is a statistical boundary, not a danger threshold. The 11,500 aggregate training q rows remain in ignored local work. The archive records their count and checksum but does not publish them.

## Source and attribution

The source is `Data_Madras.zip` from [Zenodo record 13830435](https://doi.org/10.5281/zenodo.13830435), which declares CC BY 4.0 at record scope. The dataset creators are Oscar Dufour, Huu-Tu Dang, Jakob Cordes, Raphael Korbmacher, Mohcine Chraibi, Benoit Gaudou, Alexandre Nicolas, and Antoine Tordeux. The final article is "Dense Crowd Dynamics and Pedestrian Trajectories: A Multiscale Field Dataset from the Festival of Lights in Lyon," *Scientific Data* 12, 718 (2025), [DOI 10.1038/s41597-025-04732-3](https://doi.org/10.1038/s41597-025-04732-3). The Zenodo record has a different title. The dataset terms do not apply to the code.

The research scripts are byte-identical copies of the frozen run helper and launcher. They are MIT licensed; see [research-code/LICENSE](research-code/LICENSE). They are included for inspection, not as a one-command public replay. The helper depends on ignored protocol and freeze inputs and original paths. Source hashes and the archived numerical definitions allow independent recreation of the quantities; the original execution metadata and private frozen inputs remain in ignored work and are identified by checksum.

The summary is an allowlisted derivative of the private fit output. It omits tile bounds, absolute source paths, machine details, and q rows. The sanitized launcher record replaces the canonical repository path; its source and derived hashes are recorded in the manifest. Raw stdout and stderr are copied byte-for-byte under [run-logs](run-logs/). No source tracks, coordinates, trajectory IDs, or raw q rows are published.

The source declares EPSG:2154 coordinates in metres and `t/s` in seconds. Independent calibration accuracy and drift were not measured. This is a within-recording training fit, not event-held-out generalization, forecast performance, latent physical identification, or parent early-warning effectiveness.
