from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from crowd_warning.lyon import read_lyon_topview

MEMBERS = (
    "Data_Madras/TopView_trajectories/TopView_1A.txt",
    "Data_Madras/TopView_trajectories/TopView_2A.txt",
)
REPLICATES = (0, 1, 2)
PATHS = 256
HORIZON_S = 30.0
ZONES = 4


def finite(value: float) -> bool:
    return math.isfinite(value)


def build_series(rows: list[dict], n: int, member: str):
    times: list[float | None] = [None] * n
    extrema = [[None, None, None, None] for _ in range(n)]
    for row in rows:
        frame = row["source_frame"]
        timestamp = row["source_t_s"]
        if not 0 <= frame < n:
            raise ValueError("source frame outside validated frame range")
        if times[frame] is not None and times[frame] != timestamp:
            raise ValueError("source frame has inconsistent source times")
        times[frame] = timestamp
        x, y = row["projected_x_epsg2154_m"], row["projected_y_epsg2154_m"]
        box = extrema[frame]
        extrema[frame] = [x if box[0] is None else min(box[0], x),
                          x if box[1] is None else max(box[1], x),
                          y if box[2] is None else min(box[2], y),
                          y if box[3] is None else max(box[3], y)]
    if any(value is None for value in times) or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("source frames or source times are incomplete")
    edge = int(0.6 * n)
    edge80 = int(0.8 * n)
    train_boxes = [box for box in extrema[:edge] if box[0] is not None]
    bounds = (min(box[0] for box in train_boxes), max(box[1] for box in train_boxes),
              min(box[2] for box in train_boxes), max(box[3] for box in train_boxes))
    if bounds[0] == bounds[1] or bounds[2] == bounds[3]:
        raise ValueError("training bounds have zero area")
    tile_area = ((bounds[1] - bounds[0]) * (bounds[3] - bounds[2])) / 4.0
    if not finite(tile_area) or tile_area <= 0:
        raise ValueError("training tile area is invalid")

    reports = [[0] * ZONES for _ in range(n)]
    sx = [[0.0] * ZONES for _ in range(n)]
    sy = [[0.0] * ZONES for _ in range(n)]
    counts = [[0] * ZONES for _ in range(n)]
    previous: dict[str, tuple[int, float, float, float]] = {}
    for row in rows:
        frame, timestamp = row["source_frame"], row["source_t_s"]
        x, y = row["projected_x_epsg2154_m"], row["projected_y_epsg2154_m"]
        inside = bounds[0] <= x <= bounds[1] and bounds[2] <= y <= bounds[3]
        tile = (1 if x >= (bounds[0] + bounds[1]) / 2 else 0) + \
               (2 if y >= (bounds[2] + bounds[3]) / 2 else 0)
        if inside:
            reports[frame][tile] += 1
        trace = row["trace_id"]
        old = previous.get(trace)
        if old is not None and frame == old[0] + 1 and timestamp > old[1] and inside:
            dt = timestamp - old[1]
            sx[frame][tile] += (x - old[2]) / dt
            sy[frame][tile] += (y - old[3]) / dt
            counts[frame][tile] += 1
        previous[trace] = (frame, timestamp, x, y)

    mean_x: list[list[float | None]] = [[None] * ZONES for _ in range(n)]
    mean_y: list[list[float | None]] = [[None] * ZONES for _ in range(n)]
    for frame in range(n):
        for zone in range(ZONES):
            if counts[frame][zone]:
                mean_x[frame][zone] = sx[frame][zone] / counts[frame][zone]
                mean_y[frame][zone] = sy[frame][zone] / counts[frame][zone]
    q: list[list[float | None]] = [[None] * ZONES for _ in range(n)]
    left = 0
    for frame in range(n):
        while left <= frame and times[left] < times[frame] - 1.0:
            left += 1
        for zone in range(ZONES):
            values = [idx for idx in range(left, frame + 1) if mean_x[idx][zone] is not None]
            if reports[frame][zone] and len({times[idx] for idx in values}) >= 2:
                mx = sum(mean_x[idx][zone] for idx in values) / len(values)
                my = sum(mean_y[idx][zone] for idx in values) / len(values)
                vx = sum((mean_x[idx][zone] - mx) ** 2 for idx in values) / len(values)
                vy = sum((mean_y[idx][zone] - my) ** 2 for idx in values) / len(values)
                value = (reports[frame][zone] / tile_area) * (vx + vy)
                q[frame][zone] = value if finite(value) else None
    return list(times), edge, edge80, q


