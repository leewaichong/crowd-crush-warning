"""Reader and summary functions for the published temporal density table."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


_YEARS = (2022, 2023, 2024)
_DESCRIPTION = (
    "Density averaged over space and plotted against time for Pamplona 2022, 2023 and 2024. "
    "Time is negative, representing the time to the opening of the festival. "
    "Delimiter is a tab character."
)
_HEADER = tuple(
    field
    for year in _YEARS
    for field in (f"Time {year} (s)", f"Density {year} (m^-2)")
)
_METADATA = {
    "source_format": "zenodo-density-time-v1",
    "time_reference": "seconds_relative_to_festival_opening",
    "units": {"time": "s", "density": "m^-2"},
}


def read_density_table(path: str | Path) -> dict[str, Any]:
    """Parse the exact six-column source format, rejecting ambiguous gaps."""
    series = [{"year": year, "points": [], "missing_count": 0} for year in _YEARS]
    ended = [False, False, False]
    last_time: list[float | None] = [None, None, None]
    row_count = 0

    with Path(path).open("r", encoding="utf-8", newline="") as source:
        description = source.readline().rstrip("\r\n")
        if description != _DESCRIPTION:
            raise ValueError("density table description does not match the required source")
        header = source.readline().rstrip("\r\n").split("\t")
        if tuple(header) != _HEADER:
            raise ValueError("density table header does not match the required schema")

        for line_number, raw_line in enumerate(source, start=3):
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                continue
            fields = line.split("\t")
            if len(fields) != 6:
                raise ValueError(f"line {line_number}: expected exactly six tab-separated columns")
            row_count += 1

            for index, entry in enumerate(series):
                time_text, density_text = fields[index * 2:index * 2 + 2]
                try:
                    timestamp, density = float(time_text), float(density_text)
                except ValueError as exc:
                    raise ValueError(f"line {line_number}: invalid numeric pair for {entry['year']}") from exc

                time_missing, density_missing = math.isnan(timestamp), math.isnan(density)
                if time_missing or density_missing:
                    if not (time_missing and density_missing):
                        raise ValueError(f"line {line_number}: partial missing pair for {entry['year']}")
                    ended[index] = True
                    entry["missing_count"] += 1
                    continue

                if not math.isfinite(timestamp) or not math.isfinite(density):
                    raise ValueError(f"line {line_number}: non-finite value for {entry['year']}")
                if ended[index]:
                    raise ValueError(f"line {line_number}: non-trailing missing pair for {entry['year']}")
                if density < 0:
                    raise ValueError(f"line {line_number}: negative density for {entry['year']}")
                previous = last_time[index]
                if previous is not None and timestamp <= previous:
                    raise ValueError(f"line {line_number}: times must increase for {entry['year']}")
                entry["points"].append([timestamp, density])
                last_time[index] = timestamp

    return {**_METADATA, "row_count": row_count, "series": series}


def summarize_density_table(table: dict[str, Any]) -> dict[str, Any]:
    """Return per-year counts and observed range without including point data."""
    summary = []
    for entry in table["series"]:
        points = entry["points"]
        densities = [point[1] for point in points]
        summary.append({
            "year": entry["year"],
            "observation_count": len(points),
            "missing_count": entry["missing_count"],
            "start_timestamp_s": points[0][0] if points else None,
            "end_timestamp_s": points[-1][0] if points else None,
            "min_density_per_m2": min(densities) if densities else None,
            "max_density_per_m2": max(densities) if densities else None,
        })
    return {**_METADATA, "row_count": table["row_count"], "series": summary}
