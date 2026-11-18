"""Verify local files against a source manifest without fetching or changing them."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping
from urllib.parse import urlparse


_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_SOURCE_DIGEST = re.compile(r"([a-zA-Z0-9_-]+):([0-9a-fA-F]+)\Z")
_FILE_FIELDS = {"path", "url", "size_bytes", "sha256", "source_checksum",
                "retrieved_at", "purpose", "status"}


def _finite_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _finite_json(item) for key, item in value.items())
    return False


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_url(value: Any) -> bool:
    if not _nonempty_text(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_timestamp(value: Any) -> bool:
    if not _nonempty_text(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _source_digest(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    match = _SOURCE_DIGEST.fullmatch(value)
    if not match:
        return None
    algorithm, digest = match.groups()
    try:
        expected_length = hashlib.new(algorithm).digest_size * 2
    except (ValueError, TypeError):
        return None
    if len(digest) != expected_length:
        return None
    return algorithm, digest.lower()


def verify_source_manifest(manifest: Any, *, base_dir: str | Path) -> dict[str, Any]:
    """Check manifest metadata and local file bytes; this does not clear rights."""
    errors: list[str] = []
    files_checked = 0
    bytes_checked = 0
    if not _finite_json(manifest):
        errors.append("manifest metadata must contain only finite JSON values")
    if not isinstance(manifest, Mapping):
        return {"integrity_verified": False, "errors": [*errors, "manifest must be an object"],
                "files_checked": 0, "bytes_checked": 0, "rights_review_required": True}

    version = manifest.get("manifest_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        errors.append("manifest_version must be 1")

    record = manifest.get("source_record")
    if not isinstance(record, Mapping):
        errors.append("source_record must be an object")
        record = {}
    for key in ("doi", "version"):
        if not _nonempty_text(record.get(key)):
            errors.append(f"source_record.{key} must be a non-empty string")
    if not _valid_url(record.get("url")):
        errors.append("source_record.url must be an absolute HTTP(S) URL")
    license_info = record.get("license")
    if not isinstance(license_info, Mapping):
        errors.append("source_record.license must be an object")
    else:
        if not _nonempty_text(license_info.get("id")):
            errors.append("source_record.license.id must be a non-empty string")
        scope = license_info.get("scope")
        if not _nonempty_text(scope):
            errors.append("source_record.license.scope must be a non-empty string")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        errors.append("files must be a list")
        entries = []
    elif not entries:
        errors.append("files must contain at least one file to verify")

    base = Path(base_dir).resolve()
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"files[{index}]"
        if not isinstance(entry, Mapping):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(_FILE_FIELDS - entry.keys())
        if missing:
            errors.append(f"{label} missing fields: {', '.join(missing)}")
        if not _valid_url(entry.get("url")):
            errors.append(f"{label}.url must be an absolute HTTP(S) URL")
        size = entry.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            errors.append(f"{label}.size_bytes must be a positive integer")
        if not isinstance(entry.get("sha256"), str) or not _SHA256.fullmatch(entry.get("sha256", "")):
            errors.append(f"{label}.sha256 must be 64 hexadecimal characters")
        source_checksum = _source_digest(entry.get("source_checksum"))
        if source_checksum is None:
            errors.append(f"{label}.source_checksum must be algorithm:hex with a valid digest length")
        if not _valid_timestamp(entry.get("retrieved_at")):
            errors.append(f"{label}.retrieved_at must be an ISO8601 timestamp with timezone")
        purpose = entry.get("purpose")
        if not isinstance(purpose, str) or purpose not in {"documentation", "measurement"}:
            errors.append(f"{label}.purpose must be documentation or measurement")
        status = entry.get("status")
        if not isinstance(status, str) or status not in {"downloaded", "inspected"}:
            errors.append(f"{label}.status must be downloaded or inspected")

        relative = entry.get("path")
        if not _nonempty_text(relative):
            errors.append(f"{label}.path must be a non-empty relative path")
            continue
        candidate = Path(relative)
        if candidate.is_absolute() or PureWindowsPath(relative).is_absolute() or ".." in candidate.parts \
                or ".." in PureWindowsPath(relative).parts:
            errors.append(f"{label}.path must not be absolute or traverse directories")
            continue
        normalized = candidate.as_posix()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in seen:
            errors.append(f"{label}.path is duplicated")
            continue
        seen.add(normalized)
        target = base / candidate
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError):
            errors.append(f"{label}.path does not exist")
            continue
        try:
            resolved.relative_to(base)
        except ValueError:
            errors.append(f"{label}.path resolves outside base_dir")
            continue
        if not resolved.is_file():
            errors.append(f"{label}.path is not a regular file")
            continue
        try:
            digest = hashlib.sha256()
            secondary = hashlib.new(source_checksum[0]) if source_checksum else None
            size_actual = 0
            with resolved.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    size_actual += len(chunk)
                    digest.update(chunk)
                    if secondary:
                        secondary.update(chunk)
        except OSError:
            errors.append(f"{label}.path could not be read")
            continue
        files_checked += 1
        bytes_checked += size_actual
        if size_actual == 0:
            errors.append(f"{label}.path is empty")
        if isinstance(size, int) and not isinstance(size, bool) and size_actual != size:
            errors.append(f"{label}.size_bytes does not match file size")
        if isinstance(entry.get("sha256"), str) and _SHA256.fullmatch(entry.get("sha256", "")) \
                and digest.hexdigest().lower() != entry["sha256"].lower():
            errors.append(f"{label}.sha256 does not match file bytes")
        if secondary and secondary.hexdigest().lower() != source_checksum[1]:
            errors.append(f"{label}.source_checksum does not match file bytes")

    return {"integrity_verified": not errors, "errors": errors,
            "files_checked": files_checked, "bytes_checked": bytes_checked,
            "rights_review_required": True}
