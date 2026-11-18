"""Unit tests with synthetic fixtures; these are not crowd effectiveness results."""

import unittest
import random

from crowd_warning.features import extract_features
from crowd_warning.forecast import _poisson, forecast_crossing


def fixture_features(*, quality=0.9, calibrated=True, proxy_values=(0.2, 0.3),
                     times=(0.0, 1.0), variance=0.01):
    """Build minimal synthetic temporal zone-window rows for unit tests."""
    return [
        {
            "timestamp_s": time,
            "zone_id": "zone-a",
            "density_per_m2": 1.0,
            "velocity_variance": variance,
            "pressure_proxy": proxy,
            "quality": quality,
            "calibrated": calibrated,
        }
        for time, proxy in zip(times, proxy_values)
    ]


def pipeline_observations(zone_times, *, bad_quality_at=None):
    """Build synthetic observation rows for data-to-features-to-forecast tests."""
    rows = []
    for zone, times in zone_times.items():
        for index, timestamp in enumerate(times):
            rows.append({
                "timestamp_s": timestamp,
                "zone_id": zone,
                "density_per_m2": 1.0,
                "vx_mps": float(index % 2),
                "vy_mps": float(index % 3),
                "quality": 0.2 if (zone, timestamp) == bad_quality_at else 0.9,
                "calibrated": True,
            })
    return extract_features(rows)


def feature_row(timestamp, variance, proxy, *, zone="A"):
    """Build one synthetic feature row with explicit warmup values."""
    return {
        "timestamp_s": timestamp,
        "zone_id": zone,
        "density_per_m2": 1.0,
        "velocity_variance": variance,
        "pressure_proxy": proxy,
        "quality": 1.0,
        "calibrated": True,
    }