def fit(times: list[float], edge: int, q: list[list[float | None]]):
    training = [(frame, q[frame]) for frame in range(2, edge)]
    if not training or any(any(value is None or not finite(value) for value in values)
                           for _, values in training):
        raise ValueError("incomplete or nonfinite training q")
    train_values = [value for _, values in training for value in values]
    ordered = sorted(train_values)
    boundary = ordered[math.ceil(0.95 * len(ordered)) - 1]
    if not finite(boundary) or boundary <= 0:
        raise ValueError("training boundary must be finite and positive")
    mu, sigma = [], []
    for zone in range(ZONES):
        pairs = [(times[frame], values[zone]) for frame, values in training]
        elapsed = pairs[-1][0] - pairs[0][0]
        if not finite(elapsed) or elapsed <= 0:
            raise ValueError("training elapsed time must be finite and positive")
        drift = (pairs[-1][1] - pairs[0][1]) / elapsed
        residual = sum(((b[1] - a[1]) - drift * (b[0] - a[0])) ** 2
                       for a, b in zip(pairs, pairs[1:]))
        total_elapsed = sum(b[0] - a[0] for a, b in zip(pairs, pairs[1:]))
        diffusion = math.sqrt(residual / total_elapsed) if total_elapsed > 0 else float("nan")
        if not finite(drift) or not finite(diffusion) or diffusion <= 0:
            raise ValueError("fit coefficients must be finite and sigma strictly positive")
        mu.append(drift)
        sigma.append(diffusion)
    return training, mu, sigma, boundary


def seed_for(member: str, origin_frame: int, replicate: int) -> int:
    payload = f"{member}|{origin_frame}|{replicate}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def simulate(initial, mu, sigma, coupling, noise, boundary):
    state = list(initial)
    if any(not finite(value) for value in state):
        raise ValueError("nonfinite initial simulated state")
    crossed = any(value >= boundary for value in state)
    elapsed = 0.0
    step = 0
    while elapsed < HORIZON_S and not crossed:
        dt = min(1.0, HORIZON_S - elapsed)
        shared_mean = sum(state) / ZONES
        for zone in range(ZONES):
            state[zone] += mu[zone] * dt + coupling * (shared_mean - state[zone]) * dt
            state[zone] += sigma[zone] * math.sqrt(dt) * noise[step][zone]
            if not finite(state[zone]):
                raise ValueError("nonfinite simulated state")
        elapsed += dt
        step += 1
        crossed = any(value >= boundary for value in state)
    return int(crossed)


def score_partition(member, partition, start, stop, times, q, mu, sigma, boundary):
    excluded = {"horizon_unavailable": 0, "incomplete_current_q": 0,
                "current_at_or_above_boundary": 0, "incomplete_future_target": 0}
    origins = []
    end_time = times[stop - 1]
    for frame in range(start, stop):
        if times[frame] + HORIZON_S > end_time:
            excluded["horizon_unavailable"] += 1
            continue
        if any(value is None or not finite(value) for value in q[frame]):
            excluded["incomplete_current_q"] += 1
            continue
        if any(value >= boundary for value in q[frame]):
            excluded["current_at_or_above_boundary"] += 1
            continue
        future = [idx for idx in range(frame + 1, stop) if times[idx] <= times[frame] + HORIZON_S]
        if not future or any(any(value is None or not finite(value) for value in q[idx]) for idx in future):
            excluded["incomplete_future_target"] += 1
            continue
        label = int(any(value >= boundary for idx in future for value in q[idx]))
        origins.append((frame, label))

    replicate_rows = []
    detailed = []
    for replicate in REPLICATES:
        scores = {arm: [] for arm in ("coupled", "uncoupled", "persistence")}
        for frame, label in origins:
            probabilities = {"coupled": [], "uncoupled": []}
            initial = q[frame]
            seed = seed_for(member, frame, replicate)
            rng = random.Random(seed)
            noise_by_path = [
                [[rng.gauss(0.0, 1.0) for _ in range(ZONES)] for _ in range(30)]
                for _ in range(PATHS)
            ]
            for noise in noise_by_path:
                probabilities["coupled"].append(
                    simulate(initial, mu, sigma, 0.15, noise, boundary))
                probabilities["uncoupled"].append(
                    simulate(initial, mu, sigma, 0.0, noise, boundary))
            predictions = {
                "coupled": sum(probabilities["coupled"]) / PATHS,
                "uncoupled": sum(probabilities["uncoupled"]) / PATHS,
                "persistence": 0.0,
            }
            for arm, probability in predictions.items():
                scores[arm].append((probability - label) ** 2)
            detailed.append({"member": member, "partition": partition,
                             "replicate": replicate, "origin_frame": frame,
                             "source_t_s": times[frame], "label": label,
                             "predictions": predictions})
        briers = {arm: (sum(values) / len(values) if values else None)
                  for arm, values in scores.items()}
        replicate_rows.append({"replicate": replicate, "eligible_origins": len(origins),
                               "event_count": sum(label for _, label in origins),
                               "brier": briers})

    means = {}
    ranges = {}
    for arm in ("coupled", "uncoupled", "persistence"):
        values = [row["brier"][arm] for row in replicate_rows]
        means[arm] = sum(values) / len(values) if values and values[0] is not None else None
        ranges[arm] = ({"minimum": min(values), "maximum": max(values)}
                       if values and values[0] is not None else None)
    comparisons = {}
    coupled = means["coupled"]
    for control in ("uncoupled", "persistence"):
        value = means[control]
        comparisons[control] = ("no_evaluable_origins" if coupled is None else
                                "lower" if coupled < value else
                                "equal" if coupled == value else "higher")
    return ({"status": "NO_EVALUABLE_ORIGINS" if not origins else "descriptive_scores_available",
             "candidate_horizon_origins": stop - start - excluded["horizon_unavailable"],
             "eligible_origins": len(origins),
             "event_count": sum(label for _, label in origins),
             "overlapping_origin_exposure_s": len(origins) * HORIZON_S,
             "excluded_origins": excluded, "replicates": replicate_rows,
             "mean_brier_across_three_replicates": means,
             "replicate_brier_min_max": ranges,
             "coupled_mean_brier_vs_controls": comparisons,
             "coupled_test_skill_falsifier":
                 ("NO_EVALUABLE_ORIGINS" if partition == "test" and not origins else
                  "strictly_lower_than_both" if partition == "test" and
                  comparisons["uncoupled"] == comparisons["persistence"] == "lower" else
                  "fails_strict_improvement_over_both" if partition == "test" else None)}, detailed)


