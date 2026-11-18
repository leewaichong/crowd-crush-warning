"""Focused software fixtures for image-space motion diagnostics."""

import unittest

import numpy as np

from crowd_warning.motion import estimate_motion_pair, summarize_camera_residual


class MotionTests(unittest.TestCase):
    def test_textured_integer_translation(self):
        # Synthetic texture checks displacement bookkeeping, not motion accuracy.
        rng = np.random.default_rng(17)
        previous = rng.integers(0, 256, size=(32, 32), dtype=np.uint8)
        current = np.roll(previous, shift=(-1, 1), axis=(0, 1))
        result = estimate_motion_pair(previous, current, dt_s=0.1, patch_size=8, search_radius=2)

        self.assertTrue(result["cells"])
        for cell in result["cells"]:
            self.assertEqual((cell["dx_px"], cell["dy_px"]), (1, -1))
            self.assertEqual(cell["status"], "unique_minimum")
        self.assertEqual(result["method"], "integer_ssd_blocks_v1")
        self.assertEqual(result["camera_motion_status"], "unknown")
        self.assertEqual(result["physical_calibration"], "unknown")

    def test_uniform_ambiguity_and_caller_background(self):
        uniform = np.zeros((24, 24), dtype=np.uint8)
        result = estimate_motion_pair(uniform, uniform, dt_s=1, patch_size=8, search_radius=2)
        self.assertTrue(all(cell["status"] == "ambiguous" for cell in result["cells"]))
        self.assertIsNone(result["cells"][0]["dx_px"])
        self.assertEqual(summarize_camera_residual(result)["camera_motion_status"], "unknown")
        self.assertIsNone(summarize_camera_residual(result)["residuals_px"])

        field = {"cells": [
            {"cell_id": "bg", "dx_px": 2, "dy_px": -1, "status": "unique_minimum", "at_search_boundary": False},
            {"cell_id": "crowd", "dx_px": 9, "dy_px": 8, "status": "unique_minimum", "at_search_boundary": False},
        ]}
        summary = summarize_camera_residual(field, background_cell_ids=["bg"])
        self.assertEqual(summary["camera_motion_status"], "caller_supplied_background")
        self.assertEqual(summary["translation_px"], {"dx_px": 2.0, "dy_px": -1.0})
        self.assertEqual(summary["background_cell_ids"], ["bg"])

    def test_invalid_frames_and_dt(self):
        with self.assertRaises(ValueError):
            estimate_motion_pair(np.zeros((8, 8)), np.zeros((8, 7)), dt_s=1)
        with self.assertRaises(ValueError):
            estimate_motion_pair(np.zeros((8, 8)), np.zeros((8, 8)), dt_s=float("nan"))
        with self.assertRaises(ValueError):
            estimate_motion_pair(np.zeros((8, 8)), np.zeros((8, 8)), dt_s=0)


if __name__ == "__main__":
    unittest.main()
