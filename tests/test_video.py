"""Small mocked fixtures for local video timestamp and decode inspection."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from crowd_warning.video import inspect_video


class VideoInspectionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="crowd-video-test-")
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "fixture.mov"
        self.path.write_bytes(b"test fixture only")

    def inspect_with(self, pts, *, decode_code=0, probe_code=0, max_gap_s=None):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            executable = Path(argv[0]).name
            if argv[1] == "-version":
                return subprocess.CompletedProcess(argv, 0, f"{executable} version fixture\n", "")
            if executable == "ffprobe":
                if probe_code:
                    return subprocess.CompletedProcess(argv, probe_code, "", "probe fixture failure")
                return subprocess.CompletedProcess(argv, 0, json.dumps({
                    "streams": [{"codec_name": "h264", "width": 16, "height": 9,
                                 "time_base": "1/1000", "r_frame_rate": "25/1",
                                 "avg_frame_rate": "25/1", "nb_frames": "3"}],
                    "frames": [{"pts_time": value} for value in pts],
                }), "")
            return subprocess.CompletedProcess(
                argv, decode_code, "", "decode fixture failure" if decode_code else ""
            )

        with patch("crowd_warning.video.shutil.which", side_effect=lambda name: f"/tools/{name}"), \
             patch("crowd_warning.video.subprocess.run", side_effect=run):
            if probe_code or decode_code:
                with self.assertRaises(ValueError):
                    inspect_video(self.path, max_gap_s=max_gap_s)
                return None, calls
            return inspect_video(self.path, max_gap_s=max_gap_s), calls

    def test_preserves_actual_pts_and_decodes_only_video_to_null(self):
        result, calls = self.inspect_with(["12.25", "12.29", "12.33"])
        self.assertEqual([frame["pts_time"] for frame in result["frames"]], [12.25, 12.29, 12.33])
        self.assertEqual(result["timing_status"], "ok")
        self.assertEqual(result["frame_count"], 3)
        self.assertAlmostEqual(result["observed_deltas_s"][0]["delta_s"], 0.04)
        decode = next(call for call in calls if Path(call[0]).name == "ffmpeg" and call[1] != "-version")
        self.assertIn("0:v:0", decode)
        self.assertEqual(decode[-3:], ["-f", "null", "-"])
        self.assertIn("-an", decode)

    def test_bad_pts_abstain_and_gap_is_reported_when_configured(self):
        for pts, missing, duplicate, nonmonotonic in (
            (["1", None, "2"], 1, 0, 0),
            (["1", "1", "2"], 0, 1, 0),
            (["2", "1", "3"], 0, 0, 1),
        ):
            with self.subTest(pts=pts):
                result, _ = self.inspect_with(pts)
                self.assertEqual(result["timing_status"], "abstain")
                self.assertEqual(result["missing_pts_count"], missing)
                self.assertEqual(result["duplicate_pts_count"], duplicate)
                self.assertEqual(result["nonmonotonic_pts_count"], nonmonotonic)

        result, _ = self.inspect_with(["0", "0.5", "3"], max_gap_s=1.0)
        self.assertEqual(result["timing_status"], "abstain")
        self.assertEqual(result["gap_assessment"]["exceeding_intervals"][0]["delta_s"], 2.5)

    def test_probe_and_decode_failures_are_not_success(self):
        self.inspect_with(["0"], probe_code=1)
        self.inspect_with(["0"], decode_code=1)

    def test_cli_emits_strict_json_and_returns_success_for_completed_abstention(self):
        from crowd_warning.cli import main

        fixture = {"timing_status": "abstain", "frames": [{"pts_time": None}]}
        with patch("crowd_warning.video.inspect_video", return_value=fixture):
            import contextlib
            import io

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["inspect-video", str(self.path)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue()), fixture)


if __name__ == "__main__":
    unittest.main()
