"""Conditional reference-plane projection of image-pattern motion."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any


_QUALITY_STATES = {"eligible_under_supplied_evidence", "abstain"}


def project_motion_video(
    result: Mapping[str, Any], *, calibration: Mapping[str, Any] | None = None,
    quality_by_pair: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project eligible pixel displacements onto a caller-supplied plane."""
    if not isinstance(result, Mapping):
        raise ValueError("result must be a mapping")
    pairs = result.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("result pairs must be a list")
    shape = _validate_result_shape(result)
    output = {**result, "pairs": [], "projection_status": "abstain",
              "projection_scope": "conditional reference-plane image-pattern motion",
              "projection_units": "conditional_reference_plane_image_pattern_m_per_s",
              "calibration_reference": None,
              "calibration_source_sha256": None,
              "calibration_reference_independently_verified": False,
              "quality_supplied_evidence": []}
    # An absent or explicitly unverified calibration is missing evidence.
    if isinstance(calibration, Mapping) and "verified" in calibration and not isinstance(calibration["verified"], bool):
        raise ValueError("calibration verified flag must be boolean")
    if calibration is None or (isinstance(calibration, Mapping) and calibration.get("verified") is not True):
        reason = "calibration_not_supplied" if calibration is None else "calibration_unverified"
        output["projection_abstention_reason"] = reason
        output["quality_supplied_evidence"] = _aligned_supplied_evidence(quality_by_pair, len(pairs))
        output["pairs"] = [_abstain_pair(p, reason, quality_by_pair[i] if isinstance(quality_by_pair, list) and i < len(quality_by_pair) else None)
                           for i, p in enumerate(pairs)]
        return output
    if not isinstance(calibration, Mapping):
        raise ValueError("calibration must be a mapping")
    matrix = _validate_calibration(result, calibration, shape)
    if quality_by_pair is None:
        output["projection_abstention_reason"] = "quality_not_supplied"
        output["calibration_reference"] = calibration["reference"]
        output["calibration_source_sha256"] = calibration["source_sha256"]
        output["pairs"] = [_abstain_pair(p, "quality_not_supplied") for p in pairs]
        return output
    if not isinstance(quality_by_pair, list) or len(quality_by_pair) != len(pairs):
        raise ValueError("quality_by_pair must align exactly with result pairs")
    output["calibration_reference"] = calibration["reference"]
    output["calibration_source_sha256"] = calibration["source_sha256"]
    output["quality_supplied_evidence"] = [
        q.get("supplied_evidence") if isinstance(q, Mapping) else None for q in quality_by_pair
    ]
    any_projected = False
    for pair, quality in zip(pairs, quality_by_pair):
        projected = _project_pair(result, pair, quality, matrix, shape)
        any_projected |= any(_finite(c.get("plane_vx_mps")) and _finite(c.get("plane_vy_mps")) for c in projected["motion"]["cells"])
        output["pairs"].append(projected)
    output["projection_status"] = "conditional_projection" if any_projected else "abstain"
    return output


def _aligned_supplied_evidence(quality_by_pair: Any, pair_count: int) -> list[Any]:
    if not isinstance(quality_by_pair, list):
        return [None] * pair_count
    return [
        q.get("supplied_evidence") if isinstance(q, Mapping) else None
        for q in quality_by_pair[:pair_count]
    ] + [None] * max(0, pair_count - len(quality_by_pair))


