import itertools
import unittest

import numpy as np

from hmm import (
    conditional_mean,
    emission_log_probabilities,
    filter_states,
    forward_backward,
    next_state_probabilities,
)


class FixedHMMSoftwareChecks(unittest.TestCase):
    def test_forward_backward_matches_short_brute_force(self):
        emissions = np.log(np.asarray([[0.8, 0.2], [0.3, 0.7], [0.6, 0.4]]))
        pi = np.asarray([0.6, 0.4])
        transition = np.asarray([[0.7, 0.3], [0.2, 0.8]])
        likelihood, gamma, xi = forward_backward(emissions, pi, transition)
        paths = list(itertools.product(range(2), repeat=3))
        weights = []
        for path in paths:
            weight = pi[path[0]]
            for t, state in enumerate(path):
                weight *= np.exp(emissions[t, state])
                if t:
                    weight *= transition[path[t - 1], state]
            weights.append(weight)
        total = sum(weights)
        expected_gamma = np.zeros((3, 2))
        expected_xi = np.zeros((2, 2))
        for path, weight in zip(paths, weights):
            for t, state in enumerate(path):
                expected_gamma[t, state] += weight / total
            for t in range(2):
                expected_xi[path[t], path[t + 1]] += weight / total
        self.assertAlmostEqual(likelihood, np.log(total), places=13)
        np.testing.assert_allclose(gamma, expected_gamma, atol=1e-13)
        np.testing.assert_allclose(xi, expected_xi, atol=1e-13)

    def test_conditional_prediction_is_analytic_and_causal(self):
        observations = np.asarray([[0.0], [1.0], [2.0], [8.0]])
        means = np.asarray([[0.0], [5.0]])
        variances = np.asarray([[1.0], [2.0]])
        pi = np.asarray([0.7, 0.3])
        transition = np.asarray([[0.8, 0.2], [0.1, 0.9]])
        full_filter = filter_states(emission_log_probabilities(observations, means, variances), pi, transition)
        changed_future = observations.copy()
        changed_future[3, 0] = -100.0
        changed_filter = filter_states(emission_log_probabilities(changed_future, means, variances), pi, transition)
        np.testing.assert_allclose(full_filter[:3], changed_filter[:3], atol=1e-14)
        next_probs = next_state_probabilities(full_filter[2], transition)
        np.testing.assert_allclose(next_probs, full_filter[2] @ transition, atol=1e-15)
        prediction = conditional_mean(next_probs, means)
        self.assertAlmostEqual(float(prediction[0]), float(next_probs @ means[:, 0]), places=14)


if __name__ == "__main__":
    unittest.main()
