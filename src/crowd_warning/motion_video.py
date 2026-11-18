"""Offline image-space motion diagnostics for local video files."""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import numpy as np

from .video import inspect_video


_SHOWINFO_FRAME = re.compile(
    r"Parsed_showinfo_\d+.*?\bn:\s*(\d+)\s+pts:\s*(NOPTS|-?\d+)\s+pts_time:\s*(\S+)"
)
_SHOWINFO_TIME_BASE = re.compile(r"config in time_base:\s*(\d+/\d+)")
_RAW_MEMORY_LIMIT = 128 * 1024 * 1024


def inspect_motion_video(
    path: str | Path,
    *,
    sample_interval_s: float = 1.0,
    width: int = 320,
    patch_size: int = 16,
    search_radius: int = 4,
) -> dict[str, Any]:
    """Return anonymous image-pixel diagnostics between timestamped samples."""
    if isinstance(sample_interval_s, bool) or not isinstance(sample_interval_s, (int, float)):
        raise ValueError("sample_interval_s must be a positive finite number")
    sample_interval_s = float(sample_interval_s)
    if not math.isfinite(sample_interval_s) or sample_interval_s <= 0:
        raise ValueError("sample_interval_s must be a positive finite number")
    for name, value in (("width", width), ("patch_size", patch_size)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if isinstance(search_radius, bool) or not isinstance(search_radius, int) or search_radius < 0:
        raise ValueError("search_radius must be a non-negative integer")

    source = Path(path)
    inspection = inspect_video(source)
    native_width = inspection["stream"].get("width")
    native_height = inspection["stream"].get("height")
    if not isinstance(native_width, int) or not isinstance(native_height, int) or min(native_width, native_height) <= 0:
        raise ValueError("video stream has invalid dimensions")
    frames = inspection["frames"]
    if len(frames) > 2000:
        raise ValueError("video exceeds the 2000 native-frame limit")
    timestamps = [frame.get("pts_time") for frame in frames]
    if timestamps and all(isinstance(value, (int, float)) and math.isfinite(value) for value in timestamps):
        if max(timestamps) - min(timestamps) > 60.0:
            raise ValueError("video exceeds the 60-second limit")

    scaled_height = max(2, int(round(width * native_height / native_width / 2.0)) * 2)
    frame_bytes = width * scaled_height
    raw_bytes = len(frames) * frame_bytes
    if raw_bytes > _RAW_MEMORY_LIMIT:
        raise ValueError("scaled native frames exceed the 128 MiB raw decode limit")
    result: dict[str, Any] = {
        "input": inspection["input"],
        "timing_status": inspection["timing_status"],
        "native_dimensions": {"width": native_width, "height": native_height},
        "scaled_dimensions": {"width": width, "height": scaled_height},
        "transform": {"method": "aspect-preserving resize to explicit even dimensions", "scale_x": width / native_width, "scale_y": scaled_height / native_height},
        "sample_interval_s": sample_interval_s,
        "pairs": [],
        "scope_limits": [
            "image-pixel diagnostics only; camera motion, visibility, and calibration are unknown",
            "does not estimate world speed, physical force, crowd risk, or safety",
        ],
    }
    if inspection["timing_status"] != "ok":
        result["motion_status"] = "abstain"
        result["abstention_reason"] = "video timing is not admissible"
        return result
    if not frames:
        result["motion_status"] = "abstain"
        result["abstention_reason"] = "video contains no frames"
        return result

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise OSError("required local tool not found: ffmpeg")
    digest_before = hashlib.sha256(source.read_bytes()).hexdigest()
    command = [
        ffmpeg, "-v", "info", "-xerror", "-nostdin", "-copyts", "-noautorotate",
        "-i", str(source), "-map", "0:v:0", "-an", "-sn", "-dn", "-vf",
        f"showinfo,scale={width}:{scaled_height},setsar=1", "-fps_mode", "passthrough",
        "-pix_fmt", "gray", "-f", "rawvideo", "-",
    ]
    try:
        decoded = subprocess.run(command, capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"ffmpeg motion decode failed: {exc}") from None
    if decoded.returncode != 0:
        detail = decoded.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"ffmpeg motion decode failed: {detail or 'nonzero exit'}")
    expected_bytes = len(frames) * frame_bytes
    if len(decoded.stdout) != expected_bytes:
        raise ValueError(
            f"ffmpeg motion decode returned {len(decoded.stdout)} bytes; expected {expected_bytes}"
        )
    digest_after = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest_after != digest_before or digest_after != inspection["input"]["sha256"]:
        raise ValueError("video source changed during inspection")

    stderr_text = decoded.stderr.decode("utf-8", errors="replace")
    decoder_time_base: Fraction | None = None
    decoder_pts: list[dict[str, Any]] = []
    for line in stderr_text.splitlines():
        time_base_match = _SHOWINFO_TIME_BASE.search(line)
        if time_base_match:
            try:
                decoder_time_base = Fraction(time_base_match.group(1))
            except (ValueError, ZeroDivisionError):
                raise ValueError("ffmpeg showinfo reported an invalid time base") from None
        frame_match = _SHOWINFO_FRAME.search(line)
        if frame_match:
            frame_number, pts_text, pts_time_text = frame_match.groups()
            if pts_text == "NOPTS":
                raise ValueError("ffmpeg showinfo reported a frame without native PTS")
            try:
                pts_time = float(pts_time_text)
            except ValueError:
                raise ValueError("ffmpeg showinfo reported an invalid native PTS time") from None
            if not math.isfinite(pts_time):
                raise ValueError("ffmpeg showinfo reported a non-finite native PTS time")
            decoder_pts.append({
                "native_index": int(frame_number),
                "pts": int(pts_text),
                "pts_time_s": pts_time,
            })
    if decoder_time_base is None or decoder_time_base <= 0:
        raise ValueError("ffmpeg showinfo did not report a valid native time base")
    if len(decoder_pts) != len(frames):
        raise ValueError("ffmpeg showinfo frame count does not match admitted native frames")
    expected_time_base = Fraction(inspection["stream"]["time_base"])
    if decoder_time_base != expected_time_base:
        raise ValueError("ffmpeg showinfo time base differs from admitted stream time base")
    for index, (reported, admitted) in enumerate(zip(decoder_pts, timestamps)):
        if reported["native_index"] != index:
            raise ValueError("ffmpeg showinfo native frame order does not match admitted frames")
        exact_time = reported["pts"] * decoder_time_base
        tolerance = float(decoder_time_base) / 2 + max(1e-9, abs(float(admitted)) * 1e-12)
        if abs(float(exact_time) - float(admitted)) > tolerance:
            raise ValueError(f"ffmpeg showinfo PTS mismatch at native frame {index}")

    from .motion import estimate_motion_pair

    image_frames = np.frombuffer(decoded.stdout, dtype=np.uint8).reshape(
        (len(frames), scaled_height, width)
    )

    selected: list[int] = [0]
    last_pts = float(timestamps[0])
    tolerance = max(1e-9, abs(last_pts) * 1e-12)
    for index in range(1, len(timestamps)):
        pts = float(timestamps[index])
        if pts + tolerance >= last_pts + sample_interval_s:
            selected.append(index)
            last_pts = pts
            tolerance = max(1e-9, abs(last_pts) * 1e-12)

    pairs: list[dict[str, Any]] = []
    for previous_index, current_index in zip(selected, selected[1:]):
        previous_pts = float(timestamps[previous_index])
        current_pts = float(timestamps[current_index])
        estimate = estimate_motion_pair(
            image_frames[previous_index],
            image_frames[current_index],
            dt_s=current_pts - previous_pts,
            patch_size=patch_size,
            search_radius=search_radius,
        )
        pairs.append({
            "previous_native_index": previous_index,
            "current_native_index": current_index,
            "previous_pts_s": previous_pts,
            "current_pts_s": current_pts,
            "actual_dt_s": current_pts - previous_pts,
            "motion": estimate,
        })
    result["pairs"] = pairs
    result["decoder_pts"] = {
        "time_base": f"{decoder_time_base.numerator}/{decoder_time_base.denominator}",
        "frames": decoder_pts,
        "warnings": [
            line.strip() for line in stderr_text.splitlines()
            if "warning" in line.lower() or "error" in line.lower()
        ],
    }
    result["motion_status"] = "ok"
    return result
