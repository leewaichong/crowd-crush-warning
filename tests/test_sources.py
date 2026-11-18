"""Unit fixtures for source manifest integrity. These are not source data."""

import hashlib
import copy
import math
import tempfile
import unittest
from pathlib import Path

from crowd_warning.sources import verify_source_manifest


class SourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.payload = b"labelled fixture bytes\n"
        self.file = self.base / "fixture.txt"
        self.file.write_bytes(self.payload)
        self.manifest = {
            "manifest_version": 1,
            "source_record": {
                "doi": "10.0000/fixture",
                "url": "https://example.invalid/source",
                "version": "1.0",
                "license": {"id": "CC-BY-4.0", "scope": "record-only"},
            },
            "files": [{
                "path": "fixture.txt",
                "url": "https://example.invalid/fixture.txt",
                "size_bytes": len(self.payload),
                "sha256": hashlib.sha256(self.payload).hexdigest(),
                "source_checksum": "md5:" + hashlib.md5(self.payload).hexdigest(),
                "retrieved_at": "2026-11-18T10:00:00Z",
                "purpose": "documentation",
                "status": "inspected",
            }],
        }

    def check(self, manifest=None):
        return verify_source_manifest(self.manifest if manifest is None else manifest,
                                      base_dir=self.base)

    def test_accepts_valid_fixture_and_flags_record_level_rights_review(self):
        report = self.check()
        self.assertEqual(report, {"integrity_verified": True, "errors": [],
                                  "files_checked": 1, "bytes_checked": len(self.payload),
                                  "rights_review_required": True})

    def test_valid_manifest_verification_does_not_change_fixture(self):
        before = self.file.stat()
        self.check()
        after = self.file.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))

    def test_rejects_unsupported_manifest_version_and_invalid_metadata(self):
        for mutate in (
            lambda m: m.update(manifest_version=2),
            lambda m: m.update(manifest_version=1.0),
            lambda m: m["source_record"].update(version=" "),
            lambda m: m["source_record"].update(url="relative/path"),
            lambda m: m["files"][0].update(retrieved_at="2026-11-18T10:00:00"),
            lambda m: m["files"][0].update(retrieved_at="not-a-date"),
            lambda m: m["files"][0].update(purpose="unknown"),
            lambda m: m["files"][0].update(status="pending"),
            lambda m: m["source_record"].update(extra=math.inf),
        ):
            with self.subTest(line=mutate.__code__.co_firstlineno):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                self.assertFalse(self.check(manifest)["integrity_verified"])

    def test_rejects_empty_files_list_because_no_payload_was_verified(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["files"] = []
        report = self.check(manifest)
        self.assertFalse(report["integrity_verified"])
        self.assertEqual(report["files_checked"], 0)
        self.assertIn("at least one file", " ".join(report["errors"]))

    def test_malformed_urls_return_structured_errors(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["source_record"]["url"] = "http://[broken"
        manifest["files"][0]["url"] = "http://[broken"
        report = self.check(manifest)
        self.assertFalse(report["integrity_verified"])
        self.assertEqual(len(report["errors"]), 2)

    def test_unhashable_purpose_and_status_return_schema_errors(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["files"][0]["purpose"] = ["documentation"]
        manifest["files"][0]["status"] = {"state": "inspected"}
        report = self.check(manifest)
        self.assertFalse(report["integrity_verified"])
        self.assertTrue(any("purpose" in error for error in report["errors"]))
        self.assertTrue(any("status" in error for error in report["errors"]))

    def test_rejects_malformed_checksums_and_wrong_size_or_bytes(self):
        changes = (
            {"sha256": "xyz"},
            {"source_checksum": "md5:abcd"},
            {"size_bytes": len(self.payload) + 1},
            {"sha256": "0" * 64},
            {"source_checksum": "md5:" + "0" * 32},
        )
        for change in changes:
            with self.subTest(change=change):
                manifest = copy.deepcopy(self.manifest)
                manifest["files"][0].update(change)
                self.assertFalse(self.check(manifest)["integrity_verified"])

    def test_rejects_missing_and_empty_files(self):
        self.file.unlink()
        self.assertIn("does not exist", " ".join(self.check()["errors"]))
        self.file.write_bytes(b"")
        self.assertIn("empty", " ".join(self.check()["errors"]))

    def test_rejects_traversal_absolute_and_symlink_escape(self):
        outside = self.base.parent / (self.base.name + "-outside.txt")
        outside.write_bytes(self.payload)
        self.addCleanup(outside.unlink)
        for path in ("../" + outside.name, str(outside)):
            manifest = copy.deepcopy(self.manifest)
            manifest["files"][0]["path"] = path
            self.assertFalse(self.check(manifest)["integrity_verified"])
        link = self.base / "escape.txt"
        link.symlink_to(outside)
        manifest = copy.deepcopy(self.manifest)
        manifest["files"][0]["path"] = link.name
        self.assertIn("outside", " ".join(self.check(manifest)["errors"]))

    def test_rejects_duplicate_paths(self):
        manifest = copy.deepcopy(self.manifest)
        duplicate = dict(manifest["files"][0])
        duplicate["path"] = "./fixture.txt"
        manifest["files"].append(duplicate)
        report = self.check(manifest)
        self.assertFalse(report["integrity_verified"])
        self.assertIn("duplicated", " ".join(report["errors"]))

    def test_unknown_license_scope_requires_rights_review(self):
        self.manifest["source_record"]["license"]["scope"] = "dataset"
        report = self.check()
        self.assertTrue(report["integrity_verified"])
        self.assertTrue(report["rights_review_required"])

    def test_file_scope_does_not_require_record_level_review(self):
        self.manifest["source_record"]["license"]["scope"] = "file-level"
        self.assertFalse(self.check()["rights_review_required"])


if __name__ == "__main__":
    unittest.main()
