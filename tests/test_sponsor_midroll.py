import unittest
import writer_room_v3_1 as writer


class SponsorMidrollTests(unittest.TestCase):
    def test_six_dates_rotate_without_accumulating_ads(self):
        script = '### SEGMENT 3 — Story\nALEX: Keep this news.\n### SEGMENT 4 — Next\nJAMIE: Keep this too.'
        rendered = set()
        for day in range(1, 7):
            date = f'2026-10-{day:02d}'
            script = writer._normalize_midroll(script, date)
            self.assertEqual(script.count('A short sponsor break'), 1)
            self.assertEqual(script, writer._normalize_midroll(script, date))
            self.assertIn('ALEX: Keep this news.', script)
            self.assertIn('JAMIE: Keep this too.', script)
            rendered.add(script)
        self.assertEqual(len(rendered), 6)

    def test_rotation_preserves_opening_and_only_inserts_once(self):
        script = '\n'.join([
            '### SEGMENT 1 — Intro', '[MUSIC]',
            'ALEX: Today’s episode is brought to you by The Ledger.',
            '### SEGMENT 2 — News', 'JAMIE: News.',
            '### SEGMENT 3 — Markets', 'RUFUS: Markets.',
            '### SEGMENT 4 — More news', 'ALEX: More news.',
            '### SEGMENT 5 — Closing', 'JAMIE: A quick final note: The Ledger.',
        ])
        first = writer._normalize_midroll(script, '2026-09-10')
        self.assertEqual(first, writer._normalize_midroll(first, '2026-09-10'))
        rotated = writer._normalize_midroll(first, '2026-09-11')
        self.assertNotEqual(first, rotated)
        self.assertEqual(rotated.count('A short sponsor break'), 1)
        self.assertIn('ALEX: Today’s episode is brought to you by The Ledger.', rotated)
        self.assertIn('JAMIE: A quick final note: The Ledger.', rotated)
        self.assertLess(rotated.index('A short sponsor break'), rotated.index('### SEGMENT 4'))
        for treatment in writer.MIDROLL_TREATMENTS:
            for line in treatment:
                self.assertIn('the ledger', line.lower())  # Existing dry-audio routing.
                self.assertLessEqual(len(line.split()), 55)
            self.assertTrue(70 <= sum(len(line.split()) - 1 for line in treatment) <= 100)
