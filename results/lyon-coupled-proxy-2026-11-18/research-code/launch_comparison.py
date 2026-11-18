from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_state(root: Path) -> dict:
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1"],
                            capture_output=True, text=True, check=True).stdout
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return {"git_sha": commit, "clean": not status}


def source_hashes(freeze: dict) -> dict:
    return {key: sha(Path(path)) for key, path in freeze["verified_paths"].items()}


def main() -> int:
    attempt = Path(__file__).resolve().parent
    root = attempt.parents[2]
    freeze_path = attempt / "comparison-freeze.json"
    freeze = json.loads(freeze_path.read_text())
    if len(sys.argv) != 3 or sys.argv[1] != "--attempt-dir" or \
            Path(sys.argv[2]) != Path(freeze["attempt_dir"]):
        raise SystemExit("unexpected invocation")
    if freeze.get("lead_reviewed") is not True or freeze.get("status") != "PREPARED NOT RUN":
        raise SystemExit("explicit lead review marker is required before the one bounded run")
    frozen_config = {key: value for key, value in freeze.items()
                     if key not in ("lead_reviewed", "frozen_configuration_sha256")}
    actual_config_hash = hashlib.sha256(
        json.dumps(frozen_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if actual_config_hash != freeze.get("frozen_configuration_sha256"):
        raise SystemExit("frozen configuration changed beyond the lead review marker")
    outputs = ("comparison-aggregates.json", "comparison-result.json",
               "comparison.stdout.log", "comparison.stderr.log", "comparison-execution.json")
    if any((attempt / name).exists() for name in outputs):
        raise SystemExit("refusing existing output; no overwrite or retry")

    before = tracked_state(root)
    if before != {"git_sha": freeze["git_sha"], "clean": True}:
        raise SystemExit("tracked state differs from frozen clean SHA")
    actual_before_hashes = source_hashes(freeze)
    if actual_before_hashes != freeze["verified_hashes"]:
        raise SystemExit("frozen source/input hash changed before launch")
    prepared_hashes = {key: sha(attempt / filename)
                       for key, filename in freeze["prepared_files"].items()}
    if prepared_hashes != freeze["prepared_file_hashes"]:
        raise SystemExit("prepared code or protocol changed after freeze")
    archive = Path(freeze["archive_path"])
    if archive.stat().st_size != freeze["archive_size_bytes"] or \
            sha(archive) != freeze["archive_sha256"]:
        raise SystemExit("source archive changed before launch")

    started = datetime.datetime.now(datetime.timezone.utc)
    monotonic_start = time.monotonic()
    child_argv = [sys.executable, str(attempt / "run_comparison.py")]
    timed_out = False
    return_code = None
    stdout = b""
    stderr = b""
    try:
        process = subprocess.run(child_argv, cwd=root, capture_output=True,
                                 timeout=freeze["timeout_seconds"])
        stdout, stderr, return_code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        return_code = 124
    (attempt / "comparison.stdout.log").write_bytes(stdout)
    (attempt / "comparison.stderr.log").write_bytes(stderr)
    after = tracked_state(root)
    actual_after_hashes = source_hashes(freeze)
    prepared_hashes_after = {key: sha(attempt / filename)
                             for key, filename in freeze["prepared_files"].items()}
    ended = datetime.datetime.now(datetime.timezone.utc)
    clean_sha_ok = after == {"git_sha": freeze["git_sha"], "clean": True}
    hashes_ok = actual_after_hashes == freeze["verified_hashes"]
    prepared_files_unchanged = prepared_hashes_after == freeze["prepared_file_hashes"]
    status = ("completed" if return_code == 0 and not timed_out and clean_sha_ok and
              hashes_ok and prepared_files_unchanged else "failed")
    record = {
        "status": status,
        "attempt_id": freeze["attempt_id"],
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "duration_seconds": time.monotonic() - monotonic_start,
        "outer_command": freeze["exact_future_command"],
        "outer_argv": freeze["outer_argv"],
        "child_argv": child_argv,
        "timeout_seconds": freeze["timeout_seconds"],
        "timed_out": timed_out,
        "return_code": return_code,
        "python_runtime": sys.version,
        "model_identity": freeze["model_identity"],
        "endpoint": None,
        "tracked_state_before": before,
        "tracked_state_after": after,
        "verified_hashes_before": actual_before_hashes,
        "verified_hashes_after": actual_after_hashes,
        "prepared_file_hashes_before": prepared_hashes,
        "prepared_file_hashes_after": prepared_hashes_after,
        "prepared_files_unchanged": prepared_files_unchanged,
        "clean_sha_and_hashes_unchanged": clean_sha_ok and hashes_ok and prepared_files_unchanged,
    }
    (attempt / "comparison-execution.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
