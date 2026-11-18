"""Software fixtures for the temporal density source parser."""

import tempfile
import unittest
from pathlib import Path

from crowd_warning.density import read_density_table, summarize_density_table


HEADER = (
    "Time 2022 (s)\tDensity 2022 (m^-2)\t"
    "Time 2023 (s)\tDensity 2023 (m^-2)\t"
    "Time 2024 (s)\tDensity 2024 (m^-2)"
)
DESCRIPTION = (
    "Density averaged over space and plotted against time for Pamplona 2022, 2023 and 2024. "
    "Time is negative, representing the time to the opening of the festival. "
    "Delimiter is a tab character."
)


class DensityReaderTests(unittest.TestCase):
    def parse(self, rows, header=HEADER):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.tsv"
            path.write_text(DESCRIPTION + "\n" + header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
            return read_density_table(path)

    def assert_rejected(self, rows, header=HEADER):
        with self.assertRaises(ValueError):
            self.parse(rows, header)

    def test_negative_times_and_independent_year_lengths(self):
        table = self.parse([
            "-2\t1.5\t-3\t2\t-4\t3",
            "-1\t2.5\tnan\tnan\t-3\t4",
            "nan\tnan\tnan\tnan\t-2\t5",
        ])
        self.assertEqual(table["row_count"], 3)
        self.assertEqual([s["year"] for s in table["series"]], [2022, 2023, 2024])
        self.assertEqual(table["series"][0]["points"], [[-2.0, 1.5], [-1.0, 2.5]])
        self.assertEqual([s["missing_count"] for s in table["series"]], [1, 2, 0])

    def test_summary_counts_and_ranges(self):
        table = self.parse(["-2\t1.5\t-3\t2\t-4\t3", "-1\t2.5\tnan\tnan\t-3\t4"])
        summary = summarize_density_table(table)
        self.assertEqual(summary["row_count"], 2)
        self.assertNotIn("points", summary["series"][0])
        self.assertEqual(summary["series"][0], {
            "year": 2022, "observation_count": 2, "missing_count": 0,
            "start_timestamp_s": -2.0, "end_timestamp_s": -1.0,
            "min_density_per_m2": 1.5, "max_density_per_m2": 2.5,
        })
        self.assertEqual(summary["series"][1]["missing_count"], 1)

    def test_rejects_partial_missing_values(self):
        for pair in ("nan\t1", "1\tnan"):
            with self.subTest(pair=pair):
                self.assert_rejected([pair + "\t0\t1\t0\t1"])

    def test_rejects_internal_missing_pairs(self):
        self.assert_rejected([
            "0\t1\t0\t1\t0\t1",
            "nan\tnan\t1\t1\t1\t1",
            "2\t1\t2\t1\t2\t1",
        ])

    def test_rejects_duplicate_and_nonmonotonic_times(self):
        for second in ("0\t2\t1\t1\t1\t1", "-1\t2\t1\t1\t1\t1"):
            with self.subTest(second=second):
                self.assert_rejected(["0\t1\t0\t1\t0\t1", second])

    def test_rejects_wrong_units_year_order_or_schema(self):
        for header in (
            HEADER.replace("m^-2", "m^-1"),
            HEADER.replace("Time 2022", "Time 2021"),
            HEADER.replace("\t", ","),
        ):
            with self.subTest(header=header):
                self.assert_rejected(["0\t1\t0\t1\t0\t1"], header)
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "fixture.tsv"
                path.write_text("wrong description\n" + HEADER + "\n", encoding="utf-8")
                read_density_table(path)

    def test_rejects_malformed_rows_and_numbers(self):
        for row in ("0\t1", "0\t1\t0\t1\t0\t1\textra", "x\t1\t0\t1\t0\t1"):
            with self.subTest(row=row):
                self.assert_rejected([row])

    def test_rejects_infinities_and_negative_density(self):
        for row in ("inf\t1\t0\t1\t0\t1", "0\t-inf\t0\t1\t0\t1", "0\t-0.1\t0\t1\t0\t1"):
            with self.subTest(row=row):
                self.assert_rejected([row])


if __name__ == "__main__":
    unittest.main()
