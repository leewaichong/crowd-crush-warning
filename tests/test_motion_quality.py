"""Software-only fixtures. These do not evaluate crowd motion quality."""

import unittest

from crowd_warning.motion_quality import assess_motion_quality


class MotionQualityTests(unittest.TestCase):
    def test_missing_evidence_abstains(self):
        field = {"cells": [{"cell_id": "0:0", "dx_px": 1, "dy_px": 0,
                            "status": "unique_minimum", "at_search_boundary": False}]}
        result = assess_motion_quality(field)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["eligible_cell_ids"], [])
        self.assertEqual(result["counts"]["eligible_cells"], 1)

    def test_moving_camera_abstains(self):
        field = {"cells": [{"cell_id": "a", "dx_px": 1, "dy_px": 2,
                            "status": "unique_minimum", "at_search_boundary": False}]}
        result = assess_motion_quality(field, camera_stable=False, camera_reference="camera note",
                                       visible_cell_ids=["a"], visibility_reference="visibility note")
        self.assertEqual(result["status"], "abstain")
        self.assertIn("camera_stability_evidence_missing_or_negative", result["abstention_reasons"])

    def test_supplied_references_keep_only_eligible_cells_and_coverage(self):
        field = {"cells": [
            {"cell_id": "ok", "dx_px": 1, "dy_px": -2, "status": "unique_minimum", "at_search_boundary": False},
            {"cell_id": "ambiguous", "dx_px": None, "dy_px": None, "status": "ambiguous", "at_search_boundary": False},
            {"cell_id": "edge", "dx_px": 2, "dy_px": 3, "status": "unique_minimum", "at_search_boundary": True},
            {"cell_id": "hidden", "dx_px": 0, "dy_px": 0, "status": "unique_minimum", "at_search_boundary": False},
        ]}
        result = assess_motion_quality(field, camera_stable=True, camera_reference="caller camera record",
                                       visible_cell_ids=["ok", "ambiguous", "edge"],
                                       visibility_reference="caller visibility record")
        self.assertEqual(result["status"], "eligible_under_supplied_evidence")
        self.assertEqual(result["eligible_cell_ids"], ["ok"])
        self.assertEqual(result["counts"], {"total_cells": 4, "eligible_cells": 1,
                                             "excluded_cells": 3, "eligible_fraction": 0.25})
        self.assertEqual(result["reasons"], {"ambiguous_or_nonunique": 1, "not_nominated_visible": 1,
                                              "search_boundary": 1})
        self.assertIn("not independently verified", result["supplied_evidence"]["scope"])

    def test_malformed_or_mismatched_inputs_raise(self):
        base = {"cells": [{"cell_id": "a", "dx_px": 1, "dy_px": 1,
                            "status": "unique_minimum", "at_search_boundary": False}]}
        with self.assertRaisesRegex(ValueError, "duplicate cell_id"):
            assess_motion_quality({"cells": [base["cells"][0], base["cells"][0]]})
        with self.assertRaisesRegex(ValueError, "unknown visible cell ID"):
            assess_motion_quality(base, visible_cell_ids=["missing"])
        malformed = {"cells": [{**base["cells"][0], "at_search_boundary": "false"}]}
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            assess_motion_quality(malformed)
        with self.assertRaisesRegex(ValueError, "camera_stable"):
            assess_motion_quality(base, camera_stable=1)


if __name__ == "__main__":
    unittest.main()
