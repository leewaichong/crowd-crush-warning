"""Forecast the published spatial-average density series on its native grid."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from crowd_warning.density import read_density_table

GRID_S = 0.04
HORIZON_S = 30.0
WARMUP_S = 30.0
ORIGIN_STEP_S = 30.0
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_BLOCK = 5
YEARS = (2022, 2023, 2024)
ARMS = ("persistence", "local_trend", "ar1")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _event(path: Path, name: str, **details: object) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": name, "time_utc": _now(), **details}, sort_keys=True, allow_nan=False) + "\n")


def _finite(value: float) -> bool:
    return math.isfinite(value)


def fit_ar1(points: list[list[float]]) -> dict[str, float | bool]:
    """Fit finite discrete AR(1) OLS parameters on adjacent training values."""
    pairs = list(zip(points, points[1:]))
    if len(pairs) < 2:
        raise ValueError("AR(1) fit needs at least two adjacent pairs")
    xs, ys = [a[1] for a, _ in pairs], [b[1] for _, b in pairs]
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom == 0:
        raise ValueError("AR(1) fit is undefined because training values are constant")
    phi = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - phi * xbar
    residuals = [y - intercept - phi * x for x, y in zip(xs, ys)]
    variance = sum(value * value for value in residuals) / len(residuals)
    if not all(_finite(value) for value in (phi, intercept, variance)):
        raise ValueError("AR(1) fit produced nonfinite parameters")
    return {"intercept": intercept, "phi": phi, "residual_variance": variance,
            "abs_phi_below_one_training_diagnostic": abs(phi) < 1}


def _grid(points: list[list[float]]) -> None:
    if len(points) < 2:
        raise ValueError("each source year needs at least two observations")
    for (ta, _), (tb, _) in zip(points, points[1:]):
        if abs((tb - ta) - GRID_S) > 1e-6:
            raise ValueError("timestamps do not follow the native 0.04-second grid")


def _ols(history: list[tuple[float, float]], target: float) -> tuple[float, float, float, float]:
    if len(history) < 2:
        raise ValueError("local trend is undefined with fewer than two observations")
    mx = sum(t for t, _ in history) / len(history)
    my = sum(v for _, v in history) / len(history)
    denom = sum((t - mx) ** 2 for t, _ in history)
    if denom == 0:
        raise ValueError("local trend is undefined for duplicate timestamps")
    slope = sum((t - mx) * (v - my) for t, v in history) / denom
    intercept = my - slope * mx
    prediction = intercept + slope * target
    if not all(_finite(value) for value in (intercept, slope, prediction)):
        raise ValueError("local trend produced nonfinite values")
    return prediction, intercept, slope, history[0][0]


def _ar_forecast(last: float, fit: dict[str, float | bool], steps: int) -> float:
    phi, intercept = float(fit["phi"]), float(fit["intercept"])
    if phi == 1.0:
        prediction = last + steps * intercept
    else:
        power = phi ** steps
        prediction = power * last + intercept * (1.0 - power) / (1.0 - phi)
    if not _finite(prediction):
        raise ValueError("AR(1) prediction is nonfinite")
    return prediction


def forecast_year(points: list[list[float]], fit: dict[str, float | bool], year: int) -> list[dict]:
    _grid(points)
    by_time = {round(timestamp, 6): value for timestamp, value in points}
    start, end = points[0][0], points[-1][0]
    rows = []
    origin = start + WARMUP_S
    while origin + HORIZON_S <= end + 1e-6:
        origin_key, target_key = round(origin, 6), round(origin + HORIZON_S, 6)
        if origin_key not in by_time or target_key not in by_time:
            raise ValueError("scheduled origin or target is absent from the observed grid")
        history = [(t, value) for t, value in points if origin - WARMUP_S - 1e-6 <= t <= origin + 1e-6]
        actual, persistence = by_time[target_key], by_time[origin_key]
        predictions: dict[str, float | None] = {"persistence": persistence, "local_trend": None, "ar1": None}
        abstentions: dict[str, str] = {}
        local_intercept = local_slope = None
        local_start = local_end = None
        try:
            local, local_intercept, local_slope, local_start = _ols(history, target_key)
            predictions["local_trend"] = local
            local_end = history[-1][0]
        except ValueError as exc:
            abstentions["local_trend"] = str(exc)
        try:
            predictions["ar1"] = _ar_forecast(persistence, fit, round(HORIZON_S / GRID_S))
        except (ValueError, OverflowError) as exc:
            abstentions["ar1"] = str(exc)
        errors = {}
        for arm in ARMS:
            prediction = predictions[arm]
            error = prediction - actual if prediction is not None else None
            if error is not None and not _finite(error):
                predictions[arm] = None
                abstentions[arm] = "forecast error is nonfinite"
                error = None
            errors[arm] = error
        rows.append({
            "year": year, "origin_timestamp_s": origin_key, "cutoff_timestamp_s": origin_key,
            "target_timestamp_s": target_key, "actual_timestamp_s": target_key, "actual": actual,
            "local_trend_window_start_s": local_start, "local_trend_window_end_s": local_end,
            "local_trend_intercept": local_intercept, "local_trend_slope_per_s": local_slope,
            "predictions": predictions, "errors": errors, "arm_abstentions": abstentions,
        })
        origin += ORIGIN_STEP_S
    return rows


def _percentile_interval(values: list[float]) -> list[float]:
    values.sort()
    return [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]]


def _metrics(rows: list[dict], seed: int = 0) -> dict:
    valid = {arm: [r for r in rows if r["errors"][arm] is not None] for arm in ARMS}
    metrics = {"scheduled_origin_count": len(rows), "arms": {}, "paired_vs_persistence": {}}
    for arm in ARMS:
        errors = [r["errors"][arm] for r in valid[arm]]
        metrics["arms"][arm] = {
            "valid_count": len(errors), "abstention_count": len(rows) - len(errors),
            "mae": sum(abs(e) for e in errors) / len(errors) if errors else None,
            "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None,
        }
    paired_rows = {arm: [r for r in rows if r["errors"]["persistence"] is not None and r["errors"][arm] is not None] for arm in ARMS[1:]}
    for arm in ARMS[1:]:
        pairs = paired_rows[arm]
        mae_deltas = [abs(r["errors"][arm]) - abs(r["errors"]["persistence"]) for r in pairs]
        rmse_delta = (math.sqrt(sum(r["errors"][arm] ** 2 for r in pairs) / len(pairs)) -
                      math.sqrt(sum(r["errors"]["persistence"] ** 2 for r in pairs) / len(pairs))) if pairs else None
        disagreements = sorted(({
            "origin_timestamp_s": r["origin_timestamp_s"],
            "absolute_error_difference": abs(r["errors"][arm]) - abs(r["errors"]["persistence"]),
        } for r in pairs), key=lambda row: abs(row["absolute_error_difference"]), reverse=True)
        metrics["paired_vs_persistence"][arm] = {
            "paired_count": len(pairs), "mae_delta": sum(mae_deltas) / len(pairs) if pairs else None,
            "rmse_delta": rmse_delta,
            "disagreement_count": sum(r["predictions"][arm] != r["predictions"]["persistence"] for r in pairs),
            "largest_five_absolute_error_disagreements": disagreements[:5],
        }
    complete = [r for r in rows if all(r["errors"][arm] is not None for arm in ARMS)]
    metrics["bootstrap"] = _bootstrap(complete, seed)
    metrics["bootstrap"]["common_complete_origin_count"] = len(complete)
    metrics["bootstrap"]["note"] = "Intervals use common complete origins and shared circular block indices across arms."
    return metrics


def _bootstrap(rows: list[dict], seed: int) -> dict:
    import random
    n = len(rows)
    if not n:
        return {"replicates": BOOTSTRAP_REPLICATES, "block_length": BOOTSTRAP_BLOCK, "seed": seed, "intervals": {}}
    rng = random.Random(seed)
    keys = [f"{metric}:{arm}" for metric in ("mae", "rmse") for arm in ARMS]
    keys += [f"{metric}_delta:{arm}" for metric in ("mae", "rmse") for arm in ARMS[1:]]
    samples = {key: [] for key in keys}
    blocks_needed = math.ceil(n / BOOTSTRAP_BLOCK)
    for _ in range(BOOTSTRAP_REPLICATES):
        starts = [rng.randrange(n) for _ in range(blocks_needed)]
        indices = [(start + offset) % n for start in starts for offset in range(BOOTSTRAP_BLOCK)][:n]
        selected = [rows[index] for index in indices]
        errors = {arm: [row["errors"][arm] for row in selected] for arm in ARMS}
        for arm in ARMS:
            samples[f"mae:{arm}"].append(sum(abs(e) for e in errors[arm]) / n)
            samples[f"rmse:{arm}"].append(math.sqrt(sum(e * e for e in errors[arm]) / n))
        for arm in ARMS[1:]:
            samples[f"mae_delta:{arm}"].append(sum(abs(a) - abs(p) for a, p in zip(errors[arm], errors["persistence"])) / n)
            samples[f"rmse_delta:{arm}"].append(
                math.sqrt(sum(a * a for a in errors[arm]) / n) - math.sqrt(sum(p * p for p in errors["persistence"]) / n))
    return {"replicates": BOOTSTRAP_REPLICATES, "block_length": BOOTSTRAP_BLOCK, "seed": seed,
            "interpretation": "descriptive intervals only", "intervals": {key: _percentile_interval(values) for key, values in samples.items()}}


def _git_state() -> tuple[str, bool]:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    clean = not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    return sha, clean


def _scheduled_count(points: list[list[float]]) -> int:
    span = points[-1][0] - points[0][0] - WARMUP_S - HORIZON_S
    return max(0, math.floor((span + 1e-6) / ORIGIN_STEP_S) + 1)


def run(input_path: Path, output_dir: Path, protocol_path: Path, command: list[str]) -> None:
    if output_dir.exists():
        raise ValueError("output directory already exists")
    if not protocol_path.is_file():
        raise ValueError("protocol file is missing")
    sha, clean = _git_state()
    if not clean:
        raise ValueError("actual run requires a clean git worktree")
    output_dir.mkdir(parents=True)
    trail_path = output_dir / "trail.jsonl"
    protocol_copy = output_dir / "protocol.snapshot.md"
    protocol_copy.write_bytes(protocol_path.read_bytes())
    config = {"grid_s": GRID_S, "horizon_s": HORIZON_S, "warmup_s": WARMUP_S,
              "origin_spacing_s": ORIGIN_STEP_S, "arms": list(ARMS), "seed_policy": {"bootstrap": 0, "other": "N/A"},
              "split": {"train_in_sample_diagnostic": [2022], "check": [2023], "same_venue_holdout": [2024]},
              "control": "persistence, latest observed density", "units": "source-declared m^-2",
              "expected_outputs": ["origins.jsonl", "model.json", "metrics.json", "manifest.json", "trail.jsonl", "protocol.snapshot.md", "config.json"]}
    config_path = output_dir / "config.json"
    _json_write(config_path, config)
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "status": "started", "git_sha": sha, "git_clean_before_run": clean, "command": command,
        "started_at_utc": _now(), "host": socket.gethostname(), "python": platform.python_version(),
        "dependencies": "Python standard library plus repository read_density_table",
        "source": {"path": str(input_path.resolve()), "sha256": _sha256(input_path), "size_bytes": input_path.stat().st_size,
                   "format": "source-declared spatial-average density, units m^-2"},
        "protocol": {"path": str(protocol_path.resolve()), "sha256": _sha256(protocol_copy)},
        "config_sha256": _sha256(config_path), "split": config["split"],
        "control": config["control"], "model_identity": "local discrete density forecasts; no external endpoint",
        "expected_outputs": config["expected_outputs"], "seed_policy": config["seed_policy"],
        "source_counts": "pending source validation",
    }
    _json_write(manifest_path, manifest)
    _event(trail_path, "started", git_sha=sha, input_sha256=_sha256(input_path), protocol_sha256=_sha256(protocol_copy))
    try:
        table = read_density_table(input_path)
        series = {entry["year"]: entry["points"] for entry in table["series"]}
        for year in YEARS:
            _grid(series[year])
        counts = {str(year): {
            "source_observations": len(series[year]),
            "trailing_padding_excluded_rows": table["series"][year - 2022]["missing_count"],
            "scheduled_origins": _scheduled_count(series[year]),
            "completed_origins": None, "excluded_origins": 0,
        } for year in YEARS}
        manifest["source_counts"] = counts
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        _event(trail_path, "source_validated", counts=counts, parser_metadata={k: v for k, v in table.items() if k != "series"})
        fit = fit_ar1(series[2022])
        _json_write(output_dir / "model.json", {
            "identity": "local discrete AR(1), fit on adjacent 2022 training observations",
            "parameters": fit, "math": "OLS intercept and phi; population variance of training residuals",
            "phi_diagnostic": "abs(phi) < 1 recorded as a training diagnostic; no stationarity gate",
            "forecast": "finite-step discrete recurrence in closed form; phi == 1 uses last + steps * intercept",
            "units": "source-declared density units m^-2",
        })
        _event(trail_path, "fit_completed", training_year=2022, parameters=fit)
        rows_by_year = {year: forecast_year(series[year], fit, year) for year in YEARS}
        for year in YEARS:
            scheduled = counts[str(year)]["scheduled_origins"]
            if len(rows_by_year[year]) != scheduled or scheduled == 0:
                raise ValueError(f"year {year} completed {len(rows_by_year[year])} of {scheduled} scheduled origins")
            counts[str(year)]["completed_origins"] = len(rows_by_year[year])
        raw_path = output_dir / "origins.jsonl"
        with raw_path.open("x", encoding="utf-8") as stream:
            for year in YEARS:
                for row in rows_by_year[year]:
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        summaries = {str(year): _metrics(rows_by_year[year]) for year in YEARS}
        _json_write(output_dir / "metrics.json", {
            "status": "descriptive benchmark metrics; no generalization, promotion, significance, or safety claim",
            "counts": counts, "years": summaries,
            "caveat": "The series reports spatial-average density in source-declared m^-2. It does not establish sensor accuracy or warning performance.",
        })
        artifacts = list(config["expected_outputs"])
        empty = [name for name in artifacts if not (output_dir / name).is_file() or (output_dir / name).stat().st_size == 0]
        if empty:
            raise ValueError(f"required output artifacts are missing or empty: {empty}")
        _event(trail_path, "completed", counts=counts, artifacts=artifacts)
        # Completion is recorded in the append-only trail. The manifest remains the immutable start record.
    except Exception as exc:
        _event(trail_path, "failed", error_type=type(exc).__name__, reason=str(exc))
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.input, args.output_dir, args.protocol, [sys.argv[0], *(argv or sys.argv[1:])])
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
