import unittest

import grounded_news_v1 as news
import writer_room_v3_1 as writer


class EditorialFreshnessTests(unittest.TestCase):
    def test_recent_lead_actor_and_argument_are_demoted_without_dropping_story(self):
        history = [{
            "date": "2026-09-08",
            "title": "OpenAI model pricing and enterprise risk",
            "lead_headline": "OpenAI launches a flagship model",
            "central_fight": "Is the new model worth its enterprise price?",
            "topics": ["OpenAI pricing", "enterprise adoption"],
            "positions": {"alex": "Defends utility", "jamie": "Challenges cost", "rufus": "Tracks risk"},
        }]
        stories = [
            {"headline": "OpenAI agents access unauthorized websites", "summary": "A security event affecting enterprise agent permissions."},
            {"headline": "Mistral raises three billion euros", "summary": "A major funding round changes competition in Europe."},
            {"headline": "DeepMind releases a genome research atlas", "summary": "A scientific research platform maps DNA variants."},
        ]
        ordered, report = writer._freshen_story_order(stories, history)
        self.assertNotEqual(ordered[0]["headline"], stories[0]["headline"])
        self.assertIn(stories[0]["headline"], [row["headline"] for row in ordered])
        self.assertTrue(report["changed"])
        self.assertEqual(report["lookback_episodes"], 1)

    def test_grounded_search_receives_history_and_broad_news_desks(self):
        prompt = news._story_prompt(
            "2026-09-10", 8,
            recent_editorial_history=[{"lead_headline": "OpenAI launches a model"}],
        )
        for source in ("Bloomberg", "CNBC", "Wall Street Journal", "Yahoo Finance"):
            self.assertIn(source, prompt)
        self.assertIn("public-market moves worldwide", prompt)
        self.assertIn("data centers", prompt)
        self.assertIn("OpenAI launches a model", prompt)
        self.assertIn("strong alternatives", prompt)

    def test_writer_keeps_all_three_hosts_in_the_deep_dive(self):
        self.assertIn("Keep all three hosts available", writer.CAST_CONNECTION_DIRECTION)
        self.assertNotIn("Segment 2 must contain only Alex and Jamie", writer._punchup_prompt("", {}, {}))
        self.assertTrue(any("bing.com/news" in url for _, url in writer.EDITORIAL_DISCOVERY_FEEDS))
        prompt = writer._writer_prompt([], [], "2026-09-10", {}, {})
        self.assertIn('Never speak production labels such as "shareable exchange,"', prompt)
        self.assertIn("RUFUS GLOBAL MARKETS DESK", prompt)
        self.assertIn("Jamie challenges one assumption", prompt)


if __name__ == "__main__":
    unittest.main()
