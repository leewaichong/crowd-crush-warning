# Lyon observation support

Source availability check executed on 18 November 2026. Model fitting, forecasting and warning effectiveness for these candidate recordings remain **NOT RUN**.

All nine released TopView members were checked using supplied relative seconds, a 60/20/20 chronological frame split and four tiles defined from each recording's training rows. A supported future requires reports and the declared trailing-window increment history in every tile at every observed future frame for 30 seconds. Missing cells remain unsupported. No q values, target crossings, fitted parameters or model scores were calculated.

Counts below are upper bounds on model-eligible origins. Origin history and training-boundary gates have not been applied. They are observations from the released processed trajectories, not independent physical motion measurements.

| Recording | Validation candidates | Supported upper bound | Test candidates | Supported upper bound |
|---|---:|---:|---:|---:|
| TopView_1A | 368 | 368 | 369 | 369 |
| TopView_1B | 59 | 0 | 60 | 0 |
| TopView_1C | 324 | 244 | 324 | 324 |
| TopView_2A | 66 | 66 | 66 | 66 |
| TopView_2B | 0 | 0 | 0 | 0 |
| TopView_2C | 193 | 0 | 193 | 193 |
| TopView_2D | 65 | 0 | 65 | 65 |
| TopView_2E | 0 | 0 | 0 | 0 |
| TopView_2F | 0 | 0 | 0 | 0 |

TopView 1A, 1C and 2A have positive support in both held-out partitions and can proceed to a separate training-support gate. This does not establish that their training features, fitted processes or forecast origins will pass subsequent checks. TopView 2C and 2D have test coverage despite having no fully supported validation horizons. No 30-second horizon fits either held-out partition in 2B, 2E or 2F.

The 2B and 2D coordinate headers have exact whitespace variants. A private source-only parser accepted those inspected variants without changing the production reader or raw files. The malformed 2F calendar timestamp remains invalid and unparsed. The separate 210-second paper/header discrepancy for 1A remains unresolved. Relative-time coverage does not establish wall-clock, event or video alignment.

The successful run used clean tracked SHA `982b145e43f3e1c6f15729861a594f993a396155` from 2026-11-18T09:40:20.037418+00:00 to 2026-11-18T09:40:51.161464+00:00. The [machine-readable record](lyon-observation-support.json) retains source, code and run hashes, command, runtime, exclusions and review scope. Static review and provenance/accounting checks passed. All nine support counts have not been independently numerically reproduced. The earlier helper attempt produced no usable coverage counts; its raw failure records and the unexecuted prepared versions remain retained privately.

Credit: Oscar Dufour and coauthors, [Dense Crowd Dynamics and Pedestrian Trajectories: A Multiscale Field Dataset from the Festival of Lights in Lyon](https://doi.org/10.1038/s41597-025-04732-3), and the [Zenodo dataset](https://zenodo.org/records/13830435), record-level CC BY 4.0. Full attribution is in [CITATIONS.md](../CITATIONS.md). The repository's MIT licence does not replace third-party terms.
