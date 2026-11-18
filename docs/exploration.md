# Crowd motion, hidden state, and warning claims

This review asks what video and other sensors can establish about hazardous crowd dynamics, which models deserve comparison, and what evidence a warning claim would require. It is a literature-based assessment, not a report of experiments in this repository. **All project experiments and real-warning evaluations are NOT RUN.**

## Three different things: observation, state, and hazard

A camera records image intensity over time. Processing can estimate visible motion, apparent direction, occupancy, counts, or trajectories. With fixed geometry, known timestamps, calibration, and sufficient visibility, some estimates can be expressed in physical units. Each step adds assumptions. A camera does not directly reveal contact force, internal body compression, balance margin, intent, or people hidden behind others.

Crowd state is the latent physical organization that produced those observations: who contacts whom, how motion travels through a group, whether people can recover balance, and how boundaries or inflow constrain movement. Even good video features only provide partial evidence about this state. Occlusion, camera movement, perspective, resolution, lighting, and missing frames can make the same image pattern compatible with different physical situations.

A hazard is a further claim about harmful outcomes. A motion pattern may be physically interesting without being a reliable precursor of injury. To make a warning claim, one needs outcome definitions and timing, non-event comparisons, independent labels, useful lead time, and a way to count false alarms over valid exposure. No amount of model complexity supplies missing outcome evidence.

## What published work shows

