# -*- coding: utf-8 -*-
"""
The AI Edge v3.1 hybrid TTS router.

Paste this entire file as: hybrid_tts_router_v3_1.py

Production voice routing:
- JAMIE -> Gemini 3.1 Flash TTS Preview first
- ALEX  -> OpenAI TTS
- RUFUS -> OpenAI TTS
- ElevenLabs -> off by default until audience/sponsor economics justify it

This file monkey-patches main.py's tts_to_file() after main.py is loaded by
v3_1_runner.py. It does not replace main.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List


BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / ".tts_cache" / "gemini_jamie"
REPORT_PATH = BASE_DIR / "hybrid_tts_report.json"

STATS: Dict[str, Any] = {
    "version": "v3.1-jamie-gemini-openai-hybrid",
    "routing": {
        "ALEX": "openai",
        "JAMIE": "gemini",
        "RUFUS": "openai",
        "ELEVENLABS": "disabled",
    },
    "gemini_model": os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
    "gemini_voice_jamie": os.getenv("GEMINI_TTS_VOICE_JAMIE", "Sulafat"),
    "calls": [],
    "fallbacks": [],
    "jamie_chars_requested": 0,
    "jamie_cache_hits": 0,
    "jamie_gemini_successes": 0,
    "jamie_gemini_failures": 0,
}


def _safe_print(msg: str) -> None:
    print(msg, flush=True)


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _write_report() -> None:
    try:
        REPORT_PATH.write_text(json.dumps(STATS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _sanitize_spoken_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", t, flags=re.IGNORECASE).strip()
    # Gemini handles audio tags. Normalize some existing cue variants but keep useful ones.
    replacements = {
        "[laugh]": "[laughs]",
        "[chuckle]": "[laughs softly]",
        "[chuckles]": "[laughs softly]",
        "[scoff]": "[scoffs]",
        "[huff]": "[sighs]",
        "[pause]": "[short pause]",
        "[beat]": "[short pause]",
        "[amused exhale]": "[laughs softly]",
        "[sharp exhale]": "[sighs]",
    }
    for old, new in replacements.items():
        t = t.replace(old, new)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _jamie_prompt(text: str) -> str:
    transcript = _sanitize_spoken_text(text)
    return f"""Synthesize speech only. Do not read headings, instructions, labels, speaker names, markdown, or quotation marks. Speak only the words in the TRANSCRIPT section.

# AUDIO PROFILE: Jamie
Jamie is a sharp, warm, emotionally alive podcast co-host on The AI Edge. She is the heavy reactor in the room: intelligent, quick, funny, and human. She reacts to Alex and Rufus with amused disbelief, small laughs, warmth, and plain-English clarity. She sounds modern, confident, and conversational — never robotic, never valley-girl, never over-acted.

# SCENE
A premium conversational technology podcast. Alex is the host, Rufus is the dry British analyst, and Jamie is the smart human translator who makes the story land for normal listeners. Jamie is listening closely and responding in the moment.

# DIRECTOR'S NOTES
Style: Warm, intelligent, emotionally present, witty, and reactive. Let the listener hear the smile when something is funny and the concern when the human stakes are real.
Pacing: Natural podcast pace. Quick on short reactions. Slower and clearer when explaining the simple version.
Performance: Use tasteful micro-reactions when the transcript asks for them: [laughs], [sighs], [sarcastic], [curious], [short pause]. Do not exaggerate.
Clarity: Keep articulation crisp. This is a serious show, not a character skit.

