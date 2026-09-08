"""Offline research-recovery contracts: no provider or TTS calls."""
import datetime as dt
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import grounded_news_v1 as news


def story(index, **changes):
    row = dict(headline=f"Distinct AI event {index}", publisher="Reuters",
               source_url=f"https://reuters.com/technology/event-{index}",
               published_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               summary="Confirmed factual description of a newly reported AI development. " * 3,
               facts=["First sourced fact", "Second sourced fact"],
               original_publication_verified=True)
    row.update(changes)
    return row


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        news.build_grounded_story_slate.cache_clear()
        self.cwd = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()
        news.build_grounded_story_slate.cache_clear()

    def run_slate(self, primary, refill, n=3):
        with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": primary})) as first, patch.object(news, "_recovery_search", return_value=json.dumps({"stories": refill})) as second:
            result = news.build_grounded_story_slate("2026-09-08", n=n)
            return result, first.call_count, second.call_count

    def test_sparse_result_refilled_and_retained(self):
        rows, first, second = self.run_slate([story(1)], [story(2), story(3)])
        self.assertEqual((len(rows), first, second), (3, 1, 1))
        self.assertEqual(rows[0]["headline"], "Distinct AI event 1")

    def test_sufficient_result_has_no_extra_spend(self):
        rows, _, second = self.run_slate([story(i) for i in range(3)], [])
        self.assertEqual(second, 0)

    def test_production_five_story_contract_refills_three(self):
        rows, first, second = self.run_slate(
            [story(i) for i in range(3)], [story(3), story(4)], n=5)
        self.assertEqual((len(rows), first, second), (5, 1, 1))

    def test_production_does_not_return_cached_incomplete_slate(self):
        with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": [story(i) for i in range(3)]})), patch.object(news, "_recovery_search", return_value="{}"):
            with self.assertRaisesRegex(RuntimeError, "at least 5 required"):
                news.build_grounded_story_slate("2026-09-08")
        self.assertEqual(news.build_grounded_story_slate.cache_info().currsize, 0)

    def test_stale_duplicate_and_unverified_rejected(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=60)).isoformat()
        rows, _, _ = self.run_slate([story(1), story(8, published_at=old), story(9, original_publication_verified=False)], [story(1), story(2), story(3)])
        self.assertEqual(len(rows), 3)
        with open("grounded_research_report.json") as handle:
            report = json.load(handle)
        self.assertEqual(report["attempts"][0]["rejections"]["outside_freshness_window"], 1)
        self.assertEqual(report["attempts"][1]["rejections"]["duplicate"], 1)

    def test_same_url_different_headline_not_two_stories(self):
        rows, _, second = self.run_slate([story(1), story(2, source_url=story(1)["source_url"])], [story(3), story(4)])
        self.assertEqual((len(rows), second), (3, 1))

    def test_provider_failure_recovers(self):
        with patch.object(news, "_grounded_text", side_effect=RuntimeError("sensitive body")), patch.object(news, "_recovery_search", return_value=json.dumps({"stories": [story(i) for i in range(3)]})):
            self.assertEqual(len(news.build_grounded_story_slate("2026-09-08", n=3)), 3)
        with open("grounded_research_report.json") as handle:
            self.assertNotIn("sensitive body", handle.read())

    def test_exhaustion_stops_before_generation(self):
        with patch.object(news, "_grounded_text", return_value="invalid JSON"), patch.object(news, "_recovery_search", return_value="{}") as second:
            with self.assertRaisesRegex(RuntimeError, "at least 5 required"):
                news.build_grounded_story_slate("2026-09-08")
            self.assertEqual(second.call_count, 1)

    def test_trusted_candidates_not_hidden_by_untrusted(self):
        weak = [story(i, publisher="Unknown", source_url=f"https://example.org/{i}") for i in range(5)]
        rows, _, second = self.run_slate(weak, [story(i) for i in range(5, 8)])
        self.assertEqual(second, 1)
        self.assertTrue(all(row["source_tier"] >= 2 for row in rows[:3]))


if __name__ == "__main__":
    unittest.main()
