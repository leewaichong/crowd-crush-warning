"""Clearly labelled synthetic unit fixtures, not crowd effectiveness results."""

import unittest
import hashlib
import subprocess
import tempfile
from pathlib import Path

from crowd_warning.evaluation import (alarm_episodes, brier_accounting, brier_score,
    disjoint_event_splits, false_alarms_per_monitoring_hour, match_alarm_episodes,
    match_events, monitoring_exposure, split_by_venue_and_event, verify_run_provenance)


class EvaluationFixtureTests(unittest.TestCase):
    def test_matching_is_scoped_by_recording_and_zone_type(self):
        forecasts = [
            {"timestamp_s": 9, "zone_id": "A", "event_id": "video1"},
            {"timestamp_s": 9, "zone_id": "A", "event_id": "video2"},
        ]
        events = [{"timestamp_s": 10, "zone_id": "A", "event_id": "video2"}]
        result = match_events(forecasts, events, horizon_s=2)
        self.assertEqual([m["forecast_index"] for m in result["matches"]], [1])
        self.assertEqual(result["false_alarm_count"], 1)
        typed = match_events([{"timestamp_s": 9, "zone_id": True}],
                             [{"timestamp_s": 10, "zone_id": 1}], horizon_s=2)
        self.assertEqual(typed["matched_event_count"], 0)

    def test_recording_context_and_venue_scope_are_shared_by_episodes(self):
        forecasts = [
            {"timestamp_s": 9, "zone_id": "A", "recording_id": "r1", "event_id": "f1", "venue_id": 1},
            {"timestamp_s": 9, "zone_id": "A", "recording_id": "r2", "event_id": "f2", "venue_id": 1},
        ]
        events = [{"timestamp_s": 10, "zone_id": "A", "recording_id": "r2", "event_id": "outcome", "venue_id": 1}]
        result = match_alarm_episodes(forecasts, events, horizon_s=2, episode_gap_s=1)
        self.assertEqual(result["episode_count"], 2)
        self.assertEqual(result["matches"][0]["forecast_indices"], [1])
        self.assertEqual(result["false_alarm_count"], 1)
        self.assertEqual([ep["venue_id"] for ep in alarm_episodes(forecasts, episode_gap_s=1)["episodes"]], [1, 1])
        venue_result = match_events(
            [{"timestamp_s": 9, "zone_id": "A", "recording_id": "r", "venue_id": "v1"}],
            [{"timestamp_s": 10, "zone_id": "A", "recording_id": "r", "venue_id": "v2"}],
            horizon_s=2,
        )
        self.assertEqual(venue_result["matched_event_count"], 0)

    def test_mixed_missing_context_rejected_across_pooled_rows(self):
        with self.assertRaisesRegex(ValueError, "recording_id"):
            match_events([{"timestamp_s": 9, "zone_id": "A", "recording_id": "r"}],
                         [{"timestamp_s": 10, "zone_id": "A"}], horizon_s=2)
        with self.assertRaisesRegex(ValueError, "venue_id"):
            match_alarm_episodes([{"timestamp_s": 9, "zone_id": "A", "recording_id": "r", "venue_id": "v"}],
                                 [{"timestamp_s": 10, "zone_id": "A", "recording_id": "r"}],
                                 horizon_s=2, episode_gap_s=1)
        for bad in (None, "", "  ", True, 1.5):
            with self.subTest(value=bad), self.assertRaisesRegex(ValueError, "recording_id"):
                match_events([{"timestamp_s": 9, "zone_id": "A", "recording_id": bad}],
                             [{"timestamp_s": 10, "zone_id": "A", "recording_id": "r"}], horizon_s=2)

    def test_recording_id_precedes_event_id_for_multiple_events(self):
        forecasts = [{"timestamp_s": 9, "zone_id": "A", "recording_id": "r", "event_id": "hazard-1"},
                     {"timestamp_s": 10, "zone_id": "A", "recording_id": "r", "event_id": "hazard-2"}]
        events = [{"timestamp_s": 11, "zone_id": "A", "recording_id": "r", "event_id": "outcome-1"},
                  {"timestamp_s": 12, "zone_id": "A", "recording_id": "r", "event_id": "outcome-2"}]
        self.assertEqual(match_events(forecasts, events, horizon_s=3)["matched_event_count"], 2)

    def test_duplicate_deduplication_is_context_local_and_legacy_matches(self):
        rows = [{"timestamp_s": 9, "zone_id": "A", "event_id": "r1"},
                {"timestamp_s": 9, "zone_id": "A", "event_id": "r1"},
                {"timestamp_s": 9, "zone_id": "A", "event_id": "r2"}]
        episodes = alarm_episodes(rows, episode_gap_s=1)
        self.assertEqual(episodes["duplicate_forecast_indices"], [1])
        self.assertEqual(len(episodes["episodes"]), 2)
        legacy = match_events([{"timestamp_s": 9, "zone_id": "A"}],
                              [{"timestamp_s": 10, "zone_id": "A"}], horizon_s=2)
        self.assertEqual(legacy["matched_event_count"], 1)

    def test_alarm_episodes_revalidates_reserved_context_keys(self):
        forged = {"_context_fields": ("recording_id",),
                  "_context_key": (("recording_id", "str", "shared"),),
                  "_context_values": {"recording_id": "shared"}}
        rows = [
            {"timestamp_s": 9, "zone_id": "A", "recording_id": "r1", **forged},
            {"timestamp_s": 10, "zone_id": "A", "recording_id": "r2", **forged},
        ]
        result = alarm_episodes(rows, episode_gap_s=2)
        self.assertEqual(len(result["episodes"]), 2)
        self.assertEqual([episode["recording_id"] for episode in result["episodes"]], ["r1", "r2"])

        missing_scope = [{"timestamp_s": 9, "zone_id": "A", "recording_id": "r1", **forged},
                         {"timestamp_s": 10, "zone_id": "A", **forged}]
        with self.assertRaisesRegex(ValueError, "recording_id"):
            alarm_episodes(missing_scope, episode_gap_s=2)

    def test_event_matches_and_counts_false_alarms_and_misses(self):
        forecasts = [
            {"timestamp_s": 10, "zone_id": "a"},
            {"timestamp_s": 20, "zone_id": "b"},
            {"timestamp_s": 40, "zone_id": "a"},
        ]
        events = [{"timestamp_s": 30, "zone_id": "a"}, {"timestamp_s": 60, "zone_id": "b"}]
        result = match_events(forecasts, events, horizon_s=25)
        self.assertEqual(result["matches"], [{"event_index": 0, "forecast_index": 0, "lead_time_s": 20.0}])
        self.assertEqual(result["missed_event_count"], 1)
        self.assertEqual(result["false_alarm_count"], 2)
        self.assertEqual(result["mean_lead_time_s"], 20.0)

    def test_forecast_at_event_time_matches_with_zero_lead(self):
        result = match_events([{"timestamp_s": 4, "zone_id": 1}], [{"timestamp_s": 4, "zone_id": 1}], horizon_s=0)
        self.assertEqual(result["lead_times_s"], [0.0])

    def test_no_match_reports_none_mean(self):
        result = match_events([], [{"timestamp_s": 4, "zone_id": 1}], horizon_s=2)
        self.assertIsNone(result["mean_lead_time_s"])

    def test_repeated_forecasts_form_one_episode_and_exact_duplicates_are_reported(self):
        rows = [{"timestamp_s": 10, "zone_id": "a"}, {"timestamp_s": 10, "zone_id": "a"},
                {"timestamp_s": 12, "zone_id": "a"}, {"timestamp_s": 30, "zone_id": "a"}]
        grouped = alarm_episodes(rows, episode_gap_s=3)
        self.assertEqual([e["forecast_indices"] for e in grouped["episodes"]], [[0, 2], [3]])
        self.assertEqual(grouped["duplicate_forecast_indices"], [1])
        matched = match_alarm_episodes(rows, [{"timestamp_s": 15, "zone_id": "a"}], horizon_s=5, episode_gap_s=3)
        self.assertEqual(matched["episode_count"], 2)
        self.assertEqual(matched["false_alarm_count"], 1)
        with self.assertRaisesRegex(ValueError, "input_cutoff_s"):
            match_alarm_episodes([{"timestamp_s": 10, "input_cutoff_s": 11, "zone_id": "a"}],
                                 [], horizon_s=3, episode_gap_s=1)
        with self.assertRaisesRegex(ValueError, "equal timestamp_s"):
            match_alarm_episodes([{"timestamp_s": 10, "forecast_origin_s": 11, "zone_id": "a"}],
                                 [], horizon_s=3, episode_gap_s=1)

    def test_mixed_zone_id_types_keep_separate_episode_groups(self):
        rows = [{"timestamp_s": 0, "zone_id": 1}, {"timestamp_s": 1, "zone_id": "1"},
                {"timestamp_s": 2, "zone_id": 1}]
        episodes = alarm_episodes(rows, episode_gap_s=5)["episodes"]
        self.assertEqual(len(episodes), 2)
        self.assertEqual([episode["forecast_indices"] for episode in episodes], [[0, 2], [1]])
        with self.assertRaisesRegex(ValueError, "finite scalar"):
            alarm_episodes([{"timestamp_s": 0, "zone_id": []}], episode_gap_s=1)

    def test_exposure_excludes_invalid_periods_and_rejects_overlap(self):
        result = monitoring_exposure([{"start_s": 0, "end_s": 3600, "valid": True},
                                      {"start_s": 3600, "end_s": 7200, "valid": False}])
        self.assertEqual(result["monitoring_hours"], 1)
        self.assertEqual(result["excluded"], [{"index": 1, "reason": "invalid_period", "duration_s": 3600.0}])
        self.assertEqual(result["excluded_seconds"], 3600)
        with self.assertRaisesRegex(ValueError, "overlap"):
            monitoring_exposure([{"start_s": 0, "end_s": 10, "valid": True},
                                 {"start_s": 9, "end_s": 20, "valid": True}])
        with self.assertRaises(ValueError):
            monitoring_exposure([{"start_s": 0, "end_s": float("inf"), "valid": True}])
        for intervals in (
            [{"start_s": 0, "end_s": 10, "valid": True}, {"start_s": 5, "end_s": 8, "valid": False}],
            [{"start_s": 0, "end_s": 10, "valid": False}, {"start_s": 5, "end_s": 8, "valid": False}],
        ):
            with self.assertRaisesRegex(ValueError, "overlap"):
                monitoring_exposure(intervals)
        for segment in (
            {"start_s": 1, "end_s": 1, "valid": True},
            {"start_s": 2, "end_s": 1, "valid": False},
            {"start_s": 0, "end_s": 1},
            {"start_s": 0, "end_s": 1, "valid": 1},
        ):
            with self.assertRaises(ValueError):
                monitoring_exposure([segment])
        with self.assertRaisesRegex(ValueError, "accumulated"):
            monitoring_exposure([
                {"start_s": -1.7e308, "end_s": -0.8e308, "valid": True},
                {"start_s": 0.8e308, "end_s": 1.7e308, "valid": True},
            ])

    def test_venue_split_membership_does_not_depend_on_input_order(self):
        rows = [{"venue_id": f"v{i}", "event_id": f"e{i}", "input_cutoff_s": 1,
                 "forecast_origin_s": 2, "outcome_timestamp_s": 3} for i in range(8)]
        first = split_by_venue_and_event(rows, train_fraction=0.5, seed=4)
        second = split_by_venue_and_event(list(reversed(rows)), train_fraction=0.5, seed=4)
        for partition in ("train", "test"):
            self.assertEqual({r["venue_id"] for r in first[partition]},
                             {r["venue_id"] for r in second[partition]})

    def test_venue_event_split_and_chronology(self):
        rows = [{"venue_id": f"v{i}", "event_id": f"e{i}", "input_cutoff_s": 1,
                 "forecast_origin_s": 2, "outcome_timestamp_s": 3} for i in range(8)]
        split = split_by_venue_and_event(rows, train_fraction=0.5, seed=4)
        self.assertFalse({r["venue_id"] for r in split["train"]} & {r["venue_id"] for r in split["test"]})
        self.assertFalse({r["event_id"] for r in split["train"]} & {r["event_id"] for r in split["test"]})
        rows[0]["input_cutoff_s"] = 4
        with self.assertRaisesRegex(ValueError, "chronology"):
            split_by_venue_and_event(rows)

    def test_event_shared_across_venues_rejected_as_leakage(self):
        rows = [{"venue_id": venue, "event_id": "shared", "input_cutoff_s": 1,
                 "forecast_origin_s": 2, "outcome_timestamp_s": 3} for venue in ("a", "b")]
        with self.assertRaisesRegex(ValueError, "both venue partitions"):
            split_by_venue_and_event(rows, train_fraction=0.5, seed=1)

    def test_brier_ignores_missing_outcomes(self):
        self.assertEqual(brier_score([0.2, 0.9, 0.7], [0, 1, None]), 0.025)
        self.assertIsNone(brier_score([0.3], [None]))
        self.assertEqual(brier_accounting([0.2, 0.9, 0.7], [0, 1, None]), {
            "score": 0.025, "total_count": 3, "scored_count": 2, "excluded_count": 1,
            "excluded": [{"index": 2, "reason": "missing_outcome"}],
        })

    def test_brier_rejects_invalid_probability(self):
        with self.assertRaises(ValueError):
            brier_score([1.2], [1])

    def test_brier_checks_probability_even_when_outcome_missing(self):
        with self.assertRaises(ValueError):
            brier_accounting([float("nan")], [None])

    def test_false_alarm_rate_requires_explicit_positive_denominator(self):
        self.assertEqual(false_alarms_per_monitoring_hour(3, monitoring_hours=1.5), 2)
        with self.assertRaises(ValueError):
            false_alarms_per_monitoring_hour(3, monitoring_hours=0)

    def test_event_splits_are_reproducible_and_disjoint(self):
        rows = [{"event_id": f"e{i}", "row": n} for i in range(8) for n in range(2)]
        first = disjoint_event_splits(rows, train_fraction=0.5, seed=42)
        second = disjoint_event_splits(rows, train_fraction=0.5, seed=42)
        self.assertEqual(first, second)
        train_ids = {row["event_id"] for row in first["train"]}
        test_ids = {row["event_id"] for row in first["test"]}
        self.assertFalse(train_ids & test_ids)
        self.assertEqual(len(first["train"]), 8)
        self.assertEqual(len(first["test"]), 8)

    def test_missing_event_id_rejected(self):
        with self.assertRaises(ValueError):
            disjoint_event_splits([{"timestamp_s": 1}])

    def test_provenance_checks_real_git_and_artifact_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            files = {"input.csv": b"timestamp,value\n1,2\n", "out.json": b"{\"ok\":true}\n", "raw.json": b"{\"response\":1}\n"}
            for name, content in files.items():
                (repo / name).write_bytes(content)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
            sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            record = {
                "git_sha": sha, "clean": True, "command": "python evaluate.py", "timestamp": "2026-01-01T00:00:00Z",
                "input_sha256": hashlib.sha256(files["input.csv"]).hexdigest(), "input_path": "input.csv",
                "model_endpoint": "endpoint-name", "model_id": "fixture-model-v1",
                "output_artifacts": ["out.json"], "raw_outputs": ["raw.json"], "baseline": "baseline-v1",
            }
            result = verify_run_provenance(record, repo_path=str(repo))
            self.assertTrue(result["verified"], result["errors"])
            self.assertFalse(result["scope"]["external_model_identity_verified"])
            (repo / "raw.json").unlink()
            result = verify_run_provenance(record, repo_path=str(repo))
            self.assertFalse(result["verified"])
            self.assertTrue(any("raw_outputs" in error for error in result["errors"]))

    def test_provenance_rejects_bad_timestamp_and_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            for name, content in {"input": b"in", "out": b"out", "raw": b"raw"}.items():
                (repo / name).write_bytes(content)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
            sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            record = {"git_sha": sha, "clean": True, "command": "run", "timestamp": "gibberish",
                      "input_sha256": "0" * 64, "input_path": "input", "model_endpoint": "ep", "model_id": "id",
                      "output_artifacts": ["out"], "raw_outputs": ["raw"], "baseline": "base"}
            result = verify_run_provenance(record, repo_path=str(repo))
            self.assertFalse(result["verified"])
            self.assertTrue(any("ISO 8601" in error for error in result["errors"]))
            self.assertTrue(any("checksum" in error for error in result["errors"]))

    def test_missing_provenance_is_unverified(self):
        result = verify_run_provenance({})
        self.assertFalse(result["verified"])
        self.assertIn("missing required fields", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