# TRANSCRIPT
{transcript}
""".strip()


def _write_wave(filename: Path, pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def _extract_audio_bytes(response: Any) -> bytes:
    try:
        part = response.candidates[0].content.parts[0]
    except Exception as e:
        raise RuntimeError(f"Gemini TTS response did not include an audio part: {e}")

    inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
    if inline is None and isinstance(part, dict):
        inline = part.get("inline_data") or part.get("inlineData")
    if inline is None:
        raise RuntimeError("Gemini TTS response part had no inline_data audio payload")

    data = getattr(inline, "data", None)
    if data is None and isinstance(inline, dict):
        data = inline.get("data")
    if data is None:
        raise RuntimeError("Gemini TTS inline_data had no data field")

    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except Exception:
            return data.encode("latin1")
    raise RuntimeError(f"Unexpected Gemini TTS audio payload type: {type(data)!r}")


def _ffmpeg_wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav_path),
        "-c:a", "libmp3lame",
        "-b:a", os.getenv("SEGMENT_EXPORT_BITRATE", "192k"),
        str(mp3_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _cache_key(text: str, voice: str, model: str) -> str:
    raw = json.dumps({"speaker": "JAMIE", "voice": voice, "model": model, "text": _sanitize_spoken_text(text)}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _gemini_jamie_to_file(text: str, out_path: Path) -> None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; cannot render Jamie with Gemini TTS")

    model = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()
    voice = os.getenv("GEMINI_TTS_VOICE_JAMIE", "Sulafat").strip()
    retries = max(1, int(os.getenv("GEMINI_TTS_MAX_RETRIES", "2")))
    use_cache = _bool_env("GEMINI_TTS_CACHE", "true")

    clean_text = _sanitize_spoken_text(text)
    STATS["jamie_chars_requested"] += len(clean_text)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{_cache_key(clean_text, voice, model)}.mp3"
    if use_cache and cache_file.exists() and cache_file.stat().st_size > 1000:
        shutil.copyfile(cache_file, out_path)
        STATS["jamie_cache_hits"] += 1
        STATS["calls"].append({"speaker": "JAMIE", "provider": "gemini", "cache": True, "chars": len(clean_text)})
        _write_report()
        return

    prompt = _jamie_prompt(clean_text)
    last_err: Exception | None = None

    for attempt in range(1, retries + 1):
        wav_path = out_path.with_suffix(f".gemini_attempt_{attempt}.wav")
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                        )
                    ),
                ),
            )
            pcm = _extract_audio_bytes(response)
            if not pcm or len(pcm) < 500:
                raise RuntimeError("Gemini TTS returned empty or tiny audio payload")
            _write_wave(wav_path, pcm)
            _ffmpeg_wav_to_mp3(wav_path, out_path)
            if out_path.exists() and out_path.stat().st_size > 1000:
                if use_cache:
                    shutil.copyfile(out_path, cache_file)
                STATS["jamie_gemini_successes"] += 1
                STATS["calls"].append({
                    "speaker": "JAMIE",
                    "provider": "gemini",
                    "cache": False,
                    "model": model,
                    "voice": voice,
                    "chars": len(clean_text),
                    "attempt": attempt,
                })
                _write_report()
                return
            raise RuntimeError("Gemini TTS MP3 output missing or too small")
        except Exception as e:
            last_err = e
            STATS["jamie_gemini_failures"] += 1
            _safe_print(f" ⚠️ Gemini TTS failed for JAMIE attempt {attempt}/{retries}: {e}")
            time.sleep(min(6, 1.5 * attempt))
        finally:
            try:
                if wav_path.exists():
                    wav_path.unlink()
            except Exception:
                pass

    raise RuntimeError(f"Gemini TTS failed for JAMIE after {retries} attempts: {last_err}")


def install(g: Dict[str, Any]) -> None:
    """Install hybrid TTS routing into the loaded main.py globals dictionary."""
    original_tts_to_file = g.get("tts_to_file")
    if not callable(original_tts_to_file):
        raise RuntimeError("hybrid_tts_router_v3_1 could not find main.py tts_to_file() to wrap")

    # Force main.py away from ElevenLabs scene/dialogue rendering. We still let OpenAI render Alex/Rufus.
    os.environ["AUDIO_BACKEND"] = "openai"
    os.environ["ELEVENLABS_ENABLED"] = "false"
    g["AUDIO_BACKEND"] = "openai"
    if "ELEVEN_USE_DIALOGUE_SCENES" in g:
        g["ELEVEN_USE_DIALOGUE_SCENES"] = False

    def hybrid_tts_to_file(text: str, speaker: str, out_path: Path) -> None:
        spk = (speaker or "").strip().upper()
        out = Path(out_path)
        if spk == "JAMIE" and os.getenv("JAMIE_TTS_PROVIDER", "gemini").strip().lower() == "gemini":
            try:
                _gemini_jamie_to_file(text, out)
                return
            except Exception as e:
                STATS["fallbacks"].append({"speaker": "JAMIE", "from": "gemini", "to": "openai", "reason": str(e)[:500]})
                _write_report()
                if os.getenv("GEMINI_TTS_FALLBACK_PROVIDER", "openai").strip().lower() == "openai":
                    _safe_print(f" ⚠️ Falling back to OpenAI TTS for JAMIE: {e}")
                    return original_tts_to_file(text, speaker, out)
                raise
        return original_tts_to_file(text, speaker, out)

    g["tts_to_file"] = hybrid_tts_to_file
    STATS["installed"] = True
    _write_report()
    _safe_print(">> ✅ Installed hybrid TTS router: Jamie=Gemini, Alex/Rufus=OpenAI, ElevenLabs=OFF")
