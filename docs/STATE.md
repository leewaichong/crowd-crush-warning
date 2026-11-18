# Project status

Snapshot date: 18 November 2026.

## Implemented

The repository contains offline observation ingestion, causal temporal zone-motion features, a conditional stochastic proxy-crossing model, evaluation utilities, and a command-line interface. Forecasting abstains if any observed zone lacks two complete adequate feature observations. Forecast responses record forecast origin, input cutoff, seed, effective model parameters, and discretization. Evaluation helpers support alarm-episode matching for preselected alarm rows, disjoint valid timeline exposure accounting, venue/event splitting, and chronology checks. The legacy row-matching helper remains available, so callers must explicitly choose episode matching for episode-level accounting. The code does not ingest video, estimate physical force, or fit spatial propagation from crowd data.

## Locally verified

Locally verified on 18 November 2026: the integrated full suite ran 66 tests and passed. These checks concern software behavior only; they do not establish empirical model performance.

## Evaluated

**Real crowd evaluation: NOT RUN. Warning effectiveness: NOT RUN.** No real crowd dataset, independently established outcome labels, frozen protocol, or empirical result is included.

## Evidence limits

No real crowd data have been admitted, no harm probability is calibrated, and no useful-warning evidence exists. The episode helper requires callers to supply selected alarm rows; legacy row matching remains available and does not automatically use episode accounting. Software checks do not establish warning effectiveness.
