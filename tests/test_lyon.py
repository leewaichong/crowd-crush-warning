"""Focused format and integrity checks for the Lyon TopView source reader."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from crowd_warning.lyon import DEFAULT_MEMBER, LyonDataError, read_lyon_topview, summarize_lyon_topview


TOPVIEW_HEADER = """# trajectory data of sequence TopView_1B
# recorded at 30 fps
# recording started at 2022-12-08T22:55:06+01:00
# z coordinate is the estimated height of person
# x_RGF and y_RGF are coordinates (in meters) in the RGF-93 Lambert-93 coordinate system (EPSG:2154)
# t/s is the time (number of seconds) using as reference date Friday, Dec. 9th at 20:00:00 (UTC+1)
# id frame x/m y/m z/m id_global t/s x_RGF y_RGF
"""


def row(trace=1, frame=0, time=-1.0, global_id=9001):
    return f"{trace} {frame} 1.25 -2.5 1.8 {global_id} {time} 842496.6 6520341.09\n"


class LyonTopViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / "fixture.zip"

    def write_archive(self, text, member=DEFAULT_MEMBER):
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            output.writestr(member, text.encode("utf-8"))

    def read_text(self, text):
        self.write_archive(text)
        return read_lyon_topview(self.archive)

    def test_preserves_negative_source_time_and_omits_global_id(self):
        table = self.read_text(TOPVIEW_HEADER + row(frame=10, time=-2.0, global_id=123456))

        self.assertEqual(table["metadata"]["sequence"], "TopView_1B")
        self.assertEqual(table["metadata"]["declared_source_frame_rate_fps"], 30)
        self.assertEqual(table["metadata"]["recording_started_at"], "2022-12-08T22:55:06+01:00")
        self.assertEqual(table["rows"][0]["source_t_s"], -2.0)
        self.assertEqual(table["rows"][0]["trace_id"], f"{DEFAULT_MEMBER}::1")
        self.assertNotIn("id_global", table["rows"][0])
        self.assertNotIn("123456", repr(table))
        summary = summarize_lyon_topview(table)
        self.assertNotIn("rows", summary)
        self.assertEqual(summary["source_temporal_range_s"], [-2.0, -2.0])

    def test_reports_frame_gap_as_trace_sampling_gap(self):
        table = self.read_text(
            TOPVIEW_HEADER + row(frame=10, time=-2.0) + row(frame=12, time=-1.933))
        summary = summarize_lyon_topview(table)

        self.assertEqual(summary["trace_sampling_gap_count"], 1)
        self.assertIn("not video decode-loss", summary["metadata"]["trace_sampling_gap_semantics"])
        self.assertEqual(summary["row_count"], 2)
        self.assertEqual(summary["trace_count"], 1)

    def test_rejects_malformed_and_nonfinite_rows(self):
        invalid_rows = (
            "1 0 1.25 -2.5 1.8 9001 -1 842496.6\n",
            row().replace("1.25", "nan"),
            row().replace("-2.5", "inf"),
        )
        for invalid in invalid_rows:
            with self.subTest(row=invalid.strip()):
                with self.assertRaises(LyonDataError):
                    self.read_text(TOPVIEW_HEADER + invalid)

    def test_rejects_duplicate_or_backward_per_trace_frames_and_times(self):
        invalid_pairs = (
            (row(frame=4, time=-2.0), row(frame=4, time=-1.9)),
            (row(frame=5, time=-2.0), row(frame=4, time=-1.9)),
            (row(frame=4, time=-2.0), row(frame=5, time=-2.0)),
            (row(frame=4, time=-2.0), row(frame=5, time=-2.1)),
        )
        for first, second in invalid_pairs:
            with self.subTest(second=second.strip()):
                with self.assertRaises(LyonDataError):
                    self.read_text(TOPVIEW_HEADER + first + second)

    def test_rejects_largeview_interpolated_schema(self):
        largeview = """# trajectory data of sequence TopView_1B
# recorded at 12 fps, extracted at 2 fps and then interpolated at 10 fps for final output
# recording started at 2022-12-09T20:13:35+01:00
# z coordinate is the estimated height of person
# x_RGF and y_RGF are coordinates (in meters) in the RGF-93 Lambert-93 coordinate system (EPSG:2154)
# t/s is the time (number of seconds) using as reference date Friday, Dec. 9th at 20:00:00 (UTC+1)
# id frame x/m y/m z/m t/s x_RGF y_RGF
1 0 1.0 2.0 1.8 813 842496 6520341
"""
        with self.assertRaisesRegex(LyonDataError, "frame rate"):
            self.read_text(largeview)


if __name__ == "__main__":
    unittest.main()
