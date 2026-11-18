"""Analytic software checks; synthetic values are not crowd evaluation data."""

import hashlib
import json
import unittest

from crowd_warning.calibration import project_motion_video


def fixture():
    field = {"patch_size": 2, "units": "pixels_per_pair", "cells": [{"cell_id": "0:0", "x_px": 0, "y_px": 0,
        "dx_px": 2, "dy_px": 0, "status": "unique_minimum", "at_search_boundary": False}]}
    digest = hashlib.sha256(json.dumps(field, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    result = {"input": {"sha256": "a" * 64}, "native_dimensions": {"width": 8, "height": 8},
        "scaled_dimensions": {"width": 4, "height": 4},
        "transform": {"method": "aspect-preserving resize to explicit even dimensions", "scale_x": 0.5, "scale_y": 0.5},
        "pairs": [{"actual_dt_s": 2.0, "motion": field}]}
    quality = [{"field_sha256": digest, "status": "eligible_under_supplied_evidence", "eligible_cell_ids": ["0:0"]}]
    calibration = {"verified": True, "reference": "test plane", "source_sha256": "a" * 64,
        "native_width": 8, "native_height": 8,
        "image_to_plane_m": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    return result, quality, calibration


class CalibrationTests(unittest.TestCase):
    def test_unknown_evidence_abstains_without_metric_values(self):
        result, quality, cal = fixture()
        out = project_motion_video(result)
        cell = out["pairs"][0]["motion"]["cells"][0]
        self.assertIsNone(cell["plane_vx_mps"])
        self.assertIsNone(cell["plane_vy_mps"])
        self.assertEqual(out["projection_status"], "abstain")
        cal["verified"] = False
        out = project_motion_video(result, calibration=cal, quality_by_pair=quality)
        self.assertEqual(out["projection_status"], "abstain")
        self.assertEqual(out["pairs"][0]["motion"]["cells"][0]["projection_abstention_reason"], "calibration_unverified")
        _, quality, cal = fixture()
        quality[0]["status"] = "abstain"
        quality[0]["evidence_references"] = ["visibility log"]
        out = project_motion_video(result, calibration=cal, quality_by_pair=quality)
        self.assertIsNone(out["pairs"][0]["motion"]["cells"][0]["plane_vx_mps"])
        self.assertEqual(out["pairs"][0]["motion"]["cells"][0]["projection_abstention_reason"], "quality_abstain")
        self.assertEqual(out["pairs"][0]["quality_reference"], ["visibility log"])

    def test_known_scale_planar_translation(self):
        result, quality, cal = fixture()
        cal["image_to_plane_m"] = [[0.5, 0, 0], [0, 0.25, 0], [0, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertAlmostEqual(cell["plane_vx_mps"], 1.0)
        self.assertAlmostEqual(cell["plane_vy_mps"], 0.0)
        out = project_motion_video(result, calibration=cal, quality_by_pair=quality)
        self.assertEqual(out["pairs"][0]["motion"]["units"], "pixels_per_pair")
        self.assertIn("m_per_s", out["projection_units"])
        cal["image_to_plane_m"] = [[v * 1e-20 for v in row] for row in cal["image_to_plane_m"]]
        self.assertAlmostEqual(project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]["plane_vx_mps"], 1.0)

    def test_resize_uses_pixel_center_mapping(self):
        result, quality, cal = fixture()
        # Perspective term makes native endpoint coordinates depend on the
        # half-pixel center correction. Correct velocity is 800/713 m/s.
        cal["image_to_plane_m"] = [[1, 0, 0], [0, 1, 0], [0.1, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertAlmostEqual(cell["plane_vx_mps"], 800 / 713)

    def test_wrong_context_and_malformed_matrix_rejected(self):
        result, quality, cal = fixture()
        cal["source_sha256"] = "b" * 64
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)
        _, _, cal = fixture()
        cal["image_to_plane_m"] = [[1, 0], [0, 1]]
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)
        for bad in (True, "1"):
            _, _, cal = fixture()
            cal["image_to_plane_m"][0][0] = bad
            with self.assertRaises(ValueError):
                project_motion_video(result, calibration=cal, quality_by_pair=quality)
        _, quality, cal = fixture()
        quality[0]["status"] = "eligible_typo"
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)
        _, quality, cal = fixture()
        quality[0]["eligible_cell_ids"] = ["0:0", "0:0"]
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)
        _, quality, cal = fixture()
        quality[0]["eligible_cell_ids"] = ["unknown"]
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)
        _, quality, cal = fixture()
        result["pairs"][0]["motion"]["cells"].append(dict(result["pairs"][0]["motion"]["cells"][0]))
        quality[0]["field_sha256"] = hashlib.sha256(json.dumps(result["pairs"][0]["motion"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)

    def test_projective_horizon_abstains_for_cell(self):
        result, quality, cal = fixture()
        cal["image_to_plane_m"] = [[1, 0, 0], [0, 1, 0], [-1 / 5.5, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertIsNone(cell["plane_vx_mps"])
        self.assertIsNone(cell["plane_vy_mps"])
        self.assertEqual(cell["projection_abstention_reason"], "projection_horizon")
        # Finite endpoints on opposite sides still cross the projective horizon.
        cal["image_to_plane_m"] = [[1, 0, 0], [0, 1, 0], [-1 / 3.5, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertEqual(cell["projection_abstention_reason"], "projection_horizon")


if __name__ == "__main__":
    unittest.main()
