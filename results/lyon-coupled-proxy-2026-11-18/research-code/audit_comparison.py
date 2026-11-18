#!/usr/bin/env python3
"""Independent numerical consistency audit for a completed CROWD16 comparison."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import shlex
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = {
    "runner": "bb51601c06da103c39a1ca3e8b62d9edc4d63f8898c1d539aa706a662d53f1da",
    "protocol": "baa7e74f904fb54a3fbc5ed44ec5a31c089db747dfb091b664a1ea43dcfd5f29",
    "launcher": "5533b6d997b1a8e8ef13823577aa4a464a778f261632fc9fae69e3c8f8241d64",
    "source_archive": "efd80ef53dcf124286e5ca280d7d3daf52e0b6b2fe9441afb1d23c9a0baf150c",
    "comparison_git_sha": "982b145e43f3e1c6f15729861a594f993a396155",
}
MEMBERS = (
    "Data_Madras/TopView_trajectories/TopView_1A.txt",
    "Data_Madras/TopView_trajectories/TopView_2A.txt",
)
ARMS = ("coupled", "uncoupled", "persistence")
REPLICATES = (0, 1, 2)
ZONES = 4
PATHS = 256
HORIZON = 30.0
LIMIT = 180.0
DEADLINE = None


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def alarm_timeout(_signum, _frame):
    raise TimeoutError("180 second audit bound exceeded")


def fit_from_retained_q(record):
    training = record["training_q"]
    require(bool(training), "training q is empty")
    frames = [row["frame"] for row in training]
    times = [row["source_t_s"] for row in training]
    values = [row["q"] for row in training]
    require(all(isinstance(f, int) for f in frames), "training frame is not an integer")
    require(all(b == a + 1 for a, b in zip(frames, frames[1:])), "training frames are not consecutive")
    require(all(len(row) == ZONES and all(number(x) for x in row) for row in values),
            "training q is incomplete or nonfinite")
    require(all(number(t) for t in times) and all(a < b for a, b in zip(times, times[1:])),
            "training times are invalid")
    ordered = sorted(x for row in values for x in row)
    boundary = ordered[math.ceil(.95 * len(ordered)) - 1]
    require(number(boundary) and boundary > 0, "invalid retained training q boundary")
    mus, sigmas = [], []
    for z in range(ZONES):
        elapsed = times[-1] - times[0]
        mu = (values[-1][z] - values[0][z]) / elapsed
        residual = sum(((values[i + 1][z] - values[i][z]) - mu * (times[i + 1] - times[i])) ** 2
                       for i in range(len(times) - 1))
        total = sum(times[i + 1] - times[i] for i in range(len(times) - 1))
        sigma = math.sqrt(residual / total)
        require(number(mu) and number(sigma) and sigma > 0, "invalid independently fitted coefficients")
        mus.append(mu)
        sigmas.append(sigma)
    return mus, sigmas, boundary


def eligible_origins(record, start, stop, boundary):
    series = record["q_by_frame"]
    require(len(series) >= stop, "q series ends before partition")
    times = [row["source_t_s"] for row in series]
    q = [row["q"] for row in series]
    end_time = times[stop - 1]
    excluded = {"horizon_unavailable": 0, "incomplete_current_q": 0,
                "current_at_or_above_boundary": 0, "incomplete_future_target": 0}
    origins = []
    for frame in range(start, stop):
        if times[frame] + HORIZON > end_time:
            excluded["horizon_unavailable"] += 1
            continue
        if len(q[frame]) != ZONES or any(not number(v) for v in q[frame]):
            excluded["incomplete_current_q"] += 1
            continue
        if any(v >= boundary for v in q[frame]):
            excluded["current_at_or_above_boundary"] += 1
            continue
        future = [i for i in range(frame + 1, stop) if times[i] <= times[frame] + HORIZON]
        if not future or any(len(q[i]) != ZONES or any(not number(v) for v in q[i]) for i in future):
            excluded["incomplete_future_target"] += 1
            continue
        label = int(any(v >= boundary for i in future for v in q[i]))
        origins.append((frame, times[frame], label))
    return origins, excluded


def seed_for(member, frame, replicate):
    payload = (member + "|" + str(frame) + "|" + str(replicate)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def independent_path(initial, mu, sigma, coupling, noise):
    x = list(initial)
    crossed = any(v >= CURRENT_BOUNDARY[0] for v in x)
    elapsed = 0.0
    step = 0
    while elapsed < HORIZON and not crossed:
        if DEADLINE is not None and time.monotonic() > DEADLINE:
            raise TimeoutError("180 second audit bound exceeded")
        dt = min(1.0, HORIZON - elapsed)
        mean = sum(x) / ZONES
        next_x = []
        for z in range(ZONES):
            v = x[z] + mu[z] * dt + coupling * (mean - x[z]) * dt
            v += sigma[z] * math.sqrt(dt) * noise[step][z]
            if not math.isfinite(v):
                raise ValueError("nonfinite value during independent replay")
            next_x.append(v)
        x = next_x
        elapsed += dt
        step += 1
        crossed = any(v >= CURRENT_BOUNDARY[0] for v in x)
    return int(crossed)


CURRENT_BOUNDARY = [0.0]


def replay_origin(member, frame, initial, rep, mus, sigmas, boundary):
    require(len(initial) == ZONES and all(number(v) for v in initial), "selected origin q invalid")
    CURRENT_BOUNDARY[0] = boundary
    got = {arm: [] for arm in ("coupled", "uncoupled")}
    rng = random.Random(seed_for(member, frame, rep))
    noise_paths = [[[rng.gauss(0.0, 1.0) for _ in range(ZONES)] for _ in range(30)]
                   for _ in range(PATHS)]
    for noise in noise_paths:
        got["coupled"].append(independent_path(initial, mus, sigmas, .15, noise))
        got["uncoupled"].append(independent_path(initial, mus, sigmas, 0.0, noise))
    return {"coupled": sum(got["coupled"]) / PATHS,
            "uncoupled": sum(got["uncoupled"]) / PATHS}


def audit(attempt, started, tick):
    freeze_path = attempt / "comparison-freeze.json"
    freeze = json.loads(freeze_path.read_text())
    runner = attempt / freeze["prepared_files"]["runner"]
    protocol = attempt / freeze["prepared_files"]["protocol"]
    launcher = attempt / freeze["prepared_files"]["launcher"]
    require(freeze["prepared_file_hashes"]["runner"] == EXPECTED["runner"] and
            freeze["prepared_file_hashes"]["protocol"] == EXPECTED["protocol"] and
            freeze["prepared_file_hashes"]["launcher"] == EXPECTED["launcher"],
            "freeze's original prepared artifact hashes differ")
    require(digest(runner) == EXPECTED["runner"], "frozen numerical runner hash mismatch")
    require(digest(protocol) == EXPECTED["protocol"], "frozen numerical protocol hash mismatch")
    require(digest(launcher) == EXPECTED["launcher"], "frozen launcher hash mismatch")
    require(freeze["archive_sha256"] == EXPECTED["source_archive"], "frozen source archive hash mismatch")
    expected_config = {k: v for k, v in freeze.items()
                       if k not in ("lead_reviewed", "frozen_configuration_sha256")}
    config_hash = hashlib.sha256(json.dumps(expected_config, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    require(config_hash == freeze["frozen_configuration_sha256"], "frozen configuration hash mismatch")
    require(freeze["status"] == "PREPARED NOT RUN" and freeze["lead_reviewed"] is True,
            "comparison freeze is not approved")
    names = ("comparison-aggregates.json", "comparison-result.json", "comparison-execution.json")
    paths = [attempt / n for n in names]
    require(all(p.is_file() for p in paths), "comparison output or execution record is missing")
    aggregates, result, execution = [json.loads(p.read_text()) for p in paths]
    require(aggregates.get("status") == "private_descriptive_aggregates", "unexpected aggregate status")
    require(execution.get("status") == "completed" and execution.get("return_code") == 0 and
            execution.get("timed_out") is False,
            "actual comparison execution did not complete successfully; no rerun was attempted")
    require(execution.get("attempt_id") == freeze["attempt_id"], "execution attempt ID differs from freeze")
    completion_path = Path("/Users/waichong/projects/crowd-crush-warning/work/milestone-09/comparison-run-completion.json")
    require(completion_path.is_file(), "comparison completion marker is missing")
    completion = json.loads(completion_path.read_text())
    require(completion.get("exit_code") == 0 and
            completion.get("execution_file") == str(paths[2]),
            "completion marker does not identify this successful comparison execution")
    expected_git = freeze["git_sha"]
    for field in ("tracked_state_before", "tracked_state_after"):
        state = execution.get(field, {})
        require(state.get("clean") is True and state.get("git_sha") == expected_git == EXPECTED["comparison_git_sha"],
                "comparison tracked state differs from the frozen clean SHA")
    require(execution.get("clean_sha_and_hashes_unchanged") is True and
            execution.get("prepared_files_unchanged") is True,
            "comparison execution did not retain clean, unchanged provenance")
    frozen_inputs = freeze["verified_hashes"]
    require(execution.get("verified_hashes_before") == frozen_inputs and
            execution.get("verified_hashes_after") == frozen_inputs,
            "actual verified before/after hashes differ from the freeze")
    prepared = {"runner": EXPECTED["runner"], "protocol": EXPECTED["protocol"],
                "launcher": EXPECTED["launcher"]}
    require(execution.get("prepared_file_hashes_before") == prepared and
            execution.get("prepared_file_hashes_after") == prepared and
            freeze["prepared_file_hashes"] == prepared,
            "actual prepared before/after hashes differ from frozen/current code")
    inner_started = datetime.fromisoformat(execution["started_utc"])
    inner_ended = datetime.fromisoformat(execution["ended_utc"])
    outer_completed = datetime.fromisoformat(completion["at_utc"])
    audit_started = datetime.fromisoformat(started)
    require(all(value.utcoffset() is not None for value in
                (inner_started, inner_ended, outer_completed, audit_started)) and
            inner_started <= inner_ended <= outer_completed <= audit_started,
            "comparison and completion timestamps are not in valid chronological order")
    audit_root = Path(__file__).resolve().parent
    manifest_path = audit_root / "audit-freeze.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get("audit_script_sha256") == digest(Path(__file__).resolve()) and
            manifest.get("audit_protocol_sha256") == digest(audit_root / "comparison-audit-protocol.md"),
            "audit script or protocol changed after audit freeze")
    require(manifest.get("comparison_execution_sha256") == digest(paths[2]) and
            manifest.get("comparison_completion_sha256") == digest(completion_path),
            "comparison execution or completion marker changed after audit freeze")
    frozen_input_paths = [freeze_path, runner, protocol, launcher, *paths, completion_path]
    input_hashes = {str(p): digest(p) for p in frozen_input_paths}
    require(manifest.get("input_sha256") == input_hashes,
            "one or more frozen comparison inputs changed before audit")
    require(len(aggregates["records"]) == len(MEMBERS), "unexpected aggregate recording count")
    summary_by_key = {(r["member"], r["partition"]): r for r in result["records"]}
    require({r["member"] for r in aggregates["records"]} == set(MEMBERS),
            "aggregate recording membership differs")
    require(set(summary_by_key) == {(m, p) for m in MEMBERS for p in ("validation", "test")},
            "result summary does not contain exactly the frozen recording/partition pairs")
    outputs = []
    checks = 0
    for record in aggregates["records"]:
        member = record["member"]
        require(member in MEMBERS, "unexpected recording member")
        mus, sigmas, boundary = fit_from_retained_q(record)
        n = len(record["q_by_frame"])
        edge, edge80 = int(.6 * n), int(.8 * n)
        require([row["frame"] for row in record["training_q"]] == list(range(2, edge)),
                "training q frame range differs from frozen split")
        require([row["frame"] for row in record["q_by_frame"]] == list(range(n)),
                "retained q series frames are not consecutive from zero")
        require(all(row["source_t_s"] == record["q_by_frame"][row["frame"]]["source_t_s"]
                    for row in record["training_q"]), "training q times differ from retained full series")
        for key, actual, label in (("fit_mu", mus, "mu"), ("fit_sigma", sigmas, "sigma")):
            for a, b in zip(record[key], actual):
                require(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-14), "independent " + label + " mismatch")
                checks += 1
        require(math.isclose(record["training_boundary"], boundary, rel_tol=0, abs_tol=0),
                "independent training q boundary mismatch")
        checks += 1
        for part, start, stop in (("validation", len(record["training_q"]) + 2,
                                   int(len(record["q_by_frame"]) * .8)),
                                  ("test", int(len(record["q_by_frame"]) * .8),
                                   len(record["q_by_frame"]))):
            # Use frozen split rules, with N inferred from the complete retained frame series.
            start, stop = (edge, edge80) if part == "validation" else (edge80, n)
            origins, excluded = eligible_origins(record, start, stop, boundary)
            section = record["partitions"][part]
            metrics = section["metrics"]
            stored = section["origin_forecasts"]
            require(len(stored) == len(origins) * len(REPLICATES),
                    "retained forecast row denominator differs from independent selection")
            expected_exclusions = metrics["excluded_origins"]
            require(excluded == expected_exclusions, "exclusion denominators differ")
            require(metrics["eligible_origins"] == len(origins), "eligible-origin denominator differs")
            require(metrics["status"] == ("NO_EVALUABLE_ORIGINS" if not origins else "descriptive_scores_available"),
                    "partition status differs from eligible-origin count")
            require(metrics["candidate_horizon_origins"] == stop - start - excluded["horizon_unavailable"],
                    "candidate horizon denominator differs")
            require(metrics["event_count"] == sum(y for _, _, y in origins) and
                    metrics["overlapping_origin_exposure_s"] == len(origins) * HORIZON,
                    "event count or overlapping exposure differs")
            per_rep = []
            for rep in REPLICATES:
                rows = [r for r in stored if r["replicate"] == rep]
                require(len(rows) == len(origins), "replicate forecast row count differs")
                scores = {arm: [] for arm in ARMS}
                for row, (frame, source_t, label) in zip(rows, origins):
                    require(row["origin_frame"] == frame and row["label"] == label and
                            math.isclose(row["source_t_s"], source_t, rel_tol=0, abs_tol=0),
                            "retained origin details differ")
                    pred = row["predictions"]
                    require(all(number(pred[a]) for a in ARMS), "nonfinite retained prediction")
                    for arm in ARMS:
                        scores[arm].append((pred[arm] - label) ** 2)
                briers = {arm: (sum(scores[arm]) / len(scores[arm]) if scores[arm] else None)
                          for arm in ARMS}
                saved = next(x for x in metrics["replicates"] if x["replicate"] == rep)
                require(saved["eligible_origins"] == len(origins) and
                        saved["event_count"] == sum(y for _, _, y in origins),
                        "replicate denominator or event count differs")
                for arm in ARMS:
                    a, b = saved["brier"][arm], briers[arm]
                    require(a is None and b is None or number(a) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-14),
                            "replicate Brier mismatch")
                per_rep.append(briers)
                checks += 1
            means = {arm: (sum(x[arm] for x in per_rep) / 3 if origins else None) for arm in ARMS}
            ranges = {arm: ({"minimum": min(x[arm] for x in per_rep),
                             "maximum": max(x[arm] for x in per_rep)} if origins else None) for arm in ARMS}
            require(metrics["mean_brier_across_three_replicates"] == means or
                    all(metrics["mean_brier_across_three_replicates"][a] is None and means[a] is None or
                        math.isclose(metrics["mean_brier_across_three_replicates"][a], means[a], rel_tol=1e-12, abs_tol=1e-14)
                        for a in ARMS), "mean Brier mismatch")
            for arm in ARMS:
                saved_range = metrics["replicate_brier_min_max"][arm]
                if origins:
                    require(math.isclose(saved_range["minimum"], ranges[arm]["minimum"], rel_tol=1e-12, abs_tol=1e-14) and
                            math.isclose(saved_range["maximum"], ranges[arm]["maximum"], rel_tol=1e-12, abs_tol=1e-14),
                            "replicate Brier range mismatch")
                else:
                    require(saved_range is None, "empty partition should have null Brier range")
            comparisons = {control: ("no_evaluable_origins" if not origins else
                                     "lower" if means["coupled"] < means[control] else
                                     "equal" if means["coupled"] == means[control] else "higher")
                           for control in ("uncoupled", "persistence")}
            require(metrics["coupled_mean_brier_vs_controls"] == comparisons, "control comparison mismatch")
            skill = ("NO_EVALUABLE_ORIGINS" if part == "test" and not origins else
                     "strictly_lower_than_both" if part == "test" and
                     comparisons["uncoupled"] == comparisons["persistence"] == "lower" else
                     "fails_strict_improvement_over_both" if part == "test" else None)
            require(metrics["coupled_test_skill_falsifier"] == skill,
                    "test skill falsifier status differs")
            summary = summary_by_key[(member, part)]
            require(summary["eligible_origins"] == len(origins) and
                    summary["candidate_horizon_origins"] == stop - start - excluded["horizon_unavailable"] and
                    summary["event_count"] == sum(y for _, _, y in origins) and
                    summary["overlapping_origin_exposure_s"] == len(origins) * HORIZON and
                    summary["excluded_origins"] == excluded and
                    summary["status"] == metrics["status"] and
                    summary["mean_brier_across_three_replicates"] == means and
                    summary["replicate_brier_min_max"] == ranges and
                    summary["coupled_mean_brier_vs_controls"] == comparisons and
                    summary["coupled_test_skill_falsifier"] == skill,
                    "public summary values differ from private aggregates")
            # Pick first, middle and last eligible origin; deduplicate when fewer than three exist.
            chosen = []
            if origins:
                for index in (0, len(origins) // 2, len(origins) - 1):
                    origin = origins[index]
                    if origin not in chosen:
                        chosen.append(origin)
            detail_by_key = {(r["replicate"], r["origin_frame"]): r for r in stored}
            replayed = []
            for frame, source_t, label in chosen:
                for rep in REPLICATES:
                    noise_row = detail_by_key[(rep, frame)]
                    initial = record["q_by_frame"][frame]["q"]
                    independent = replay_origin(member, frame, initial, rep, mus, sigmas, boundary)
                    for arm in ("coupled", "uncoupled"):
                        require(math.isclose(noise_row["predictions"][arm], independent[arm], rel_tol=0, abs_tol=0),
                                "selected-origin independent path replay mismatch")
                replayed.append({"origin_frame": frame, "label": label, "source_t_s": source_t,
                                 "replicates_replayed": list(REPLICATES)})
            outputs.append({"member": member, "partition": part,
                            "eligible_origins": len(origins), "excluded_origins": excluded,
                            "selected_replay_origins": replayed,
                            "recomputed_mean_brier": means, "recomputed_min_max": ranges,
                            "control_comparisons": comparisons})
    require(result.get("safety_evaluation") is False, "summary safety_evaluation flag is not false")
    return {"status": "NUMERICAL_CONSISTENCY_AUDIT_PASSED", "scope":
            "Numerical consistency of retained private outputs only. Fit coefficients are recomputed from retained training q; no independent source-q reconstruction is claimed. This does not verify source measurements or warning effectiveness.",
            "method": "local standard-library independent recomputation from retained data and selected-origin Euler/RNG replay",
            "endpoint": None, "authoring_route_model_profile": None,
            "recordings": outputs, "assertion_groups_checked": checks,
            "frozen_hashes_checked": {"runner": EXPECTED["runner"], "protocol": EXPECTED["protocol"],
                                       "launcher": EXPECTED["launcher"],
                                       "source_archive_as_pinned_in_freeze": EXPECTED["source_archive"]},
            "comparison_execution": {"status": execution["status"],
                                     "return_code": execution["return_code"],
                                     "timed_out": execution["timed_out"],
                                     "started_utc": execution["started_utc"],
                                     "ended_utc": execution["ended_utc"],
                                     "git_sha": expected_git},
            "audit_freeze": manifest,
            "input_sha256": input_hashes,
            "audit_started_utc": started, "audit_completed_utc": now(),
            "runtime_seconds": time.monotonic() - tick}


def main():
    global DEADLINE
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-dir", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    require(args.timeout_seconds == 180, "audit is fixed to a 180 second bound")
    attempt = args.attempt_dir.resolve()
    started, tick = now(), time.monotonic()
    result_path = Path(__file__).resolve().parent / "comparison-audit-result.json"
    execution_path = Path(__file__).resolve().parent / "comparison-audit-execution.json"
    stdout_path = Path(__file__).resolve().parent / "comparison-audit.stdout.log"
    stderr_path = Path(__file__).resolve().parent / "comparison-audit.stderr.log"
    if any(p.exists() for p in (result_path, execution_path, stdout_path, stderr_path)):
        raise SystemExit("refusing to overwrite existing audit artifacts")
    DEADLINE = tick + LIMIT
    signal.signal(signal.SIGALRM, alarm_timeout)
    status, detail = "FAILED", None
    stdout_buffer, stderr_buffer = io.StringIO(), io.StringIO()
    stdout_buffer.write("CROWD16 numerical consistency audit started at " + started + "\n")
    try:
        signal.setitimer(signal.ITIMER_REAL, LIMIT)
        detail = audit(attempt, started, tick)
        require(time.monotonic() <= DEADLINE, "180 second audit bound exceeded")
        status = detail["status"]
        stdout_buffer.write("Audit status: " + status + "\n")
    except BaseException as exc:
        detail = {"status": status, "error": str(exc), "traceback": traceback.format_exc(),
                  "audit_started_utc": started, "audit_completed_utc": now(),
                  "runtime_seconds": time.monotonic() - tick}
        stderr_buffer.write(detail["traceback"])
    signal.setitimer(signal.ITIMER_REAL, 0)
    stdout_path.write_text(stdout_buffer.getvalue())
    stderr_path.write_text(stderr_buffer.getvalue())
    result_path.write_text(json.dumps(detail, sort_keys=True, indent=2) + "\n")
    command_argv = [sys.executable, *sys.argv]
    execution = {"status": status, "exit_status": 0 if status.endswith("PASSED") else 1,
                 "command_argv": command_argv, "exact_command": shlex.join(command_argv),
                 "started_utc": started, "completed_utc": now(),
                 "runtime_seconds": time.monotonic() - tick,
                 "result_sha256": digest(result_path),
                 "stdout_sha256": digest(stdout_path), "stderr_sha256": digest(stderr_path),
                 "audit_script_sha256": digest(Path(__file__).resolve()), "python": sys.version,
                 "method": "local standard-library numerical audit", "endpoint": None,
                 "authoring_route_model_profile": None}
    execution_path.write_text(json.dumps(execution, sort_keys=True, indent=2) + "\n")
    raise SystemExit(execution["exit_status"])


if __name__ == "__main__":
    main()
