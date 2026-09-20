"""One bounded cast audition. Reuse identical paid takes in both timing variants.

This is an explicitly hypothetical conversation, not a reported AI news event.
No feed, publishing, main-voice replacement or full-episode regeneration.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from pydub import AudioSegment
from pydub.silence import detect_leading_silence
from broadcast_performance import performance_settings
from dialogue_direction import boundary_pause
from hybrid_tts_router_v3_1 import infer_mood
from grok_tts_v4 import render_jamie
from audio_engineering import write_engineering_report

SCENE = [
    ("ALEX", "Imagine an AI tool that gives you an hour back each week. What would make that genuinely useful?"),
    ("JAMIE", "Getting the hour back. Not spending fifty minutes checking what it did, then another ten telling everyone how productive I am."),
    ("RUFUS", "An efficiency programme with its own administrative department."),
    ("JAMIE", "You would absolutely chair that department."),
    ("RUFUS", "Only until we found someone less qualified. Tradition matters."),
    ("ALEX", "Before we appoint anyone—"),
    ("JAMIE", "Try one ordinary task. Something dull, repeatable, and easy to check. See whether it actually helps."),
    ("ALEX", "So what would you choose?"),
    ("RUFUS", "Turning my own meeting notes into a first draft. Keep anything confidential out of an unapproved tool. Then check the draft against the notes."),
    ("JAMIE", "And if it works, enjoy the time. Go outside. Phone somebody. The prize does not have to be another meeting."),
    ("RUFUS", "A radical proposal. I shall circulate it for discussion."),
    ("ALEX", "The useful question is whether it gives you something back. That is a result worth measuring."),
]


def main():
    if os.getenv("GITHUB_RUN_ATTEMPT", "1") != "1":
        raise RuntimeError("Refusing automatic paid rerun; use preserved takes.")
    output = Path("auditions/performance_output")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"hypothetical_scene": True, "listened": False, "calls": [], "variants": {},
                "comparison": "Same script and identical paid takes; only inter-turn gaps differ; baseline uses a fixed 100 ms gap.",
                "limitation": "Does not isolate improved writing or prove natural acting; HD voices cannot accept acting instructions."}
    transcript = "HYPOTHETICAL PERFORMANCE AUDITION — NOT A NEWS REPORT\n\n" + "\n".join(f"{s}: {t}" for s, t in SCENE)
    (output / "TRANSCRIPT.txt").write_text(transcript)
    clips = []
    for index, (speaker, text) in enumerate(SCENE):
        raw = output / f"take_{index:02d}_{speaker}.mp3"
        mood = infer_mood(text, speaker)
        if speaker == "JAMIE":
            call = render_jamie(text, mood, raw, primary_only=True)
        else:
            voice = {"ALEX": "onyx", "RUFUS": "fable"}[speaker]
            response = requests.post("https://api.openai.com/v1/audio/speech",
                headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                json={"model": "tts-1-hd", "voice": voice, "input": text, "response_format": "mp3"}, timeout=120)
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI speech request failed: HTTP {response.status_code}")
            raw.write_bytes(response.content)
            call = {"provider": "openai", "model": "tts-1-hd", "voice": voice, "characters": len(text), "directed": False}
        manifest["calls"].append({"index": index, "speaker": speaker, **call})
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        clip = AudioSegment.from_file(raw)
        start = max(0, detect_leading_silence(clip, silence_threshold=-45) - 35)
        end = max(0, detect_leading_silence(clip.reverse(), silence_threshold=-45) - 60)
        trimmed = output / f"trim_{index}.wav"
        clip[start:len(clip)-end if end else len(clip)].export(trimmed, format="wav").close()
        speed, delta = performance_settings(text, speaker, mood)
        speed *= {"ALEX": 1.01, "JAMIE": 1.05, "RUFUS": .99}[speaker]
        processed = output / f"processed_{index}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(trimmed), "-af",
                        f"atempo={speed:.4f},volume={ {'ALEX':3.5,'JAMIE':1.0,'RUFUS':.3}[speaker]+delta}dB",
                        str(processed)], check=True)
        clips.append(AudioSegment.from_file(processed))
    for variant in ("baseline", "directed"):
        mix = AudioSegment.empty()
        decisions = []
        for index, ((speaker, text), clip) in enumerate(zip(SCENE, clips)):
            next_speaker, next_text = SCENE[index+1] if index+1 < len(SCENE) else ("", "")
            edit = boundary_pause(text, speaker, next_text, next_speaker, infer_mood(text, speaker))
            # A fixed-gap control, not a claim to reproduce every legacy heuristic.
            baseline = 100
            gap = edit["milliseconds"] if variant == "directed" else baseline
            decisions.append({"speaker": speaker, "text": text, "start_ms": len(mix), "end_ms": len(mix)+len(clip), "gap_ms": gap, "reason": edit["reason"] if variant == "directed" else "frozen_baseline"})
            mix += clip
            if index+1 < len(SCENE):
                mix += AudioSegment.silent(duration=gap)
        wav = output / f"{variant}.wav"
        mix.export(wav, format="wav").close()
        final = output / f"{variant}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af",
            "acompressor=threshold=-16dB:ratio=2.2:attack=18:release=180:makeup=2.5,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "192k", str(final)], check=True)
        report = write_engineering_report(final, output / f"{variant}_engineering.json")
        manifest["variants"][variant] = {"seconds": len(AudioSegment.from_file(final))/1000, "edits": decisions, "engineering": report}
    manifest["paid_take_count"] = len(clips)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"completed": True, "paid_takes": len(clips), "listened": False,
                      "seconds": {k:v["seconds"] for k,v in manifest["variants"].items()}}))


if __name__ == "__main__":
    main()
