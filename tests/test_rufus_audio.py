import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from rufus_audio import entrance_due, prepare_entrance


class RufusAudioTests(unittest.TestCase):
    def test_default_uses_original_transition_and_preserves_its_length(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, dest = root/'transition.mp3', root/'entrance.mp3'
            Sine(440).to_audio_segment(duration=2800).export(source, format='mp3').close()
            audit = {}
            with patch('rufus_audio.__file__', str(root/'rufus_audio.py')):
                self.assertEqual(prepare_entrance(dest, audit=audit), dest)
            self.assertAlmostEqual(len(AudioSegment.from_file(dest)), 2800, delta=50)
            self.assertEqual(audit['asset'], 'transition.mp3')
            self.assertEqual(audit['provider'], 'existing_show_asset')

    def test_entrance_only_follows_host_feature_handoff_once(self):
        for text in ('Rufus, take us on location.', 'Rufus, take us to the global desk.'):
            self.assertTrue(entrance_due('ALEX', text, 3))
            self.assertFalse(entrance_due('ALEX', text, 3, True))
            self.assertFalse(entrance_due('RUFUS', text, 3))
            self.assertFalse(entrance_due('ALEX', text, 2))
        self.assertFalse(entrance_due('ALEX', 'Back to the wider story.', 3))

    def test_asset_is_bounded_and_missing_media_is_optional(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder)/'source.wav', Path(folder)/'entrance.mp3'
            Sine(440).to_audio_segment(duration=3500).export(source, format='wav').close()
            self.assertEqual(prepare_entrance(dest, source), dest)
            rendered = AudioSegment.from_file(dest)
            self.assertLessEqual(len(rendered), 2050)
            self.assertLess(rendered.max_dBFS, -3)
            self.assertIsNone(prepare_entrance(dest, Path(folder)/'missing.mp3'))


if __name__ == '__main__':
    unittest.main()