def main():
    attempt = Path(__file__).resolve().parent
    freeze = json.loads((attempt / "comparison-freeze.json").read_text())
    if freeze.get("lead_reviewed") is not True or freeze.get("status") != "PREPARED NOT RUN":
        raise SystemExit("explicit lead review marker is required before computation")
    frozen_config = {key: value for key, value in freeze.items()
                     if key not in ("lead_reviewed", "frozen_configuration_sha256")}
    actual_config_hash = hashlib.sha256(
        json.dumps(frozen_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if actual_config_hash != freeze.get("frozen_configuration_sha256"):
        raise SystemExit("frozen configuration changed beyond the lead review marker")
    outputs = ("comparison-aggregates.json", "comparison-result.json",
               "comparison.stdout.log", "comparison.stderr.log", "comparison-execution.json")
    if any((attempt / name).exists() for name in outputs):
        raise SystemExit("refusing existing output")
    archive = Path(freeze["archive_path"])
    records = []
    for member in MEMBERS:
        expected = freeze["members"][member]
        table = read_lyon_topview(archive, member=member)
        provenance = table["provenance"]
        if (provenance["archive_sha256"] != freeze["archive_sha256"] or
                provenance["member_sha256"] != expected["sha256"] or
                provenance["member_size_bytes"] != expected["size_bytes"]):
            raise ValueError("parser provenance does not match frozen member and archive hashes")
        rows = table["rows"]
        n = max(row["source_frame"] for row in rows) + 1
        times, edge, edge80, q = build_series(rows, n, member)
        training, mu, sigma, boundary = fit(times, edge, q)
        record = {
            "member": member,
            "training_q": [{"frame": frame, "source_t_s": times[frame], "q": values}
                           for frame, values in training],
            "fit_mu": mu, "fit_sigma": sigma, "training_boundary": boundary,
            "q_by_frame": [{"frame": frame, "source_t_s": times[frame], "q": values}
                           for frame, values in enumerate(q)],
            "partitions": {},
        }
        for name, start, stop in (("validation", edge, edge80), ("test", edge80, n)):
            metrics, origins = score_partition(member, name, start, stop, times, q,
                                               mu, sigma, boundary)
            record["partitions"][name] = {"metrics": metrics, "origin_forecasts": origins}
        records.append(record)
    (attempt / "comparison-aggregates.json").write_text(
        json.dumps({"status": "private_descriptive_aggregates", "records": records},
                   allow_nan=False, separators=(",", ":")) + "\n")
    summary = [{"member": record["member"], "partition": name, **entry["metrics"]}
               for record in records for name, entry in record["partitions"].items()]
    (attempt / "comparison-result.json").write_text(
        json.dumps({"status": "descriptive_comparison_completed", "records": summary,
                    "safety_evaluation": False}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