def _validate_result_shape(result: Mapping[str, Any]) -> tuple[int, int, int, int]:
    native, scaled, transform = result.get("native_dimensions"), result.get("scaled_dimensions"), result.get("transform")
    if not isinstance(native, Mapping) or not isinstance(scaled, Mapping) or not isinstance(transform, Mapping):
        raise ValueError("result dimensions and transform are required")
    values = []
    for obj, key in ((native, "width"), (native, "height"), (scaled, "width"), (scaled, "height")):
        value = obj.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("result dimensions must be positive integers")
        values.append(value)
    nw, nh, sw, sh = values
    expected_h = max(2, int(round(sw * nh / nw / 2.0)) * 2)
    if sh != expected_h or sh % 2:
        raise ValueError("scaled dimensions do not match inspector resize")
    if transform.get("method") != "aspect-preserving resize to explicit even dimensions":
        raise ValueError("result transform does not match inspector resize")
    if not _finite(transform.get("scale_x")) or not _finite(transform.get("scale_y")):
        raise ValueError("result transform scales must be finite")
    if transform["scale_x"] != sw / nw or transform["scale_y"] != sh / nh:
        raise ValueError("result transform scales do not match dimensions")
    return nw, nh, sw, sh


def _validate_calibration(result: Mapping[str, Any], calibration: Mapping[str, Any], shape: tuple[int, int, int, int]) -> list[list[float]]:
    if calibration.get("verified") is not True:
        raise ValueError("verified calibration flag must be true")
    ref = calibration.get("reference")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("verified calibration must include a reference")
    inp = result.get("input")
    source = inp.get("sha256") if isinstance(inp, Mapping) else None
    if calibration.get("source_sha256") != source or not isinstance(source, str):
        raise ValueError("calibration source SHA-256 does not match result")
    for key, expected in (("native_width", shape[0]), ("native_height", shape[1])):
        value = calibration.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            raise ValueError(f"calibration {key} does not match result")
    raw = calibration.get("image_to_plane_m")
    if not isinstance(raw, (list, tuple)) or len(raw) != 3 or any(not isinstance(row, (list, tuple)) or len(row) != 3 for row in raw):
        raise ValueError("image_to_plane_m must be a 3 by 3 matrix")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for row in raw for v in row):
        raise ValueError("homography entries must be finite numeric values")
    matrix = [[float(v) for v in row] for row in raw]
    scale = max(abs(v) for row in matrix for v in row)
    if scale == 0:
        raise ValueError("homography must be nonsingular")
    matrix = [[v / scale for v in row] for row in matrix]
    a, b, c = matrix
    det = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if det == 0 or not math.isfinite(det):
        raise ValueError("homography must be nonsingular")
    return matrix


