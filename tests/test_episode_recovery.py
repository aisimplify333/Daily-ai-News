import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import episode_recovery as recovery
import writer_room_v3_1 as writer
from test_production_contract import SCRIPT, STORIES, BOARD


class RecoveryTests(unittest.TestCase):
    def test_missing_welcome_and_duplicate_ad_are_repaired_idempotently(self):
        script = SCRIPT.replace('Welcome to The AI Edge.', "I'm Alex.").replace(
            '### SEGMENT 4', 'ALEX: The Ledger helps you follow the news. Subscribe at T-H-E-L-E-D-G-R dot I-O.\n### SEGMENT 4')
        def repair(text):
            assessment = writer._assess(text, STORIES, BOARD, {})
            return writer._ensure_connection_elements(writer._normalize_primary_sponsor(
                writer._deterministic_structure_repair(text, assessment, BOARD)), STORIES, BOARD, '2026-09-04')
        result = repair(script)
        self.assertEqual(result, repair(result))
        self.assertEqual(result.lower().count('t-h-e-l-e-d-g-r dot i-o'), 1)
        self.assertIn('A short sponsor break for The Ledger', result)
        self.assertTrue(writer._assess(result, STORIES, BOARD, {})['gate']['welcome_after_music'])
        self.assertIn("I'm Alex.", result)

    def test_recovery_requires_matching_day_and_fresh_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            row = {'published_at': '2026-09-22T10:00:00Z', 'grounded': True, 'facts': ['Synthetic fact']}
            (root/'grounded_story_slate.json').write_text(json.dumps({'date': '2026-09-22', 'selected': [row]*5}))
            (root/'story_slate_decision.json').write_text(json.dumps({'date': '2026-09-22', 'v3_3_debate_board': {'published_title': 'Synthetic title'}}))
            (root/'script_fact_repaired_2026-09-22.txt').write_text(SCRIPT)
            with patch.dict(os.environ, {'EPISODE_RECOVERY_DIR': folder}), patch.object(recovery.dt, 'datetime', wraps=dt.datetime) as clock:
                clock.now.return_value = dt.datetime(2026, 9, 22, 18, tzinfo=dt.timezone.utc)
                self.assertEqual(len(recovery.load_recovery('2026-09-22')['stories']), 5)
                with self.assertRaises(ValueError):
                    recovery.load_recovery('2026-09-23')
                row['published_at'] = '2026-09-19T10:00:00Z'
                (root/'grounded_story_slate.json').write_text(json.dumps({'date': '2026-09-22', 'selected': [row]*5}))
                with self.assertRaises(ValueError):
                    recovery.load_recovery('2026-09-22')

    def test_normal_runs_do_not_use_recovery(self):
        with patch.dict(os.environ, {'EPISODE_RECOVERY_DIR': ''}):
            self.assertIsNone(recovery.load_recovery('2026-09-22'))
