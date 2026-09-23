import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import grok_tts_v4 as grok
from hybrid_tts_router_v3_1 import infer_mood
from jamie_performance import direct_delivery
import writer_room_v3_1 as writer


class EmotionalPerformanceTests(unittest.TestCase):
    def test_intent_reaches_actual_provider_payload(self):
        cases = [('I love that. Give me back an hour.', 'delight', 'build-intensity'),
                 ("I'm glad. That gives people another option.", 'warmth', 'soft'),
                 ('Did you just cite yourself? That is ambitious.', 'disbelief', 'emphasis'),
                 ("I'm curious. What did they measure?", 'curiosity', 'slow')]
        response = Mock(ok=True, content=b'ID3' + b'a' * 2000)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XAI_API_KEY': 'test', 'GROK_TTS_CACHE': 'false', 'JAMIE_EMOTIONAL_DIRECTION': 'true'}), patch.object(grok, 'CACHE_DIR', Path(folder)/'cache'), patch.object(grok.requests, 'post', return_value=response) as post:
            for line, mood, tag in cases:
                self.assertEqual(infer_mood(line, 'JAMIE'), mood)
                report = grok.render_jamie(line, mood, Path(folder)/'test.mp3', primary_only=True)
                payload = post.call_args.kwargs['json']
                self.assertEqual(payload['voice_id'], 'ursa')
                self.assertIn(f'<{tag}>', payload['text'])
                self.assertIn(tag, report['expressions'])

    def test_sponsor_rollback_and_long_facts_stay_plain(self):
        line = "Today's episode is brought to you by The Ledger."
        for mood in ['delight', 'warmth', 'disbelief', 'curiosity']:
            self.assertEqual(grok._expressive_text(line, mood), line)
        with patch.dict(os.environ, {'JAMIE_EMOTIONAL_DIRECTION': 'false'}):
            self.assertEqual(direct_delivery('I love that.', 'delight'), 'I love that.')
        self.assertIsNone(__import__('jamie_performance').emotional_intent('The vendor calls it wonderful.'))
        self.assertEqual(direct_delivery('word ' * 40, 'delight'), 'word ' * 40)

    def test_closing_cleanup_preserves_same_host_editorial(self):
        from test_production_contract import SCRIPT, STORIES, BOARD
        script = SCRIPT + '\nALEX: Question for listeners: Which matters?\nALEX: Independent reviews remain missing.\nALEX: Thanks for listening. Follow us wherever you get your podcasts.\nJAMIE: See you tomorrow.\nRUFUS: Until then.'
        result = writer._ensure_connection_elements(script, STORIES, BOARD, '2026-09-23')
        self.assertIn('Independent reviews remain missing.', result)
        self.assertNotIn('Question for listeners:', result)
        self.assertNotIn('See you tomorrow.', result)
        self.assertEqual(result.count('Follow The AI Edge now.'), 1)
        self.assertEqual(result, writer._ensure_connection_elements(result, STORIES, BOARD, '2026-09-23'))
