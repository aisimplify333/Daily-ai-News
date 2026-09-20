import os
import unittest
from unittest.mock import patch
from dialogue_direction import boundary_pause


class DialogueDirectionTests(unittest.TestCase):
    def test_next_turn_controls_handoff_without_removing_words(self):
        self.assertEqual(boundary_pause("Does that help?", "ALEX", "Yes, for this task.", "JAMIE")["milliseconds"], 85)
        self.assertEqual(boundary_pause("The useful part is—", "ALEX", "Who can use it?", "JAMIE")["milliseconds"], 25)
        self.assertEqual(boundary_pause("An impressive committee of one.", "RUFUS", "You would chair it.", "JAMIE", "dry_wit")["milliseconds"], 210)

    def test_no_joke_pause_for_rufus_question_or_long_explanation(self):
        self.assertEqual(boundary_pause("Who can access it?", "RUFUS", "Students.", "JAMIE", "dry_wit")["reason"], "question_to_answer")
        self.assertNotEqual(boundary_pause("A fact " * 20, "RUFUS", "That makes sense.", "ALEX", "dry_wit")["reason"], "short_rufus_observation")

    def test_sponsors_and_structural_boundaries_are_protected(self):
        self.assertEqual(boundary_pause("Today's episode is brought to you by The Ledger.", "ALEX", "Yes.", "JAMIE")["milliseconds"], 320)
        self.assertEqual(boundary_pause("A committee of one.", "RUFUS", "[MUSIC]", "MUSIC", "dry_wit")["reason"], "structural_boundary")
        self.assertEqual(boundary_pause("Part one", "ALEX", "Part two", "ALEX", continuation=True)["milliseconds"], 45)

    def test_disable_returns_configured_baseline(self):
        with patch.dict(os.environ, {"DIALOGUE_DIRECTION_ENABLED": "false"}):
            self.assertEqual(boundary_pause("Who—", "ALEX", "Me.", "JAMIE", baseline_ms=120), {"milliseconds": 120, "reason": "baseline"})


if __name__ == "__main__":
    unittest.main()
