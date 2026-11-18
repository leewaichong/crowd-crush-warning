"""Subprocess tests use tiny synthetic unit fixtures, never evaluation data."""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]

# Synthetic zone observations for command wiring and warmup checks only.
SYNTHETIC_ROWS = [
    {"timestamp_s": float(index), "zone_id": "test-zone",
     "density_per_m2": 0.4, "vx_mps": velocity, "vy_mps": 0.0,
     "quality": 1.0, "calibrated": True}
    for index, velocity in enumerate((0.0, 0.2, -0.1, 0.3, -0.2, 0.1))
]


class CliSubprocessTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="crowd-cli-test-")
        self.addCleanup(self.tempdir.cleanup)
        self.directory = Path(self.tempdir.name)
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(REPO_ROOT / "src")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "crowd_warning", *map(str, args)],
            cwd=REPO_ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_jsonl(self, name="observations.jsonl"):
        path = self.directory / name
        path.write_text("".join(json.dumps(row) + "\n" for row in SYNTHETIC_ROWS), encoding="utf-8")
        return path

    def write_csv(self, name="observations.csv"):
        path = self.directory / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SYNTHETIC_ROWS[0].keys())
            writer.writeheader()
            writer.writerows(SYNTHETIC_ROWS)
        return path

    def test_validate_accepts_jsonl_and_csv(self):
        for path in (self.write_jsonl(), self.write_csv()):
            with self.subTest(extension=path.suffix):
                completed = self.run_cli("validate", path)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(json.loads(completed.stdout), {
                    "row_count": len(SYNTHETIC_ROWS), "status": "valid",
                })

    def test_features_report_warmup_then_finite_variance(self):
        path = self.write_jsonl()
        completed = self.run_cli("features", path, "--window-s", "5")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = json.loads(completed.stdout)
        self.assertEqual(len(rows), len(SYNTHETIC_ROWS))
        self.assertIsNone(rows[0]["velocity_variance"])
        self.assertIsNone(rows[0]["pressure_proxy"])
        self.assertTrue(math.isfinite(rows[1]["velocity_variance"]))
        self.assertTrue(math.isfinite(rows[1]["pressure_proxy"]))

    def test_forecast_returns_finite_conditional_frequency_after_warmup(self):
        path = self.write_jsonl()
        # The threshold is only a test input used to exercise model output.
        completed = self.run_cli(
            "forecast", path, "--threshold", "999", "--horizon-s", "2", "--paths", "16", "--seed", "4",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["model_id"], "coupled-zone-first-passage-v1")
        self.assertIsInstance(result["probability"], (int, float))
        self.assertTrue(math.isfinite(result["probability"]))
        self.assertGreaterEqual(result["probability"], 0.0)
        self.assertLessEqual(result["probability"], 1.0)
        self.assertIn("conditional proxy crossing frequency", " ".join(result["caveats"]))

    def test_invalid_input_returns_nonzero_json_error(self):
        path = self.directory / "invalid.jsonl"
        path.write_text('{"timestamp_s": nope}\n', encoding="utf-8")
        completed = self.run_cli("validate", path)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        error = json.loads(completed.stderr)
        self.assertEqual(error["status"], "error")
        self.assertIn("invalid JSON", error["error"])


if __name__ == "__main__":
    unittest.main()
