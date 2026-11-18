"""Event-level evaluation helpers for offline research runs.

These metrics describe proxy forecast crossings against supplied event labels.
They do not measure physical force, safety, or calibrated danger.
"""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
from datetime import datetime
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def match_events(
    forecasts: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    *,
    horizon_s: float,
) -> dict[str, Any]:
    """Match each event to the earliest eligible forecast in its preceding horizon.

    Forecast rows require ``timestamp_s`` and ``zone_id``. Events require
    ``timestamp_s`` and ``zone_id``. One forecast and one event can be matched
    at most once; matching is chronological within each zone.
    """
    if not math.isfinite(horizon_s) or horizon_s < 0:
        raise ValueError("horizon_s must be finite and non-negative")
    fs = _validated_rows(forecasts, "forecast")
    es = _validated_rows(events, "event")
    unused = set(range(len(fs)))
    matches = []
    for ei, event in sorted(enumerate(es), key=lambda pair: (pair[1]["timestamp_s"], str(pair[1]["zone_id"]))):
        candidates = [
            i for i in unused
            if fs[i]["zone_id"] == event["zone_id"]
            and 0 <= event["timestamp_s"] - fs[i]["timestamp_s"] <= horizon_s
        ]
        if candidates:
            fi = min(candidates, key=lambda i: (fs[i]["timestamp_s"], i))
            unused.remove(fi)
            matches.append({
                "event_index": ei,
                "forecast_index": fi,
                "lead_time_s": event["timestamp_s"] - fs[fi]["timestamp_s"],
            })
    return {
        "matches": matches,
        "matched_event_count": len(matches),
        "missed_event_count": len(es) - len(matches),
        "false_alarm_count": len(unused),
        "lead_times_s": [m["lead_time_s"] for m in matches],
        "mean_lead_time_s": (sum(m["lead_time_s"] for m in matches) / len(matches)) if matches else None,
    }


def alarm_episodes(
    forecasts: Sequence[Mapping[str, Any]], *, episode_gap_s: float
) -> dict[str, Any]:
    """Collapse repeated forecast rows into alarm episodes by zone.

    Rows are ordered by timestamp, then input order. A new episode begins when
    the gap from the preceding row in that zone is greater than episode_gap_s.
    Duplicate (zone_id, timestamp_s) rows count once; the first input row wins.
    """
    if not math.isfinite(episode_gap_s) or episode_gap_s < 0:
        raise ValueError("episode_gap_s must be finite and non-negative")
    rows = _validated_rows(forecasts, "forecast")
    seen = set()
    unique = []
    duplicates = []
    for index, row in enumerate(rows):
        zone = row["zone_id"]
        if not isinstance(zone, (str, int, float, bool)) or (isinstance(zone, float) and not math.isfinite(zone)):
            raise ValueError(f"forecast row {index} zone_id must be a finite scalar")
        key = (type(zone).__name__, str(zone), row["timestamp_s"])
        if key in seen:
            duplicates.append(index)
            continue
        seen.add(key)
        unique.append((index, row))
    unique.sort(key=lambda item: (type(item[1]["zone_id"]).__name__, str(item[1]["zone_id"]),
                                  item[1]["timestamp_s"], item[0]))
    episodes = []
    for index, row in unique:
        if (episodes and type(episodes[-1]["zone_id"]) is type(row["zone_id"])
                and episodes[-1]["zone_id"] == row["zone_id"]
                and row["timestamp_s"] - episodes[-1]["end_timestamp_s"] <= episode_gap_s):
            episodes[-1]["end_timestamp_s"] = row["timestamp_s"]
            episodes[-1]["forecast_indices"].append(index)
        else:
            episodes.append({"zone_id": row["zone_id"], "start_timestamp_s": row["timestamp_s"],
                             "end_timestamp_s": row["timestamp_s"], "forecast_indices": [index]})
    return {"episodes": episodes, "duplicate_forecast_indices": duplicates,
            "forecast_count": len(rows), "unique_forecast_count": len(unique)}


