import json
import re
import unittest

from crowd_warning.replay import render_density_replay


def table(points=None):
    return {
        "source_format": "zenodo-density-time-v1",
        "time_reference": "seconds_relative_to_festival_opening",
        "units": {"time": "s", "density": "m^-2"}, "row_count": 5,
        "series": [
            {"year": 2022, "points": points or [[-2, 0.1], [-1, 0.2], [0, 0.5], [1, 0.2], [2, 0.1]], "missing_count": 1},
            {"year": 2023, "points": [[-1, 0.3], [1, 0.4]], "missing_count": 3},
        ],
    }


class ReplayTests(unittest.TestCase):
    def test_controls_units_credit_and_missingness(self):
        html = render_density_replay(table())
        self.assertIn('<select id="year">', html)
        self.assertIn('value="all"', html)
        self.assertIn('id="time" type="range"', html)
        self.assertIn('Time relative to festival opening (s)', html)
        self.assertIn('Spatially averaged density (m^-2)', html)
        self.assertIn('Missing trailing padding rows', html)
        self.assertIn('Francois Gu, Benjamin Guiselin, and Denis Bartolo', html)
        self.assertIn('10.5281/zenodo.14050598', html)
        self.assertIn('CC BY 4.0', html)
        self.assertIn('10.1038/s41586-024-08514-6', html)
        self.assertIn('no forecast', html)
        self.assertNotRegex(html, r'<(?:script|link|img)[^>]+(?:src|href)=\"https?://')

    def test_cursor_uses_prior_display_sample_and_reports_time_age_or_coverage(self):
        html = render_density_replay(table())
        self.assertIn("p[0]<=t", html)
        self.assertIn("age '+(t-best[0])+' s", html)
        self.assertIn("outside actual coverage", html)
        self.assertIn("class:'cursor-line'", html)
        self.assertIn("plot.querySelector('.cursor-line')?.remove()", html)
        self.assertNotIn("no observation at this time", html)

    def test_axis_has_numeric_tick_labels_and_year_color_legend(self):
        html = render_density_replay(table())
        self.assertIn("class:'tick'", html)
        self.assertIn('id="legend"', html)
        self.assertIn("stroke:s.color", html)
        self.assertIn("String(s.year)", html)

    def test_escapes_embedded_script_delimiters_and_year_markup(self):
        t = table()
        t["series"][0]["year"] = '</option><script>bad()</script>'
        html = render_density_replay(t)
        self.assertNotIn('</option><script>bad()', html)
        self.assertIn('\\u003c/script\\u003e', html)
        self.assertIn('textContent', html)
        self.assertNotIn('innerHTML=', html.replace('document.getElementById(\'source\').innerHTML=source;', ''))

    def test_trailing_missing_pairs_are_omitted_and_count_is_reported(self):
        t = table([[-2, .1], [0, .4], [None, None]])
        html = render_density_replay(t)
        match = re.search(r'const data=(.*?);\nconst source=', html, re.S)
        data = json.loads(match.group(1))
        self.assertEqual(data[0]["missing_count"], 1)
        self.assertEqual(data[0]["observation_count"], 2)

    def test_rejects_internal_and_partial_missing_pairs(self):
        for points in (
            [[-2, .1], [None, None], [0, .4]],
            [[-2, .1], [None, .4]],
            [[-2, .1], [0, None]],
        ):
            with self.subTest(points=points), self.assertRaises(ValueError):
                render_density_replay(table(points))

    def test_rejects_nonfinite_negative_or_nonmonotonic_source_points(self):
        for points in (
            [[0, float('nan')]], [[0, float('inf')]], [[0, -0.1]],
            [[1, .2], [1, .3]], [[1, .2], [0, .3]],
        ):
            with self.subTest(points=points), self.assertRaises(ValueError):
                render_density_replay(table(points))

    def test_decimation_is_bounded_and_retains_extrema(self):
        points = [[i, 1000 if i == 2500 else (0 if i == 4000 else i % 10)] for i in range(5000)]
        html = render_density_replay(table(points))
        match = re.search(r'const data=(.*?);\nconst source=', html, re.S)
        data = json.loads(match.group(1))[0]["points"]
        self.assertLessEqual(len(data), 2000)
        self.assertIn([2500, 1000], data)
        self.assertIn([4000, 0], data)
        self.assertIn('Display decimation is active', html)

    def test_rejects_other_contract(self):
        t = table()
        t["units"]["density"] = "kg/m2"
        with self.assertRaises(ValueError):
            render_density_replay(t)


if __name__ == "__main__":
    unittest.main()
