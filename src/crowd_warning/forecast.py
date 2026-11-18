"""Seeded first-passage proxy forecasts for temporal zone observations.

This is a hypothesis-driven stochastic model, not a physical crowd simulator.
Each input row describes a zone observation, not an individual person or track.
"""

import math
import random
from collections import defaultdict


MODEL_ID = "coupled-zone-first-passage-v1"
_MAX_JUMP_RATE_PER_S = 20.0
_MAX_JUMP_SCALE = 1_000_000.0
_MAX_HORIZON_S = 86_400.0
_CAVEAT = (
    "This is a conditional proxy crossing frequency under an unvalidated model, "
    "not a calibrated harm probability or a measure of physical force. "
    "Rows describe temporal zone observations, so variance is over zone windows, "
    "not person tracks."
)


def _abstain(horizon_s, threshold, reason, *, warmup_counts=None, warmup_reasons=None,
             stale_zones=None, incomplete_zones=None, metadata=None):
    return {
        "status": "abstain",
        "probability": None,
        "model_id": MODEL_ID,
        "horizon_s": horizon_s,
        "threshold": threshold,
        "caveats": [_CAVEAT, reason],
        "warmup_counts": warmup_counts or {},
        "warmup_reasons": warmup_reasons or {},
        "stale_zones": stale_zones or [],
        "incomplete_zones": incomplete_zones or [],
        **(metadata or {}),
    }