def _project_pair(result: Mapping[str, Any], pair: Mapping[str, Any], quality: Mapping[str, Any], matrix: list[list[float]], shape: tuple[int, int, int, int]) -> dict[str, Any]:
    if not isinstance(pair, Mapping) or not isinstance(pair.get("motion"), Mapping):
        raise ValueError("each pair must contain a motion field")
    field = pair["motion"]
    cells = field.get("cells")
    if not isinstance(cells, list) or any(not isinstance(c, Mapping) for c in cells):
        raise ValueError("motion cells must be a list of mappings")
    ids = [c.get("cell_id") for c in cells]
    if any(not isinstance(v, str) or not v for v in ids) or len(set(ids)) != len(ids):
        raise ValueError("motion cell IDs must be unique nonempty strings")
    patch = field.get("patch_size")
    if isinstance(patch, bool) or not isinstance(patch, int) or patch <= 0:
        raise ValueError("motion patch_size is invalid")
    digest = hashlib.sha256(json.dumps(field, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if not isinstance(quality, Mapping):
        raise ValueError("each quality assessment must be a mapping")
    status, eligible = quality.get("status"), quality.get("eligible_cell_ids")
    if status not in _QUALITY_STATES or quality.get("field_sha256") != digest:
        raise ValueError("quality assessment state or field digest is invalid")
    if not isinstance(eligible, list) or any(not isinstance(v, str) for v in eligible) or len(set(eligible)) != len(eligible) or not set(eligible).issubset(ids):
        raise ValueError("quality eligible IDs must be unique motion cell IDs")
    dt = pair.get("actual_dt_s")
    valid_dt = _finite(dt) and dt > 0
    nw, nh, sw, sh = shape
    sx, sy = sw / nw, sh / nh
    projected_cells = []
    for cell in cells:
        item = dict(cell)
        item["plane_vx_mps"] = item["plane_vy_mps"] = None
        item["projection_abstention_reason"] = None
        for key in ("x_px", "y_px"):
            if not _finite(item.get(key)):
                raise ValueError(f"motion cell {key} must be finite numeric")
        boundary = item.get("at_search_boundary")
        if not isinstance(boundary, bool):
            raise ValueError("motion boundary flag must be boolean")
        if item.get("status") == "unique_minimum":
            if not _finite(item.get("dx_px")) or not _finite(item.get("dy_px")):
                raise ValueError("unique motion displacement must be finite numeric")
        elif item.get("dx_px") is not None or item.get("dy_px") is not None:
            if not _finite(item.get("dx_px")) or not _finite(item.get("dy_px")):
                raise ValueError("motion displacement must be finite numeric or absent")
        reason = None
        if status == "abstain" or item["cell_id"] not in eligible:
            reason = "quality_abstain"
        elif not valid_dt:
            reason = "timing_unavailable"
        elif item.get("status") != "unique_minimum" or boundary:
            reason = "motion_ineligible"
        else:
            x_scaled = float(item["x_px"]) + (patch - 1) / 2
            y_scaled = float(item["y_px"]) + (patch - 1) / 2
            x = (x_scaled + 0.5) / sx - 0.5
            y = (y_scaled + 0.5) / sy - 0.5
            dx, dy = float(item["dx_px"]) / sx, float(item["dy_px"]) / sy
            start_den = _denominator(matrix, x, y)
            end_den = _denominator(matrix, x + dx, y + dy)
            if start_den is None or end_den is None or start_den == 0 or end_den == 0 or start_den * end_den < 0:
                reason = "projection_horizon"
            else:
                start, end = _map(matrix, x, y), _map(matrix, x + dx, y + dy)
                if start is None or end is None:
                    reason = "projection_horizon"
                else:
                    vx, vy = (end[0] - start[0]) / dt, (end[1] - start[1]) / dt
                    if _finite(vx) and _finite(vy):
                        item["plane_vx_mps"], item["plane_vy_mps"] = vx, vy
                    else:
                        reason = "nonfinite_projected_velocity"
        item["projection_abstention_reason"] = reason
        projected_cells.append(item)
    new_field = {**field, "cells": projected_cells}
    return {**pair, "motion": new_field,
            "projection_status": "conditional_projection" if any(_finite(c["plane_vx_mps"]) and _finite(c["plane_vy_mps"]) for c in projected_cells) else "abstain",
            "quality_supplied_evidence": quality.get("supplied_evidence"),
            "quality_status": status}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _denominator(matrix: list[list[float]], x: float, y: float) -> float | None:
    value = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    return value if math.isfinite(value) else None


def _map(matrix: list[list[float]], x: float, y: float) -> tuple[float, float] | None:
    q = [matrix[i][0] * x + matrix[i][1] * y + matrix[i][2] for i in range(3)]
    if not all(math.isfinite(v) for v in q) or q[2] == 0:
        return None
    xy = q[0] / q[2], q[1] / q[2]
    return xy if all(math.isfinite(v) for v in xy) else None


def _abstain_pair(pair: Any, reason: str, quality: Any = None) -> Any:
    if not isinstance(pair, Mapping) or not isinstance(pair.get("motion"), Mapping):
        return pair
    field = dict(pair["motion"])
    cells = field.get("cells", [])
    field["cells"] = [{**cell, "plane_vx_mps": None, "plane_vy_mps": None,
                       "projection_abstention_reason": reason} for cell in cells if isinstance(cell, Mapping)]
    out = {**pair, "motion": field, "projection_status": "abstain"}
    if isinstance(quality, Mapping):
        out["quality_supplied_evidence"] = quality.get("supplied_evidence")
    return out
