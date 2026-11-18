"""Strict ingestion for zone-level crowd observations.

Each row is one zone observation at a time, not a person track. The loader
checks data shape and quality metadata; it cannot establish camera scale or
physical crowd forces.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable


FIELDS = ("timestamp_s", "zone_id", "density_per_m2", "vx_mps", "vy_mps", "quality", "calibrated")


class ObservationDataError(ValueError):
    """Invalid input with separate parse and validation row counts.

    ``parsed_rows`` counts complete records decoded from the file.
    ``validated_rows`` counts records that passed validation. ``rejected_rows``
    counts records that failed parsing or validation, and ``unprocessed_rows``
    counts known remaining records. ``unprocessed_reason`` explains why later
    input was left unread when parsing stopped. ``accepted_rows``
    remains an alias for ``validated_rows``.
    """

    def __init__(self, message: str, *, parsed_rows: int = 0, validated_rows: int = 0,
                 rejected_rows: int = 0, unprocessed_rows: int = 0,
                 unprocessed_reason: str = "no remaining records were identified"):
        super().__init__(message)
        self.parsed_rows = parsed_rows
        self.validated_rows = validated_rows
        self.accepted_rows = validated_rows
        self.rejected_rows = rejected_rows
        self.unprocessed_rows = unprocessed_rows
        self.unprocessed_reason = unprocessed_reason
        self.total_rows = parsed_rows + rejected_rows + unprocessed_rows


def _number(value: Any, field: str, row_number: int) -> float:
    if isinstance(value, bool):
        raise ObservationDataError(f"row {row_number}: {field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ObservationDataError(f"row {row_number}: {field} must be a finite number") from None
    if not math.isfinite(number):
        raise ObservationDataError(f"row {row_number}: {field} must be a finite number")
    return number


def _boolean(value: Any, row_number: int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ObservationDataError(f"row {row_number}: calibrated must be a boolean")


def validate_observations(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize rows; errors identify the input row and counts.

    Low quality and uncalibrated rows remain represented for downstream
    abstention. Values outside the declared quality range are rejected.
    """
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    total = 0
    try:
        for total, row in enumerate(rows, start=1):
            try:
                if not isinstance(row, dict):
                    raise ObservationDataError(f"row {total}: expected an object")
                missing = [field for field in FIELDS if field not in row]
                extra = [field for field in row if field not in FIELDS]
                if missing:
                    raise ObservationDataError(f"row {total}: missing fields: {', '.join(missing)}")
                if extra:
                    raise ObservationDataError(f"row {total}: unexpected fields: {', '.join(map(str, extra))}")
                timestamp = _number(row["timestamp_s"], "timestamp_s", total)
                if timestamp < 0:
                    raise ObservationDataError(f"row {total}: timestamp_s must be non-negative")
                zone = row["zone_id"]
                if not isinstance(zone, str) or not zone.strip():
                    raise ObservationDataError(f"row {total}: zone_id must be a non-empty string")
                zone = zone.strip()
                key = (zone, timestamp)
                if key in seen:
                    raise ObservationDataError(f"row {total}: duplicate zone_id and timestamp_s")
                density = _number(row["density_per_m2"], "density_per_m2", total)
                if density < 0:
                    raise ObservationDataError(f"row {total}: density_per_m2 must be non-negative")
                vx = _number(row["vx_mps"], "vx_mps", total)
                vy = _number(row["vy_mps"], "vy_mps", total)
                quality = _number(row["quality"], "quality", total)
                if not 0 <= quality <= 1:
                    raise ObservationDataError(f"row {total}: quality must be in [0, 1]")
                calibrated = _boolean(row["calibrated"], total)
                result.append({"timestamp_s": timestamp, "zone_id": zone,
                               "density_per_m2": density, "vx_mps": vx, "vy_mps": vy,
                               "quality": quality, "calibrated": calibrated})
                seen.add(key)
            except ObservationDataError as exc:
                raise ObservationDataError(str(exc), parsed_rows=total - 1,
                                           validated_rows=len(result), rejected_rows=1) from exc
    except TypeError as exc:
        raise ObservationDataError("observations must be an iterable of row objects",
                                   parsed_rows=total, validated_rows=len(result)) from exc
    return result


def load_observations(path: str | Path) -> list[dict[str, Any]]:
    """Load CSV or JSON Lines observations selected by filename suffix.

    A CSV with the exact required header and no records is valid and returns
    an empty list. File parsing completes before row validation begins, so a
    parse error reports parsed records separately from validated records.
    """
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in {".csv", ".jsonl", ".ndjson"}:
        raise ObservationDataError(f"unsupported observation format: {suffix or '(no extension)'}")
    rows = []
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            if suffix == ".csv":
                reader = csv.reader(handle, strict=True)
                try:
                    header = next(reader)
                except StopIteration:
                    raise ObservationDataError("CSV is empty; expected a header") from None
                if len(header) != len(set(header)):
                    raise ObservationDataError("CSV header contains duplicate columns")
                missing = [field for field in FIELDS if field not in header]
                extra = [field for field in header if field not in FIELDS]
                if missing or extra or len(header) != len(FIELDS):
                    detail = []
                    if missing:
                        detail.append(f"missing columns: {', '.join(missing)}")
                    if extra:
                        detail.append(f"unexpected columns: {', '.join(extra)}")
                    raise ObservationDataError("CSV header does not match schema (" + "; ".join(detail) + ")")
                rows = []
                try:
                    for line_number, values in enumerate(reader, start=2):
                        if len(values) != len(header):
                            reason = "too many" if len(values) > len(header) else "too few"
                            raise ObservationDataError(f"line {line_number}: {reason} CSV fields",
                                                       parsed_rows=len(rows), rejected_rows=1,
                                                       unprocessed_reason="later CSV records were not counted")
                        rows.append(dict(zip(header, values)))
                except csv.Error as exc:
                    raise ObservationDataError(f"line {reader.line_num}: malformed CSV: {exc}",
                                               parsed_rows=len(rows), rejected_rows=1,
                                               unprocessed_reason="later CSV records were not counted") from exc
            else:
                rows = []
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        raise ObservationDataError(f"line {line_number}: blank JSON Lines record",
                                                   parsed_rows=len(rows), rejected_rows=1,
                                                   unprocessed_reason="later lines were not read")
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ObservationDataError(f"line {line_number}: invalid JSON: {exc.msg}",
                                                   parsed_rows=len(rows), rejected_rows=1,
                                                   unprocessed_reason="later lines were not read") from exc
                    if not isinstance(row, dict):
                        raise ObservationDataError(f"line {line_number}: expected a JSON object",
                                                   parsed_rows=len(rows), rejected_rows=1,
                                                   unprocessed_reason="later lines were not read")
                    rows.append(row)
    except UnicodeDecodeError as exc:
        raise ObservationDataError(f"observation file is not valid UTF-8 near byte {exc.start}",
                                   parsed_rows=len(rows), rejected_rows=1,
                                   unprocessed_reason="remaining bytes could not be decoded") from exc
    except OSError as exc:
        raise ObservationDataError(f"cannot read observation file: {source}") from exc
    except csv.Error as exc:
        raise ObservationDataError(f"malformed CSV: {exc}") from exc
    try:
        return validate_observations(rows)
    except ObservationDataError as exc:
        raise ObservationDataError(str(exc), parsed_rows=exc.parsed_rows,
                                   validated_rows=exc.validated_rows,
                                   rejected_rows=exc.rejected_rows,
                                   unprocessed_rows=len(rows) - exc.parsed_rows - exc.rejected_rows) from exc