def _number(value, name, *, minimum=None, strict=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and (value < minimum or (strict and value == minimum)):
        op = "greater than" if strict else "at least"
        raise ValueError(f"{name} must be {op} {minimum}")
    return value


def forecast_crossing(
    features, horizon_s=30.0, threshold=1.0, paths=256, seed=0,
    *, jump_rate_per_s=0.0, jump_scale=0.0, coupling=0.15, max_gap_s=5.0,
):
    """Estimate the fraction of paths that cross a proxy threshold by horizon.

    Hypotheses: zone proxy values have local linear drift; their changes include
    Gaussian noise estimated from pressure-proxy increments; zones interact
    through mean reversion toward the current cross-zone mean; optional positive
    jumps arrive as a Poisson process. These assumptions are explicit and are
    not claimed to describe crowd physics.

    Features may contain leading rows with both ``velocity_variance`` and
    ``pressure_proxy`` set to ``None`` by the trailing-window warmup. The
    forecast discards only that leading prefix, reports its count and reason,
    then requires at least two complete adequate rows per zone. Any later bad
    quality, uncalibrated row, incomplete value, excessive per-zone gap, or
    stale zone causes abstention. ``max_gap_s`` also sets the maximum age
    difference allowed between latest zone observations at the forecast origin.
    Features require finite ``timestamp_s``, ``zone_id``, ``density_per_m2``,
    ``velocity_variance``, ``pressure_proxy``, ``quality`` and ``calibrated``.
    Low quality and uncalibrated observations, gaps, and incomplete later
    windows cause abstention. Noise is a proxy-unit diffusion estimate from
    time-scaled pressure-proxy increments, after subtracting each zone's linear
    drift. ``jump_rate_per_s`` and ``jump_scale`` enable optional
    positive exponential jumps. The result's ``probability`` is a simulated
    conditional proxy crossing frequency, never a calibrated harm probability.
    """
    horizon_s = _number(horizon_s, "horizon_s", minimum=0, strict=True)
    if horizon_s > _MAX_HORIZON_S:
        raise ValueError(f"horizon_s must be at most {_MAX_HORIZON_S}")
    threshold = _number(threshold, "threshold", minimum=0, strict=True)
    jump_rate_per_s = _number(jump_rate_per_s, "jump_rate_per_s", minimum=0)
    jump_scale = _number(jump_scale, "jump_scale", minimum=0)
    coupling = _number(coupling, "coupling", minimum=0)
    max_gap_s = _number(max_gap_s, "max_gap_s", minimum=0, strict=True)
    if jump_rate_per_s > _MAX_JUMP_RATE_PER_S:
        raise ValueError(f"jump_rate_per_s must be at most {_MAX_JUMP_RATE_PER_S}")
    if jump_scale > _MAX_JUMP_SCALE:
        raise ValueError(f"jump_scale must be at most {_MAX_JUMP_SCALE}")
    if not isinstance(paths, int) or isinstance(paths, bool) or paths < 1:
        raise ValueError("paths must be a positive integer")
    if paths > 1_000_000:
        raise ValueError("paths must be at most 1000000")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if coupling > 1.0:
        raise ValueError("coupling must be at most 1.0")
    if (jump_rate_per_s == 0) != (jump_scale == 0):
        raise ValueError("jump_rate_per_s and jump_scale must both be zero or positive")
    metadata = {
        "forecast_origin_s": None,
        "input_cutoff_s": None,
        "seed": seed,
        "effective_model_parameters": {
            "horizon_s": horizon_s, "threshold": threshold, "paths": paths,
            "jump_rate_per_s": jump_rate_per_s, "jump_scale": jump_scale,
            "coupling": coupling, "max_gap_s": max_gap_s,
        },
        "discretization": {"step_s": 1.0, "final_step": "min(step_s, remaining_horizon)"},
    }

    def abstain(reason, **kwargs):
        return _abstain(horizon_s, threshold, reason, metadata=metadata, **kwargs)

    if not isinstance(features, (list, tuple)) or not features:
        return abstain("No feature rows were supplied.")

    required = ("timestamp_s", "zone_id", "density_per_m2", "velocity_variance",
                "pressure_proxy", "quality", "calibrated")
    ordered_rows = []
    for row in features:
        if not isinstance(row, dict) or any(key not in row for key in required):
            return abstain("Feature rows are incomplete.")
        try:
            timestamp = _number(row["timestamp_s"], "timestamp_s")
        except ValueError:
            return abstain("Feature values are invalid.")
        zone = row["zone_id"]
        if not isinstance(zone, (str, int)) or isinstance(zone, bool):
            return abstain("Zone identifiers are invalid.")
        ordered_rows.append((str(zone), timestamp, row))
    ordered_rows.sort(key=lambda item: (item[1], item[0]))
    metadata["forecast_origin_s"] = max(item[1] for item in ordered_rows)
    metadata["input_cutoff_s"] = metadata["forecast_origin_s"]

    by_zone = defaultdict(list)
    warmup_counts = defaultdict(int)
    warmup_reasons = {}
    active_zone = {}
    observed_zones = set()
    latest_input_times = {}
    seen_zone_times = defaultdict(set)
    try:
        for _, timestamp, row in ordered_rows:
            density = _number(row["density_per_m2"], "density_per_m2", minimum=0)
            quality = _number(row["quality"], "quality", minimum=0)
            if quality > 1:
                return abstain("Quality must be in [0, 1].",
                                warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons)
            if not isinstance(row["calibrated"], bool):
                return abstain("Calibration status is unknown.",
                                warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons)
            zone = row["zone_id"]
            warmup_counts.setdefault(zone, 0)
            observed_zones.add(zone)
            latest_input_times[zone] = max(timestamp, latest_input_times.get(zone, timestamp))
            if timestamp in seen_zone_times[zone]:
                if row["velocity_variance"] is None and row["pressure_proxy"] is None:
                    warmup_counts[zone] += 1
                    warmup_reasons[zone] = (
                        "leading trailing-window warmup has fewer than two observations"
                    )
                return abstain(
                    f"Zone {zone!r} has duplicate timestamps, including warmup rows.",
                    warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
                )
            seen_zone_times[zone].add(timestamp)
            if not row["calibrated"] or quality < 0.5:
                return abstain(
                    f"Zone {zone!r} has low quality or is uncalibrated at {timestamp}.",
                    warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
                )
            variance_value, proxy_value = row["velocity_variance"], row["pressure_proxy"]
            if variance_value is None or proxy_value is None:
                if variance_value is not None or proxy_value is not None:
                    return abstain(
                        f"Zone {zone!r} has incomplete feature values at {timestamp}.",
                        warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
                    )
                if active_zone.get(zone, False):
                    warmup_counts[zone] += 1
                    warmup_reasons[zone] = (
                        "leading trailing-window warmup has fewer than two observations"
                    )
                    return abstain(
                        f"Zone {zone!r} has an interior feature warmup at {timestamp}.",
                        warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
                    )
                warmup_counts[zone] += 1
                warmup_reasons[zone] = "leading trailing-window warmup has fewer than two observations"
                continue
            variance = _number(variance_value, "velocity_variance", minimum=0)
            proxy = _number(proxy_value, "pressure_proxy", minimum=0)
            active_zone[zone] = True
            by_zone[zone].append((timestamp, proxy, variance, density))
    except ValueError:
        return abstain("Feature values are invalid.",
                        warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons)

    if latest_input_times:
        metadata["forecast_origin_s"] = max(latest_input_times.values())
        metadata["input_cutoff_s"] = metadata["forecast_origin_s"]
    incomplete_zones = sorted(
        (zone for zone in observed_zones if len(by_zone.get(zone, ())) < 2), key=str
    )
    if incomplete_zones:
        return abstain(
            f"Zones need at least two complete adequate observations: {incomplete_zones!r}.",
            warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
            incomplete_zones=incomplete_zones,
        )
    for zone, values in by_zone.items():
        values.sort(key=lambda item: item[0])
        if len({v[0] for v in values}) != len(values):
            return abstain(f"Zone {zone!r} has duplicate timestamps.",
                            warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons)
        if any(b[0] - a[0] > max_gap_s for a, b in zip(values, values[1:])):
            return abstain(f"Zone {zone!r} has an interior observation gap.",
                            warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons)

    zones = sorted(by_zone, key=str)
    latest_times = {zone: by_zone[zone][-1][0] for zone in zones}
    forecast_origin = max(latest_times.values())
    metadata["forecast_origin_s"] = forecast_origin
    metadata["input_cutoff_s"] = forecast_origin
    stale_zones = [zone for zone, timestamp in latest_times.items()
                   if forecast_origin - timestamp > max_gap_s]
    if stale_zones:
        return abstain(
            f"Zones are stale at forecast origin {forecast_origin}: {stale_zones!r}.",
            warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
            stale_zones=stale_zones,
        )
    latest = [by_zone[z][-1] for z in zones]
    initial = [v[1] for v in latest]
    diffusion = []
    drift = []
    for zone in zones:
        values = by_zone[zone]
        dt = values[-1][0] - values[0][0]
        slope = (values[-1][1] - values[0][1]) / dt
        drift.append(slope)
        residual_sq = sum(
            ((b[1] - a[1]) - slope * (b[0] - a[0])) ** 2
            for a, b in zip(values, values[1:])
        )
        elapsed_s = sum(b[0] - a[0] for a, b in zip(values, values[1:]))
        diffusion.append(math.sqrt(residual_sq / elapsed_s))
    if any(not math.isfinite(value) for value in drift + diffusion):
        return abstain("Temporal increments exceed finite model limits.",
            warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
        )

    rng = random.Random(seed)
    crossings = 0
    for _ in range(paths):
        state = initial[:]
        crossed = any(x >= threshold for x in state)
        elapsed = 0.0
        while elapsed < horizon_s and not crossed:
            dt = min(1.0, horizon_s - elapsed)
            mean = sum(state) / len(state)
            for i in range(len(state)):
                state[i] += drift[i] * dt + coupling * (mean - state[i]) * dt
                state[i] += diffusion[i] * math.sqrt(dt) * rng.gauss(0.0, 1.0)
                if jump_rate_per_s:
                    count = _poisson(rng, jump_rate_per_s * dt)
                    for _jump in range(count):
                        state[i] += rng.expovariate(1.0 / jump_scale)
                if not math.isfinite(state[i]):
                    return abstain(
                        "Simulated proxy values exceed finite model limits.",
                        warmup_counts=dict(warmup_counts), warmup_reasons=warmup_reasons,
                    )
            elapsed += dt
            crossed = any(x >= threshold for x in state)
        crossings += int(crossed)

    return {
        "status": "ok",
        "probability": crossings / paths,
        "model_id": MODEL_ID,
        "horizon_s": horizon_s,
        "threshold": threshold,
        "caveats": [_CAVEAT, "Monte Carlo estimate; no empirical calibration is available."],
        "warmup_counts": dict(warmup_counts),
        "warmup_reasons": warmup_reasons,
        "stale_zones": [],
        "incomplete_zones": [],
        **metadata,
    }


def _poisson(rng, rate):
    """Draw a bounded Poisson count with a rate no greater than 20 per step."""
    rate = _number(rate, "Poisson rate", minimum=0)
    if rate > _MAX_JUMP_RATE_PER_S:
        raise ValueError(f"Poisson rate must be at most {_MAX_JUMP_RATE_PER_S}")
    if rate == 0:
        return 0
    limit = math.exp(-rate)
    product = 1.0
    count = 0
    while product > limit:
        count += 1
        product *= rng.random()
    return count - 1
