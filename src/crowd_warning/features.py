"""Causal zone-level motion features for research use.

Each row is one observation for a zone, not a person track. Velocity variance
therefore describes temporal variation in zone observations, not physical
force or individual movement.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


MIN_QUALITY = 0.5
_Aggregate = tuple[int, float, float, float, float]
_INVALID = object()


def extract_features(
    rows: Iterable[Mapping[str, Any]],
    window_s: float = 5.0,
    min_quality: float = MIN_QUALITY,
) -> list[dict[str, Any]]:
    """Return one causal, trailing-window feature row per observation.

    Windows include observations in ``[timestamp_s - window_s, timestamp_s]``.
    Each window must contain at least two rows, all calibrated and at or above
    ``min_quality``. The default cutoff of 0.5 is an unvalidated quality policy,
    not an evidence-based threshold. Numeric features abstain when calculation
    overflows. Invalid input fields, duplicate zone timestamps, and invalid
    parameters raise ``ValueError``.

    ``velocity_variance`` is population ``var(vx) + var(vy)``. The
    ``pressure_proxy`` multiplies it by the current density; this is a research
    proxy, not physical pressure or a safety measure. Additive ``status``,
    ``reason``, and ``count`` fields report whether and why a row abstained.
    """
    window = _finite_parameter(window_s, "window_s", positive=True)
    quality_cutoff = _finite_parameter(min_quality, "min_quality")
    if not 0 <= quality_cutoff <= 1:
        raise ValueError("min_quality must be between 0 and 1")

    required = ("timestamp_s", "zone_id", "density_per_m2", "vx_mps", "vy_mps", "quality", "calibrated")
    zones: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[Any, float]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"row {index} must be a mapping")
        missing = [key for key in required if key not in row or row[key] is None]
        if missing:
            raise ValueError(f"row {index} is missing required fields: {', '.join(missing)}")
        timestamp = _finite_number(row["timestamp_s"], f"row {index} timestamp_s")
        density = _finite_number(row["density_per_m2"], f"row {index} density_per_m2")
        vx = _finite_number(row["vx_mps"], f"row {index} vx_mps")
        vy = _finite_number(row["vy_mps"], f"row {index} vy_mps")
        quality = _finite_number(row["quality"], f"row {index} quality")
        if density < 0:
            raise ValueError(f"row {index} density_per_m2 must be nonnegative")
        if not 0 <= quality <= 1:
            raise ValueError(f"row {index} quality must be between 0 and 1")
        if not isinstance(row["calibrated"], bool):
            raise ValueError(f"row {index} calibrated must be a bool")
        zone_id = row["zone_id"]
        try:
            hash(zone_id)
        except TypeError as exc:
            raise ValueError(f"row {index} zone_id must be hashable") from exc
        key = (zone_id, timestamp)
        if key in seen:
            raise ValueError(f"duplicate timestamp_s for zone_id at row {index}")
        seen.add(key)
        zones[zone_id].append({
            "timestamp_s": timestamp,
            "zone_id": zone_id,
            "density_per_m2": density,
            "vx_mps": vx,
            "vy_mps": vy,
            "quality": quality,
            "calibrated": row["calibrated"],
        })

    output: list[dict[str, Any]] = []
    for zone_id, observations in zones.items():
        observations.sort(key=lambda item: item["timestamp_s"])
        window_queue = _AggregateQueue(quality_cutoff)
        for current in observations:
            start = current["timestamp_s"] - window
            while window_queue and window_queue.oldest["timestamp_s"] < start:
                window_queue.popleft()
            window_queue.append(current)

            count = len(window_queue)
            variance = None
            proxy = None
            if count < 2:
                reason = "insufficient_window"
            elif window_queue.uncalibrated_count:
                reason = "uncalibrated"
            elif window_queue.low_quality_count:
                reason = "low_quality"
            else:
                aggregate = window_queue.aggregate
                if aggregate is None or aggregate is _INVALID:
                    reason = "numeric_overflow"
                else:
                    _, _, _, m2_x, m2_y = aggregate
                    variance = m2_x / count + m2_y / count
                    proxy = current["density_per_m2"] * variance
                    if not math.isfinite(variance) or not math.isfinite(proxy):
                        variance = None
                        proxy = None
                        reason = "numeric_overflow"
                    else:
                        reason = None
            output.append({
                "timestamp_s": current["timestamp_s"],
                "zone_id": zone_id,
                "density_per_m2": current["density_per_m2"],
                "velocity_variance": variance,
                "pressure_proxy": proxy,
                "quality": current["quality"],
                "calibrated": current["calibrated"],
                "status": "ok" if reason is None else "abstain",
                "reason": reason,
                "count": count,
            })
    output.sort(key=lambda item: (item["timestamp_s"], repr(item["zone_id"])))
    return output


class _AggregateQueue:
    """FIFO queue with Welford aggregates stored on two stacks.

    Merging aggregates avoids the unstable ``E[x*x] - E[x]**2`` formula.
    Each observation enters and leaves a stack once, so window updates are
    amortized O(1) rather than rescanning all prior rows.
    """

    def __init__(self, quality_cutoff: float) -> None:
        self._in: list[tuple[dict[str, Any], _Aggregate | None | object]] = []
        self._out: list[tuple[dict[str, Any], _Aggregate | None | object]] = []
        self._quality_cutoff = quality_cutoff
        self.uncalibrated_count = 0
        self.low_quality_count = 0

    def __bool__(self) -> bool:
        return bool(self._in or self._out)

    def __len__(self) -> int:
        return len(self._in) + len(self._out)

    @property
    def oldest(self) -> dict[str, Any]:
        self._move_oldest()
        return self._out[-1][0]

    @property
    def aggregate(self) -> _Aggregate | None | object:
        left = self._out[-1][1] if self._out else None
        right = self._in[-1][1] if self._in else None
        return _merge(left, right)

    def append(self, item: dict[str, Any]) -> None:
        single = (1, item["vx_mps"], item["vy_mps"], 0.0, 0.0)
        previous = self._in[-1][1] if self._in else None
        self._in.append((item, _merge(previous, single)))
        self.uncalibrated_count += not item["calibrated"]
        self.low_quality_count += item["quality"] < self._quality_cutoff

    def popleft(self) -> dict[str, Any]:
        self._move_oldest()
        item = self._out.pop()[0]
        self.uncalibrated_count -= not item["calibrated"]
        self.low_quality_count -= item["quality"] < self._quality_cutoff
        return item

    def _move_oldest(self) -> None:
        if not self._out:
            while self._in:
                item, _ = self._in.pop()
                single = (1, item["vx_mps"], item["vy_mps"], 0.0, 0.0)
                previous = self._out[-1][1] if self._out else None
                self._out.append((item, _merge(previous, single)))


def _merge(left: _Aggregate | None | object, right: _Aggregate | None | object) -> _Aggregate | None | object:
    if left is _INVALID or right is _INVALID:
        return _INVALID
    if left is None:
        return right
    if right is None:
        return left
    n_left, mean_x_left, mean_y_left, m2_x_left, m2_y_left = left
    n_right, mean_x_right, mean_y_right, m2_x_right, m2_y_right = right
    count = n_left + n_right
    delta_x = mean_x_right - mean_x_left
    delta_y = mean_y_right - mean_y_left
    weight = n_right / count
    mean_x = mean_x_left + delta_x * weight
    mean_y = mean_y_left + delta_y * weight
    m2_x = m2_x_left + m2_x_right + delta_x * delta_x * n_left * weight
    m2_y = m2_y_left + m2_y_right + delta_y * delta_y * n_left * weight
    if not all(math.isfinite(value) for value in (mean_x, mean_y, m2_x, m2_y)):
        return _INVALID
    return count, mean_x, mean_y, m2_x, m2_y


def _finite_parameter(value: Any, label: str, positive: bool = False) -> float:
    number = _finite_number(value, label)
    if positive and number <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return number


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number
