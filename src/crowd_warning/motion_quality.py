"""Quality gate for caller-supplied image-motion evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping
from typing import Any


def assess_motion_quality(
    field: Mapping[str, Any],
    *,
    camera_stable: bool | None = None,
    camera_reference: str | None = None,
    visible_cell_ids: list[str] | tuple[str, ...] | None = None,
    visibility_reference: str | None = None,
) -> dict[str, Any]:
    """Assess eligible cells under evidence supplied by the caller.

    The function checks consistency and coverage. It does not verify either
    reference, camera stability, or visibility independently.
    """
    if not isinstance(field, Mapping) or not isinstance(field.get("cells"), list):
        raise ValueError("field must be a motion mapping with a cells list")
    try:
        canonical = json.dumps(field, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("field must be canonical JSON with finite values") from exc
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    if camera_stable is not None and not isinstance(camera_stable, bool):
        raise ValueError("camera_stable must be true, false, or None")
    _reference(camera_reference, "camera_reference")
    _reference(visibility_reference, "visibility_reference")
    if visible_cell_ids is not None and not isinstance(visible_cell_ids, (list, tuple)):
        raise ValueError("visible_cell_ids must be a list or tuple of cell IDs")

    cells = field["cells"]
    by_id: dict[str, Mapping[str, Any]] = {}
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError("each cell must be a mapping")
        cell_id = cell.get("cell_id")
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError("each cell must have a nonempty string cell_id")
        if cell_id in by_id:
            raise ValueError(f"duplicate cell_id: {cell_id}")
        by_id[cell_id] = cell
        if "at_search_boundary" not in cell or not isinstance(cell["at_search_boundary"], bool):
            raise ValueError(f"cell {cell_id} at_search_boundary must be a boolean")
        if not isinstance(cell.get("status"), str):
            raise ValueError(f"cell {cell_id} status must be a string")
        if cell["status"] == "unique_minimum":
            for axis in ("dx_px", "dy_px"):
                value = cell.get(axis)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"unique cell {cell_id} {axis} must be numeric")

    nominated: set[str] | None = None
    if visible_cell_ids is not None:
        nominated = set()
        for cell_id in visible_cell_ids:
            if not isinstance(cell_id, str) or not cell_id:
                raise ValueError("visible_cell_ids must contain nonempty strings")
            if cell_id in nominated:
                raise ValueError(f"duplicate visible cell ID: {cell_id}")
            if cell_id not in by_id:
                raise ValueError(f"unknown visible cell ID: {cell_id}")
            nominated.add(cell_id)

    reasons: Counter[str] = Counter()
    eligible: list[str] = []
    for cell_id, cell in by_id.items():
        if cell["status"] != "unique_minimum":
            reasons["ambiguous_or_nonunique"] += 1
            continue
        if cell["at_search_boundary"]:
            reasons["search_boundary"] += 1
            continue
        if not all(math.isfinite(float(cell[key])) for key in ("dx_px", "dy_px")):
            reasons["nonfinite_displacement"] += 1
            continue
        if nominated is not None and cell_id not in nominated:
            reasons["not_nominated_visible"] += 1
            continue
        eligible.append(cell_id)

    evidence_reasons = []
    if camera_stable is not True or not camera_reference:
        evidence_reasons.append("camera_stability_evidence_missing_or_negative")
    if nominated is None or not visibility_reference:
        evidence_reasons.append("visibility_evidence_missing")
    admitted = eligible if not evidence_reasons else []
    counts = {
        "total_cells": len(by_id),
        "eligible_cells": len(admitted),
        "excluded_cells": len(by_id) - len(admitted),
        "eligible_fraction": len(admitted) / len(by_id) if by_id else 0.0,
    }
    return {
        "field_sha256": digest,
        "status": "eligible_under_supplied_evidence" if not evidence_reasons and eligible else "abstain",
        "eligible_cell_ids": admitted,
        "counts": counts,
        "reasons": dict(sorted(reasons.items())),
        "abstention_reasons": evidence_reasons or ([] if eligible else ["no_eligible_cells"]),
        "supplied_evidence": {
            "camera_stable": camera_stable,
            "camera_reference": camera_reference,
            "visible_cell_ids": list(visible_cell_ids) if visible_cell_ids is not None else None,
            "visibility_reference": visibility_reference,
            "scope": "caller-supplied evidence; references and claims are not independently verified",
        },
    }


def _reference(value: str | None, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be a nonempty string or None")
