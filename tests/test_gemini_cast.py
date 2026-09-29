import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
from gemini_cast_tts import payload, render_wav

class GeminiCastTests(unittest.TestCase):
    def test_direction_is_not_spoken_and_sponsor_has_no_laugh(self):
        p = payload('A serious point.', 'RUFUS', 'neutral', 'Iapetus', 'Measured emphasis')
        part = p['contents'][0]['parts'][0]
        self.assertEqual(part['text'], 'A serious point.')
        self.assertIn('brisk', part['speech_metadata']['style'])
        p = payload('The Ledger helps.', 'RUFUS', 'amused', 'Iapetus', '')
        self.assertEqual(p['contents'][0]['parts'][0]['text'], 'The Ledger helps.')

    @patch('gemini_cast_tts.time.sleep')
    @patch('gemini_cast_tts.requests.post')
    def test_wav_container_is_preserved(self, post, sleep):
        import base64
        data = b'RIFF' + b'\0'*4 + b'WAVE' + b'\0'*600
        post.return_value = Mock(ok=True)
        post.return_value.json.return_value = {'candidates':[{'content':{'parts':[{'inlineData':{'data':base64.b64encode(data).decode()}}]}}]}
        with TemporaryDirectory() as d:
            path = Path(d)/'take.wav'
            render_wav('Hello', 'ALEX', 'neutral', 'Orus', 'gemini-3.8-flash-tts', '', path, 'test')
            self.assertEqual(path.read_bytes(), data)
