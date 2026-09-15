import unittest
from unittest.mock import patch

import listener_editorial as editorial
import writer_room_v3_1 as writer


def episode(counts):
    blocks = ['### SEGMENT 1 — Intro', '[MUSIC]', 'ALEX: Welcome.', ]
    for segment, words in zip((2, 3, 4), counts):
        blocks += [f'### SEGMENT {segment} — Story',
                   'JAMIE: ' + ' '.join(f'word{segment}_{i}' for i in range(words)) + '.']
    return '\n'.join(blocks + ['### SEGMENT 5 — Closing', 'ALEX: Goodbye.'])


class ListenerEditorialTests(unittest.TestCase):
    def test_weighted_expansion_can_choose_any_story(self):
        for counts, expected in [((50, 300, 900), 2), ((600, 50, 900), 3), ((600, 500, 50), 4)]:
            self.assertEqual(editorial.expansion_segment(episode(counts)), expected)
        self.assertIsNone(editorial.expansion_segment(''))

    def test_diagnostics_report_imbalance_without_blocking(self):
        report = editorial.editorial_diagnostics(episode((100, 100, 900)))
        self.assertFalse(report['blocking'])
        self.assertTrue(any('dominance' in flag for flag in report['flags']))
        self.assertFalse(editorial.editorial_diagnostics(episode((400, 300, 300)))['flags'])

    def test_exact_repeated_argument_is_reported_but_short_reaction_is_not(self):
        script = episode((100, 100, 100))
        repeat = '\nRUFUS: This is the same substantial argument repeated without any new evidence.\nJAMIE: Indeed.\n'
        report = editorial.editorial_diagnostics(script.replace('### SEGMENT 3', repeat + '### SEGMENT 3').replace('### SEGMENT 4', repeat + '### SEGMENT 4'))
        self.assertEqual(len(report['repeated_sentences']), 1)

    def test_existing_expansion_targets_matching_source_and_preserves_sponsor_boundary(self):
        script = writer._normalize_midroll(episode((500, 30, 600)), '2026-09-15')
        stories = [{'headline': 'SOURCE_ONE'}, {'headline': 'SOURCE_TWO'}, {'headline': 'SOURCE_THREE'}]
        addon = 'RUFUS: An additional observation grounded in the second story changes this interpretation.'
        with patch.object(writer, '_anthropic_text', return_value=addon) as call:
            result = writer._expand_segment_four({}, script, stories, '2026-09-15', {}, 100)
        prompt = call.call_args.args[1]
        source = prompt.split('SOURCE RECORD FOR THIS STORY ONLY:')[1].split('EXISTING SEGMENT')[0]
        self.assertIn('SOURCE_TWO', source)
        self.assertNotIn('SOURCE_ONE', source)
        self.assertNotIn('SOURCE_THREE', source)
        self.assertLess(result.index(addon), result.index('A short sponsor break'))
        self.assertEqual(result.count('A short sponsor break'), 1)
        self.assertLess(result.index('### SEGMENT 3'), result.index(addon))
        self.assertLess(result.index(addon), result.index('### SEGMENT 4'))

    def test_recycled_expansion_preserves_original(self):
        script = episode((500, 30, 600))
        repeated = next(line for line in script.splitlines() if line.startswith('JAMIE:'))
        with patch.object(writer, '_anthropic_text', return_value=repeated), patch.object(writer, '_openai_text', return_value=repeated):
            self.assertEqual(writer._expand_segment_four({}, script, [{}, {}, {}], '2026-09-15', {}, 800), script)

    def test_clip_score_has_no_segment_four_bonus(self):
        dialogue = ('ALEX: Google says the new tool costs 20 dollars per month, but what does that buy a small team using it every day?\n'
                    'JAMIE: The catch is that access does not tell us whether it completes the work reliably, so test one real task before buying seats.\n'
                    'RUFUS: Because a subscription is only a bargain if someone actually wants the work it produces.')
        a = writer._find_shareable_exchange('### SEGMENT 2 — News\n' + dialogue)
        b = writer._find_shareable_exchange('### SEGMENT 4 — News\n' + dialogue)
        self.assertTrue(a['passed'])
        self.assertEqual(a['score'], b['score'])


if __name__ == '__main__':
    unittest.main()
