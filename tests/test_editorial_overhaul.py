import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import grounded_news_v1 as news
import writer_room_v3_1 as writer
from editorial_selection import balanced_story_order, concentrated
from production_review import review_episode


class EditorialOverhaulTests(unittest.TestCase):
    def test_three_governance_stories_are_recognized_and_diversified(self):
        rows = [{"headline": h, "source_tier": 3} for h in (
            "US proposes AI incident alerts in China talks", "Labs face antitrust lawsuit",
            "UN Security Council schedules AI meeting", "New AI accessibility tool launches",
            "Chip manufacturer adds production capacity")]
        self.assertTrue(concentrated(rows))
        result = balanced_story_order(rows)
        self.assertEqual(result[0]["headline"], rows[0]["headline"])
        self.assertFalse(concentrated(result))
        self.assertEqual({x["headline"] for x in result}, {x["headline"] for x in rows})
        rows[3]["source_tier"] = rows[4]["source_tier"] = 0
        self.assertTrue(concentrated(balanced_story_order(rows)))

    def test_one_bounded_variety_refill_and_no_failure_when_day_is_concentrated(self):
        now = dt.datetime.now(dt.timezone.utc)
        rows = [{"headline": h, "publisher": "AP", "published_at": now.isoformat(),
                 "source_url": f"https://apnews.com/article/{i}", "summary": "Confirmed description of this distinct event and its implications, with enough source detail to satisfy the current validation contract.",
                 "facts": ["A sourced fact", "Another sourced fact"], "original_publication_verified": True}
                for i, h in enumerate(("US proposes AI incident alerts in China talks", "Labs face antitrust lawsuit", "UN Security Council schedules AI meeting"))]
        news.build_grounded_story_slate.cache_clear()
        with tempfile.TemporaryDirectory() as folder:
            previous = os.getcwd()
            try:
                os.chdir(folder)
                with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": rows})), patch.object(news, "_recovery_search", return_value='{"stories": []}') as refill:
                    result = news.build_grounded_story_slate("2026-09-21", n=3)
                self.assertEqual(refill.call_count, 1)
                self.assertEqual(len(result), 3)
                self.assertTrue(json.loads(Path("grounded_research_report.json").read_text())["concentrated_slate"])
            finally:
                os.chdir(previous)
                news.build_grounded_story_slate.cache_clear()

    def test_research_housekeeping_is_not_a_story(self):
        row = {"headline": "Reuters-style? No verified Reuters result found in-window", "publisher": "AP", "source_url": "https://apnews.com/article/example", "summary": "x" * 100}
        self.assertEqual(news._rejection_reason(row, dt.datetime.now(dt.timezone.utc)), "research_note_not_news")

    def test_both_gemini_failures_use_one_cross_provider_plan(self):
        stories = [{"headline": "Google expands AI security access", "facts": ["A fact"]}]
        with tempfile.TemporaryDirectory() as folder:
            previous = os.getcwd()
            try:
                os.chdir(folder)
                with patch.object(writer, "_gemini_text", return_value="") as gemini, patch.object(writer, "_openai_text", return_value=json.dumps({"published_title": "Google Expands AI Security: Who Gets Access Now?"})) as alternative:
                    result = writer._preproduction({}, stories, "2026-09-21", {})
                self.assertEqual(gemini.call_count, 2)
                self.assertEqual(alternative.call_count, 1)
                self.assertEqual(result["planning_status"], "model_plan")
                self.assertTrue(result["story_scenes"])
            finally:
                os.chdir(previous)

    def test_next_title_candidate_is_used_before_headline_fallback(self):
        stories = [{"headline": "Google expands AI security access"}]
        title = "Google Expands AI Security: Who Gets Access Now?"
        with patch.object(writer, "_gemini_text", return_value=json.dumps({"published_title": "Google Announces More Enterprise Products Today", "title_candidates": [title]})):
            board = writer._preproduction({}, stories, "2026-09-21", {})
        self.assertEqual(board["published_title"], title)

    def test_named_lead_does_not_get_a_duplicate_roll_call(self):
        from test_production_contract import SCRIPT, BOARD, STORIES
        script = SCRIPT.replace("ALEX: Who decides which questions we can ask?", "ALEX: Google expands AI security access. Who can use it?")
        result = writer._ensure_connection_elements(script, STORIES, BOARD, "2026-09-21")
        self.assertNotIn("Our lead story today is", result)
        self.assertEqual(result, writer._ensure_connection_elements(result, STORIES, BOARD, "2026-09-21"))

    def test_usable_shorter_script_has_zero_runtime_penalty(self):
        self.assertEqual(writer._runtime_distance({"metrics": {"words": 3400}}), 0)
        self.assertGreater(writer._runtime_distance({"metrics": {"words": 3200}}), 0)

    def test_review_flags_production_gaps_without_inventing_a_rating(self):
        rows = [{"headline": h} for h in ("AI governance talks", "Antitrust lawsuit", "UN Security Council AI meeting")]
        report = review_episode(rows, {"rows": [{"kind": "segment", "segment": 2, "start": 169.6}]}, {}, {"accepted": False, "reason": "runtime_regression"}, {"status": "source_only_fallback"})
        self.assertEqual(len(report["issues"]), 4)
        self.assertIsNone(report["entertainment_rating"])
        self.assertFalse(report["blocking"])
