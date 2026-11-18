"""Offline command line interface for the crowd warning research prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
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

    baselines = commands.add_parser("baselines", help="compute causal diagnostic baseline signals")
    baselines.add_argument("input", help="path to the observation file")
    baselines.add_argument("--density-threshold", type=float, required=True)
    baselines.add_argument("--proxy-threshold", type=float, required=True)
    baselines.add_argument("--change-threshold", type=float, required=True)
    baselines.add_argument("--allowance", type=float, default=0.0)
    baselines.add_argument("--window-s", type=float, default=5.0)
    baselines.add_argument("--max-gap-s", type=float, default=5.0)

    verify_source = commands.add_parser("verify-source", help="check a local source manifest")
    verify_source.add_argument("manifest", help="path to a source manifest JSON file")
    verify_source.add_argument("--base-dir", help="directory containing manifest files")

    inspect_density = commands.add_parser("inspect-density", help="summarize a temporal density source")
    inspect_density.add_argument("input", help="path to a temporal density table")

    replay_density = commands.add_parser("replay-density", help="write a temporal density source viewer")
    replay_density.add_argument("input", help="path to a temporal density table")
    replay_density.add_argument("--output", required=True, help="new HTML output path; existing files are refused")

    inspect_video = commands.add_parser(
        "inspect-video", help="inspect local video timestamps and decode the video stream"
    )
    inspect_video.add_argument("input", help="path to a local video file")
    inspect_video.add_argument(
        "--max-gap-s", type=float,
        help="report timestamp intervals above this positive finite research check",
    )

    inspect_motion = commands.add_parser(
        "inspect-motion", help="inspect image-space motion diagnostics in a local video"
    )
    inspect_motion.add_argument("input", help="path to a local video file")
    inspect_motion.add_argument("--width", type=int, default=320, help="scaled grayscale frame width")
    inspect_motion.add_argument(
        "--sample-interval-s", type=float, default=1.0,
        help="minimum interval between selected actual presentation timestamps",
    )
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

    if args.command == "baselines":
        from .baselines import baseline_signals
        from .features import extract_features

        rows = _load_and_validate(args.input)
        features = extract_features(rows, window_s=args.window_s)
        return baseline_signals(
            features,
            density_threshold=args.density_threshold,
            proxy_threshold=args.proxy_threshold,
            change_threshold=args.change_threshold,
            allowance=args.allowance,
            max_gap_s=args.max_gap_s,
        )

    if args.command == "verify-source":
        from .sources import verify_source_manifest

        manifest_path = Path(args.manifest)
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        base_dir = args.base_dir if args.base_dir is not None else manifest_path.parent
        return verify_source_manifest(manifest, base_dir=base_dir)

    if args.command == "inspect-density":
        from .density import read_density_table, summarize_density_table

        table = read_density_table(args.input)
        return summarize_density_table(table)

    if args.command == "replay-density":
        from .density import read_density_table
        from .replay import render_density_replay

        input_path = Path(args.input)
        table = read_density_table(input_path)
        input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
        html = render_density_replay(table)
        output_path = Path(args.output)
        with output_path.open("x", encoding="utf-8") as handle:
            handle.write(html)
        return {
            "status": "written",
            "output": str(output_path.resolve()),
            "input_sha256": input_sha256,
        }

    if args.command == "inspect-video":
        from .video import inspect_video

        return inspect_video(args.input, max_gap_s=args.max_gap_s)

    if args.command == "inspect-motion":
        from .motion_video import inspect_motion_video

        return inspect_motion_video(
            args.input, width=args.width, sample_interval_s=args.sample_interval_s
        )

    raise ValueError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except (ImportError, OSError, ValueError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2

    try:
        encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": f"result is not valid JSON: {exc}"}), file=sys.stderr)
        return 2
    print(encoded)
    if args.command == "verify-source" and result.get("integrity_verified") is not True:
        return 2
    return 0
