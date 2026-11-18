#!/usr/bin/env python3
"""One-shot exploratory native-frame lag analysis, parser revision v2."""

import hashlib
import json
import math
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ARCHIVE = Path("/Users/waichong/projects/crowd-crush-warning/.planning/milestone03-worktree-archive/crowd-m03-controlled-data/data/source/2022impulse_crowd_trajectories_txt.zip")
MEMBER = "2022impulse_crowd_trajectories_txt/1A11_240_n10_fs_d0_p+.txt"
ARCHIVE_SHA256 = "1a197b0fd068f7b9bea3ac53118a31f7fc698f90167d871bb44b8de34b10030f"
MEMBER_SHA256 = "3f5bfdaf2d9c4a07b22b489f8cef3c7d8b3fdc16c9d5a37a32e74ed8b6f627a1"
DECLARED_HEADER = "# id frame x/m y/m z/m markerID"
HEADER = ("id", "frame", "x/m", "y/m", "z/m", "markerID")
LAGS = tuple(range(-10, 11))
EXPECTED_FRAMES = tuple(range(102))
ANCHORS = tuple(range(10, 91))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def parse_text_lines(lines, expected_row_count, expected_frames):
    if len(lines) < 5:
        raise ValueError("missing metadata or declared header")
    if any(not line.startswith("# ") for line in lines[:4]):
        raise ValueError("metadata preamble mismatch")
    if lines[4] != DECLARED_HEADER or tuple(lines[4][2:].split()) != HEADER:
        raise ValueError("declared header mismatch")
    rows = lines[5:]
    if len(rows) != expected_row_count:
        raise ValueError("data row count mismatch")
    traces = {}
    for line in rows:
        fields = line.split()
        if len(fields) != 6:
            raise ValueError("data row width mismatch")
        trace_id, frame_s, x_s, y_s, _unused_z, marker_s = fields
        try:
            trace_id, frame, marker = int(trace_id), int(frame_s), int(marker_s)
            x, y = float(x_s), float(y_s)
        except ValueError as exc:
            raise ValueError("invalid integer identifier/frame/marker or xy value") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("nonfinite xy value")
        if frame not in expected_frames:
            raise ValueError("unexpected frame index")
        track = traces.setdefault(trace_id, {"marker": marker, "xy": {}})
        if track["marker"] != marker or frame in track["xy"]:
            raise ValueError("inconsistent marker or duplicate trace-frame")
        track["xy"][frame] = (x, y)
    if len(traces) != 11:
        raise ValueError("trace count mismatch")
    bags = [track for track in traces.values() if track["marker"] == 778]
    heads = [traces[key] for key in sorted(traces) if traces[key]["marker"] != 778]
    if len(bags) != 1 or len(heads) != 10:
        raise ValueError("bag/head marker role count mismatch")
    for track in traces.values():
        if tuple(sorted(track["xy"])) != expected_frames:
            raise ValueError("trace frame continuity mismatch")
    return bags[0]["xy"], [head["xy"] for head in heads]


def parse_member(data):
    return parse_text_lines(data.decode("utf-8").splitlines(), 1122, EXPECTED_FRAMES)


def step_vectors(track):
    return [(track[t + 1][0] - track[t][0], track[t + 1][1] - track[t][1]) for t in range(101)]


def magnitude(v):
    return math.hypot(v[0], v[1])


def pearson(xs, ys):
    if len(xs) != len(ys) or len(xs) < 2:
        return {"value": None, "reason": "insufficient paired values"}
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    xx, yy = sum(x * x for x in dx), sum(y * y for y in dy)
    if xx == 0 or yy == 0:
        return {"value": None, "reason": "constant input series"}
    return {"value": sum(x * y for x, y in zip(dx, dy)) / math.sqrt(xx * yy), "reason": None}


def lag_profile(bag_q, head_q):
    profile = []
    for lag in LAGS:
        pairs = [(bag_q[t], head_q[t + lag]) for t in ANCHORS]
        corr = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        profile.append({"lag_frames": lag, "n": len(pairs), **corr})
    defined = [row for row in profile if row["value"] is not None]
    if not defined:
        return {"profile": profile, "max_abs_lag_frames": None, "ties": []}
    best = max(abs(row["value"]) for row in defined)
    ties = [row["lag_frames"] for row in defined if abs(row["value"]) == best]
    return {"profile": profile, "max_abs_lag_frames": ties[0] if len(ties) == 1 else None, "ties": ties}


