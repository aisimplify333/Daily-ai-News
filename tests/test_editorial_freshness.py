import unittest

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


if __name__ == "__main__":
    unittest.main()
