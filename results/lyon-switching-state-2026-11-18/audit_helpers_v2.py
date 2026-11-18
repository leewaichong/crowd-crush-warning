"""Small independent scalar HMM calculations for the CROWD50 audit."""

import math

import numpy as np


def _logsumexp(values):
    peak = max(values)
    if peak == -math.inf:
        return peak
    return peak + math.log(sum(math.exp(value - peak) for value in values))


def _log_emission_2d(observation, means, variances):
    total = 0.0
    for axis in range(2):
        variance = variances[axis]
        if not math.isfinite(variance) or variance <= 0:
            raise ValueError("emission variances must be finite and positive")
        delta = observation[axis] - means[axis]
        total += -0.5 * (math.log(2.0 * math.pi * variance) + delta * delta / variance)
    return total


def filter_observations(observations, initial, transition, means, variances):
    """Return filtered state probabilities after each observation, in input order."""
    if len(initial) != 2 or len(transition) != 2 or any(len(row) != 2 for row in transition):
        raise ValueError("expected a two-state model")
    if any(p < 0 or not math.isfinite(p) for p in initial) or sum(initial) <= 0:
        raise ValueError("invalid initial probabilities")
    if any(p < 0 or not math.isfinite(p) for row in transition for p in row):
        raise ValueError("invalid transition probabilities")
    if any(sum(row) <= 0 for row in transition):
        raise ValueError("transition rows must have positive mass")

    alpha = [p / sum(initial) for p in initial]
    filtered = []
    for index, observation in enumerate(observations):
        if index == 0:
            predicted = alpha
        else:
            predicted = [
                alpha[0] * transition[0][state] / sum(transition[0])
                + alpha[1] * transition[1][state] / sum(transition[1])
                for state in range(2)
            ]
        log_weights = [
            math.log(predicted[state]) + _log_emission_2d(observation, means[state], variances[state])
            if predicted[state] > 0 else -math.inf
            for state in range(2)
        ]
        normalizer = _logsumexp(log_weights)
        if not math.isfinite(normalizer):
            raise ArithmeticError("observation has zero likelihood under both states")
        alpha = [math.exp(value - normalizer) for value in log_weights]
        filtered.append(tuple(alpha))
    return filtered


def next_state_probabilities(filtered, transition):
    """Advance one step from a filtered posterior using the row-stochastic matrix."""
    rows = [[value / sum(row) for value in row] for row in transition]
    return tuple(sum(filtered[source] * rows[source][target] for source in range(2)) for target in range(2))


def conditional_mean(next_probabilities, means):
    """Mixture mean in the model's current coordinate system."""
    return tuple(sum(next_probabilities[state] * means[state][axis] for state in range(2)) for axis in range(2))


def stationary_probabilities(transition):
    """Stationary weights for a positive two-state transition matrix."""
    row0 = [value / sum(transition[0]) for value in transition[0]]
    row1 = [value / sum(transition[1]) for value in transition[1]]
    denominator = row0[1] + row1[0]
    if denominator <= 0:
        raise ValueError("transition matrix has no unique two-state stationary mixture")
    return row1[0] / denominator, row0[1] / denominator


def logsumexp(values):
    """Stable scalar log(sum(exp(values)))."""
    peak = max(float(value) for value in values)
    if peak == -math.inf:
        return peak
    return peak + math.log(sum(math.exp(float(value) - peak) for value in values))


def sequence_log_likelihood(observations, initial, transition, means, variances):
    """Scalar forward likelihood for one sequence under diagonal 2D Gaussians."""
    if len(observations) == 0:
        return 0.0
    alpha = [math.log(float(initial[s])) for s in range(2)]
    for index, observation in enumerate(observations):
        emission = [_log_emission_2d(observation, means[s], variances[s]) for s in range(2)]
        if index == 0:
            alpha = [alpha[s] + emission[s] for s in range(2)]
        else:
            alpha = [
                emission[target] + logsumexp([
                    alpha[source] + math.log(float(transition[source][target]))
                    for source in range(2)
                ])
                for target in range(2)
            ]
    return logsumexp(alpha)


def source_error_metrics(prediction, target):
    delta = np.asarray(prediction, dtype=np.float64) - np.asarray(target, dtype=np.float64)
    vector = np.sqrt(np.sum(delta * delta, axis=1))
    return {
        "n": int(len(target)),
        "mean_vector_euclidean_error_source_units_per_native_frame": float(vector.mean()),
        "rmse_vector_euclidean_error_source_units_per_native_frame": float(np.sqrt(np.mean(vector * vector))),
        "axis_mae_source_units_per_native_frame": np.mean(np.abs(delta), axis=0).tolist(),
    }