def calculate(bag_track, head_tracks):
    bag_vec = step_vectors(bag_track)
    head_vecs = [step_vectors(head) for head in head_tracks]
    common = [(sum(v[t][0] for v in head_vecs) / 10, sum(v[t][1] for v in head_vecs) / 10) for t in range(101)]
    bag_q = [magnitude(v) for v in bag_vec]
    raw = [[magnitude(v) for v in head] for head in head_vecs]
    residual = [[magnitude((head[t][0] - common[t][0], head[t][1] - common[t][1])) for t in range(101)] for head in head_vecs]
    common_q = [magnitude(v) for v in common]
    raw_profiles = [lag_profile(bag_q, q) for q in raw]
    residual_profiles = [lag_profile(bag_q, q) for q in residual]
    common_profile = lag_profile(bag_q, common_q)
    return {
        "scope": "exploratory source-native co-movement; native frames only",
        "positive_lag": "head later",
        "anchor_support": {"first_step_index": 10, "last_step_index": 90, "n_per_lag": 81},
        "lags_frames": list(LAGS),
        "head_trace_count": 10,
        "raw_head_magnitude": {f"head_{i:02d}": value for i, value in enumerate(raw_profiles, 1)},
        "common_mode_magnitude": common_profile,
        "residual_head_magnitude": {f"head_{i:02d}": value for i, value in enumerate(residual_profiles, 1)},
        "lag_zero_controls": {
            "raw_head": {name: series["profile"][10] for name, series in ((f"head_{i:02d}", p) for i, p in enumerate(raw_profiles, 1))},
            "common_mode": common_profile["profile"][10],
            "residual_head": {name: series["profile"][10] for name, series in ((f"head_{i:02d}", p) for i, p in enumerate(residual_profiles, 1))},
        },
    }


def append_event(event, **fields):
    fields.setdefault("utc", datetime.now(timezone.utc).isoformat())
    with (OUT / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": event, **fields}, sort_keys=True) + "\n")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    append_event("v2_run_started", utc=started)
    try:
        archive_before = sha256_bytes(ARCHIVE.read_bytes())
        if archive_before != ARCHIVE_SHA256:
            raise ValueError("archive SHA-256 mismatch")
        with zipfile.ZipFile(ARCHIVE) as zf:
            member_data = zf.read(MEMBER)
        member_hash = sha256_bytes(member_data)
        if member_hash != MEMBER_SHA256:
            raise ValueError("member SHA-256 mismatch")
        bag, heads = parse_member(member_data)
        result = calculate(bag, heads)
        archive_after = sha256_bytes(ARCHIVE.read_bytes())
        if archive_after != archive_before:
            raise ValueError("archive changed during run")
        result["input_checks"] = {
            "archive_sha256_before": archive_before,
            "archive_sha256_after": archive_after,
            "member_sha256": member_hash,
            "member_bytes": len(member_data),
            "metadata_lines": 4,
            "declared_header": DECLARED_HEADER,
            "data_rows": 1122,
            "frame_range": [0, 101],
            "trace_count": 11,
            "bag_count": 1,
            "head_count": 10,
            "z_used": False,
            "source_rows_written": False,
        }
        result["execution"] = {
            "python": sys.version,
            "platform": platform.platform(),
            "model_identity": "local deterministic Python standard library; no model endpoint",
            "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
        }
        encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        (OUT / "lag_profiles.json").write_text(encoded, encoding="utf-8")
        append_event("v2_analysis_complete", profiles_sha256=sha256_bytes(encoded.encode()))
        return 0
    except Exception as exc:
        append_event("v2_run_blocked", error_type=type(exc).__name__, reason=str(exc))
        raise


def smoke():
    # In-memory parser and calculation checks only; not an experimental control.
    rows = ["# metadata one", "# metadata two", "# metadata three", "# metadata four", DECLARED_HEADER]
    for frame in range(2):
        rows.append(f"0 {frame} {frame}.0 0.0 ambiguous-z 778")
        for trace_id in range(1, 11):
            rows.append(f"{trace_id} {frame} {frame + trace_id}.0 {trace_id}.0 ignored 1")
    bag, heads = parse_text_lines(rows, 22, (0, 1))
    assert len(bag) == 2 and len(heads) == 10
    assert bag[1] == (1.0, 0.0) and heads[0][0] == (1.0, 1.0)
    assert len(ANCHORS) == 81 and LAGS == tuple(range(-10, 11))
    assert pearson([2.0, 2.0], [1.0, 3.0]) == {"value": None, "reason": "constant input series"}
    assert pearson([1.0, 2.0], [1.0, 2.0])["value"] == 1.0
    alternating = [float(i % 2) for i in range(101)]
    tied = lag_profile(alternating, alternating)
    assert len(tied["profile"]) == 21 and tied["profile"][10]["n"] == 81
    assert tied["ties"] == list(LAGS) and tied["max_abs_lag_frames"] is None
    json.dumps({"smoke": True, "profile": tied}, allow_nan=False)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--smoke":
        smoke()
    else:
        raise SystemExit(run())