def match_alarm_episodes(
    forecasts: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]], *,
    horizon_s: float, episode_gap_s: float,
) -> dict[str, Any]:
    """Match selected alarm rows to episode starts, one episode and event at most once.

    These inputs must already be alarm rows, not all probability forecasts.
    If rows provide forecast_origin_s, it must equal timestamp_s. Any
    input_cutoff_s must be finite and no later than the forecast origin.
    Matching further requires the episode start to be at or before the event
    outcome and within horizon_s.
    """
    for index, row in enumerate(forecasts):
        if "input_cutoff_s" in row or "forecast_origin_s" in row:
            try:
                origin = float(row["timestamp_s"])
                cutoff = float(row["input_cutoff_s"]) if "input_cutoff_s" in row else origin
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"forecast row {index} requires numeric chronology fields") from exc
            if not math.isfinite(cutoff) or not math.isfinite(origin) or cutoff > origin:
                raise ValueError(f"forecast row {index} requires input_cutoff_s <= forecast origin")
            if "forecast_origin_s" in row:
                try:
                    declared_origin = float(row["forecast_origin_s"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"forecast row {index} forecast_origin_s must be numeric") from exc
                if not math.isfinite(declared_origin) or declared_origin != origin:
                    raise ValueError(f"forecast row {index} forecast_origin_s must equal timestamp_s")
    episodic = alarm_episodes(forecasts, episode_gap_s=episode_gap_s)
    rows = [{"timestamp_s": ep["start_timestamp_s"], "zone_id": ep["zone_id"]}
            for ep in episodic["episodes"]]
    result = match_events(rows, events, horizon_s=horizon_s)
    for match in result["matches"]:
        match["episode_index"] = match.pop("forecast_index")
        match["forecast_indices"] = episodic["episodes"][match["episode_index"]]["forecast_indices"]
    result["false_alarm_count"] = len(episodic["episodes"]) - result["matched_event_count"]
    result["episode_count"] = len(episodic["episodes"])
    result["duplicate_forecast_indices"] = episodic["duplicate_forecast_indices"]
    return result


def brier_score(predictions: Sequence[float], outcomes: Sequence[int | bool | None]) -> float | None:
    """Return the scalar score. Rows without labels do not enter the score."""
    return brier_accounting(predictions, outcomes)["score"]


def brier_accounting(predictions: Sequence[float], outcomes: Sequence[int | bool | None]) -> dict[str, Any]:
    """Return Brier score and explicit counts for labelled and excluded rows."""
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have equal length")
    pairs = []
    excluded = []
    for probability, outcome in zip(predictions, outcomes):
        try:
            p = float(probability)
        except (TypeError, ValueError) as exc:
            raise ValueError("all predictions must be numeric probabilities") from exc
        if not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("predictions must be finite probabilities in [0, 1]")
        if outcome not in (0, 1, False, True):
            if outcome is None:
                excluded.append({"index": len(pairs) + len(excluded), "reason": "missing_outcome"})
                continue
            raise ValueError("outcomes must be binary or None")
        pairs.append((p - int(outcome)) ** 2)
    return {
        "score": sum(pairs) / len(pairs) if pairs else None,
        "total_count": len(predictions),
        "scored_count": len(pairs),
        "excluded_count": len(excluded),
        "excluded": excluded,
    }


def false_alarms_per_monitoring_hour(false_alarm_count: int, *, monitoring_hours: float) -> float:
    """Normalize supplied unmatched forecast count by explicitly observed hours."""
    if isinstance(false_alarm_count, bool) or not isinstance(false_alarm_count, int) or false_alarm_count < 0:
        raise ValueError("false_alarm_count must be a non-negative integer")
    if not math.isfinite(monitoring_hours) or monitoring_hours <= 0:
        raise ValueError("monitoring_hours must be finite and positive")
    return false_alarm_count / monitoring_hours


def monitoring_exposure(intervals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Account for disjoint declared timeline segments [start_s, end_s).

    Each row requires finite increasing endpoints and a boolean valid flag.
    All overlaps are rejected, including segments marked invalid. Invalid
    segments are excluded from exposure and reported by index and duration.
    """
    segments = []
    excluded = []
    for index, interval in enumerate(intervals):
        try:
            start, end = float(interval["start_s"]), float(interval["end_s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"interval {index} requires numeric start_s and end_s") from exc
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError(f"interval {index} endpoints must be finite")
        if end <= start:
            raise ValueError(f"interval {index} must have end_s greater than start_s")
        duration = end - start
        if not math.isfinite(duration):
            raise ValueError(f"interval {index} duration must be finite")
        if not isinstance(interval.get("valid"), bool):
            raise ValueError(f"interval {index} requires a boolean valid flag")
        segments.append((start, end, index, interval["valid"], duration))
    segments.sort()
    for previous, current in zip(segments, segments[1:]):
        if current[0] < previous[1]:
            raise ValueError(f"declared timeline segments overlap: {previous[2]} and {current[2]}")
    valid = [segment for segment in segments if segment[3]]
    invalid = [segment for segment in segments if not segment[3]]
    seconds = sum(segment[4] for segment in valid)
    excluded_seconds = sum(segment[4] for segment in invalid)
    if not math.isfinite(seconds) or not math.isfinite(excluded_seconds):
        raise ValueError("accumulated interval durations must be finite")
    excluded = [{"index": index, "reason": "invalid_period", "duration_s": duration}
                for _, _, index, _, duration in invalid]
    return {"monitoring_seconds": seconds, "monitoring_hours": seconds / 3600,
            "excluded_seconds": excluded_seconds,
            "included_interval_indices": [segment[2] for segment in valid],
            "excluded": excluded, "excluded_count": len(excluded)}


def split_by_venue_and_event(
    rows: Sequence[Mapping[str, Any]], *, train_fraction: float = 0.7, seed: int = 0,
    input_cutoff_field: str = "input_cutoff_s", forecast_origin_field: str = "forecast_origin_s",
    outcome_time_field: str = "outcome_timestamp_s",
) -> dict[str, list[Mapping[str, Any]]]:
    """Split rows by venue, then event, and reject chronology violations.

    Venue IDs are sorted by type name and string value before seeded splitting.
    Rows require venue_id, event_id, and finite chronology values satisfying
    input_cutoff <= forecast_origin <= outcome timestamp.
    """
    import random
    if not math.isfinite(train_fraction) or not 0 <= train_fraction <= 1:
        raise ValueError("train_fraction must be in [0, 1]")
    venues: dict[Any, list[Mapping[str, Any]]] = {}
    for index, row in enumerate(rows):
        if row.get("venue_id") is None or row.get("event_id") is None:
            raise ValueError(f"row {index} requires non-null venue_id and event_id")
        try:
            cutoff, origin, outcome = (float(row[key]) for key in
                (input_cutoff_field, forecast_origin_field, outcome_time_field))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {index} requires numeric chronology fields") from exc
        if not all(math.isfinite(x) for x in (cutoff, origin, outcome)) or not cutoff <= origin <= outcome:
            raise ValueError(f"row {index} chronology must satisfy input_cutoff <= forecast_origin <= outcome")
        venues.setdefault(row["venue_id"], []).append(row)
    ids = sorted(venues, key=lambda value: (type(value).__name__, str(value)))
    random.Random(seed).shuffle(ids)
    cut = int(len(ids) * train_fraction)
    train_ids, test_ids = set(ids[:cut]), set(ids[cut:])
    # Event identities must not cross venue partitions.
    train_events = {r["event_id"] for v in train_ids for r in venues[v]}
    test_events = {r["event_id"] for v in test_ids for r in venues[v]}
    if train_events & test_events:
        raise ValueError("event_id appears in both venue partitions")
    return {"train": [r for v in ids[:cut] for r in venues[v]],
            "test": [r for v in ids[cut:] for r in venues[v]]}


def disjoint_event_splits(
    events: Sequence[Mapping[str, Any]], *, train_fraction: float = 0.7, seed: int = 0
) -> dict[str, list[Mapping[str, Any]]]:
    """Split by event identity, keeping every observation of an event together.

    Rows require ``event_id``. Event IDs are deterministically shuffled using
    stdlib randomness seeded by ``seed``. No event appears in both partitions.
    """
    import random

    if not math.isfinite(train_fraction) or not 0 <= train_fraction <= 1:
        raise ValueError("train_fraction must be in [0, 1]")
    groups: dict[Any, list[Mapping[str, Any]]] = {}
    for row in events:
        if "event_id" not in row or row["event_id"] is None:
            raise ValueError("each row requires a non-null event_id")
        groups.setdefault(row["event_id"], []).append(row)
    ids = list(groups)
    random.Random(seed).shuffle(ids)
    cut = int(len(ids) * train_fraction)
    return {
        "train": [row for event_id in ids[:cut] for row in groups[event_id]],
        "test": [row for event_id in ids[cut:] for row in groups[event_id]],
    }


def input_sha256(path: str) -> str:
    """Hash an input file without retaining or printing its contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_run_provenance(provenance: Mapping[str, Any], *, repo_path: str = ".") -> dict[str, Any]:
    """Check recorded run metadata against the current git checkout.

    Required fields include a SHA-256 input checksum and either input_path or
    input_manifest. Paths are resolved relative to repo_path unless absolute.
    Files are checked for readability and nonzero size. External model identity
    is recorded only; this helper cannot independently verify it.
    """
    required = ("git_sha", "clean", "command", "timestamp", "input_sha256",
                "model_endpoint", "model_id", "output_artifacts", "raw_outputs", "baseline")
    missing = [key for key in required if key not in provenance or provenance[key] in (None, "", [])]
    if not provenance.get("input_path") and not provenance.get("input_manifest"):
        missing.append("input_path or input_manifest")
    if missing:
        return {"verified": False, "errors": ["missing required fields: " + ", ".join(missing)], "scope": {"repo_path": os.path.abspath(repo_path), "external_model_identity_verified": False}}
    errors = []
    for field in ("command", "model_endpoint", "model_id", "baseline"):
        if not isinstance(provenance[field], str) or not provenance[field].strip():
            errors.append(f"{field} must be a non-empty string")
    try:
        stamp = provenance["timestamp"]
        if not isinstance(stamp, str) or not stamp.strip():
            raise ValueError
        if "T" not in stamp and " " not in stamp:
            raise ValueError
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        errors.append("timestamp must be a valid ISO 8601 datetime")
    if not isinstance(provenance["input_sha256"], str) or not _is_sha256(provenance["input_sha256"]):
        errors.append("input_sha256 must be a 64-character SHA-256 hex digest")
    input_paths = []
    if provenance.get("input_manifest"):
        manifest = provenance["input_manifest"]
        if not isinstance(manifest, list) or not manifest:
            errors.append("input_manifest must be a non-empty list")
        else:
            for entry in manifest:
                if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str) or not _is_sha256(entry.get("sha256")):
                    errors.append("each input_manifest entry requires path and SHA-256 sha256")
                    continue
                input_paths.append((entry["path"], entry["sha256"], "manifest"))
    else:
        input_path = provenance["input_path"]
        if not isinstance(input_path, str) or not input_path.strip():
            errors.append("input_path must be a non-empty path string")
        elif _is_sha256(provenance.get("input_sha256")):
            input_paths.append((input_path, provenance["input_sha256"], "input"))
    if provenance.get("input_manifest") and _is_sha256(provenance.get("input_sha256")):
        combined = hashlib.sha256("\n".join(f"{p}\0{digest}" for p, digest, _ in input_paths).encode()).hexdigest()
        if combined != provenance["input_sha256"]:
            errors.append("input_sha256 does not match canonical input_manifest digest")
    files_checked = {"inputs": [], "output_artifacts": [], "raw_outputs": []}
    for path, expected, category in input_paths:
        resolved = _resolve_provenance_path(path, repo_path)
        error = _check_file(resolved, expected)
        if error:
            errors.append(f"input {path}: {error}")
        else:
            files_checked["inputs"].append(os.path.abspath(resolved))
    for field in ("output_artifacts", "raw_outputs"):
        paths = provenance[field]
        if not isinstance(paths, (list, tuple)) or not paths:
            errors.append(f"{field} must be a non-empty list of file paths")
            continue
        for path in paths:
            if not isinstance(path, str) or not path.strip():
                errors.append(f"{field} contains an invalid path")
                continue
            resolved = _resolve_provenance_path(path, repo_path)
            error = _check_file(resolved)
            if error:
                errors.append(f"{field} {path}: {error}")
            else:
                files_checked[field].append(os.path.abspath(resolved))
    try:
        sha = subprocess.check_output(["git", "-C", repo_path, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "-C", repo_path, "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        return {"verified": False, "errors": errors + ["git state unavailable"], "scope": {"repo_path": os.path.abspath(repo_path), "files_checked": files_checked, "external_model_identity_verified": False}}
    if provenance["git_sha"] != sha:
        errors.append("git_sha does not match current HEAD")
    if provenance["clean"] is not True or dirty:
        errors.append("recorded or current git state is not clean")
    return {"verified": not errors, "errors": errors, "current_git_sha": sha,
            "current_clean": not dirty, "scope": {"repo_path": os.path.abspath(repo_path),
            "files_checked": files_checked, "external_model_identity_verified": False}}


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def _resolve_provenance_path(path: str, repo_path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(repo_path, path)


def _check_file(path: str, expected_sha256: str | None = None) -> str | None:
    try:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return "file is missing, not regular, or empty"
        with open(path, "rb") as source:
            digest = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return "file is not readable"
    if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
        return "SHA-256 does not match recorded checksum"
    return None


def _validated_rows(rows: Iterable[Mapping[str, Any]], kind: str) -> list[dict[str, Any]]:
    result = []
    for index, row in enumerate(rows):
        if "timestamp_s" not in row or "zone_id" not in row:
            raise ValueError(f"{kind} row {index} requires timestamp_s and zone_id")
        try:
            timestamp = float(row["timestamp_s"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{kind} row {index} has invalid timestamp_s") from exc
        if not math.isfinite(timestamp):
            raise ValueError(f"{kind} row {index} has invalid timestamp_s")
        if row["zone_id"] is None:
            raise ValueError(f"{kind} row {index} has null zone_id")
        result.append({**row, "timestamp_s": timestamp})
    return result
