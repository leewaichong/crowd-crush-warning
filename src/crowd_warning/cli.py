"""Offline command line interface for the crowd warning research prototype."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crowd-warning",
        description="Inspect crowd-zone observations and run research proxies.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate an observation file")
    validate.add_argument("input", help="path to the observation file")

    features = commands.add_parser("features", help="extract trailing-window features")
    features.add_argument("input", help="path to the observation file")
    features.add_argument("--window-s", type=float, default=5.0)

    forecast = commands.add_parser("forecast", help="forecast a proxy threshold crossing")
    forecast.add_argument("input", help="path to the observation file")
    forecast.add_argument("--threshold", type=float, required=True)
    forecast.add_argument("--horizon-s", type=float, default=30.0)
    forecast.add_argument("--paths", type=int, default=256)
    forecast.add_argument("--seed", type=int, default=0)
    forecast.add_argument("--window-s", type=float, default=5.0)
    return parser


def _load_and_validate(path: str) -> list[dict[str, Any]]:
    # These modules are integrated independently. Import only when a command needs them.
    from .data import load_observations, validate_observations

    rows = load_observations(path)
    validate_observations(rows)
    return rows


def _run(args: argparse.Namespace) -> Any:
    if args.command == "validate":
        rows = _load_and_validate(args.input)
        return {"status": "valid", "row_count": len(rows)}

    if args.command == "features":
        from .features import extract_features

        rows = _load_and_validate(args.input)
        return extract_features(rows, window_s=args.window_s)

    if args.command == "forecast":
        from .features import extract_features
        from .forecast import forecast_crossing

        rows = _load_and_validate(args.input)
        features = extract_features(rows, window_s=args.window_s)
        return forecast_crossing(
            features,
            horizon_s=args.horizon_s,
            threshold=args.threshold,
            paths=args.paths,
            seed=args.seed,
        )

    raise ValueError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except (ImportError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2

    try:
        encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": f"result is not valid JSON: {exc}"}), file=sys.stderr)
        return 2
    print(encoded)
    return 0
