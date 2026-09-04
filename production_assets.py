"""Measured navigation and promotional excerpts, using only the paid master.

No model or TTS calls. Derivative failures are advisory, never episode blockers.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import textwrap
from typing import Any, Callable

from pydub import AudioSegment


def build_timeline(
    files: list[Path], markers: list[dict[str, Any]], final_seconds: float,
    padding_seconds: float = 0.0, duration_reader: Callable | None = None,
) -> dict[str, Any]:
    reader = duration_reader or (lambda path: len(AudioSegment.from_file(path)) / 1000.0)
    offsets = [0.0]
    durations: dict[Path, float] = {}
    for path in files:
        if path not in durations:
            durations[path] = float(reader(path))
        offsets.append(offsets[-1] + durations[path])
    outro = next((row for row in markers if row["kind"] == "outro"), None)
    pad_at = int(outro["start_index"]) if outro else len(files)
    denominator = offsets[-1] + max(0, padding_seconds)
    scale = final_seconds / denominator if denominator else 1.0

    def timestamp(index: int) -> float:
        return round((offsets[index] + (padding_seconds if index >= pad_at else 0)) * scale, 3)

    rows = []
    for marker in markers:
        row = {key: value for key, value in marker.items() if not key.endswith("_index")}
        row["start"] = timestamp(int(marker["start_index"]))
        row["end"] = timestamp(int(marker.get("end_index", marker["start_index"])))
        rows.append(row)
    return {"version": 1, "method": "measured-assembly-scaled-to-master", "duration_seconds": final_seconds, "rows": rows}


def choose_clip(timeline: dict[str, Any]) -> dict[str, Any] | None:
    from writer_room_v3_1 import _find_shareable_exchange

    turns = [row for row in timeline.get("rows", []) if row["kind"] == "speech"]
    candidates = []
    for start in range(len(turns)):
        for count in range(3, 8):
            window = turns[start:start + count]
            if len(window) != count or len({row["segment"] for row in window}) != 1:
                continue
            seconds = window[-1]["end"] - window[0]["start"]
            if not 20 <= seconds <= 45:
                continue
            if any(row["kind"] == "intro" and window[0]["start"] < row["start"] < window[-1]["end"] for row in timeline.get("rows", [])):
                continue
            script = f"### SEGMENT {window[0]['segment']} — Clip\n" + "\n".join(
                f"{row['speaker']}: {' '.join(row['text'].split())}" for row in window
            )
            candidate = _find_shareable_exchange(script)
            if not candidate.get("passed") or len(candidate["turns"]) != count:
                continue
            candidates.append({"start": window[0]["start"], "end": window[-1]["end"], "seconds": round(seconds, 3), "score": candidate["score"], "turns": window})
    return max(candidates, key=lambda row: row["score"]) if candidates else None


def _vtt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds_int, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds_int:02}.{milliseconds:03}"


def write_clip_captions(clip: dict[str, Any], path: Path) -> None:
    cues = ["WEBVTT", ""]
    for turn in clip["turns"]:
        words = str(turn["text"]).split()
        groups = [words[i:i + 12] for i in range(0, len(words), 12)]
        for index, group in enumerate(groups):
            start = turn["start"] + (turn["end"] - turn["start"]) * index / len(groups) - clip["start"]
            end = turn["start"] + (turn["end"] - turn["start"]) * (index + 1) / len(groups) - clip["start"]
            cues.extend([f"{_vtt_time(start)} --> {_vtt_time(end)}", "\n".join(textwrap.wrap(f"{turn['speaker']}: {' '.join(group)}", width=40)), ""])
    path.write_text("\n".join(cues), encoding="utf-8")


def trailer_ranges(timeline: dict[str, Any], clip: dict[str, Any]) -> list[tuple[float, float]]:
    """A trailer demonstrates the actual cast; no fabricated fan endorsement."""
    rows = timeline.get("rows", [])
    speech = [row for row in rows if row["kind"] == "speech"]
    intro = next((row for row in rows if row["kind"] == "intro"), None)
    welcome = next((row for row in speech if "welcome to the ai edge" in row["text"].lower()), None)
    promise = next((row for row in speech if "what changed. who wins. what you do next." in row["text"].lower()), None)
    follow = next((row for row in speech if "follow the ai edge now" in row["text"].lower()), None)
    outro = next((row for row in rows if row["kind"] == "outro"), None)
    if not all((speech, intro, welcome, promise, follow, outro)):
        return []
    welcome_index = speech.index(welcome)
    introductions = speech[welcome_index:welcome_index + 3]
    intro_text = " ".join(row["text"] for row in introductions).lower()
    if not all(name in intro_text for name in ("alex", "jamie", "rufus")):
        return []
    selections = [speech[0], intro, *introductions, {"start": clip["start"], "end": clip["end"]}, promise, follow, outro]
    ranges = []
    for row in selections:
        end = min(row["end"], row["start"] + 6) if row in (intro, outro) else row["end"]
        pair = (row["start"], end)
        if pair not in ranges and pair[1] > pair[0]:
            ranges.append(pair)
    seconds = sum(end - start for start, end in ranges)
    return ranges if 60 <= seconds <= 90 else []


def export_promo_assets(master_path: Path, timeline: dict[str, Any], date: str, cover: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"date": date, "new_tts_calls": 0, "warnings": [], "publication": "assets_only_not_uploaded_to_spotify"}
    output_dir = master_path.parent
    clip = choose_clip(timeline)
    if not clip:
        report["warnings"].append("No self-contained measured 20–45 second candidate; producer review needed.")
        return report
    master = AudioSegment.from_mp3(master_path)
    clip_path = output_dir / f"clip_{date}.mp3"
    caption_path = output_dir / f"clip_{date}.vtt"
    video_path = output_dir / f"clip_{date}.mp4"
    master[round(clip["start"] * 1000):round(clip["end"] * 1000)].export(clip_path, format="mp3", bitrate="192k").close()
    write_clip_captions(clip, caption_path)
    report["clip"] = {**clip, "audio": clip_path.name, "captions": caption_path.name, "caption_timing": "measured-turn-boundaries-with-estimated-word-groups", "needs_editorial_review": True}
    if cover.exists():
        command = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(cover.resolve()), "-i", clip_path.name,
                   "-vf", f"scale=720:720:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:120:color=0x101827,subtitles={caption_path.name}:force_style='FontName=DejaVu Sans,FontSize=20,MarginV=70,Outline=2'",
                   "-t", str(clip["seconds"]), "-c:v", "libx264", "-preset", "veryfast", "-r", "25", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", video_path.name]
        try:
            subprocess.run(command, cwd=output_dir, check=True, timeout=180, capture_output=True)
            report["clip"]["video"] = video_path.name
        except Exception as exc:
            report["warnings"].append(f"Captioned video not completed: {type(exc).__name__}; audio clip preserved.")
    else:
        report["warnings"].append("Cover image unavailable; audio clip and captions preserved.")

    trailer_path = output_dir / "show_trailer.mp3"
    if trailer_path.exists():
        report["trailer"] = {"status": "existing_trailer_preserved", "audio": trailer_path.name}
    else:
        ranges = trailer_ranges(timeline, clip)
        if ranges:
            trailer = AudioSegment.empty()
            for start, end in ranges:
                trailer += master[round(start * 1000):round(end * 1000)].fade_in(35).fade_out(65)
            trailer.export(trailer_path, format="mp3", bitrate="192k").close()
            report["trailer"] = {"status": "ready_for_review_and_pinning", "audio": trailer_path.name, "seconds": round(len(trailer) / 1000, 3), "source_ranges": ranges}
        else:
            report["warnings"].append("Trailer beats do not fit 60–90 seconds cleanly; prepared trailer script remains available.")
    return report
