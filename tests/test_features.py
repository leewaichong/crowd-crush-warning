"""Unit tests use labelled synthetic fixtures, not crowd effectiveness data."""

import unittest

from crowd_warning.features import extract_features


def row(timestamp, vx, vy=0.0, **overrides):
    value = {
        "timestamp_s": timestamp,
        "zone_id": "zone-a",
        "density_per_m2": 2.0,
        "vx_mps": vx,
        "vy_mps": vy,
        "quality": 1.0,
        "calibrated": True,
    }
    value.update(overrides)
    return value


class ExtractFeaturesTests(unittest.TestCase):
    def test_opposite_motion_has_positive_vector_velocity_variance(self):
        features = extract_features([row(0, 1), row(1, -1)])
        self.assertIsNone(features[0]["velocity_variance"])
        self.assertEqual(features[1]["velocity_variance"], 1.0)
        self.assertEqual(features[1]["pressure_proxy"], 2.0)

    def test_variance_uses_both_velocity_components(self):
        features = extract_features([row(0, 0, 1), row(1, 0, -1)])
        self.assertEqual(features[-1]["velocity_variance"], 1.0)

    def test_future_rows_do_not_change_earlier_features(self):
        prefix = [row(0, 0), row(1, 1)]
        future = row(2, 100)
        before = extract_features(prefix)[-1]
        after = extract_features(prefix + [future])[-2]
        self.assertEqual(before, after)

    def test_window_is_causal_and_trailing(self):
        features = extract_features([row(0, 0), row(1, 1), row(4, 100)], window_s=2)
        self.assertIsNone(features[0]["velocity_variance"])
        self.assertEqual(features[1]["velocity_variance"], 0.25)
        self.assertIsNone(features[2]["velocity_variance"])

    def test_out_of_window_bad_row_does_not_poison_current_window(self):
        features = extract_features([
            row(0, 0, quality=0.1),
            row(1, 1),
            row(2, 2),
        ], window_s=1)
        self.assertEqual(features[1]["reason"], "low_quality")
        self.assertEqual(features[2]["status"], "ok")
        self.assertEqual(features[2]["count"], 2)

    def test_duplicate_zone_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate timestamp"):
            extract_features([row(1, 0), row(1, 1)])

    def test_large_shared_velocity_keeps_small_variance(self):
        features = extract_features([row(0, 1e12), row(1, 1e12 + 1)])
        self.assertAlmostEqual(features[-1]["velocity_variance"], 0.25)

    def test_overflow_abstains_with_finite_serializable_values(self):
        features = extract_features([row(0, 1e308), row(1, -1e308)])
        result = features[-1]
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["reason"], "numeric_overflow")
        self.assertIsNone(result["velocity_variance"])
        self.assertIsNone(result["pressure_proxy"])
        self.assertEqual(result["count"], 2)

    def test_density_times_variance_overflow_abstains(self):
        features = extract_features([
            row(0, -1e154, density=1e308),
            row(1, 1e154, density=1e308),
        ])
        self.assertEqual(features[-1]["reason"], "numeric_overflow")
        self.assertIsNone(features[-1]["pressure_proxy"])

    def test_insufficient_quality_or_calibration_abstains(self):
        low_quality = extract_features([row(0, 0), row(1, 1, quality=0.4)])
        uncalibrated = extract_features([row(0, 0), row(1, 1, calibrated=False)])
        for result in (low_quality[-1], uncalibrated[-1]):
            self.assertIsNone(result["velocity_variance"])
            self.assertIsNone(result["pressure_proxy"])

    def test_missing_or_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            extract_features([{"timestamp_s": 0}])
        with self.assertRaises(ValueError):
            extract_features([row(0, float("nan"))])
        with self.assertRaises(ValueError):
            extract_features([], window_s=0)

    def test_quality_cutoff_is_configurable(self):
        features = extract_features([row(0, 0), row(1, 1, quality=0.4)], min_quality=0.4)
        self.assertEqual(features[-1]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
