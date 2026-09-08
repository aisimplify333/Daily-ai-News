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

    def test_live_stale_pattern_uses_targeted_discovery_recovery(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=60)).isoformat()
        primary = [story(1), story(2)] + [story(i, published_at=old) for i in range(10, 17)]
        refill = [story(1), story(3)] + [story(i, published_at=old) for i in range(20, 26)]
        seeds = json.dumps([{"title": "Fresh AI financial announcement",
                             "published": story(1)["published_at"]}])
        with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": primary})), patch.object(news, "_recovery_search", side_effect=[
            json.dumps({"stories": refill}), json.dumps({"stories": [story(4), story(5)]})
        ]) as recover:
            result = news.build_grounded_story_slate("2026-09-08", discovery_json=seeds)
        self.assertEqual(len(result), 5)
        self.assertEqual(recover.call_count, 2)
        self.assertIn("Fresh AI financial announcement", recover.call_args.args[0])
        self.assertIn("outside_freshness_window", recover.call_args.args[0])
        self.assertIn(old, recover.call_args.args[0])

    def test_discovery_never_substitutes_for_verified_stories(self):
        seeds = json.dumps([{"title": "Unverified headline", "published": story(1)["published_at"]}])
        with patch.object(news, "_grounded_text", return_value="{}"), patch.object(news, "_recovery_search", return_value="{}") as recover:
            with self.assertRaisesRegex(RuntimeError, "at least 5 required"):
                news.build_grounded_story_slate("2026-09-08", discovery_json=seeds)
        self.assertEqual(recover.call_count, 2)

    def test_discovery_filters_stale_future_and_malformed_items(self):
        now = dt.datetime.now(dt.timezone.utc)
        rows = news._fresh_discovery_seeds([
            None, {"title": "missing date"},
            {"title": "old", "published": (now-dt.timedelta(hours=49)).isoformat()},
            {"title": "future", "published": (now+dt.timedelta(hours=1)).isoformat()},
            {"title": "fresh", "published": now.isoformat()},
            {"title": "fresh", "published": now.isoformat()},
        ], now)
        self.assertEqual([x["headline"] for x in rows], ["fresh"])

    def test_prompt_uses_exact_rolling_window(self):
        now = dt.datetime(2026, 9, 8, 22, 9, tzinfo=dt.timezone.utc)
        prompt = news._story_prompt("2026-09-08", 8, now)
        self.assertIn("2026-09-06T22:09:00+00:00", prompt)
        self.assertIn("2026-09-08T22:09:00+00:00", prompt)

    def test_installed_production_selector_passes_rss_to_research(self):
        import writer_room_v3_1 as writer
        namespace = {}
        writer.install_v3_1(namespace)
        rss = [{"title": "Current AI announcement", "published": story(1)["published_at"]}]
        with patch.object(news, "_grounded_text", return_value=json.dumps({
            "stories": [story(i) for i in range(5)]
        })) as search:
            result = namespace["pick_top_stories"](rss, n=5, date_str="2026-09-08")
        self.assertEqual(len(result), 5)
        self.assertIn("Current AI announcement", search.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