class ForecastTests(unittest.TestCase):
    def test_initial_threshold_is_already_a_first_passage(self):
        result = forecast_crossing(
            fixture_features(proxy_values=(0.4, 0.8)), threshold=0.8,
            horizon_s=3, paths=20, seed=4,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["probability"], 1.0)

    def test_seed_reproduces_monte_carlo_estimate(self):
        args = (fixture_features(variance=0.2),)
        first = forecast_crossing(*args, horizon_s=8, threshold=0.7, paths=80, seed=91)
        second = forecast_crossing(*args, horizon_s=8, threshold=0.7, paths=80, seed=91)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first["probability"], 0.0)
        self.assertLessEqual(first["probability"], 1.0)

    def test_invalid_numeric_arguments_raise(self):
        for kwargs in ({"horizon_s": 0}, {"threshold": float("nan")},
                       {"paths": 0}, {"jump_rate_per_s": 1.0},
                       {"max_gap_s": 0}, {"max_gap_s": float("inf")},
                       {"jump_rate_per_s": 21, "jump_scale": 0.2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                forecast_crossing(fixture_features(), **kwargs)

    def test_incomplete_window_abstains(self):
        result = forecast_crossing(fixture_features(times=(2.0,), proxy_values=(0.2,)))
        self.assertEqual(result["status"], "abstain")
        self.assertIsNone(result["probability"])

    def test_uncalibrated_or_low_quality_inputs_abstain(self):
        for rows in (fixture_features(calibrated=False), fixture_features(quality=0.49)):
            with self.subTest(rows=rows):
                result = forecast_crossing(rows)
                self.assertEqual(result["status"], "abstain")
                self.assertIsNone(result["probability"])

    def test_temporal_gap_abstains(self):
        result = forecast_crossing(fixture_features(times=(0.0, 20.0)))
        self.assertEqual(result["status"], "abstain")

    def test_optional_jump_hypothesis_is_reproducible(self):
        kwargs = dict(horizon_s=2, threshold=0.9, paths=40, seed=3,
                      jump_rate_per_s=2, jump_scale=0.4)
        first = forecast_crossing(fixture_features(), **kwargs)
        second = forecast_crossing(fixture_features(), **kwargs)
        self.assertEqual(first, second)

    def test_output_does_not_claim_calibrated_harm_probability(self):
        result = forecast_crossing(fixture_features())
        self.assertIn("not a calibrated harm probability", result["caveats"][0])

    def test_feature_pipeline_discards_only_leading_warmup(self):
        features = pipeline_observations({"north": (0, 1, 2), "south": (0, 1, 2)})
        result = forecast_crossing(features, threshold=100, max_gap_s=1.1, seed=7)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["warmup_counts"], {"north": 1, "south": 1})
        self.assertIn("leading trailing-window warmup", result["warmup_reasons"]["north"])

    def test_warmup_only_zone_abstains_and_is_enumerated(self):
        complete = pipeline_observations({"ready": (0, 1, 2)})
        warmup_only = pipeline_observations({"warming": (0,)})
        # Feature extraction emits one leading warmup for each zone. Add the
        # warming zone's rows after the complete zone to reproduce issue 30.
        result = forecast_crossing(complete + warmup_only, max_gap_s=2)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["incomplete_zones"], ["warming"])
        self.assertEqual(result["warmup_counts"], {"ready": 1, "warming": 1})
        self.assertEqual(result["forecast_origin_s"], 2.0)
        self.assertEqual(result["input_cutoff_s"], 2.0)

    def test_shuffled_interior_warmup_abstains_after_chronological_sort(self):
        rows = [
            feature_row(1, None, None),
            feature_row(0, 0, 0),
            feature_row(2, 0, 0),
        ]
        result = forecast_crossing(rows)
        self.assertEqual(result["status"], "abstain")
        self.assertIn("interior feature warmup", result["caveats"][1])
        self.assertEqual(result["warmup_counts"], {"A": 1})
        self.assertEqual(result["forecast_origin_s"], 2.0)
        self.assertEqual(result["input_cutoff_s"], 2.0)

    def test_leading_warmup_arriving_after_complete_rows_is_accepted(self):
        rows = [
            feature_row(1, 0, 0),
            feature_row(2, 0, 0),
            feature_row(0, None, None),
        ]
        result = forecast_crossing(rows)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["warmup_counts"], {"A": 1})
        self.assertEqual(result["forecast_origin_s"], 2.0)
        self.assertEqual(result["input_cutoff_s"], 2.0)

    def test_duplicate_warmup_timestamps_abstain(self):
        rows = [
            feature_row(0, None, None),
            feature_row(0, None, None),
            feature_row(1, 0, 0),
            feature_row(2, 0, 0),
        ]
        result = forecast_crossing(rows)
        self.assertEqual(result["status"], "abstain")
        self.assertIn("duplicate timestamps", result["caveats"][1])
        self.assertEqual(result["warmup_counts"], {"A": 2})

    def test_success_metadata_records_effective_model_and_time(self):
        result = forecast_crossing(
            fixture_features(times=(4.0, 5.0)), horizon_s=2, threshold=0.8,
            paths=12, seed=19, coupling=0.3, max_gap_s=2,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["forecast_origin_s"], 5.0)
        self.assertEqual(result["input_cutoff_s"], 5.0)
        self.assertEqual(result["seed"], 19)
        self.assertEqual(result["effective_model_parameters"], {
            "horizon_s": 2.0, "threshold": 0.8, "paths": 12,
            "jump_rate_per_s": 0.0, "jump_scale": 0.0,
            "coupling": 0.3, "max_gap_s": 2.0,
        })
        self.assertEqual(result["discretization"]["step_s"], 1.0)

    def test_stale_abstention_preserves_metadata_and_audit_counts(self):
        features = pipeline_observations({"north": (0, 1, 2, 3, 4), "south": (0, 1, 2)})
        result = forecast_crossing(features, seed=8, max_gap_s=1.1)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["warmup_counts"], {"north": 1, "south": 1})
        self.assertEqual(result["forecast_origin_s"], 4.0)
        self.assertEqual(result["input_cutoff_s"], 4.0)
        self.assertEqual(result["seed"], 8)
        self.assertEqual(result["stale_zones"], ["south"])

    def test_bad_quality_in_pipeline_abstains_instead_of_dropping_row(self):
        features = pipeline_observations(
            {"north": (0, 1, 2, 3), "south": (0, 1, 2, 3)},
            bad_quality_at=("north", 2),
        )
        result = forecast_crossing(features, max_gap_s=1.1)
        self.assertEqual(result["status"], "abstain")
        self.assertIn("low quality", result["caveats"][1])
        self.assertEqual(result["warmup_counts"], {"north": 1, "south": 1})

    def test_stale_zone_is_named(self):
        features = pipeline_observations({
            "north": (0, 1, 2, 3, 4),
            "south": (0, 1, 2),
        })
        result = forecast_crossing(features, max_gap_s=1.1)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["stale_zones"], ["south"])

    def test_interior_gap_in_a_zone_abstains(self):
        features = fixture_features(times=(0, 1, 8), proxy_values=(0.1, 0.2, 0.3))
        result = forecast_crossing(features, max_gap_s=2)
        self.assertEqual(result["status"], "abstain")
        self.assertIn("interior observation gap", result["caveats"][1])

    def test_poisson_zero_rate_and_rate_bound(self):
        self.assertEqual(_poisson(random.Random(1), 0), 0)
        with self.assertRaises(ValueError):
            _poisson(random.Random(1), 21)


if __name__ == "__main__":
    unittest.main()
