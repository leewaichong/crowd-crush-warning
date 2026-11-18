"""Subprocess tests use tiny synthetic unit fixtures, never evaluation data."""

from __future__ import annotations

import csv
import hashlib
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

    def write_manifest(self, *, wrong_digest=False):
        source = self.directory / "source.dat"
        source.write_bytes(b"labelled unit-test fixture\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if wrong_digest:
            digest = "0" * 64
        manifest = {
            "manifest_version": 1,
            "source_record": {
                "doi": "10.0000/unit-test",
                "url": "https://example.invalid/unit-test",
                "version": "fixture-v1",
                "license": {"id": "CC-BY-4.0", "scope": "fixture"},
            },
            "files": [{
                "path": source.name,
                "url": "https://example.invalid/unit-test/source.dat",
                "size_bytes": source.stat().st_size,
                "sha256": digest,
                "source_checksum": "md5:" + hashlib.md5(source.read_bytes()).hexdigest(),
                "retrieved_at": "2026-11-18T00:00:00Z",
                "purpose": "documentation",
                "status": "inspected",
            }],
        }
        path = self.directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def write_density_table(self):
        path = self.directory / "density.tsv"
        path.write_text(
            "Time 2022 (s)\tDensity 2022 (m^-2)\tTime 2023 (s)\tDensity 2023 (m^-2)\t"
            "Time 2024 (s)\tDensity 2024 (m^-2)\n"
            "\n"
            "-2\t0.1\t-3\t0.2\t-1\t0.3\n"
            "\n"
            "-1\t0.2\t-2\t0.3\t0\t0.4\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def strict_json(text):
        def reject_constant(value):
            raise ValueError(f"nonstandard JSON constant: {value}")

        return json.loads(text, parse_constant=reject_constant)

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

    def test_baselines_uses_real_features_and_baseline_module(self):
        path = self.write_jsonl()
        completed = self.run_cli(
            "baselines", path,
            "--density-threshold", "2",
            "--proxy-threshold", "2",
            "--change-threshold", "2",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        rows = self.strict_json(completed.stdout)
        self.assertEqual(len(rows), len(SYNTHETIC_ROWS))
        self.assertEqual(rows[0]["forecast_origin_s"], rows[0]["timestamp_s"])
        self.assertEqual(rows[0]["input_cutoff_s"], rows[0]["timestamp_s"])
        self.assertEqual(set(rows[0]["arms"]), {"density", "persistence", "change_point"})

    def test_verify_source_reports_success_from_real_source_module(self):
        manifest = self.write_manifest()
        completed = self.run_cli("verify-source", manifest)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        result = self.strict_json(completed.stdout)
        self.assertIs(result["integrity_verified"], True)
        self.assertEqual(result["files_checked"], 1)

    def test_verify_source_integrity_failure_is_json_nonzero_without_traceback(self):
        manifest = self.write_manifest(wrong_digest=True)
        completed = self.run_cli("verify-source", manifest)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        result = self.strict_json(completed.stdout)
        self.assertIs(result["integrity_verified"], False)
        self.assertTrue(result["errors"])
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_inspect_density_uses_real_density_module(self):
        path = self.write_density_table()
        completed = self.run_cli("inspect-density", path)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        result = self.strict_json(completed.stdout)
        self.assertEqual(result["source_format"], "zenodo-density-time-v1")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["time_reference"], "seconds_relative_to_festival_opening")
        self.assertEqual([series["year"] for series in result["series"]], [2022, 2023, 2024])
        self.assertTrue(all(series["observation_count"] == 2 for series in result["series"]))

    def test_replay_density_creates_html_and_reports_input_digest(self):
        path = self.write_density_table()
        output = self.directory / "density-replay.html"
        completed = self.run_cli("replay-density", path, "--output", output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        result = self.strict_json(completed.stdout)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["output"], str(output.resolve()))
        self.assertEqual(result["input_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("<!doctype html>", output.read_text(encoding="utf-8").lower())

    def test_replay_density_refuses_existing_output_without_changing_it(self):
        path = self.write_density_table()
        output = self.directory / "existing.html"
        original = b"keep this file\n"
        output.write_bytes(original)
        completed = self.run_cli("replay-density", path, "--output", output)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertNotIn("Traceback", completed.stderr)
        error = self.strict_json(completed.stderr)
        self.assertEqual(error["status"], "error")
        self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
