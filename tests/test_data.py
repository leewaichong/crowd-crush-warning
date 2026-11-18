"""Unit fixtures for the observation parser. These are not crowd data."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from crowd_warning.data import ObservationDataError, load_observations, validate_observations


def row(**changes):
    value = {"timestamp_s": 1, "zone_id": "north", "density_per_m2": 2.5,
             "vx_mps": 0.1, "vy_mps": -0.2, "quality": 0.9, "calibrated": True}
    value.update(changes)
    return value


class ObservationDataTests(unittest.TestCase):
    def test_normalizes_and_preserves_quality_and_calibration(self):
        result = validate_observations([row(timestamp_s="1.5", quality="0.2", calibrated="false")])
        self.assertEqual(result[0]["timestamp_s"], 1.5)
        self.assertEqual(result[0]["quality"], 0.2)
        self.assertFalse(result[0]["calibrated"])

    def test_accepts_low_quality_and_uncalibrated_rows_for_downstream_abstention(self):
        result = validate_observations([row(quality=0, calibrated=False)])
        self.assertEqual(len(result), 1)

    def test_rejects_nonfinite_and_wrong_numeric_values(self):
        for value in (math.nan, math.inf, True, "wat"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ObservationDataError, "vx_mps"):
                    validate_observations([row(vx_mps=value)])

    def test_rejects_missing_extra_and_invalid_ranges(self):
        missing = row()
        del missing["quality"]
        cases = ([missing], [row(extra=1)], [row(quality=1.01)], [row(density_per_m2=-1)],
                 [row(timestamp_s=-1)], [row(zone_id=" ")], [row(calibrated=1)])
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ObservationDataError):
                validate_observations(rows)

    def test_rejects_duplicate_zone_timestamp_but_allows_other_zone(self):
        self.assertEqual(len(validate_observations([row(), row(zone_id="south")])), 2)
        with self.assertRaisesRegex(ObservationDataError, "duplicate"):
            validate_observations([row(), row()])

    def test_error_reports_row_accounting(self):
        with self.assertRaises(ObservationDataError) as caught:
            validate_observations([row(), row(quality=2), row(timestamp_s=3)])
        self.assertEqual((caught.exception.total_rows, caught.exception.accepted_rows,
                          caught.exception.rejected_rows), (2, 1, 1))

    def test_loads_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.csv"
            path.write_text("timestamp_s,zone_id,density_per_m2,vx_mps,vy_mps,quality,calibrated\n"
                            "1,north,2.5,0.1,-0.2,0.9,true\n", encoding="utf-8")
            self.assertEqual(load_observations(path), validate_observations([row()]))

    def test_loads_jsonl_and_reports_malformed_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            path.write_text(json.dumps(row()) + "\n", encoding="utf-8")
            self.assertEqual(len(load_observations(path)), 1)
            path.write_text(json.dumps(row()) + "\n{bad}\n", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "line 2") as caught:
                load_observations(path)
            self.assertEqual((caught.exception.total_rows, caught.exception.accepted_rows,
                              caught.exception.rejected_rows), (2, 0, 1))
            self.assertEqual((caught.exception.parsed_rows, caught.exception.validated_rows,
                              caught.exception.unprocessed_rows), (1, 0, 0))

    def test_csv_header_schema_checks_empty_wrong_and_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "empty"):
                load_observations(path)
            path.write_text("timestamp_s,zone_id\n", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "header"):
                load_observations(path)
            fields = "timestamp_s,zone_id,density_per_m2,vx_mps,vy_mps,quality,calibrated"
            path.write_text(fields + "\n", encoding="utf-8")
            # A header-only file with the exact schema is valid and contains no observations.
            self.assertEqual(load_observations(path), [])
            path.write_text(fields.replace("zone_id", "timestamp_s", 1) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "duplicate"):
                load_observations(path)
            path.write_text(fields + ",extra\n", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "unexpected"):
                load_observations(path)

    def test_csv_bad_record_counts_parsed_but_not_validated_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("timestamp_s,zone_id,density_per_m2,vx_mps,vy_mps,quality,calibrated\n"
                            "1,north,2.5,0.1,-0.2,0.9,true\n"
                            "2,south,3,0,0,0.8\n", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "too few") as caught:
                load_observations(path)
            self.assertEqual((caught.exception.parsed_rows, caught.exception.validated_rows,
                              caught.exception.rejected_rows, caught.exception.unprocessed_rows), (1, 0, 1, 0))

    def test_decode_errors_are_wrapped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            path.write_bytes(b"\xff")
            with self.assertRaisesRegex(ObservationDataError, "UTF-8"):
                load_observations(path)

    def test_rejects_unsupported_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.txt"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(ObservationDataError):
                load_observations(path)

    def test_rejects_bad_csv_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("timestamp_s,zone_id,density_per_m2,vx_mps,vy_mps,quality,calibrated\n"
                            "1,north,2.5,0.1,-0.2,0.9,true,extra\n", encoding="utf-8")
            with self.assertRaisesRegex(ObservationDataError, "too many"):
                load_observations(path)


if __name__ == "__main__":
    unittest.main()
