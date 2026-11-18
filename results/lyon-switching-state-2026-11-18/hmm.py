"""Small fixed-design NumPy HMM for M07 reported-increment research."""
from __future__ import annotations

import math

import numpy as np


def logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    if not math.isfinite(maximum):
        return maximum
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def emission_log_probabilities(
    observations: np.ndarray, means: np.ndarray, variances: np.ndarray,
) -> np.ndarray:
    delta = observations[:, None, :] - means[None, :, :]
    return -0.5 * np.sum(
        np.log(2.0 * math.pi * variances)[None, :, :] + delta * delta / variances[None, :, :],
        axis=2,
    )


def forward_backward(
    log_emissions: np.ndarray, pi: np.ndarray, transition: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Return log likelihood, smoothed state probabilities, and summed xi."""
    length, states = log_emissions.shape
    log_pi = np.log(pi)
    log_transition = np.log(transition)
    alpha = np.empty((length, states), dtype=np.float64)
    scales = np.empty(length, dtype=np.float64)

    unscaled = log_pi + log_emissions[0]
    scales[0] = logsumexp(unscaled)
    alpha[0] = unscaled - scales[0]
    for t in range(1, length):
        unscaled = log_emissions[t] + np.asarray([
            logsumexp(alpha[t - 1] + log_transition[:, state]) for state in range(states)
        ])
        scales[t] = logsumexp(unscaled)
        alpha[t] = unscaled - scales[t]

    beta = np.zeros((length, states), dtype=np.float64)
    for t in range(length - 2, -1, -1):
        for state in range(states):
            beta[t, state] = logsumexp(
                log_transition[state] + log_emissions[t + 1] + beta[t + 1]
            ) - scales[t + 1]

    gamma = np.empty_like(alpha)
    for t in range(length):
        row = alpha[t] + beta[t]
        gamma[t] = np.exp(row - logsumexp(row))

    xi_total = np.zeros((states, states), dtype=np.float64)
    for t in range(length - 1):
        log_xi = (
            alpha[t, :, None] + log_transition + log_emissions[t + 1, None, :]
            + beta[t + 1, None, :] - scales[t + 1]
        )
        log_xi -= logsumexp(log_xi.ravel())
        xi_total += np.exp(log_xi)
    return float(scales.sum()), gamma, xi_total


def filter_states(
    log_emissions: np.ndarray, pi: np.ndarray, transition: np.ndarray,
) -> np.ndarray:
    """Causal normalized filtering probabilities, one row per observation."""
    length, states = log_emissions.shape
    log_transition = np.log(transition)
    filtered = np.empty((length, states), dtype=np.float64)
    row = np.log(pi) + log_emissions[0]
    filtered[0] = np.exp(row - logsumexp(row))
    for t in range(1, length):
        row = log_emissions[t] + np.asarray([
            logsumexp(np.log(filtered[t - 1]) + log_transition[:, state])
            for state in range(states)
        ])
        filtered[t] = np.exp(row - logsumexp(row))
    return filtered


def next_state_probabilities(filtered: np.ndarray, transition: np.ndarray) -> np.ndarray:
    return filtered @ transition


def conditional_mean(next_probabilities: np.ndarray, means: np.ndarray) -> np.ndarray:
    return next_probabilities @ means


def stationary_distribution(transition: np.ndarray) -> np.ndarray:
    off_diagonal_sum = transition[0, 1] + transition[1, 0]
    result = np.asarray([transition[1, 0], transition[0, 1]], dtype=np.float64) / off_diagonal_sum
    return result / result.sum()


def fit(
    training_sequences: list[np.ndarray], *, max_updates: int, tolerance: float,
    variance_floor: float, pseudocount: float, time_limit: float, memory_limit: int,
    progress_callback=None,
) -> dict:
    """Fit the one frozen two-state diagonal Gaussian HMM."""
    import resource
    import time

    started = time.monotonic()
    all_x = np.concatenate(training_sequences, axis=0)
    center = all_x.mean(axis=0)
    scale = all_x.std(axis=0)
    scale[scale == 0.0] = 1.0
    standardized_sequences = [(seq - center) / scale for seq in training_sequences]
    flat = np.concatenate(standardized_sequences, axis=0)
    raw_variance = all_x.var(axis=0)
    sort_axis = int(np.argmax(raw_variance))
    order = np.argsort(flat[:, sort_axis], kind="stable")
    midpoint = len(order) // 2
    groups = [flat[order[:midpoint]], flat[order[midpoint:]]]
    means = np.stack([part.mean(axis=0) for part in groups])
    variances = np.stack([part.var(axis=0) for part in groups])
    variances = np.maximum(variances, variance_floor)
    pi = np.asarray([0.5, 0.5], dtype=np.float64)
    transition = np.asarray([[0.95, 0.05], [0.05, 0.95]], dtype=np.float64)
    versions = []
    likelihoods = []
    degeneracies = []

    def evaluate() -> float:
        total = 0.0
        for sequence in standardized_sequences:
            logs = emission_log_probabilities(sequence, means, variances)
            likelihood, _, _ = forward_backward(logs, pi, transition)
            total += likelihood
        return total

    def remember(version: int, likelihood: float, degenerate_states: list[int]) -> None:
        likelihoods.append(float(likelihood))
        degeneracies.append(list(degenerate_states))
        versions.append({
            "pi": pi.tolist(), "transition": transition.tolist(),
            "means_standardized": means.tolist(), "variances_standardized": variances.tolist(),
            "version": version,
        })
        if progress_callback is not None:
            progress_callback({
                "likelihoods": likelihoods, "versions": versions,
                "degeneracies": degeneracies,
            })

    previous = evaluate()
    remember(0, previous, [])
    converged = False
    nonmonotonic = False
    updates = 0
    for update in range(1, max_updates + 1):
        pi_counts = np.full(2, pseudocount, dtype=np.float64)
        transition_counts = np.full((2, 2), pseudocount, dtype=np.float64)
        state_mass = np.zeros(2, dtype=np.float64)
        weighted_sum = np.zeros((2, 2), dtype=np.float64)
        weighted_square = np.zeros((2, 2), dtype=np.float64)
        for sequence in standardized_sequences:
            logs = emission_log_probabilities(sequence, means, variances)
            _, gamma, xi = forward_backward(logs, pi, transition)
            pi_counts += gamma[0]
            transition_counts += xi
            state_mass += gamma.sum(axis=0)
            weighted_sum += gamma.T @ sequence
            weighted_square += gamma.T @ (sequence * sequence)
        pi = pi_counts / pi_counts.sum()
        transition = transition_counts / transition_counts.sum(axis=1, keepdims=True)
        empty = []
        for state in range(2):
            if state_mass[state] <= 0.0:
                empty.append(state)
                continue
            means[state] = weighted_sum[state] / state_mass[state]
            variance = weighted_square[state] / state_mass[state] - means[state] ** 2
            variances[state] = np.maximum(variance, variance_floor)
        current = evaluate()
        updates = update
        remember(update, current, empty)
        delta_per_increment = (current - previous) / len(flat)
        if current < previous - 1e-10:
            nonmonotonic = True
        previous = current
        if time.monotonic() - started > time_limit:
            raise TimeoutError("20-minute fit budget exceeded")
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if peak > memory_limit:
            raise MemoryError("1 GiB observed-memory guard exceeded")
        if abs(delta_per_increment) <= tolerance:
            converged = True
            break

    return {
        "center": center, "scale": scale, "pi": pi, "transition": transition,
        "means_standardized": means, "variances_standardized": variances,
        "means_source_units": means * scale + center,
        "variances_source_units": variances * scale * scale,
        "likelihoods": np.asarray(likelihoods, dtype=np.float64),
        "versions": versions, "degeneracies": degeneracies,
        "iterations": updates, "converged": converged,
        "hit_iteration_cap": updates == max_updates and not converged,
        "nonmonotonic": nonmonotonic, "sort_axis": sort_axis,
        "stationary": stationary_distribution(transition),
        "training_increment_count": len(flat),
    }
