"""Read the inspected Lyon TopView trajectory text member from Zenodo's ZIP."""

from __future__ import annotations

import hashlib
import math
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


DEFAULT_MEMBER = "Data_Madras/TopView_trajectories/TopView_1B.txt"
_COLUMNS = ("id", "frame", "x/m", "y/m", "z/m", "id_global", "t/s",
            "x_RGF", "y_RGF")
_SEQUENCE_LINE = re.compile(r"# trajectory data of sequence (\S+)\Z")
_FPS_LINE = re.compile(r"# recorded at ([0-9]+) fps\Z")
_START_LINE = re.compile(r"# recording started at (\S+)\Z")
_INTEGER = re.compile(r"[+-]?\d+\Z")
_TIME_REFERENCE = "Friday, Dec. 9th at 20:00:00 (UTC+1)"


class LyonDataError(ValueError):
    """Invalid archive, header, or trajectory row."""


def _archive_checksums(path: Path) -> tuple[int, str, str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                sha256.update(chunk)
                md5.update(chunk)
    except OSError as exc:
        raise LyonDataError(f"cannot read Lyon archive: {path}") from exc
    return size, sha256.hexdigest(), md5.hexdigest()


def _finite_number(value: str, field: str, line_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise LyonDataError(f"line {line_number}: {field} must be a finite number") from None
    if not math.isfinite(number):
        raise LyonDataError(f"line {line_number}: {field} must be a finite number")
    return number


def _integer(value: str, field: str, line_number: int) -> int:
    if not _INTEGER.fullmatch(value):
        raise LyonDataError(f"line {line_number}: {field} must be an integer")
    try:
        return int(value)
    except ValueError:
        raise LyonDataError(f"line {line_number}: {field} must be an integer") from None


def _decode_line(raw: bytes, line_number: int) -> str:
    try:
        return raw.decode("utf-8-sig" if line_number == 1 else "utf-8").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise LyonDataError(f"line {line_number}: member is not valid UTF-8") from exc


def _read_member(
    handle: BinaryIO, member: str, member_size: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], str, int]:
    expected_sequence = PurePosixPath(member).stem
    metadata_lines: list[str] = []
    member_hash = hashlib.sha256()
    member_bytes = 0
    rows: list[dict[str, Any]] = []
    last_by_trace: dict[int, tuple[int, float]] = {}
    gap_count = 0
    source_fps: int | None = None
    sequence: str | None = None
    recording_started_at: str | None = None
    header_read = False
    line_number = 0

    for line_number, raw in enumerate(handle, start=1):
        member_hash.update(raw)
        member_bytes += len(raw)
        line = _decode_line(raw, line_number)
        if not header_read:
            if line_number == 1:
                match = _SEQUENCE_LINE.fullmatch(line)
                if match is None:
                    raise LyonDataError("line 1: expected Lyon TopView sequence declaration")
                sequence = match.group(1)
                if sequence != expected_sequence:
                    raise LyonDataError("sequence declaration does not match member name")
                metadata_lines.append(line)
                continue
            if line_number == 2:
                match = _FPS_LINE.fullmatch(line)
                if match is None:
                    raise LyonDataError("line 2: expected declared integer frame rate")
                source_fps = int(match.group(1))
                if source_fps <= 0:
                    raise LyonDataError("line 2: frame rate must be positive")
                metadata_lines.append(line)
                continue
            if line_number == 3:
                match = _START_LINE.fullmatch(line)
                if match is None:
                    raise LyonDataError("line 3: expected recording start timestamp")
                recording_started_at = match.group(1)
                try:
                    parsed_start = datetime.fromisoformat(recording_started_at)
                except ValueError:
                    raise LyonDataError("line 3: invalid recording start timestamp") from None
                if parsed_start.tzinfo is None or parsed_start.utcoffset() is None:
                    raise LyonDataError("line 3: recording start timestamp needs a timezone")
                metadata_lines.append(line)
                continue
            if line_number in (4, 5, 6):
                metadata_lines.append(line)
                continue
            if line_number == 7:
                if line != "# " + " ".join(_COLUMNS):
                    raise LyonDataError("line 7: unsupported Lyon trajectory columns")
                if metadata_lines[3:] != [
                    "# z coordinate is the estimated height of person",
                    "# x_RGF and y_RGF are coordinates (in meters) in the RGF-93 Lambert-93 coordinate system (EPSG:2154)",
                    "# t/s is the time (number of seconds) using as reference date Friday, Dec. 9th at 20:00:00 (UTC+1)",
                ]:
                    raise LyonDataError("member metadata does not match inspected TopView format")
                header_read = True
                continue
            raise LyonDataError(f"line {line_number}: unexpected header content")

        parts = line.split()
        if len(parts) != len(_COLUMNS):
            raise LyonDataError(f"line {line_number}: expected exactly nine fields")
        trace_value = _integer(parts[0], "id", line_number)
        frame = _integer(parts[1], "frame", line_number)
        # Validate this source field, but never retain or return it.
        _integer(parts[5], "id_global", line_number)
        local_x = _finite_number(parts[2], "x/m", line_number)
        local_y = _finite_number(parts[3], "y/m", line_number)
        estimated_z = _finite_number(parts[4], "z/m", line_number)
        source_time = _finite_number(parts[6], "t/s", line_number)
        projected_x = _finite_number(parts[7], "x_RGF", line_number)
        projected_y = _finite_number(parts[8], "y_RGF", line_number)

        previous = last_by_trace.get(trace_value)
        if previous is not None:
            previous_frame, previous_time = previous
            if frame <= previous_frame:
                raise LyonDataError(f"line {line_number}: frame must increase within each trace")
            if source_time <= previous_time:
                raise LyonDataError(f"line {line_number}: t/s must increase within each trace")
            if frame - previous_frame > 1:
                gap_count += 1
        last_by_trace[trace_value] = (frame, source_time)
        rows.append({
            "trace_id": f"{member}::{trace_value}",
            "source_frame": frame,
            "source_t_s": source_time,
            "local_x_m": local_x,
            "local_y_m": local_y,
            "estimated_z_m": estimated_z,
            "projected_x_epsg2154_m": projected_x,
            "projected_y_epsg2154_m": projected_y,
        })

    if not header_read:
        raise LyonDataError("member is empty or has an incomplete header")
    if not rows:
        raise LyonDataError("member contains no trajectory rows")
    if member_bytes != member_size:
        raise LyonDataError("ZIP member byte count does not match its directory entry")

    metadata = {
        "sequence": sequence,
        "declared_source_frame_rate_fps": source_fps,
        "recording_started_at": recording_started_at,
        "source_time_field": "t/s",
        "source_time_unit": "s",
        "source_time_reference": _TIME_REFERENCE,
        "source_times_are_native_video_pts": False,
        "coordinate_system": "EPSG:2154",
        "projected_coordinate_units": "m",
        "local_coordinate_units": "m",
        "height_field": "z/m",
        "height_semantics": "estimated person height; not a ground-plane coordinate",
        "calibration_status": "source-declared coordinates; independent residuals unverified",
        "independent_reprojection_residuals_available": False,
        "calibration_drift_evidence_available": False,
        "trace_sampling_gap_semantics": "frame gaps within a supplied trajectory; not video decode-loss evidence",
    }
    return metadata, rows, member_hash.hexdigest(), gap_count


def read_lyon_topview(
    archive_path: str | Path,
    *,
    member: str = DEFAULT_MEMBER,
) -> dict[str, Any]:
    """Read one inspected nine-column TopView trajectory member without extraction."""
    member_path = PurePosixPath(member)
    if member_path.is_absolute() or ".." in member_path.parts or member_path.as_posix() != member:
        raise LyonDataError("member must be a normalized relative ZIP path")
    if member_path.parent.as_posix() != "Data_Madras/TopView_trajectories" \
            or not member_path.name.startswith("TopView_") or member_path.suffix != ".txt":
        raise LyonDataError("only a TopView trajectory text member is supported")

    source = Path(archive_path).expanduser()
    archive_size, archive_sha256, archive_md5 = _archive_checksums(source)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            try:
                info = archive.getinfo(member)
            except KeyError:
                raise LyonDataError(f"ZIP member not found: {member}") from None
            if info.is_dir():
                raise LyonDataError("trajectory member must be a file")
            with archive.open(info, "r") as handle:
                metadata, rows, member_sha256, gap_count = _read_member(
                    handle, member, info.file_size)
    except LyonDataError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise LyonDataError(f"cannot read Lyon ZIP archive: {source}") from exc

    return {
        "source_format": "lyon_topview_text",
        "source_format_version": 1,
        "provenance": {
            "archive_path": str(source.resolve()),
            "archive_size_bytes": archive_size,
            "archive_sha256": archive_sha256,
            "archive_md5": archive_md5,
            "member_path": member,
            "member_size_bytes": info.file_size,
            "member_sha256": member_sha256,
        },
        "metadata": metadata,
        "rows": rows,
        "trace_sampling_gap_count": gap_count,
    }


def summarize_lyon_topview(table: dict[str, Any]) -> dict[str, Any]:
    """Summarize parsed Lyon rows without including track-level data."""
    rows = table["rows"]
    times = [row["source_t_s"] for row in rows]
    return {
        "source_format": table["source_format"],
        "source_format_version": table["source_format_version"],
        "provenance": table["provenance"],
        "metadata": table["metadata"],
        "row_count": len(rows),
        "trace_count": len({row["trace_id"] for row in rows}),
        "source_temporal_range_s": [min(times), max(times)],
        "trace_sampling_gap_count": table["trace_sampling_gap_count"],
    }
