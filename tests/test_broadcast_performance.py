import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pydub import AudioSegment
from pydub.generators import Sine
import broadcast_performance as perf
import grok_tts_v4 as grok
import writer_room_v3_1 as writer
from production_assets import build_timeline


class BroadcastPerformanceTests(unittest.TestCase):
    def test_pushback_keeps_the_written_words_and_name_spelling_is_speech_only(self):
        original = "Amodei is making a different argument, Rufus."
        self.assertEqual(grok._clean_text(original), original)
        self.assertEqual(grok._expressive_text(original, "pushback"),
                         "Ah-moh-day is making a different argument, Rufus.")
        self.assertEqual(grok._expressive_text("No, Rufus.", "interruption"), "No, Rufus.")

    def test_sponsor_and_jamie_excluded_and_disable_supported(self):
        for speaker, text in [("ALEX", "The Ledger is our sponsor."), ("JAMIE", "No, Rufus.")]:
            self.assertEqual(perf.performance_settings(text, speaker, "pushback"), (1.0, 0.0))
        with patch.dict(os.environ, {"DYNAMIC_PERFORMANCE_ENABLED": "false"}):
            self.assertEqual(perf.performance_settings("No.", "RUFUS", "pushback"), (1.0, 0.0))

    def test_pitch_preserving_tempo_with_real_audio_and_scaled_transition_measurements(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "main.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_speed_ffmpeg")
        import shutil
        ns = {"Path": Path, "subprocess": subprocess, "shutil": shutil,
              "_has_ffmpeg": lambda: bool(shutil.which("ffmpeg")),
              "_run": lambda cmd: subprocess.run(cmd, check=True, capture_output=True)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "main.py", "exec"), ns)
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/"in.mp3", Path(temp)/"out.mp3"
            tone = Sine(440).to_audio_segment(duration=2000).apply_gain(-16)
            tone.export(a, format="mp3")
            ns["apply_speed_ffmpeg"](a, b, 1.04)
            sped = AudioSegment.from_file(b)
            self.assertAlmostEqual(len(sped), 2000/1.04, delta=60)
            # Zero crossings approximate pitch; speeding must not raise it 4%.
            samples = sped.set_channels(1).get_array_of_samples()
            crossings = sum(x <= 0 < y for x, y in zip(samples, samples[1:]))
            self.assertAlmostEqual(crossings/(len(sped)/1000), 440, delta=8)
            timeline = build_timeline([b], [{"kind":"transition", "segment":3,
                "start_index":0,"end_index":1}], len(sped)/1000)
            self.assertTrue(perf.measured_transition_checks(sped,timeline)[0]["audible_level"])
            self.assertFalse(perf.measured_transition_checks(AudioSegment.silent(duration=len(sped)),timeline)[0]["audible_level"])

    def test_variety_preserves_lead_and_all_source_records(self):
        stories = [{"headline": s} for s in ["OpenAI AI safety regulation debate",
            "OpenAI safety regulation debate continues", "Nvidia launches a new chip",
            "Hospital tests cancer detection model", "AI safety regulation debate response"]]
        ordered = writer._three_story_order(stories)
        self.assertEqual(ordered[0]["headline"], stories[0]["headline"])
        self.assertEqual(len(ordered), len(stories))
        self.assertNotIn(stories[1]["headline"], [s["headline"] for s in ordered[:3]])

    def test_title_accepts_actual_actor_and_rejects_generic_fallback(self):
        stories = [{"headline":"Trump rejects AI slowdown over China competition"}]
        self.assertTrue(writer._title_matches_lead("Trump vs. Amodei: AI Safety and Your Financial Exposure",stories))
        self.assertFalse(writer._title_matches_lead("Nvidia chips: Your next upgrade",stories))
        self.assertTrue(writer._title_is_generic("China's AI Policy Shift: What Should Users Watch?"))
