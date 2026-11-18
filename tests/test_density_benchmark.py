"""Small, synthetic fixtures for density forecast math only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from density_forecast_benchmark import fit_ar1, forecast_year


class DensityBenchmarkTests(unittest.TestCase):
    def test_ar1_fit_is_analytic_and_prior_forecasts_ignore_future_changes(self):
        points = [[i * 0.04, 2.0 + 0.8 ** i] for i in range(3000)]
        training = points[:1501]
        fit = fit_ar1(training)
        self.assertAlmostEqual(fit["phi"], 0.8, places=7)
        altered = [row[:] for row in points]
        for row in altered:
            if row[0] > 80:
                row[1] += 500
        before = forecast_year(points, fit, 2023)
        after = forecast_year(altered, fit, 2023)
        before = [row for row in before if row["target_timestamp_s"] <= 80]
        after = [row for row in after if row["target_timestamp_s"] <= 80]
        self.assertEqual(before, after)

    def test_origins_and_targets_use_native_grid_and_causal_cutoff(self):
        points = [[i * 0.04, float(i)] for i in range(1801)]
        points[750][0] += 0.4e-6
        points[1500][0] -= 0.3e-6
        rows = forecast_year(points, {"intercept": 0.0, "phi": 0.5, "residual_variance": 1.0}, 2024)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["origin_timestamp_s"], row["cutoff_timestamp_s"])
            self.assertAlmostEqual(row["scheduled_target_timestamp_s"] - row["scheduled_origin_timestamp_s"], 30.0, places=9)
            self.assertIn(row["origin_timestamp_s"], [point[0] for point in points])
            self.assertIn(row["target_timestamp_s"], [point[0] for point in points])
        self.assertEqual(rows[0]["origin_timestamp_s"], points[750][0])
        self.assertEqual(rows[0]["target_timestamp_s"], points[1500][0])
        self.assertEqual(rows[0]["actual"], points[1500][1])


if __name__ == "__main__":
    unittest.main()
