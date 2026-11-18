"""Analytic software checks; synthetic values are not crowd evaluation data."""

import hashlib
import json
import unittest

from crowd_warning.calibration import project_motion_video


def fixture():
    field = {"patch_size": 2, "cells": [{"cell_id": "0:0", "x_px": 0, "y_px": 0,
        "dx_px": 2, "dy_px": 0, "status": "unique_minimum", "at_search_boundary": False}]}
    digest = hashlib.sha256(json.dumps(field, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    result = {"input": {"sha256": "a" * 64}, "native_dimensions": {"width": 8, "height": 8},
        "scaled_dimensions": {"width": 4, "height": 4}, "pairs": [{"actual_dt_s": 2.0, "motion": field}]}
    quality = [{"field_sha256": digest, "status": "eligible_under_supplied_evidence", "eligible_cell_ids": ["0:0"]}]
    calibration = {"verified": True, "reference": "test plane", "source_sha256": "a" * 64,
        "native_width": 8, "native_height": 8,
        "image_to_plane_m": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    return result, quality, calibration


class CalibrationTests(unittest.TestCase):
    def test_unknown_evidence_abstains_without_metric_values(self):
        result, _, _ = fixture()
        out = project_motion_video(result)
        cell = out["pairs"][0]["motion"]["cells"][0]
        self.assertIsNone(cell["plane_vx_mps"])
        self.assertIsNone(cell["plane_vy_mps"])

    def test_known_scale_planar_translation(self):
        result, quality, cal = fixture()
        cal["image_to_plane_m"] = [[0.5, 0, 0], [0, 0.25, 0], [0, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertAlmostEqual(cell["plane_vx_mps"], 1.0)
        self.assertAlmostEqual(cell["plane_vy_mps"], 0.0)

    def test_resize_uses_pixel_center_mapping(self):
        result, quality, cal = fixture()
        cal["image_to_plane_m"] = [[0.01, 0, 0], [0, 0.01, 0], [0, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertAlmostEqual(cell["plane_vx_mps"], 0.02)

    def test_wrong_context_and_malformed_matrix_rejected(self):
        result, quality, cal = fixture()
        cal["source_sha256"] = "b" * 64
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)
        _, _, cal = fixture()
        cal["image_to_plane_m"] = [[1, 0], [0, 1]]
        with self.assertRaises(ValueError):
            project_motion_video(result, calibration=cal, quality_by_pair=quality)

    def test_projective_horizon_abstains_for_cell(self):
        result, quality, cal = fixture()
        cal["image_to_plane_m"] = [[1, 0, 0], [0, 1, 0], [-1 / 5.5, 0, 1]]
        cell = project_motion_video(result, calibration=cal, quality_by_pair=quality)["pairs"][0]["motion"]["cells"][0]
        self.assertIsNone(cell["plane_vx_mps"])
        self.assertIsNone(cell["plane_vy_mps"])


if __name__ == "__main__":
    unittest.main()
