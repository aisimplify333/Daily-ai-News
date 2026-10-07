import tempfile
import unittest
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from rufus_audio import entrance_due, prepare_entrance


class RufusAudioTests(unittest.TestCase):
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