Helbing, Johansson, and Al-Abideen analyzed video of the 2006 Mina disaster and described transitions from laminar movement to stop-and-go flow and later irregular correlated motion. Their “pressure” quantity used local density multiplied by the spatially local variance of velocity vectors around a local mean. It was derived from video, not measured as force on bodies. Their account of a value preceding the event is a retrospective finding from one disaster, not a transferable threshold. See [their 2007 paper](https://doi.org/10.1103/PhysRevE.75.046109).

Gu, Guiselin, Bain, Zuriguel, and Bartolo studied recurring San Fermín crowds and reported coherent collective oscillations, with retrospective comparison to Love Parade footage. The measured pattern includes orientation changes and spatial correlations, not simply people reversing speed. Their analysis and theory motivate questions about confinement and collective motion, but do not establish that the same oscillation predicts harm across festivals, concerts, ordinary dancing, and changing cameras. See [their 2025 Nature paper](https://doi.org/10.1038/s41586-024-08514-6).

Controlled-push research asks a narrower physical question. Feldmann and colleagues used a five-person row and a controlled impulse, combining video, body tracking, and pressure sensing to identify phases of receiving and passing motion. Related experiments vary impulse strength, spacing, participant preparation, and formation. These studies can inform propagation mechanisms and measurement methods. A deliberate push through a small standing group is not equivalent to spontaneous motion in a moving, crowded venue, and the imposed push is not a crush-outcome label. See Feldmann, Chatagnon, Adrian, Pettré, and Seyfried on [temporal segmentation](https://doi.org/10.1016/j.ssci.2024.106512), and Feldmann, Adrian, and Boltes on [controlled frontward impulses](https://doi.org/10.17815/CD.2024.148). Feldmann and Adrian also studied [forward propagation through a row](https://doi.org/10.1016/j.ssci.2023.106173).

Other work shows why apparent disorder needs benign controls. Jesse L. Silverberg, Matthew Bierbaum, James P. Sethna, and Itai Cohen studied organized motion in mosh and circle pits, including camera correction and spatial flow patterns. Intentional movement can be highly energetic and coherent. A detector that treats high speed, rotation, or variance as danger would confuse cause, setting, and outcome. See [their 2013 paper](https://doi.org/10.1103/PhysRevLett.110.228701). Arianna Bottinelli and Jesse L. Silverberg forecast a density-wave pattern about one second ahead in a particular Oasis concert clip using spatiotemporal fluctuations. That is a useful, narrow forecasting result, not general crush-warning evidence ([2018 preprint](https://doi.org/10.48550/arXiv.1809.07875)).

## Candidate mechanisms and what would count against them

| Mechanism hypothesis | Observable implications | Evidence that would weaken it |
| --- | --- | --- |
| Contact-network impulse propagation | A measured perturbation travels through neighbours with distance, delay, and spatial spread related to contact structure. | Matched perturbations show no change in propagation after accounting for impulse size, spacing, and formation, or apparent propagation is explained by common external motion. |
| Bottleneck stop-go transition | Inflow and outflow become imbalanced; gaps and slow-moving waves travel upstream before less coordinated motion. | Repeated, well-timed sequences show loss of control before outflow reduction or upstream waves, including settings without bottlenecks. |
| Confinement-related collective oscillation | Coherent directional oscillation develops over a crowd region, with frequency or coherence related to confinement. | Independent settings fail to reproduce it, or music, choreography, camera motion, or another external rhythm explains the pattern. |
| Balance loss as amplifier | Trunk or head motion relative to feet, recovery steps, and stumbling precede some falls and spread of displacement. | Harmful crowd motion repeatedly develops without preceding balance-loss sequences, or the available view cannot distinguish voluntary from involuntary movement. |

These mechanisms may coexist. Falls may amplify an already hazardous condition rather than initiate it. A video-only system should describe the observation and its uncertainty, not infer force or cause without independent measurements.

## Models worth comparing

The simplest candidates deserve the first comparison because data are scarce and interpretation matters. Persistence and linear trend baselines answer whether a feature simply continues or drifts. Change-point methods test whether a feature distribution shifts. Spectral measures test for periodic motion. They are cheap and legible, but routine music, camera shake, lighting changes, and edits can trigger them.

A hidden Markov or switching state-space model could represent recurring motion regimes. It needs repeated sequences and stable emissions. A regime discovered without independent labels is only a statistical segment, not “safe” or “dangerous.” Graph-delay models could represent propagation between mapped zones, but need synchronized spatial measurements and repeated events. Hawkes processes could model bursts of timestamped events, but a common surge can look like self-excitation. Interacting stochastic differential equations or jump-diffusions may represent continuous fluctuations and abrupt impulses, but require state measurements that identify their interaction terms. Parameters that cannot be distinguished from camera noise or hidden forcing should not be given a physical interpretation.

First-passage calculations provide a mathematical wrapper for asking whether a modeled quantity crosses a specified boundary within a horizon. They do not make that boundary a safety limit. A crossing frequency is conditional on the model, features, input quality, and chosen boundary. Calibration against held-out, independently labeled real outcomes would be necessary before interpreting it as an outcome probability.

The current code sits at a much simpler level. It consumes zone-level observations already expressed in metres and seconds, calculates trailing temporal features, and simulates proxy crossings under a global mean-reversion model. Its velocity variance is across observations through time for one zone. That differs from Helbing et al.'s local spatial variance across velocity vectors. Its global model also does not estimate spatial propagation. The code has no camera adapter, fitted crowd dynamics, force measurement, validated alarm threshold, or demonstrated predictive value.

## Sensors and measurement limits

| Method | Can help observe | Cannot establish by itself |
| --- | --- | --- |
| Fixed-camera optical flow or particle image velocimetry | Apparent local direction, displacement, stalls, and correlated motion. | Contact force, pressure on bodies, hidden posture, or cause of movement. Camera shake and occlusion can dominate. |
| Detection and tracking | Visible person counts, short trajectories, and boundary crossings. | Reliable identity in dense overlap or the location and state of fully occluded people. |
| Density estimation and perspective mapping | Occupancy or people per area when geometry and assumptions hold. | Accurate density on uncalibrated, sloped, tiered, or partially occluded scenes. Ground-plane homography does not correct elevated-body parallax automatically. |
| Multiple cameras or depth sensors | Additional views or geometric cues in some regions. | Complete coverage. Synchronization, parallax, occlusion, sparse depth returns, and cross-view association remain problems. |
| Wearable IMUs or calibrated pressure sensors | Motion or force at the instrumented body/device location. | Whole-crowd state from a small, selected sample or force elsewhere in the crowd. |

Unknown scale should remain image-space measurement. Missing or irregular timestamps invalidate speed estimates. Unstable compensation, insufficient visible coverage, or material occlusion should produce an unavailable measurement rather than an invented value. Derived motion energy or variance is not a force sensor.

## Dataset evidence and rights

The European Commission's [CORDIS CrowdDNA results page](https://cordis.europa.eu/project/id/899739/results) lists numerical, field, large-group laboratory, and small-group laboratory datasets. It describes dense laboratory video involving 100–200 people and small-group physical-interaction material with full-body capture, force plates, and video. Those records establish that CORDIS lists outputs. In the source audit for this review, linked download modules did not expose usable file inventories and licences. Formats, time bases, camera calibration, labels, and reuse rights remain unverified.

The [Zenodo record linked to Gu et al.'s paper](https://doi.org/10.5281/zenodo.14050598) declares open access and record-level CC BY 4.0. Its API lists 46 files totalling 1,217,698,331 bytes, about 1.22 GB, and names François Gu, Benjamin Guiselin, and Denis Bartolo as dataset creators. This three-person creator list differs from the five authors of the Nature paper. No payload files were fetched or audited; labels, calibration, and per-file applicability of the record-level terms remain unverified. Keep payloads external. The [JuSER impulse dataset record](https://juser.fz-juelich.de/record/1054781) is a lead for controlled small-group work; its file list and reuse terms were not verified. The papers establish observations and methods, not that every underlying recording is available for reuse.

Crowd-counting sets such as [SAIVT-QUT](https://researchdata.edu.au/saivt-qut-crowd-counting/673183) and PETS 2009 can help with component tasks such as counting, tracking, or calibration-aware measurement. They do not provide independently adjudicated crush outcomes. From the inspected public records, no dataset was established that pairs ordinary camera observations with independent crush-harm labels, event timing, and matched non-event periods. This is an access finding, not proof that no restricted dataset exists.

## Prior work and a credible project position

CrowdDNA's [CORDIS project record](https://cordis.europa.eu/project/id/899739) describes work linking macroscopic motion observations with microscopic interaction and simulation. That scientific gap motivates this prototype's question, but does not establish that CrowdDNA used the stochastic equations discussed here or that this code implements its methods.

Operational crowd monitoring is already served by counting, heatmaps, location analytics, CCTV, and LiDAR products. Published or vendor-described deployments show that sensors and control-room displays can be integrated. They do not by themselves establish independent alert accuracy or incident prevention. Basic occupancy monitoring is not a defensible novelty claim for this repository.

A credible near-term position is a research workbench for inspecting zone observations, their provenance, missingness, and model assumptions. The research value would be a transparent comparison of candidate motion descriptors against controls and annotated cases, including abstentions. Any future operator-facing claim would require site-specific prospective evidence, a defined human review process, false-alarm burden and lead-time analysis, privacy and governance review, and proof that the signal supports an action. Nothing here is ready for operational use.

## Open research questions

The questions below are research questions, not a committed implementation plan. Every proposed experiment is **NOT RUN**.

| Research question | Decisive evidence needed |
| --- | --- |
| Does a motion feature precede independently labeled adverse events? | Synchronized video, independent onset intervals, and held-out events with matched non-event windows. |
| Does local spatial variance add information beyond temporal zone variance? | Same clips processed with both definitions and independent spatial motion references. |
| Are oscillations specific to adverse dynamics? | Benign high-motion controls, music/event timing, stable-camera references, and replication across settings. |
| Do perturbations propagate differently with crowd structure? | Controlled input magnitude, mapped formation, synchronized body/contact measurements, and repeated trials. |
| Does bottleneck imbalance precede irregular motion? | Time-aligned inflow, outflow, gap propagation, and motion labels across bottleneck and open-area cases. |
| Can camera motion be separated from crowd motion? | Static references, independent camera-motion estimates, and residual error under parallax and zoom. |
| When is physical density identifiable? | Camera geometry, ground mapping, visibility audit, and independent count/area checks. |
| Which regimes recur across sites? | Multi-site sequences with consistent feature definitions and event/site-held-out comparisons. |
| Do simple baselines match complex models? | Same input, splits, horizons, labels, and uncertainty accounting across persistence, trend, change-point, spectral, and switching models. |
| Are model parameters identifiable? | Repeated observations plus independent measurements that distinguish interactions from noise and hidden forcing. |
| Are crossing probabilities calibrated? | Held-out real outcomes, fixed definitions, calibration analysis, and uncertainty intervals. |
| What is the valid exposure denominator? | Time coverage, unavailable intervals, episode matching rules, and independently adjudicated event windows. |
| Do warnings offer actionable lead time? | Prospective or rigorously retrospective event timing, latency accounting, and a defined response workflow. |
| How often must the system abstain? | Quality labels across camera, lighting, occlusion, and timestamp failure conditions. |
| Do analysts agree on onset and motion regimes? | Independent annotation, disagreement records, and adjudication criteria. |
| Are candidate data reusable for each task? | File manifests, provenance, licences, permitted-use terms, schemas, and label documentation. |

## Sources and limits

Full references, author credit, and source notes appear in [CITATIONS.md](../CITATIONS.md). This review is selective. It distinguishes paper findings, project descriptions, vendor claims, and hypotheses; it does not independently reproduce the cited analyses. No dataset was downloaded for this work, no model was fitted, and no experiment or warning-effectiveness evaluation was run.
