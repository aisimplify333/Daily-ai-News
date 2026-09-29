import unittest
from unittest.mock import Mock
from episode_cast import prepare

class EpisodeCastTests(unittest.TestCase):
    def router(self):
        r = Mock()
        r._RT = {}
        r.STATS = {'calls': []}
        r._provider_for.return_value = 'gemini'
        r.infer_mood.return_value = 'neutral'
        return r

    def test_late_failure_selects_fallback_for_both_hosts_from_start(self):
        r = self.router()
        def render(text, speaker, mood, path):
            if speaker == 'RUFUS':
                raise RuntimeError('daily quota')
            path.write_bytes(b'x' * 1100)
        r._gemini_tts_to_file.side_effect = render
        prepare(r, [('ALEX', 'Opening'), ('RUFUS', 'Reply')], lambda text, **k: [text], lambda s: 500)
        self.assertEqual(r._RT['episode_provider'], {'ALEX': 'openai', 'RUFUS': 'openai'})
        self.assertEqual(r._RT['prepared_audio'], {})
        self.assertEqual(r.STATS['episode_cast']['prepared_takes_preserved'], 1)

    def test_complete_cast_reuses_prepared_takes_and_ignores_music_and_jamie(self):
        r = self.router()
        r._gemini_tts_to_file.side_effect = lambda text, speaker, mood, path: path.write_bytes(b'x' * 1100)
        prepare(r, [('MUSIC', ''), ('ALEX', 'Opening'), ('JAMIE', 'Reply'), ('RUFUS', 'Response')], lambda text, **k: [text], lambda s: 500)
        self.assertEqual(r._gemini_tts_to_file.call_count, 2)
        self.assertEqual(len(r._RT['prepared_audio']), 2)
        self.assertEqual(r._RT['episode_provider'], {})
