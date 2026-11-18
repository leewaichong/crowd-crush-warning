"""Offline video timestamp and decode inspection.

This reports container/stream metadata and decoder timestamp observations only.
It does not assess calibration, visibility, camera motion, or crowd safety.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any


def _tool_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "-version"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError(f"could not identify {executable}: {exc}") from None
    if result.returncode != 0:
        raise ValueError(f"{executable} version probe failed: {result.stderr.strip()}")
    return result.stdout.splitlines()[0] if result.stdout.splitlines() else "unknown"


def _strict_json(text: str, label: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        return json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"malformed {label} JSON: {exc}") from None


def _actual_pts(frame: dict[str, Any]) -> float | None:
    value = frame.get("pts_time")
    if value is None:
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return timestamp if math.isfinite(timestamp) else None


def inspect_video(path: str | Path, *, max_gap_s: float | None = None) -> dict[str, Any]:
    """Inspect every frame's actual presentation timestamp and decode the video stream.

    A completed inspection returns ``timing_status`` as ``ok`` or ``abstain``.
    Missing/invalid PTS, duplicates, or decreasing PTS cause abstention. A
    configured positive ``max_gap_s`` reports larger observed timestamp deltas;
    it does not infer missing physical frames. CLI exit status is zero for either
    completed timing status and nonzero for tool, probe, decode, or input errors.
    """
    if max_gap_s is not None:
        if isinstance(max_gap_s, bool) or not isinstance(max_gap_s, (int, float)):
            raise ValueError("max_gap_s must be a positive finite number")
        max_gap_s = float(max_gap_s)
        if not math.isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError("max_gap_s must be a positive finite number")

    source = Path(path)
    if not source.is_file():
        raise OSError(f"input is not a local file: {source}")
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        missing = ", ".join(name for name, tool in (("ffprobe", ffprobe), ("ffmpeg", ffmpeg)) if not tool)
        raise OSError(f"required local tool not found: {missing}")

    payload = source.read_bytes()
    ffprobe_version = _tool_version(ffprobe)
    ffmpeg_version = _tool_version(ffmpeg)
    probe_command = [
        ffprobe, "-v", "error", "-select_streams", "v:0", "-show_streams",
        "-show_frames", "-show_entries",
        "stream=codec_name,width,height,time_base,r_frame_rate,avg_frame_rate,nb_frames:frame=pts_time",
        "-of", "json", str(source),
    ]
    try:
        probe = subprocess.run(
            probe_command, capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"ffprobe failed: {exc}") from None
    if probe.returncode != 0 or probe.stderr.strip():
        raise ValueError(f"ffprobe failed: {probe.stderr.strip() or 'nonzero exit'}")
    document = _strict_json(probe.stdout, "ffprobe")
    streams = document.get("streams") if isinstance(document, dict) else None
    if not isinstance(streams, list) or not streams or not isinstance(streams[0], dict):
        raise ValueError("ffprobe returned no first video stream")
    stream = streams[0]
    frames_raw = document.get("frames")
    if not isinstance(frames_raw, list) or any(not isinstance(frame, dict) for frame in frames_raw):
        raise ValueError("ffprobe returned malformed decoded-frame metadata")

    decode_command = [
        ffmpeg, "-v", "error", "-xerror", "-i", str(source), "-map", "0:v:0",
        "-an", "-sn", "-dn", "-f", "null", "-",
    ]
    try:
        decode = subprocess.run(
            decode_command, capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"ffmpeg decode failed: {exc}") from None
    if decode.returncode != 0 or decode.stderr.strip():
        raise ValueError(f"ffmpeg decode failed: {decode.stderr.strip() or 'nonzero exit'}")

    pts_values = [_actual_pts(frame) for frame in frames_raw]
    missing_count = sum(value is None for value in pts_values)
    seen: set[float] = set()
    duplicate_count = 0
    nonmonotonic_count = 0
    deltas: list[dict[str, Any]] = []
    excessive_gaps: list[dict[str, Any]] = []
    previous: float | None = None
    previous_index: int | None = None
    for index, timestamp in enumerate(pts_values, start=1):
        if timestamp is None:
            previous = None
            previous_index = None
            continue
        if timestamp in seen:
            duplicate_count += 1
        seen.add(timestamp)
        if previous is not None:
            delta = timestamp - previous
            record = {"from_frame": previous_index, "to_frame": index, "delta_s": delta}
            deltas.append(record)
            if delta < 0:
                nonmonotonic_count += 1
            elif max_gap_s is not None and delta > max_gap_s:
                excessive_gaps.append(record.copy())
        previous, previous_index = timestamp, index

    timing_status = (
        "abstain"
        if not pts_values or missing_count or duplicate_count or nonmonotonic_count
        else "ok"
    )
    if max_gap_s is not None and excessive_gaps:
        timing_status = "abstain"
    result = {
        "input": {"path": str(source), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
        "tools": {"ffprobe": ffprobe_version, "ffmpeg": ffmpeg_version},
        "stream": {
            "codec_name": stream.get("codec_name"), "width": stream.get("width"),
            "height": stream.get("height"), "time_base": stream.get("time_base"),
            "r_frame_rate": stream.get("r_frame_rate"), "avg_frame_rate": stream.get("avg_frame_rate"),
            "nb_frames": stream.get("nb_frames"),
        },
        "probe": {"status": "ok", "error": None},
        "decode": {"status": "ok", "error": None},
        "timing_status": timing_status,
        "frame_count": len(pts_values),
        "frames": [{"pts_time": value} for value in pts_values],
        "missing_pts_count": missing_count,
        "duplicate_pts_count": duplicate_count,
        "nonmonotonic_pts_count": nonmonotonic_count,
        "observed_deltas_s": deltas,
        "gap_assessment": {
            "configured": max_gap_s is not None,
            "max_gap_s": max_gap_s,
            "exceeding_intervals": excessive_gaps,
            "interpretation": "observed timestamp intervals only; not inferred missing physical frames",
        },
        "scope_limits": [
            "does not establish rights clearance beyond source-record metadata",
            "does not establish calibration, visibility, camera motion, or physical force",
            "does not establish safety or warning effectiveness",
        ],
    }
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"inspection result is not finite JSON: {exc}") from None
    return result
