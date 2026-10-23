import unittest
from pydub.generators import Sine
from transition_variation import story_transition


class TransitionVariationTests(unittest.TestCase):
    def test_four_story_boundaries_are_distinct_and_preserve_source_attack(self):
        source = Sine(440).to_audio_segment(duration=3000).apply_gain(-16)
        results = [story_transition(source, {"sha256": "source"}, s, "2026-10-23")
                   for s in (2, 3, 4, 5)]
        self.assertEqual(len({len(clip) for clip, _ in results}), 4)
        for clip, audit in results:
            self.assertEqual(clip[:200].raw_data, source[:200].raw_data)
            self.assertLessEqual(clip.max_dBFS, source.max_dBFS)
            self.assertGreater(clip.dBFS, -26)
            self.assertEqual(audit["sha256"], "source")
            self.assertEqual(audit["duration_seconds"], len(clip)/1000)

    def test_retries_are_deterministic_and_next_day_rotates(self):
        source = Sine(440).to_audio_segment(duration=3000).apply_gain(-16)
        one = story_transition(source, {}, 2, "2026-10-23")
        two = story_transition(source, {}, 2, "2026-10-23")
        next_day = story_transition(source, {}, 2, "2026-10-24")
        self.assertEqual(one[0].raw_data, two[0].raw_data)
        self.assertNotEqual(one[1]["variant"], next_day[1]["variant"])
