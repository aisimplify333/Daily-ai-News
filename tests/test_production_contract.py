"""Zero-network regression tests for the daily production contract.

Run with: python -m unittest discover -s tests -v
No model, TTS, publishing or credential access is involved.
"""

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

import writer_room_v3_1 as writer
import v3_1_runner as runner
import production_delivery_gate as delivery
import grok_tts_v4 as grok
import hybrid_tts_router_v3_1 as router
import production_assets as assets


ROOT = Path(__file__).resolve().parents[1]
STORIES = [
    {"headline": "Google expands AI security access"},
    {"headline": "Nvidia faces infrastructure questions"},
    {"headline": "Schools debate AI restrictions"},
    {"headline": "OpenAI faces copyright scrutiny"},
    {"headline": "Cities question AI power demand"},
]
BOARD = {
    "published_title": "Google AI Security Access Raises a Trust Question",
    "listener_question": "Who should control access to AI security tools?",
    "poll_options": ["Independent researchers", "The platform"],
    "_episode_date": "2026-09-04",
}
EXCHANGE = [
    "ALEX: Wait, if a platform controls both the model and access to the researchers, who gets to decide which security questions can even be asked?",
    "JAMIE: The company says this is not control but safety, and that is the catch. Ordinary people still need someone independent checking those promises before they trust the result.",
    "RUFUS: Quite. The real power is deciding who may inspect the machine. Because permission can become the product, public scrutiny matters more than a lovely press release.",
]
SCRIPT = "\n".join([
    "### SEGMENT 1 — Opening",
    "ALEX: Who decides which questions we can ask?",
    "JAMIE: That is where this gets uncomfortable.",
    "RUFUS: Quite. Permission has a price.",
    "[MUSIC]",
    "ALEX: Welcome to The AI Edge. Jamie is our sharp skeptic; Rufus brings the dry British perspective.",
    "JAMIE: And I have a few questions for Google.",
    "RUFUS: Lovely. Let us hear the evidence.",
    "### SEGMENT 2 — People",
    "ALEX: Why should anyone listening care?",
    "JAMIE: Workers need independent scrutiny, not another promise.",
    "### SEGMENT 3 — Money",
    "ALEX: What is the market missing?",
    "RUFUS: It is confusing access with accountability.",
    "### SEGMENT 4 — Pattern",
    *EXCHANGE,
    "### SEGMENT 5 — Closing",
    "ALEX: What changed, and who wins? Jamie, then Rufus.",
    "JAMIE: The platform gains control. Watch who gets excluded.",
    "RUFUS: The independent researcher needs a seat at the table.",
    "ALEX: What you do next is ask who can audit the result.",
    "JAMIE: That is the question I would take to work.",
    "RUFUS: Splendid. Bring the evidence tomorrow.",
])


def final_script():
    return writer._normalize_primary_sponsor(
        writer._ensure_connection_elements(SCRIPT, STORIES, BOARD, "2026-09-04")
    )


