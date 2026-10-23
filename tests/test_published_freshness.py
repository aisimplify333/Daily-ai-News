import json
from pathlib import Path
import tempfile
import unittest
import os
import datetime as dt
from unittest.mock import patch
import episode_recovery
from episode_freshness import assert_fresh_episode, published_history, repeated_story


class PublishedFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "feed.xml").write_text("""<rss><channel><item>
        <title>NVIDIA’s OpenShell Architecture: Enterprise Agent Security</title>
        <description>What we covered:
        • NVIDIA launched OpenShell, a reference architecture for safe enterprise AI agents
        </description><enclosure url="https://example.org/podcast_2026-10-21.mp3"/>
        </item></channel></rss>""")

    def test_actual_oct22_paraphrase_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Previously aired"):
            assert_fresh_episode([{"headline": "NVIDIA launches OpenShell, a reference architecture for safe AI agents"}],
                                 "2026-10-22", root=self.root)

    def test_same_company_new_event_is_allowed(self):
        assert_fresh_episode([{"headline": "NVIDIA announces quarterly earnings and revised revenue outlook"}],
                             "2026-10-22", root=self.root)

    def test_same_day_rerun_does_not_compare_against_itself(self):
        self.assertEqual(published_history("2026-10-21", self.root), [])

    def test_title_repeat_is_rejected_even_with_new_stories(self):
        with self.assertRaisesRegex(ValueError, "title repeats"):
            assert_fresh_episode([], "2026-10-22",
                "NVIDIA’s OpenShell Architecture: Enterprise Agent Security", self.root)

    def test_canonical_source_and_event_keys_cannot_be_evaded_by_rephrasing(self):
        history = [{"date": "2026-10-21", "stories": [
            {"event_key": "launch-1", "source_url": "https://example.com/news/launch?utm=x"}]}]
        self.assertTrue(repeated_story({"event_key": "launch-1"}, history))
        self.assertTrue(repeated_story({"source_url": "https://example.com/news/launch#top"}, history))

    def test_current_in_progress_metadata_does_not_hide_feed_history(self):
        (self.root / "episode_metadata.json").write_text(json.dumps({"date": "2026-10-22"}))
        self.assertEqual(published_history("2026-10-22", self.root)[0]["date"], "2026-10-21")

    def test_recovery_cannot_bypass_published_story_guard(self):
        row = {"headline": "NVIDIA launches OpenShell, a reference architecture for safe AI agents",
               "published_at": "2026-10-21T12:00:00Z", "grounded": True, "facts": ["Fact"]}
        (self.root / "grounded_story_slate.json").write_text(json.dumps(
            {"date": "2026-10-22", "selected": [row] * 3}))
        (self.root / "story_slate_decision.json").write_text(json.dumps(
            {"date": "2026-10-22", "v3_3_debate_board": {"published_title": "New title"}}))
        (self.root / "script_fact_repaired_2026-10-22.txt").write_text("Saved script")
        prior = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, {"EPISODE_RECOVERY_DIR": str(self.root)}), patch.object(
                    episode_recovery.dt, "datetime", wraps=dt.datetime) as clock:
                clock.now.return_value = dt.datetime(2026, 10, 22, 18, tzinfo=dt.timezone.utc)
                with self.assertRaisesRegex(ValueError, "Previously aired"):
                    episode_recovery.load_recovery("2026-10-22")
        finally:
            os.chdir(prior)


if __name__ == "__main__":
    unittest.main()
