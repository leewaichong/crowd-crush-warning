"""Simple causal diagnostic baselines for zone feature rows."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


MODEL_ID = "causal-diagnostic-baselines-v1"


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _parameter(value: Any, name: str, *, positive: bool = False) -> float:
    result = _finite(value, name)
    if result < 0 or (positive and result == 0):
        bound = "greater than zero" if positive else "nonnegative"
        raise ValueError(f"{name} must be {bound}")
    return result


def baseline_signals(
    features, *, density_threshold, proxy_threshold, change_threshold,
    allowance=0.0, min_quality=0.5, max_gap_s=5.0,
) -> list[dict[str, Any]]:
    """Return per-row density, lagged persistence, and causal CUSUM signals.

    Parameters are explicit research settings, not safety limits. Invalid
    feature rows are retained and reset that zone's causal history.
    """
    density_threshold = _parameter(density_threshold, "density_threshold", positive=True)
    proxy_threshold = _parameter(proxy_threshold, "proxy_threshold", positive=True)
    change_threshold = _parameter(change_threshold, "change_threshold", positive=True)
    allowance = _parameter(allowance, "allowance")
    min_quality = _finite(min_quality, "min_quality")
    if not 0 <= min_quality <= 1:
        raise ValueError("min_quality must be between 0 and 1")
    max_gap_s = _parameter(max_gap_s, "max_gap_s", positive=True)
    if not isinstance(features, (list, tuple)):
        raise ValueError("features must be a list or tuple")

    prepared = []
    seen = set()
    duplicates = set()
    for index, row in enumerate(features):
        if not isinstance(row, Mapping):
            raise ValueError(f"row {index} must be a mapping")
        for key in ("timestamp_s", "zone_id", "density_per_m2", "pressure_proxy", "quality", "calibrated"):
            if key not in row:
                raise ValueError(f"row {index} is missing {key}")
        timestamp = _finite(row["timestamp_s"], f"row {index} timestamp_s")
        zone = row["zone_id"]
        if isinstance(zone, bool) or not isinstance(zone, (str, int)):
            raise ValueError(f"row {index} has invalid zone_id")
        key = (type(zone), zone, timestamp)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
        prepared.append((timestamp, str(zone), index, key, row))
    prepared.sort(key=lambda item: (item[0], item[1], item[2]))

    history = {}
    outputs = []
    for timestamp, _, _, key, row in prepared:
        zone = row["zone_id"]
        state = history.setdefault(zone, {"last_time": None, "previous_proxy": None, "mean": 0.0, "cusum": 0.0})
        reason = None
        density = proxy = quality = None
        try:
            density = _finite(row["density_per_m2"], "density_per_m2")
            quality = _finite(row["quality"], "quality")
            if density < 0 or not 0 <= quality <= 1:
                raise ValueError("out_of_range")
            if row["pressure_proxy"] is not None:
                proxy = _finite(row["pressure_proxy"], "pressure_proxy")
                if proxy < 0:
                    raise ValueError("out_of_range")
            if not isinstance(row["calibrated"], bool):
                raise ValueError("calibration_unknown")
        except ValueError:
            reason = "invalid_feature"
        if key in duplicates:
            reason = "duplicate_timestamp"
        elif reason is None and not row["calibrated"]:
            reason = "uncalibrated"
        elif reason is None and quality < min_quality:
            reason = "low_quality"
        elif reason is None and row.get("status") == "abstain":
            reason = row.get("reason") or "feature_abstain"
        elif reason is None and proxy is None:
            reason = "missing_proxy"

        gap = state["last_time"] is not None and timestamp - state["last_time"] > max_gap_s
        if gap:
            state.update(previous_proxy=None, mean=0.0, cusum=0.0, n=0)
        if reason is not None:
            state.update(last_time=timestamp, previous_proxy=None, mean=0.0, cusum=0.0, n=0)
            arms = {
                "density": {"score": density, "units": "persons_per_m2", "alarm": None},
                "persistence": {"score": None, "units": "pressure_proxy", "alarm": None},
                "change_point": {"score": None, "units": "pressure_proxy_excess_cusum", "alarm": None},
            }
            status = "abstain"
        else:
            prev = state["previous_proxy"]
            density_score = density
            arms = {
                "density": {"score": density_score, "units": "persons_per_m2", "alarm": density_score >= density_threshold},
                "persistence": {"score": prev, "units": "pressure_proxy", "alarm": None if prev is None else prev >= proxy_threshold},
                "change_point": {"score": None, "units": "pressure_proxy_excess_cusum", "alarm": None},
            }
            prior_mean = state["mean"]
            cumulative = max(0.0, state["cusum"] + proxy - prior_mean - allowance) if prev is not None else None
            if cumulative is not None and math.isfinite(cumulative):
                arms["change_point"] = {"score": cumulative, "units": "pressure_proxy_excess_cusum", "alarm": cumulative >= change_threshold}
            else:
                cumulative = 0.0
            count = state.get("n", 0)
            state["mean"] = prior_mean + (proxy - prior_mean) / (count + 1)
            state["n"] = count + 1
            state["cusum"] = cumulative
            state["previous_proxy"] = proxy
            state["last_time"] = timestamp
            status = "ok" if arms["persistence"]["score"] is not None and arms["change_point"]["score"] is not None else "abstain"
            if status == "abstain":
                reason = "warmup"

        outputs.append({
            "timestamp_s": timestamp, "zone_id": zone, "status": status, "reason": reason,
            "arms": arms, "forecast_origin_s": timestamp, "input_cutoff_s": timestamp,
            "model_id": MODEL_ID,
        })
    return outputs
