"""Run the one frozen M07 CROWD50 reported-increment comparison."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import math
import os
import platform
import resource
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path

import numpy as np

from hmm import (
    conditional_mean,
    emission_log_probabilities,
    filter_states,
    fit,
    next_state_probabilities,
    stationary_distribution,
)


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work/m07-model"
CONFIG_PATH = WORK / "config.json"
FREEZE_PATH = WORK / "freeze.json"
CONFIG = json.loads(CONFIG_PATH.read_text())
sys.path.insert(0, str(ROOT / "src"))
from crowd_warning.lyon import read_lyon_topview  # noqa: E402

ARCHIVE = Path("/Users/waichong/projects/crowd-crush-warning/data/zenodo-13830435/Data_Madras.zip")
MANIFEST = ROOT / "sources/lyon-topview.json"
PROTOCOL = ROOT / ".planning/m07/switching-state-protocol.md"
ADMISSION = ROOT / "work/m07-observation/source-admission.json"
READER = ROOT / "src/crowd_warning/lyon.py"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def peak_rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def check_limits(started: float) -> None:
    if time.monotonic() - started > CONFIG["wall_limit_seconds"]:
        raise TimeoutError("20-minute overall run budget exceeded")
    if peak_rss_bytes() > CONFIG["memory_limit_bytes"]:
        raise MemoryError("1 GiB observed-memory guard exceeded")


def verify_freeze() -> dict:
    frozen = json.loads(FREEZE_PATH.read_text())
    expected_files = frozen["executable_sha256"]
    for relative, expected in expected_files.items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise ValueError(f"frozen input changed: {relative}")
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=ROOT, text=True
    )
    if git_sha != frozen["tracked_git_sha"] or status.strip():
        raise ValueError("tracked worktree SHA or clean state differs from freeze")
    return frozen


def error_metrics(prediction: np.ndarray, target: np.ndarray) -> dict:
    difference = prediction - target
    vector_error = np.sqrt(np.sum(difference * difference, axis=1))
    return {
        "n": int(len(target)),
        "mean_vector_euclidean_error_source_units_per_native_frame": float(vector_error.mean()),
        "rmse_vector_euclidean_error_source_units_per_native_frame": float(
            np.sqrt(np.mean(vector_error * vector_error))
        ),
        "axis_mae_source_units_per_native_frame": np.mean(np.abs(difference), axis=0).tolist(),
    }


def summarize_partition(predictions: np.ndarray, target: np.ndarray, names: list[str]) -> dict:
    summary = {name: error_metrics(predictions[:, i, :], target) for i, name in enumerate(names)}
    losses = {
        name: np.linalg.norm(predictions[:, i, :] - target, axis=1)
        for i, name in enumerate(names)
    }
    tolerance = CONFIG["tie_tolerance"]
    paired = {}
    for baseline in ("latest", "trailing_mean_5", "memoryless_transition"):
        delta = losses["switching_hmm"] - losses[baseline]
        paired[baseline] = {
            "mean_candidate_minus_baseline_vector_error": float(delta.mean()),
            "candidate_lower_fraction": float(np.mean(delta < -tolerance)),
            "tied_fraction": float(np.mean(np.abs(delta) <= tolerance)),
            "candidate_higher_fraction": float(np.mean(delta > tolerance)),
            "tie_tolerance": tolerance,
        }
    return {"arms": summary, "paired_candidate_vs_controls": paired}


def run() -> Path:
    frozen = verify_freeze()
    started_utc = utc_now()
    started = time.monotonic()
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = WORK / "runs" / f"attempt-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    status = {"status": "running", "started_utc": started_utc, "run_id": run_id}
    write_json(run_dir / "attempt-status.json", status)
    try:
        source_hash_before = sha256(ARCHIVE)
        table = read_lyon_topview(ARCHIVE)
        if source_hash_before != table["provenance"]["archive_sha256"]:
            raise ValueError("archive changed between prehash and reader parse")
        admission = json.loads(ADMISSION.read_text())
        manifest = json.loads(MANIFEST.read_text())
        expected_archive = manifest["files"][0]["sha256"]
        if source_hash_before != expected_archive:
            raise ValueError("archive SHA-256 does not match source manifest")
        if table["provenance"]["member_sha256"] != admission["member_sha256"]:
            raise ValueError("member SHA-256 does not match completed source admission")
        if table["provenance"]["member_path"] != admission["member_path"]:
            raise ValueError("member path does not match completed source admission")

        grouped = collections.OrderedDict()
        for row in table["rows"]:
            grouped.setdefault(row["trace_id"], []).append(row)
        b1 = CONFIG["split"]["train_end_exclusive"]
        b2 = CONFIG["split"]["validation_end_exclusive"]
        coordinate_fields = CONFIG["coordinate_fields"]
        expected_targets = admission["consecutive_increment_targets"]
        expected_eligible = admission["eligible_origins_5increments_plus_next_target"]
        train_sequences = []
        records = []
        counts = collections.Counter()
        crossing_targets = crossing_origins = 0

        for trace_ordinal, (trace_key, rows) in enumerate(grouped.items()):
            rows.sort(key=lambda row: row["source_frame"])
            trace_increments = []
            for left, right in zip(rows, rows[1:]):
                if right["source_frame"] != left["source_frame"] + 1:
                    raise ValueError("admitted trace contains a gap; refusing interpolation/reset ambiguity")
                trace_increments.append({
                    "start_frame": left["source_frame"],
                    "end_frame": right["source_frame"],
                    "start_t": left["source_t_s"],
                    "end_t": right["source_t_s"],
                    "value": [
                        right[coordinate_fields[0]] - left[coordinate_fields[0]],
                        right[coordinate_fields[1]] - left[coordinate_fields[1]],
                    ],
                })
            training = [inc["value"] for inc in trace_increments if inc["end_frame"] < b1]
            if training:
                train_sequences.append(np.asarray(training, dtype=np.float64))
            for increment in trace_increments:
                start_frame, end_frame = increment["start_frame"], increment["end_frame"]
                if end_frame < b1:
                    counts["train"] += 1
                elif start_frame >= b1 and end_frame < b2:
                    counts["validation"] += 1
                elif start_frame >= b2:
                    counts["test"] += 1
                else:
                    crossing_targets += 1

            raw_values = np.asarray([inc["value"] for inc in trace_increments], dtype=np.float64)
            if len(raw_values) == 0:
                continue
            records.append((trace_ordinal, trace_increments, raw_values))

        expected_count_map = {k: int(expected_targets[k]) for k in ("train", "validation", "test")}
        observed_count_map = {k: int(counts[k]) for k in ("train", "validation", "test")}
        if observed_count_map != expected_count_map:
            raise ValueError(f"target increment counts disagree with admission: {observed_count_map}")
        if crossing_targets != expected_targets["split_crossing_excluded"]:
            raise ValueError("split-crossing increment count disagrees with admission")
        training_count = sum(len(sequence) for sequence in train_sequences)
        if training_count != expected_count_map["train"]:
            raise ValueError("training increment count mismatch")

        verify_freeze()

        fit_progress_path = run_dir / "fit-progress.jsonl"
        fit_progress_path.open("x").close()
        def persist_progress(value):
            with fit_progress_path.open("a") as stream:
                stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")

        fit_result = fit(
            train_sequences,
            max_updates=CONFIG["max_em_updates"],
            tolerance=CONFIG["convergence_mean_loglik_delta_per_increment"],
            variance_floor=CONFIG["variance_floor_standardized"],
            pseudocount=CONFIG["count_pseudocount"],
            time_limit=CONFIG["wall_limit_seconds"],
            memory_limit=CONFIG["memory_limit_bytes"],
            progress_callback=persist_progress,
        )
        center, scale = fit_result["center"], fit_result["scale"]
        transition = fit_result["transition"]
        means = fit_result["means_standardized"]
        stationary = fit_result["stationary"]
        names = ["switching_hmm", "memoryless_transition", "latest", "trailing_mean_5"]
        result_parts = []
        for trace_ordinal, increments, raw_values in records:
            normalized = (raw_values - center) / scale
            logs = emission_log_probabilities(
                normalized, fit_result["means_standardized"], fit_result["variances_standardized"]
            )
            filtered = filter_states(logs, fit_result["pi"], transition)
            next_probs = next_state_probabilities(filtered, transition)
            for k in range(4, len(increments) - 1):
                current = increments[k]
                target_increment = increments[k + 1]
                origin_frame = current["end_frame"]
                target_frame = target_increment["end_frame"]
                if target_frame < b1:
                    partition = "train"
                elif origin_frame >= b1 and target_frame < b2:
                    partition = "validation"
                elif origin_frame >= b2 and target_frame < 4796:
                    partition = "test"
                else:
                    crossing_origins += 1
                    continue
                probabilities = filtered[k]
                next_state = next_probs[k]
                switch_norm = conditional_mean(next_state, means)
                memoryless_norm = conditional_mean(stationary, means)
                switch = switch_norm * scale + center
                memoryless = memoryless_norm * scale + center
                latest = np.asarray(current["value"], dtype=np.float64)
                trailing = np.mean(raw_values[k - 4:k + 1], axis=0)
                target = np.asarray(target_increment["value"], dtype=np.float64)
                result_parts.append((partition, (
                    trace_ordinal, origin_frame, target_frame,
                    current["end_t"], target_increment["end_t"],
                    target, switch, memoryless, latest, trailing,
                    probabilities, next_state,
                )))
        for partition in ("train", "validation", "test"):
            observed_n = sum(name == partition for name, _ in result_parts)
            expected_n = int(expected_eligible[partition])
            if observed_n != expected_n:
                raise ValueError(f"eligible {partition} origin count {observed_n} != admission {expected_n}")

        # Ensure the 105 eligible boundary-crossing cases were rejected exactly once.
        if crossing_origins != expected_eligible["split_crossing_excluded"]:
            raise ValueError(f"eligible split-crossing count mismatch: {crossing_origins}")
        check_limits(started)

        labels = {"train": 0, "validation": 1, "test": 2}
        keys = []
        times = []
        targets = []
        predictions = []
        filtered_probs = []
        next_probs_out = []
        partitions = []
        for partition, row in result_parts:
            trace, origin, target_frame, origin_t, target_t, target, switch, memoryless, latest, trailing, filtered, next_prob = row
            keys.append((labels[partition], trace, origin, target_frame))
            times.append((origin_t, target_t))
            targets.append(target)
            predictions.append((switch, memoryless, latest, trailing))
            filtered_probs.append(filtered)
            next_probs_out.append(next_prob)
            partitions.append(labels[partition])
        raw_path = run_dir / "raw-forecasts.npz"
        np.savez_compressed(
            raw_path,
            partition=np.asarray(partitions, dtype=np.int8),
            anonymous_trace_ordinal=np.asarray(keys, dtype=np.int32)[:, 1],
            origin_frame=np.asarray(keys, dtype=np.int32)[:, 2],
            target_frame=np.asarray(keys, dtype=np.int32)[:, 3],
            origin_source_t_s=np.asarray(times, dtype=np.float64)[:, 0],
            target_source_t_s=np.asarray(times, dtype=np.float64)[:, 1],
            target_increment=np.asarray(targets, dtype=np.float64),
            forecasts=np.asarray(predictions, dtype=np.float64),
            filtered_state_probabilities=np.asarray(filtered_probs, dtype=np.float64),
            next_state_probabilities=np.asarray(next_probs_out, dtype=np.float64),
            forecast_arm_names=np.asarray(names),
            partition_names=np.asarray(["train", "validation", "test"]),
        )
        if raw_path.stat().st_size > CONFIG["raw_output_limit_bytes"]:
            raise OSError("raw NPZ exceeds 100 MiB output cap")

        fit_record = {
            "iterations": fit_result["iterations"],
            "converged": fit_result["converged"],
            "hit_iteration_cap": fit_result["hit_iteration_cap"],
            "nonmonotonic_likelihood_observed": fit_result["nonmonotonic"],
            "degeneracies_by_parameter_version": fit_result["degeneracies"],
            "likelihood_total_by_parameter_version": fit_result["likelihoods"].tolist(),
            "likelihood_mean_per_training_increment": (
                fit_result["likelihoods"] / fit_result["training_increment_count"]
            ).tolist(),
            "parameter_versions": fit_result["versions"],
            "final_parameters": {
                "initial_state_probability": fit_result["pi"].tolist(),
                "transition_matrix": transition.tolist(),
                "emission_means_standardized": means.tolist(),
                "emission_diagonal_variances_standardized": fit_result["variances_standardized"].tolist(),
                "training_increment_center_source_units": center.tolist(),
                "training_increment_scale_source_units": scale.tolist(),
                "emission_means_source_increment_units": fit_result["means_source_units"].tolist(),
                "emission_diagonal_variances_source_increment_units_squared": fit_result["variances_source_units"].tolist(),
                "memoryless_stationary_weights": stationary.tolist(),
                "initialization_sort_axis": fit_result["sort_axis"],
            },
        }
        write_json(run_dir / "fit-record.json", fit_record)

        aggregate = {}
        for partition, lower, upper in (("train", 0, b1), ("validation", b1, b2), ("test", b2, 4796)):
            idx = [i for i, (name, _) in enumerate(result_parts) if name == partition]
            pred = np.asarray(predictions, dtype=np.float64)[idx]
            truth = np.asarray(targets, dtype=np.float64)[idx]
            aggregate[partition] = summarize_partition(pred, truth, names)
        aggregate_summary = {
            "status": "EXPLORATORY_REPORTED_INCREMENT_FORECAST_COMPARISON_EXECUTED",
            "not_an_independent_measurement_accuracy_or_warning_evaluation": True,
            "task": "next native-frame x_RGF,y_RGF reported increment within existing trace",
            "source_units": "source-declared EPSG:2154 metres per native-frame increment",
            "partition_frame_ranges_inclusive": {
                "train": [0, 2876], "validation": [2877, 3835], "test": [3836, 4795]
            },
            "results_by_partition": aggregate,
            "fit": {
                "updates": fit_result["iterations"], "converged": fit_result["converged"],
                "hit_cap": fit_result["hit_iteration_cap"],
                "nonmonotonic_likelihood_observed": fit_result["nonmonotonic"],
            },
            "coverage": {p: int(sum(name == p for name, _ in result_parts)) for p in labels},
            "source_and_model_limits": [
                "One recording and existing anonymous traces only; no unseen person, event, or venue generalization.",
                "Reported coordinate increments are forecast targets, not independent measurement truth.",
                "Source preprocessing may be noncausal or smoothed; online sensor performance is untested.",
                "Latent states are statistical clusters, not dangerous crowd regimes or physical mechanisms.",
                "No force, warning effectiveness, safety threshold, or calibrated probability claim.",
                "Training metrics are in-sample; validation is descriptive; test is a same-recording chronological check.",
            ],
        }
        write_json(run_dir / "aggregate-summary.json", aggregate_summary)

        source_hash_after = sha256(ARCHIVE)
        with zipfile.ZipFile(ARCHIVE, "r") as archive:
            member_digest = hashlib.sha256()
            with archive.open(admission["member_path"]) as member:
                for block in iter(lambda: member.read(1 << 20), b""):
                    member_digest.update(block)
        member_hash_after = member_digest.hexdigest()
        if source_hash_after != source_hash_before:
            raise ValueError("source archive changed during run")
        if member_hash_after != admission["member_sha256"]:
            raise ValueError("source member changed during run")

        run_record = {
            "status": "completed",
            "started_utc": started_utc,
            "ended_utc": utc_now(),
            "command": "python3 work/m07-model/runner.py",
            "statistical_model": "two-state diagonal-Gaussian HMM; local NumPy implementation",
            "model_endpoint": None,
            "model_endpoint_note": "No remote model endpoint used for statistical fitting or forecasts.",
            "tracked_git_sha": frozen["tracked_git_sha"],
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "source_archive_sha256_before": source_hash_before,
            "source_archive_sha256_after": source_hash_after,
            "source_member_sha256_before": table["provenance"]["member_sha256"],
            "source_member_sha256_after": member_hash_after,
            "source_manifest_sha256": sha256(MANIFEST),
            "source_reader_sha256": sha256(READER),
            "source_admission_sha256": sha256(ADMISSION),
            "protocol_sha256": sha256(PROTOCOL),
            "config_sha256": sha256(CONFIG_PATH),
            "runner_sha256": sha256(Path(__file__)),
            "hmm_sha256": sha256(Path(__file__).with_name("hmm.py")),
            "test_sha256": sha256(WORK / "tests/test_hmm.py"),
            "counts": {
                "training_increments": observed_count_map["train"],
                "validation_increments": observed_count_map["validation"],
                "test_increments": observed_count_map["test"],
                "split_crossing_increments_excluded": crossing_targets,
                "train_eligible_origins": int(expected_eligible["train"]),
                "validation_eligible_origins": int(expected_eligible["validation"]),
                "test_eligible_origins": int(expected_eligible["test"]),
                "split_crossing_eligible_origins_excluded": crossing_origins,
            },
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_bytes": peak_rss_bytes(),
            "raw_npz_bytes": raw_path.stat().st_size,
        }
        write_json(run_dir / "run-record.json", run_record)
        status.update({"status": "completed", "ended_utc": run_record["ended_utc"]})
        write_json(run_dir / "attempt-status.json", status)

        public_dir = WORK / "public-ready"
        public_dir.mkdir(parents=True, exist_ok=False)
        write_json(public_dir / "aggregate-summary.json", aggregate_summary)
        write_json(public_dir / "model-summary.json", fit_record)
        (public_dir / "README.md").write_text(
            "# M07 reported-increment comparison\n\n"
            "**EXPLORATORY.** One chronological test partition from a single existing CROWD50 recording. "
            "This evaluates forecasting of source-reported increments only. It is not independent motion "
            "measurement accuracy, a warning evaluation, or evidence about physical force.\n\n"
            "The task forecasts the next native-frame increment of source-declared `x_RGF, y_RGF` "
            "coordinates in EPSG:2154 metres within already observed traces. Training data set the "
            "normalization and HMM parameters. Validation is descriptive. The test partition is a "
            "chronological check in the same recording. Existing identifiers group supplied traces; "
            "this does not test new-person, event, or venue generalization. Source preprocessing may "
            "be noncausal or smoothed, so online sensor performance is unknown. Statistical states "
            "are not crowd regimes or physical mechanisms.\n\n"
            "Controls are the latest increment, causal mean of five increments, and a memoryless "
            "transition control holding fitted emissions fixed. Metrics are descriptive paired "
            "forecast errors on identical eligible support. No p-values or confidence intervals.\n\n"
            "Data source: Oscar Dufour et al., *Dense Crowd Dynamics and Pedestrian Trajectories: "
            "A Multiscale Field Dataset from the Festival of Lights in Lyon*, *Scientific Data* 12, "
            "718 (2025), DOI [10.1038/s41597-025-04732-3](https://doi.org/10.1038/s41597-025-04732-3). "
            "Archive: Zenodo record [10.5281/zenodo.13830435](https://doi.org/10.5281/zenodo.13830435), "
            "record-level CC BY 4.0. Original statistical method background: Lawrence R. Rabiner, "
            "“A Tutorial on Hidden Markov Models and Selected Applications in Speech Recognition,” "
            "*Proceedings of the IEEE* 77(2), 257–286 (1989), "
            "[10.1109/5.18626](https://doi.org/10.1109/5.18626). The experiment settings are a "
            "finite research design, not a reproduction of those authors' work.\n"
        )
        return run_dir
    except BaseException as exc:
        status.update({
            "status": "failed",
            "ended_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_bytes": peak_rss_bytes(),
        })
        write_json(run_dir / "attempt-status.json", status)
        raise


if __name__ == "__main__":
    print(run())
