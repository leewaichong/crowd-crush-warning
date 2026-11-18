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
        rows = forecast_year(points, {"intercept": 0.0, "phi": 0.5, "residual_variance": 1.0}, 2024)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["origin_timestamp_s"], row["cutoff_timestamp_s"])
            self.assertAlmostEqual(row["target_timestamp_s"] - row["origin_timestamp_s"], 30.0, places=6)
            self.assertAlmostEqual(row["target_timestamp_s"] * 25, round(row["target_timestamp_s"] * 25), places=6)
            self.assertAlmostEqual(row["actual"], row["actual_timestamp_s"] / 0.04, places=6)


if __name__ == "__main__":
    unittest.main()