class ProductionContractTests(unittest.TestCase):
    def test_connection_direction_survives_writer_and_repairs(self):
        prompts = [
            writer._writer_prompt(STORIES, [], "2026-09-07", BOARD, {}),
            writer._punchup_prompt(SCRIPT, BOARD, {}),
            writer._rescue_prompt(SCRIPT, {}, BOARD, STORIES),
            writer._native_expansion_prompt(SCRIPT, STORIES, "2026-09-07", BOARD, 300),
            writer._runtime_condense_prompt(SCRIPT, 4300, 3900, BOARD, {}),
        ]
        for prompt in prompts:
            self.assertIn(writer.CAST_CONNECTION_DIRECTION, prompt)
            self.assertIn("NOT a mandatory repeated sequence", prompt)
            self.assertIn("Leave sponsor copy clean and sincere", prompt)
            self.assertNotIn("three to five natural British", prompt)
            self.assertNotIn("Give her 4–7", prompt)

    def test_no_manufactured_concession_even_with_legacy_failed_check(self):
        repaired = writer._deterministic_structure_repair(
            SCRIPT, {"failed": ["real_concession_present"]}, BOARD
        )
        self.assertEqual(repaired, SCRIPT)
        self.assertNotIn("The evidence changed my mind", repaired)

    def test_restored_hd_voices_and_tighter_handoffs(self):
        workflow = (ROOT / ".github/workflows/daily_podcast.yml").read_text()
        for setting in ('VOICE_MODEL_ALEX: "tts-1-hd"', 'VOICE_MODEL_RUFUS: "tts-1-hd"',
                        'TAIL_PAD_MS: "0"', 'REACTION_PAUSE_MS: "70"'):
            self.assertIn(setting, workflow)

    def test_silence_trim_retains_margins_and_sponsor_is_dry(self):
        from pydub import AudioSegment
        from pydub.generators import Sine
        tree = ast.parse((ROOT / "main.py").read_text())
        names = {"_lead_silence_ms", "trim_silence", "_mix_brand_bed_if_needed"}
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *funcs], type_ignores=[])
        namespace = {"AudioSegment": AudioSegment}
        exec(compile(ast.fix_missing_locations(module), "main.py", "exec"), namespace)
        tone = Sine(440).to_audio_segment(duration=500)
        clip = AudioSegment.silent(duration=400) + tone + AudioSegment.silent(duration=600)
        trimmed = namespace["trim_silence"](clip, leading_ms=35, trailing_ms=60)
        self.assertAlmostEqual(len(trimmed), 595, delta=20)
        self.assertGreater(trimmed.max_dBFS, -2)
        quiet = AudioSegment.silent(duration=500)
        self.assertEqual(len(namespace["trim_silence"](quiet)), 500)
        for copy in ("Today's episode is brought to you by The Ledger.", "Subscribe at T-H-E-L-E-D-G-R dot I-O."):
            # Dry policy returns before even reading an audio file.
            self.assertFalse(namespace["_mix_brand_bed_if_needed"](Path("missing.mp3"), copy, "ALEX", Path("out.mp3")))

    def test_schedule_avoids_hour_boundary_and_keeps_cost_safe_triggers(self):
        workflow = (ROOT / ".github/workflows/daily_podcast.yml").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"cron:\s*'([^']+)'", workflow), ["17 10 * * 1-5"])
        triggers = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("workflow_dispatch:", triggers)
        self.assertNotRegex(triggers, r"(?m)^  (push|pull_request):")
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn('FORCE_REBUILD: "false"', workflow)
        self.assertIn('ALLOW_DUPLICATE_DATE_REBUILD: "false"', workflow)

    def test_measured_timeline_handles_speed_fit_and_pre_outro_padding(self):
        files = [Path("voice"), Path("transition"), Path("voice"), Path("outro")]
        markers = [{"kind": "segment", "segment": 1, "start_index": 0}, {"kind": "segment", "segment": 2, "start_index": 1}, {"kind": "outro", "start_index": 3, "end_index": 4}]
        durations = {"voice": 10, "transition": 2, "outro": 6}
        result = assets.build_timeline(files, markers, 33, padding_seconds=5, duration_reader=lambda path: durations[path.name])
        self.assertEqual(result["rows"][1]["start"], 10)
        self.assertEqual(result["rows"][2]["start"], 27)
        self.assertEqual(result["rows"][2]["end"], 33)
        sped_up = assets.build_timeline(files, markers, 14, duration_reader=lambda path: durations[path.name])
        self.assertEqual(sped_up["rows"][1]["start"], 5)
        self.assertEqual(sped_up["rows"][2]["end"], 14)

    def test_clip_uses_complete_measured_turns_and_writes_captions(self):
        turns = [{"kind": "speech", "segment": 4, "speaker": line.split(": ")[0], "text": line.split(": ", 1)[1], "start": index * 10, "end": (index + 1) * 10} for index, line in enumerate(EXCHANGE)]
        clip = assets.choose_clip({"rows": turns})
        self.assertIsNotNone(clip)
        self.assertEqual(clip["seconds"], 30)
        self.assertEqual(len(clip["turns"]), 3)
        with tempfile.TemporaryDirectory(prefix="ai-edge-captions-") as temporary:
            path = Path(temporary) / "clip.vtt"
            assets.write_clip_captions(clip, path)
            captions = path.read_text(encoding="utf-8")
            self.assertTrue(captions.startswith("WEBVTT"))
            self.assertIn("00:00:30.000", captions)
            self.assertIn("JAMIE:", captions)
        self.assertIsNone(assets.choose_clip({"rows": [*turns, {"kind": "intro", "start": 15, "end": 18}]}))

    def test_trailer_does_not_render_without_required_cast_beats(self):
        self.assertEqual(assets.trailer_ranges({"rows": []}, {"start": 0, "end": 30}), [])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for zero-TTS media smoke test")
    def test_clip_and_one_time_trailer_export_without_tts(self):
        def speech(start, end, speaker, text, segment=1):
            return {"kind": "speech", "start": start, "end": end, "speaker": speaker, "text": text, "segment": segment}
        rows = [speech(0, 6, "ALEX", "Who gets to hold the keys?"), {"kind": "intro", "start": 6, "end": 10},
                speech(10, 16, "ALEX", "Welcome to The AI Edge. I'm Alex, with Jamie and Rufus."),
                speech(16, 22, "JAMIE", "The quick skeptic with a question."), speech(22, 28, "RUFUS", "And the dry British perspective.")]
        rows.extend(speech(40 + i * 10, 50 + i * 10, line.split(": ")[0], line.split(": ", 1)[1], 4) for i, line in enumerate(EXCHANGE))
        rows.extend([speech(100, 105, "ALEX", writer.LISTENER_PROMISE, 5), speech(110, 115, "ALEX", "Follow The AI Edge now. See you tomorrow.", 5), {"kind": "outro", "start": 120, "end": 126}])
        with tempfile.TemporaryDirectory(prefix="ai-edge-media-") as temporary:
            output = Path(temporary)
            master = output / "master.mp3"
            assets.AudioSegment.silent(duration=126_000).export(master, format="mp3", bitrate="64k").close()
            cover = output / "cover.png"
            assets.subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=navy:s=128x128", "-frames:v", "1", "-threads", "1", str(cover)], check=True, capture_output=True)
            report = assets.export_promo_assets(master, {"rows": rows}, "2026-09-04", cover)
            self.assertEqual(report["new_tts_calls"], 0)
            self.assertEqual(report["clip"]["seconds"], 30)
            self.assertTrue((output / report["clip"]["audio"]).exists())
            self.assertTrue((output / report["clip"]["video"]).exists(), report)
            self.assertEqual(report["trailer"]["status"], "ready_for_review_and_pinning")
            self.assertTrue(60 <= report["trailer"]["seconds"] <= 90)
            second = assets.export_promo_assets(master, {"rows": rows}, "2026-09-04", output / "missing-cover.png")
            self.assertEqual(second["trailer"]["status"], "existing_trailer_preserved")

    def test_jamie_has_varied_native_laughs_without_extra_render_calls(self):
        for text, tag in (("Hah! Wait, you just priced your own objection.", "laugh"), ("Hah. That is a lovely invoice, Rufus.", "chuckle"), ("Heh. Okay, that one was good.", "giggle")):
            mood = router.infer_mood(text, "JAMIE")
            self.assertEqual(mood, "amused")
            rendered = grok._expressive_text(text, mood)
            self.assertTrue(rendered.startswith(f"[{tag}]"), rendered)
            self.assertNotIn("Hah", rendered)
        sponsor = "Today's episode is brought to you by The Ledger."
        self.assertEqual(grok._expressive_text(sponsor, "amused"), sponsor)

    def test_writer_does_not_invent_fan_mail_or_poll_results(self):
        prompt = writer._writer_prompt(STORIES, [], "2026-09-04", BOARD, {})
        self.assertIn("Never invent named listeners", prompt)
        self.assertIn("explicitly hypothetical listener question", prompt)
        self.assertIn("comic catalyst", prompt)

    def test_paid_episode_survives_missing_optional_assets_but_not_invalid_rss(self):
        feed = ET.Element("rss")
        channel = ET.SubElement(feed, "channel")
        ET.SubElement(channel, "title").text = "The AI Edge"
        ET.SubElement(channel, "description").text = writer.SHOW_DESCRIPTION
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = BOARD["published_title"]
        ET.SubElement(item, "description").text = (
            "What we covered: Google AI security access and the question of who can audit the results. "
            "Alex, Jamie and Rufus debate the consequences for researchers, workers and the platform. "
            + writer.LISTENER_PROMISE
            + " Follow The AI Edge. Sponsor: https://theledgr.io"
        )
        guid = ET.SubElement(item, "guid")
        guid.text = "test-episode"
        ET.SubElement(item, "pubDate").text = "Fri, 04 Sep 2026 10:00:00 GMT"
        ET.SubElement(item, "enclosure", url="https://example.com/podcast_test.mp3", length="4", type="audio/mpeg")
        with tempfile.TemporaryDirectory(prefix="ai-edge-contract-") as temporary:
            with contextlib.chdir(temporary):
                Path("episode_audio").mkdir()
                Path("episode_audio/podcast_test.mp3").write_bytes(b"test")
                for filename in ("feed_sanitize_report.json", "duplicate_guard_report.json"):
                    Path(filename).write_text('{"passed": true}', encoding="utf-8")
                audio = MagicMock()
                audio.__len__.return_value = 1_278_000
                with patch("sys.argv", ["production_delivery_gate.py"]), patch.object(delivery.AudioSegment, "from_mp3", return_value=audio):
                    ET.ElementTree(feed).write("feed.xml", encoding="utf-8")
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(delivery.main(), 0)
                    report = json.loads(Path("production_delivery_report.json").read_text(encoding="utf-8"))
                    self.assertEqual(report["checks"]["transcript_and_chapters"], "warning")
                    self.assertEqual(report["checks"]["listener_poll_payload"], "warning")
                    item.remove(guid)
                    ET.ElementTree(feed).write("feed.xml", encoding="utf-8")
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(delivery.main(), 2)

    def test_runner_preserves_configured_show_description(self):
        with patch.dict(os.environ, {"PODCAST_SHOW_DESCRIPTION": writer.SHOW_DESCRIPTION}):
            runner._set_default_env()
            self.assertEqual(os.environ["PODCAST_SHOW_DESCRIPTION"], writer.SHOW_DESCRIPTION)

    def test_reuse_does_not_require_new_tts_counters(self):
        with patch.object(Path, "exists", return_value=True):
            audio = runner._reusable_episode_audio({"FORCE_REBUILD": False, "_file_ok_min_bytes": lambda path: True})
            self.assertIsNotNone(audio)
            self.assertIsNone(runner._reusable_episode_audio({"FORCE_REBUILD": True}))
        with patch.dict(os.environ, {"REQUIRE_JAMIE_PRIMARY": "true"}):
            with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value='{"jamie_grok_episode_successes": 0}'):
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    runner._enforce_jamie_primary_report()
        self.assertIn("retain completed", captured.getvalue())

    def test_connection_normalization_is_idempotent(self):
        first = final_script()
        second = writer._normalize_primary_sponsor(
            writer._ensure_connection_elements(first, STORIES, BOARD, "2026-09-04")
        )
        self.assertEqual(first, second)
        self.assertEqual(first.count(writer.LISTENER_PROMISE), 1)
        self.assertEqual(first.count("Follow The AI Edge now."), 1)
        self.assertEqual(first.count("T-H-E-L-E-D-G-R dot I-O"), 1)
        self.assertIn("### SEGMENT 1 — Google expands AI security access", first)
        self.assertIn("### SEGMENT 5 — The Edge: What Changed and What Happens Next", first)

    def test_sponsor_voice_rotates_and_paid_url_stays_once(self):
        first = final_script()
        second = writer._ensure_connection_elements(first, STORIES, BOARD, "2026-09-05")
        pattern = r"^(JAMIE|RUFUS): A quick final note:"
        self.assertNotEqual(re.search(pattern, first, re.M).group(1), re.search(pattern, second, re.M).group(1))
        self.assertEqual(second.count("T-H-E-L-E-D-G-R dot I-O"), 1)

    def test_real_poll_and_character_memory_are_available(self):
        episode = {
            "date": "2026-09-03",
            "title": "An earlier episode",
            "listener_question": "Who should inspect AI tools?",
            "predictions": [{"host": "Jamie", "claim": "Independent audits will matter."}],
            "positions": {"alex": "Access matters.", "jamie": "People need scrutiny.", "rufus": "Watch incentives."},
            "strong_disagreements": [{"issue": "Who sets the access rules?"}],
            "running_jokes": ["The permission invoice"],
            "outcomes_to_revisit": [{"claim": "Check expanded access.", "check_after": "2026-09-10"}],
        }
        results = [{"episode_date": "2026-09-03", "winning_option": "Independent researchers", "winning_percent": 61, "total_votes": 84}]
        fuel = writer._continuity_fuel(writer._merge_poll_results([episode], results), {"running_bits": ["Rufus brings receipts"]})
        callbacks = " ".join(fuel["callbacks"])
        for expected in ("61%", "84 votes", "Jamie predicted", "Alex argued", "Unresolved argument", "Outcome to revisit"):
            self.assertIn(expected, callbacks)
        self.assertIn("The permission invoice", fuel["running_jokes"])
        self.assertIn("Rufus brings receipts", fuel["running_jokes"])
        without_results = writer._continuity_fuel([episode])
        self.assertNotIn("votes", " ".join(without_results["poll_callbacks"]))
        self.assertNotIn("61%", " ".join(without_results["poll_callbacks"]))

    def test_shareable_candidate_is_one_contiguous_exchange(self):
        candidate = writer._find_shareable_exchange("### SEGMENT 4 — Pattern\n" + "\n".join(EXCHANGE))
        self.assertTrue(candidate["passed"])
        self.assertGreaterEqual(candidate["estimated_seconds"], 20)
        self.assertLessEqual(candidate["estimated_seconds"], 45)
        self.assertEqual([row["text"] for row in candidate["turns"]], [line.split(": ", 1)[1] for line in EXCHANGE])
        for break_line in ("ALEX: Today’s episode is brought to you by The Ledger.", "[MUSIC]", "### SEGMENT 5 — Closing"):
            broken = "\n".join(["### SEGMENT 4 — Pattern", *EXCHANGE[:2], break_line, EXCHANGE[2]])
            self.assertFalse(writer._find_shareable_exchange(broken)["passed"])

    def test_creative_warnings_do_not_block_delivery(self):
        script = final_script()
        fuel = {"has_history": True, "poll_callbacks": ["An earlier audience question"]}
        with patch.dict(os.environ, {"RECOVERY_MIN_SCRIPT_WORDS": "1", "RECOVERY_MAX_SCRIPT_WORDS": "5000"}):
            with patch.object(writer, "_find_shareable_exchange", return_value={"passed": False}):
                assessment = writer._assess(script, STORIES, BOARD, fuel)
        self.assertTrue(assessment["pass"], assessment["failed"])
        self.assertIn("advisory_shareable_exchange_20_45s", assessment["soft_flags"])
        self.assertIn("advisory_prior_listener_question_or_poll_acknowledged", assessment["soft_flags"])

    def test_legacy_hook_preserves_editorial_closing_header(self):
        namespace = {}
        with contextlib.redirect_stdout(io.StringIO()):
            writer.install_v3_1(namespace)
        script = namespace["ensure_theledgr_readout"](final_script(), STORIES, "2026-09-04")
        self.assertIn("### SEGMENT 5 — The Edge: What Changed and What Happens Next", script)
        self.assertNotIn("The Ledger Readout + Final Button", script)

    def test_final_show_notes_include_promise_even_without_writer_pack(self):
        # Compile just this pure formatter, not main.py's provider setup.
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        formatter = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_episode_show_notes")
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), formatter], type_ignores=[])
        namespace = {"re": re, "PUBLIC_SUBSCRIBE_URL": "https://theledgr.io", "_story_display_headline": lambda story: story["headline"]}
        exec(compile(ast.fix_missing_locations(module), "main.py", "exec"), namespace)
        notes = namespace["build_episode_show_notes"]({}, {}, STORIES)
        self.assertIn(writer.LISTENER_PROMISE, notes)
        self.assertIn("Follow The AI Edge on Spotify", notes)
        self.assertIn("What we covered:", notes)
        self.assertIn("Listener question:", notes)


if __name__ == "__main__":
    unittest.main()
