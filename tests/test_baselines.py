import json
import math
import unittest

from crowd_warning.baselines import baseline_signals


def row(t, proxy, *, zone="north", density=1.0, quality=1.0, calibrated=True, status="ok"):
    return {"timestamp_s": t, "zone_id": zone, "density_per_m2": density,
            "pressure_proxy": proxy, "quality": quality, "calibrated": calibrated,
            "status": status, "reason": None if status == "ok" else "insufficient_window"}


def run(rows, **kwargs):
    params = {"density_threshold": 2, "proxy_threshold": 3, "change_threshold": 2}
    params.update(kwargs)
    return baseline_signals(rows, **params)


class BaselineTests(unittest.TestCase):
    def test_future_append_does_not_change_prior_rows(self):
        prefix = [row(0, 1), row(1, 1), row(2, 4)]
        before = run(prefix)
        after = run(prefix + [row(3, 20)])
        self.assertEqual(before, after[:len(before)])

    def test_zone_histories_are_isolated_and_results_sorted(self):
        result = run([row(1, 1, zone="b"), row(0, 8, zone="a"),
                      row(2, 2, zone="a"), row(2, 7, zone="b")])
        self.assertEqual([(r["timestamp_s"], r["zone_id"]) for r in result],
                         [(0, "a"), (1, "b"), (2, "a"), (2, "b")])
        self.assertIsNone(result[1]["arms"]["persistence"]["score"])
        self.assertEqual(result[2]["arms"]["persistence"]["score"], 8)

    def test_density_is_current_and_persistence_is_lagged(self):
        result = run([row(0, 9, density=1), row(1, 1, density=4)])
        self.assertEqual(result[1]["arms"]["density"]["score"], 4)
        self.assertTrue(result[1]["arms"]["density"]["alarm"])
        self.assertEqual(result[1]["arms"]["persistence"]["score"], 9)

    def test_cusum_detects_known_step_causally(self):
        values = [1, 1, 1, 5, 5]
        result = run([row(i, value) for i, value in enumerate(values)], allowance=0)
        scores = [item["arms"]["change_point"]["score"] for item in result]
        self.assertIsNone(scores[0])
        self.assertEqual(scores[1:4], [0, 0, 4])
        self.assertGreater(scores[4], scores[3])

    def test_shuffled_input_matches_sorted_input(self):
        rows = [row(0, 1), row(1, 2), row(2, 5)]
        self.assertEqual(run(rows), run([rows[2], rows[0], rows[1]]))

    def test_duplicate_zone_timestamp_rejected_explicitly(self):
        result = run([row(0, 1), row(1, 2), row(1, 3)])
        self.assertEqual([item["reason"] for item in result[1:]],
                         ["duplicate_timestamp", "duplicate_timestamp"])
        self.assertEqual(result[1]["status"], "abstain")

    def test_quality_and_calibration_reset_history(self):
        result = run([row(0, 1), row(1, 2, quality=0.2), row(2, 4), row(3, 5, calibrated=False)])
        self.assertEqual(result[1]["reason"], "low_quality")
        self.assertEqual(result[2]["reason"], "warmup")
        self.assertEqual(result[3]["reason"], "uncalibrated")
        self.assertIsNone(result[3]["arms"]["persistence"]["score"])

    def test_warmup_missingness_and_gap_reset(self):
        result = run([row(0, 1), row(1, None), row(2, 3), row(10, 5), row(11, 6)])
        self.assertEqual(result[0]["reason"], "warmup")
        self.assertEqual(result[1]["reason"], "missing_proxy")
        self.assertEqual(result[2]["reason"], "warmup")
        self.assertEqual(result[3]["reason"], "warmup")
        self.assertEqual(result[4]["status"], "ok")

    def test_outputs_are_finite_strict_json(self):
        result = run([row(0, 1), row(1, 1e200), row(2, 1e200)])
        encoded = json.dumps(result, allow_nan=False)
        self.assertTrue(encoded)
        for item in result:
            for arm in item["arms"].values():
                if arm["score"] is not None:
                    self.assertTrue(math.isfinite(arm["score"]))

    def test_invalid_parameters_rejected(self):
        for kwargs in ({"density_threshold": 0}, {"proxy_threshold": float("inf")},
                       {"change_threshold": -1}, {"allowance": -0.1},
                       {"min_quality": 1.1}, {"max_gap_s": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run([row(0, 1)], **kwargs)


if __name__ == "__main__":
    unittest.main()
