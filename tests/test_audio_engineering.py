"""Offline delivery-audio regression checks; no voice/model services."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pydub import AudioSegment
from pydub.generators import Sine
from audio_engineering import inspect_master, parse_measurements, write_engineering_report
from production_delivery_gate import duration_in_window


class AudioEngineeringTests(unittest.TestCase):
    def test_missing_and_silent_measurements_are_not_claimed_as_passes(self):
        for raw in ('no report', '{"input_i":"-inf","input_tp":"-inf","input_lra":"0"}'):
            with self.assertRaises(ValueError):
                parse_measurements(raw)

    def test_measurement_failure_preserves_master_and_reports_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            master = Path(directory) / "paid.mp3"
            master.write_bytes(b"existing paid master")
            report_path = Path(directory) / "report.json"
            with patch("audio_engineering.inspect_master", side_effect=RuntimeError("ffmpeg")):
                report = write_engineering_report(master, report_path)
            self.assertEqual(master.read_bytes(), b"existing paid master")
            self.assertIsNone(report["measurements"])
            self.assertFalse(report["blocking"])
            self.assertFalse(report["listened"])
            self.assertEqual(json.loads(report_path.read_text()), report)

    def test_duration_grace_does_not_relax_maximum(self):
        self.assertTrue(duration_in_window(18.5, 19, 30))
        self.assertFalse(duration_in_window(18.49, 19, 30))
        self.assertTrue(duration_in_window(30, 19, 30))
        self.assertFalse(duration_in_window(30.01, 19, 30))

    def test_broadcast_wrapper_matches_delivery_grace(self):
        import run_broadcast as broadcast
        with patch.object(broadcast, "get_latest_mp3", return_value=Path("paid.mp3")), patch.object(broadcast, "MIN_MINUTES", 19), patch.object(broadcast, "MAX_MINUTES", 30):
            for minutes in (18.5, 19, 30):
                with patch.object(broadcast, "get_mp3_duration_minutes", return_value=minutes):
                    self.assertEqual(broadcast.check_episode_length_or_fail()[1], minutes)
            for minutes in (18.49, 30.01):
                with patch.object(broadcast, "get_mp3_duration_minutes", return_value=minutes):
                    with self.assertRaises(RuntimeError):
                        broadcast.check_episode_length_or_fail()

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_encoded_measurements_find_quiet_gap_without_modifying_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.mp3"
            tone = Sine(440).to_audio_segment(duration=5000).apply_gain(-12)
            clip = tone + AudioSegment.silent(duration=2500) + tone.apply_gain(-8)
            clip.export(path, format="mp3", bitrate="192k").close()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            report = inspect_master(path)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertFalse(report["listened"])
            self.assertFalse(report["blocking"])
            self.assertLess(report["measurements"]["integrated_lufs"], -10)
            self.assertTrue(any(2.3 <= gap["seconds"] <= 2.7 for gap in report["quiet_spans"]))


if __name__ == "__main__":
    unittest.main()
