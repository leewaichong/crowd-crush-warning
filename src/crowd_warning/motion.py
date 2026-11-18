"""Image-space block matching diagnostics for adjacent grayscale frames."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np


def estimate_motion_pair(
    previous: Any,
    current: Any,
    *,
    dt_s: float,
    patch_size: int = 16,
    search_radius: int = 4,
) -> dict[str, Any]:
    """Estimate integer pixel displacements using mean SSD block matching."""
    first = np.asarray(previous)
    second = np.asarray(current)
    if first.ndim != 2 or second.ndim != 2 or first.shape != second.shape:
        raise ValueError("frames must be same-shaped 2D grayscale arrays")
    try:
        finite_frames = np.isfinite(first).all() and np.isfinite(second).all()
    except TypeError as exc:
        raise ValueError("frames must contain finite numeric values") from exc
    if not finite_frames:
        raise ValueError("frames must contain only finite values")
    dt = _positive_finite(dt_s, "dt_s")
    patch = _positive_integer(patch_size, "patch_size")
    radius = _nonnegative_integer(search_radius, "search_radius")

    height, width = first.shape
    cells: list[dict[str, Any]] = []
    y_starts = range(radius, height - radius - patch + 1, patch)
    x_starts = range(radius, width - radius - patch + 1, patch)
    for row, y in enumerate(y_starts):
        for column, x in enumerate(x_starts):
            source = first[y:y + patch, x:x + patch].astype(np.float64, copy=False)
            costs: list[tuple[float, int, int]] = []
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    candidate = second[y + dy:y + dy + patch, x + dx:x + dx + patch].astype(np.float64, copy=False)
                    delta = source - candidate
                    costs.append((float(np.mean(delta * delta)), dx, dy))
            best_cost = min(cost for cost, _, _ in costs)
            winners = [(dx, dy) for cost, dx, dy in costs if cost == best_cost]
            unique = len(winners) == 1
            dx, dy = winners[0] if unique else (None, None)
            cells.append({
                "cell_id": f"{row}:{column}",
                "x_px": x,
                "y_px": y,
                "dx_px": dx,
                "dy_px": dy,
                "status": "unique_minimum" if unique else "ambiguous",
                "at_search_boundary": any(abs(wx) == radius or abs(wy) == radius for wx, wy in winners),
                "source_variance": float(np.var(source)),
                "best_cost": best_cost,
            })

    unique_count = sum(cell["status"] == "unique_minimum" for cell in cells)
    total_count = len(cells)
    return {
        "method": "integer_ssd_blocks_v1",
        "image_shape": [int(height), int(width)],
        "dt_s": dt,
        "patch_size": patch,
        "search_radius": radius,
        "cells": cells,
        "coverage": {
            "total_cells": total_count,
            "unique_match_cells": unique_count,
            "unique_match_fraction": unique_count / total_count if total_count else 0.0,
        },
        "units": "pixels_per_pair",
        "camera_motion_status": "unknown",
        "physical_calibration": "unknown",
        "visibility": "not_assessed",
    }


def summarize_camera_residual(
    field: Mapping[str, Any],
    *,
    background_cell_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Summarize residuals against only caller-nominated background matches."""
    nominated = set(background_cell_ids or ())
    usable = [
        cell for cell in field.get("cells", [])
        if cell.get("cell_id") in nominated
        and cell.get("status") == "unique_minimum"
        and not cell.get("at_search_boundary")
    ]
    if not usable:
        return {
            "camera_motion_status": "unknown",
            "background_cell_ids": [],
            "background_verified": False,
            "translation_px": None,
            "residuals_px": None,
        }
    dx = float(np.median([cell["dx_px"] for cell in usable]))
    dy = float(np.median([cell["dy_px"] for cell in usable]))
    return {
        "camera_motion_status": "caller_supplied_background",
        "background_cell_ids": [cell["cell_id"] for cell in usable],
        "background_verified": False,
        "translation_px": {"dx_px": dx, "dy_px": dy},
        "residuals_px": {
            cell["cell_id"]: math.hypot(cell["dx_px"] - dx, cell["dy_px"] - dy)
            for cell in usable
        },
    }


def _positive_finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite and positive")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be finite and positive") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)
