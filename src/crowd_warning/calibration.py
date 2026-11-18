"""Conditional reference-plane projection of image-pattern motion."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any


def project_motion_video(
    result: Mapping[str, Any], *, calibration: Mapping[str, Any] | None = None,
    quality_by_pair: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project eligible pixel displacements onto a caller-supplied plane.

    Values describe conditional image-pattern velocity on the supplied plane,
    not independently established pedestrian motion.
    """
    if not isinstance(result, Mapping):
        raise ValueError("result must be a mapping")
    pairs = result.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("result pairs must be a list")
    output = {key: value for key, value in result.items()}
    output["projection_status"] = "abstain"
    output["projection_scope"] = "conditional reference-plane image-pattern motion"
    output["calibration_reference"] = None
    output["pairs"] = []
    if calibration is None or quality_by_pair is None:
        output["projection_abstention_reason"] = "calibration or quality evidence not supplied"
        for pair in pairs:
            output["pairs"].append(_abstain_pair(pair))
        return output

    matrix = _validate_calibration(result, calibration)
    if not isinstance(quality_by_pair, list) or len(quality_by_pair) != len(pairs):
        raise ValueError("quality_by_pair must align exactly with result pairs")
    output["calibration_reference"] = calibration["reference"]
    any_projected = False
    for pair, quality in zip(pairs, quality_by_pair):
        projected = _project_pair(result, pair, quality, matrix)
        any_projected |= any("plane_vx_mps" in c for c in projected["motion"].get("cells", []))
        output["pairs"].append(projected)
    output["projection_status"] = "conditional_projection" if any_projected else "abstain"
    return output


def _validate_calibration(result: Mapping[str, Any], calibration: Mapping[str, Any]) -> list[list[float]]:
    if not isinstance(calibration, Mapping):
        raise ValueError("calibration must be a mapping")
    ref = calibration.get("reference")
    if calibration.get("verified") is not True or not isinstance(ref, str) or not ref.strip():
        raise ValueError("calibration must be explicitly verified with a reference")
    source = result.get("input", {}).get("sha256") if isinstance(result.get("input"), Mapping) else None
    dims = result.get("native_dimensions")
    if calibration.get("source_sha256") != source or not isinstance(source, str):
        raise ValueError("calibration source SHA-256 does not match result")
    if not isinstance(dims, Mapping):
        raise ValueError("result native dimensions are missing")
    for key, dim in (("native_width", "width"), ("native_height", "height")):
        value = calibration.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value != dims.get(dim):
            raise ValueError(f"calibration {key} does not match result")
    raw = calibration.get("image_to_plane_m")
    if not isinstance(raw, (list, tuple)) or len(raw) != 3 or any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in raw):
        raise ValueError("image_to_plane_m must be a 3 by 3 matrix")
    try:
        matrix = [[float(v) for v in row] for row in raw]
    except (TypeError, ValueError, OverflowError):
        raise ValueError("homography values must be finite numbers") from None
    if any(not math.isfinite(v) for row in matrix for v in row):
        raise ValueError("homography values must be finite numbers")
    det = (matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
           - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
           + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0]))
    if not math.isfinite(det) or abs(det) <= 1e-15:
        raise ValueError("homography must be nonsingular")
    return matrix


def _project_pair(result: Mapping[str, Any], pair: Mapping[str, Any], quality: Mapping[str, Any], matrix: list[list[float]]) -> dict[str, Any]:
    if not isinstance(pair, Mapping) or not isinstance(pair.get("motion"), Mapping):
        raise ValueError("each pair must contain a motion field")
    field = pair["motion"]
    digest = hashlib.sha256(json.dumps(field, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if not isinstance(quality, Mapping):
        raise ValueError("each quality assessment must be a mapping")
    eligible = quality.get("eligible_cell_ids")
    if quality.get("field_sha256") != digest or not isinstance(eligible, list) or any(not isinstance(v, str) for v in eligible):
        raise ValueError("quality evidence does not match motion field")
    if quality.get("status") != "eligible_under_supplied_evidence":
        eligible = []
    dt = pair.get("actual_dt_s")
    valid_dt = isinstance(dt, (int, float)) and not isinstance(dt, bool) and math.isfinite(dt) and dt > 0
    native = result["native_dimensions"]
    scaled = result.get("scaled_dimensions")
    if not isinstance(scaled, Mapping) or not all(isinstance(scaled.get(k), int) and scaled[k] > 0 for k in ("width", "height")):
        raise ValueError("scaled dimensions are missing or invalid")
    sx, sy = scaled["width"] / native["width"], scaled["height"] / native["height"]
    patch = field.get("patch_size")
    if isinstance(patch, bool) or not isinstance(patch, int) or patch <= 0:
        raise ValueError("motion patch_size is invalid")
    new_field = dict(field)
    cells = []
    for cell in field.get("cells", []):
        item = dict(cell)
        item["plane_vx_mps"] = None
        item["plane_vy_mps"] = None
        if item.get("cell_id") in eligible and valid_dt and item.get("status") == "unique_minimum" and not item.get("at_search_boundary"):
            try:
                x = (float(item["x_px"]) + (patch - 1) / 2 + 0.5) / sx - 0.5
                y = (float(item["y_px"]) + (patch - 1) / 2 + 0.5) / sy - 0.5
                dx, dy = float(item["dx_px"]) / sx, float(item["dy_px"]) / sy
                start = _map(matrix, x, y)
                end = _map(matrix, x + dx, y + dy)
                if start is not None and end is not None:
                    item["plane_vx_mps"] = (end[0] - start[0]) / dt
                    item["plane_vy_mps"] = (end[1] - start[1]) / dt
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        cells.append(item)
    new_field["cells"] = cells
    new_field["units"] = "conditional_reference_plane_image_pattern_m_per_s"
    return {**pair, "motion": new_field, "projection_status": "conditional_projection" if any(c["plane_vx_mps"] is not None for c in cells) else "abstain"}


def _map(matrix: list[list[float]], x: float, y: float) -> tuple[float, float] | None:
    p = [x, y, 1.0]
    q = [sum(matrix[i][j] * p[j] for j in range(3)) for i in range(3)]
    if not all(math.isfinite(v) for v in q) or abs(q[2]) <= 1e-12:
        return None
    xy = q[0] / q[2], q[1] / q[2]
    return xy if all(math.isfinite(v) for v in xy) else None


def _abstain_pair(pair: Any) -> Any:
    if not isinstance(pair, Mapping) or not isinstance(pair.get("motion"), Mapping):
        return pair
    field = dict(pair["motion"])
    field["cells"] = [{**cell, "plane_vx_mps": None, "plane_vy_mps": None} for cell in field.get("cells", [])]
    field["units"] = "conditional_reference_plane_image_pattern_m_per_s"
    return {**pair, "motion": field, "projection_status": "abstain"}
