# -*- coding: utf-8 -*-
"""
The AI Edge v3.2 hybrid TTS router.

Paste this entire file as: hybrid_tts_router_v3_1.py

Production voice routing:
- JAMIE -> Gemini 3.1 Flash TTS Preview first
- ALEX  -> OpenAI TTS
- RUFUS -> OpenAI TTS
- ElevenLabs -> off by default until audience/sponsor economics justify it

v3.2 fix:
The prior router wrapped main.py's tts_to_file(), but the completed 2026-05-15
run showed zero Jamie Gemini calls. This version wraps BOTH tts_to_file() and
_render_spoken_chunk_to_file(), and it forces the speaker backend away from
ElevenLabs scene rendering. The report must show calls > 0 after a real run.
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
from typing import Any, Callable, Dict, Optional

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / ".tts_cache" / "gemini_jamie"
REPORT_PATH = BASE_DIR / "hybrid_tts_report.json"

STATS: Dict[str, Any] = {
    "version": "v3.2-hard-debate-jamie-gemini-forced-router",
    "routing": {
        "ALEX": "openai",
        "JAMIE": "gemini-first-openai-fallback",
        "RUFUS": "openai",
        "ELEVENLABS": "disabled",
    },
    "gemini_model": os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
    "gemini_voice_jamie": os.getenv("GEMINI_TTS_VOICE_JAMIE", "Sulafat"),
    "installed": False,
    "patched": [],
    "calls": [],
    "fallbacks": [],
    "jamie_chars_requested": 0,
    "jamie_cache_hits": 0,
    "jamie_gemini_successes": 0,
    "jamie_gemini_failures": 0,
    "alex_openai_calls": 0,
    "rufus_openai_calls": 0,
    "non_speaker_calls": 0,
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
        "[smirks]": "[amused]",
        "[smirk]": "[amused]",
    }
    for old, new in replacements.items():
        t = t.replace(old, new)
    # Remove stage directions that should not be spoken.
    t = re.sub(r"\[(?:leans in|on mic|under her breath|under his breath|beat of silence|stage direction)[^\]]*\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _jamie_prompt(text: str) -> str:
    transcript = _sanitize_spoken_text(text)
    return f"""Synthesize speech only. Do not read headings, instructions, labels, speaker names, markdown, or quotation marks. Speak only the exact words in the TRANSCRIPT section.

# AUDIO PROFILE: Jamie
Jamie is a sharp, warm, emotionally alive podcast co-host on The AI Edge. She is the heavy reactor in the room: intelligent, quick, funny, and human. She reacts to Alex and Rufus with amused disbelief, small laughs, warmth, and plain-English clarity. She sounds modern, confident, conversational, and real — never robotic, never valley-girl, never over-acted.

# SCENE
A premium conversational AI news podcast. Alex is the host, Rufus is the dry British analyst, and Jamie is the human translator who makes the debate land for normal listeners. The room is moving fast. Jamie is listening closely and responding in the moment, not reading an essay.

# DIRECTOR'S NOTES
Style: Warm, intelligent, emotionally present, witty, and reactive. The listener should hear a tiny smile when something is ridiculous and real concern when people, jobs, patients, privacy, or money are exposed.
Pacing: Natural podcast pace. Quick on short reactions. Slower and clearer when explaining the simple version.
Performance: Use tasteful micro-reactions only when the transcript asks for them: [laughs], [laughs softly], [sighs], [sarcastic], [curious], [short pause]. Keep it human, not theatrical.
Clarity: Crisp articulation. Serious show, not a character skit.

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
    if not clean_text:
        raise RuntimeError("Jamie line was empty after sanitization")

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
    last_err: Optional[Exception] = None

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


def _record_openai_call(speaker: str, text: str) -> None:
    spk = (speaker or "").strip().upper()
    if spk == "ALEX":
        STATS["alex_openai_calls"] += 1
    elif spk == "RUFUS":
        STATS["rufus_openai_calls"] += 1
    else:
        STATS["non_speaker_calls"] += 1
    STATS["calls"].append({"speaker": spk or "UNKNOWN", "provider": "openai", "chars": len(_sanitize_spoken_text(text))})
    _write_report()


def install(g: Dict[str, Any]) -> None:
    """Install hybrid TTS routing into the loaded main.py globals dictionary."""
    original_tts_to_file = g.get("tts_to_file")
    if not callable(original_tts_to_file):
        raise RuntimeError("hybrid_tts_router_v3_1 could not find main.py tts_to_file() to wrap")

    original_render_spoken = g.get("_render_spoken_chunk_to_file")
    original_backend = g.get("_speaker_audio_backend")

    # Force main.py away from ElevenLabs scene/dialogue rendering.
    os.environ["AUDIO_BACKEND"] = "openai"
    os.environ["ELEVENLABS_ENABLED"] = "false"
    os.environ["ELEVEN_USE_DIALOGUE_SCENES"] = "false"
    os.environ.setdefault("JAMIE_TTS_PROVIDER", "gemini")
    os.environ.setdefault("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    os.environ.setdefault("GEMINI_TTS_VOICE_JAMIE", "Sulafat")
    os.environ.setdefault("GEMINI_TTS_FALLBACK_PROVIDER", "openai")
    os.environ.setdefault("GEMINI_TTS_MAX_RETRIES", "2")
    os.environ.setdefault("GEMINI_TTS_CACHE", "true")

    g["AUDIO_BACKEND"] = "openai"
    if "ELEVEN_USE_DIALOGUE_SCENES" in g:
        g["ELEVEN_USE_DIALOGUE_SCENES"] = False

    def route_text_to_file(text: str, speaker: str, out_path: Path) -> None:
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
                    _record_openai_call("JAMIE", text)
                    return original_tts_to_file(text, speaker, out)
                raise
        _record_openai_call(spk, text)
        return original_tts_to_file(text, speaker, out)

    def hybrid_tts_to_file(text: str, speaker: str, out_path: Path) -> None:
        return route_text_to_file(text, speaker, Path(out_path))

    def hybrid_render_spoken_chunk_to_file(text: str, speaker: str, out_path: Path) -> None:
        # The production audio loop may call this wrapper instead of tts_to_file directly.
        return route_text_to_file(text, speaker, Path(out_path))

    def hybrid_speaker_audio_backend(speaker: str) -> str:
        # Return openai to prevent ElevenLabs dialogue-scene bundling. Jamie is intercepted by this router.
        spk = (speaker or "").strip().upper()
        if spk in {"ALEX", "JAMIE", "RUFUS"}:
            return "openai"
        if callable(original_backend):
            try:
                return original_backend(speaker)
            except Exception:
                return "openai"
        return "openai"

    g["tts_to_file"] = hybrid_tts_to_file
    STATS["patched"].append("tts_to_file")

    if callable(original_render_spoken):
        g["_render_spoken_chunk_to_file"] = hybrid_render_spoken_chunk_to_file
        STATS["patched"].append("_render_spoken_chunk_to_file")

    g["_speaker_audio_backend"] = hybrid_speaker_audio_backend
    STATS["patched"].append("_speaker_audio_backend")

    STATS["installed"] = True
    _write_report()
    _safe_print(">> ✅ Installed hybrid TTS router v3.2: Jamie=Gemini-forced, Alex/Rufus=OpenAI, ElevenLabs=OFF")
