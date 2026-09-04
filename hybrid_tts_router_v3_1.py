# -*- coding: utf-8 -*-
"""
The AI Edge v3.3 — Mood-aware hybrid TTS router.
Drop-in replacement for: hybrid_tts_router_v3_1.py  (same filename, same entry point)

WHAT CHANGED vs v3.2, AND WHY
-----------------------------
v3.2 routed Jamie to Gemini and verified the call happened — both good, both kept.
But it gave every Jamie line the SAME director's notes. A tense interruption and a
warm laugh were performed with identical direction, so the voice got warmer but the
*mood* never moved. A debate has to rise and fall; a flat read of a good script
still sounds synthetic.

v3.2 also expected bracket cues like [laughs] in the transcript. The v3.3 writer
strips all brackets (so OpenAI TTS never reads "[laughs]" aloud). So emotion can no
longer ride on inline tags — it has to be inferred from the words themselves.

v3.3 fixes both:

  1. PER-LINE MOOD INFERENCE. Every line is classified — deterministically, no extra
     LLM calls — into a debate mood: pressure, pushback, amused, concern, explainer,
     dry-wit, concession, interruption, or neutral. The v3.3 writer deliberately
     writes the signals in (em-dash interruptions, "Wait.", concession phrases,
     number-dense receipts), so reading them back is reliable and free.

  2. MOOD DRIVES DELIVERY FOR ALL THREE HOSTS. The director's notes (Gemini) and the
     style instructions (OpenAI gpt-4o-mini-tts) are now built per line from the
     mood + the host's base temperament. Alex pressing a question, Rufus landing a
     dry undercut, and Jamie conceding a point are now each directed differently.

  3. ROUTER-OWNED OPENAI PATH. To direct Alex and Rufus, the router now renders them
     itself via OpenAI TTS with a per-line `instructions` parameter. It still falls
     back to main.py's original tts_to_file on any error (logged, never silent), and
     you can revert Alex/Rufus to the old path entirely with ROUTER_OWN_OPENAI=false.

  4. PER-HOST PROVIDER CONFIG. ALEX/JAMIE/RUFUS each have a provider env var. Default
     keeps Jamie=Gemini, Alex/Rufus=OpenAI. If you want a genuinely British Rufus,
     set RUFUS_TTS_PROVIDER=gemini and pick a Gemini voice — OpenAI voices cannot do
     a real British accent (see the note at the bottom of this file).

Entry point and globals contract unchanged: main.py still calls install(g).
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
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / ".tts_cache"
REPORT_PATH = BASE_DIR / "hybrid_tts_report.json"

# ----------------------------------------------------------------------------
# Runtime handles, filled in by install()
# ----------------------------------------------------------------------------
_RT: Dict[str, Any] = {"openai_client": None, "original_tts": None}

# ----------------------------------------------------------------------------
# Report / telemetry
# ----------------------------------------------------------------------------
STATS: Dict[str, Any] = {
    "version": "v4-grok-jamie-mood-aware-router",
    "routing": {
        "ALEX": os.getenv("ALEX_TTS_PROVIDER", "openai"),
        "JAMIE": os.getenv("JAMIE_TTS_PROVIDER", "grok"),
        "RUFUS": os.getenv("RUFUS_TTS_PROVIDER", "openai"),
        "ELEVENLABS": "disabled",
    },
    "grok_primary_voice": os.getenv("GROK_TTS_VOICE_JAMIE", "ursa"),
    "grok_fallback_voice": os.getenv("GROK_TTS_VOICE_JAMIE_FALLBACK", "celeste"),
    "gemini_model": os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
    "openai_tts_model": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
    "installed": False,
    "patched": [],
    "calls": [],
    "fallbacks": [],
    "mood_distribution": {},
    "jamie_expression_distribution": {},
    "characters_by_speaker": {"ALEX": 0, "JAMIE": 0, "RUFUS": 0},
    "jamie_chars_requested": 0,
    "jamie_cache_hits": 0,
    "jamie_gemini_successes": 0,
    "jamie_gemini_failures": 0,
    "gemini_successes": 0,
    "openai_router_calls": 0,
    "openai_passthrough_calls": 0,
    "jamie_gemini_verified": False,
    "jamie_grok_successes": 0,
    "jamie_grok_episode_successes": 0,
    "jamie_grok_failures": 0,
    "jamie_grok_primary_successes": 0,
    "jamie_grok_fallback_successes": 0,
    "jamie_grok_cost_estimate_usd": 0.0,
    "jamie_primary_verified": False,
}


def _safe_print(msg: str) -> None:
    print(msg, flush=True)


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _write_report() -> None:
    STATS["jamie_gemini_verified"] = STATS["jamie_gemini_successes"] > 0
    STATS["jamie_primary_verified"] = (
        STATS.get("jamie_grok_successes", 0) > 0
        or STATS.get("jamie_gemini_successes", 0) > 0
    )
    STATS["total_characters_rendered"] = sum(
        int(value or 0) for value in STATS.get("characters_by_speaker", {}).values()
    )
    try:
        REPORT_PATH.write_text(json.dumps(STATS, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    except Exception:
        pass


# ----------------------------------------------------------------------------
# MOOD INFERENCE — the heart of v3.3. Deterministic, no LLM calls.
# The v3.3 writer writes these signals into the script on purpose.
# ----------------------------------------------------------------------------
NUMERIC_RE = re.compile(
    r"(?:\$|€|£)\s?\d[\d,.]*(?:\s?(?:million|billion|trillion|m|b))?"
    r"|\b\d+(?:\.\d+)?%\b|\b\d[\d,]*\b|\bQ[1-4]\b",
    re.IGNORECASE,
)
CONCESSION_RE = re.compile(
    r"\b(you'?re right|you are right|okay,? you'?ve got me|i was wrong|i'?ll give you that|"
    r"point taken|i concede|you'?ve convinced me|i'?ll grant (?:you|that)|alright,? you win|"
    r"fair, actually|i'?ll walk that back|i take it back|that changes my mind)\b",
    re.IGNORECASE,
)
PUSHBACK_RE = re.compile(
    r"\b(wait\.?|hold on|hang on|hold up|come on|no,|nope|i disagree|that'?s not|"
    r"that is not|let me stop you|i don'?t buy)\b", re.IGNORECASE,
)
AMUSED_RE = re.compile(
    r"\b(hah|ha[.!]|heh|funny|ridiculous|absurd|you'?re kidding|i love that|genuinely funny|"
    r"that'?s great|oh, that'?s)\b", re.IGNORECASE,
)
CONCERN_RE = re.compile(
    r"\b(scares?|scary|blamed?|lose (?:their|your|the)|patients?|workers?|families|"
    r"family|privacy|someone'?s (?:job|life|data)|real people|laid off|at risk)\b",
    re.IGNORECASE,
)
EXPLAINER_RE = re.compile(
    r"\b(in plain terms|the simple version|plain english|basically|what that (?:means|is)|"
    r"the normal[- ]person|put it this way|translate)\b", re.IGNORECASE,
)
PRESSURE_RE = re.compile(
    r"\b(who wins|who loses|who gets blamed|who is exposed|what changed|why should|"
    r"is this real|who decided|who owns)\b", re.IGNORECASE,
)
DRY_RE = re.compile(
    r"\b(lovely|quite|rather|of course|convenient|splendid|marvellous|how reassuring|"
    r"naturally|charming)\b", re.IGNORECASE,
)

MOODS = (
    "interruption", "concession", "pushback", "amused", "concern",
    "explainer", "pressure", "dry_wit", "neutral",
)


def infer_mood(text: str, speaker: str) -> str:
    """Classify one line into a debate mood. Priority order matters: the most
    delivery-defining signal wins."""
    raw = (text or "").strip()
    body = re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
    low = body.lower()
    spk = (speaker or "").strip().upper()
    if not body:
        return "neutral"
    # An explicit written laugh survives a following "wait"/challenge. Without
    # this, Jamie's best funny pushbacks were all flattened into one sharp mood.
    if spk == "JAMIE" and re.match(r"^(?:ha|hah|heh)[.!]", body, re.I):
        return "amused"

    # 1. Interruption — the line is cut off (or cuts in) on an em-dash.
    if body.endswith(("—", "–")) or body.startswith(("—", "–")):
        return "interruption"
    # 2. Concession — a host genuinely changes position.
    if CONCESSION_RE.search(low):
        return "concession"
    # 3. Pushback — live disagreement.
    if PUSHBACK_RE.search(low):
        return "pushback"
    # 4. Amused — something landed as absurd or funny.
    if AMUSED_RE.search(low):
        return "amused"
    # 5. Pressure — a pointed question. A question is interrogative delivery
    #    regardless of how weighty the topic is, so it outranks concern.
    if PRESSURE_RE.search(low) or (spk == "ALEX" and body.endswith("?")):
        return "pressure"
    # 6. Concern — real stakes for real people, stated (not asked).
    if CONCERN_RE.search(low):
        return "concern"
    # 7. Explainer — translating something, or dense with receipts.
    if EXPLAINER_RE.search(low) or len(NUMERIC_RE.findall(body)) >= 2:
        return "explainer"
    # 8. Dry wit — Rufus's understatement, or Rufus by default.
    if DRY_RE.search(low) or spk == "RUFUS":
        return "dry_wit"
    # 9. Neutral conversational.
    return "neutral"


# ----------------------------------------------------------------------------
# DIRECTION LIBRARY — how each mood should be performed.
# ----------------------------------------------------------------------------
PERSONA = {
    "ALEX": ("Alex — the host and engine of the room. Curious, blunt, high-agency, "
             "energetic. Keeps the debate moving and presses the question others avoid."),
    "JAMIE": ("Jamie — the comic catalyst and equal debating partner. Warm, sharp, funny, emotionally present. "
              "Translates jargon into plain English and makes the stakes land for "
              "normal listeners. Modern and real; never robotic, never valley-girl, "
              "Lead the earned laughs, occasional surprised guffaw and sotto-voce snicker; "
              "vary their intensity, then get straight back to the argument. Never a laugh track."),
    "RUFUS": ("Rufus — the dry British analyst. Calm, precise, quietly funny, "
              "unhurried. Tracks money, liability, and regulation. Understatement, "
              "never theatrics."),
}
PERSONA_SHORT = {
    "ALEX": "a blunt, energetic, curious podcast host",
    "JAMIE": "a warm, sharp, funny, emotionally present podcast co-host",
    "RUFUS": "a calm, dry, understated British analyst",
}

# mood -> (gemini director note, openai instruction overlay)
MOOD_DIRECTION = {
    "neutral": (
        "Natural conversational podcast pace. Engaged and in the moment, talking with "
        "people you can see — not reading an essay.",
        "Speak naturally and conversationally, engaged and in the moment.",
    ),
    "pressure": (
        "This is a pointed question. Lean in. Firm, probing, a little intensity — you "
        "want a real answer, not a dodge. A slight rising drive toward the question mark.",
        "Ask this as a pointed, probing question — firm and a little intense, pressing "
        "for a real answer.",
    ),
    "pushback": (
        "This is disagreement landing in real time. Quicker, sharper, a touch of "
        "friction. You are cutting in because you do not buy what was just said.",
        "Deliver this as live disagreement — quicker and sharper, cutting in, with a "
        "touch of friction.",
    ),
    "amused": (
        "Something just landed as absurd or funny. A real smile in the voice, light, a "
        "beat of genuine amusement — never a performed or canned laugh.",
        "Light and warm with a genuine smile in the voice — something here is absurd "
        "and you find it funny.",
    ),
    "concern": (
        "Real stakes for real people. Slow down. More weight, more sincerity. This is "
        "not abstract — someone's job, health, money, or privacy is on the line.",
        "Slower and weightier, sincere and a little grave — real people are exposed here.",
    ),
    "explainer": (
        "You are translating something technical into plain English. Slightly slower, "
        "clearer articulation, patient. Make it land on first listen.",
        "Slower and very clear, patient and articulate — explain this so anyone can "
        "follow it the first time.",
    ),
    "dry_wit": (
        "Dry, calm, understated British wit. Do not push the joke — let it sit flat. "
        "The humour is in the restraint and the timing, not the energy.",
        "Dry, calm and understated — deliver any irony flat, with restraint; let the "
        "wit sit rather than pushing it.",
    ),
    "concession": (
        "This is the moment you genuinely change your mind. Slow down. Lower the "
        "energy. Honest, a little reluctant, real — you are actually conceding the "
        "point, not being polite about it.",
        "Slower and lower-energy, honest and a little reluctant — you are genuinely "
        "conceding the point, not being polite.",
    ),
    "interruption": (
        "You are being cut off, or cutting in. Fast onset, clipped, urgent — the "
        "thought does not get to finish cleanly.",
        "Fast, clipped and urgent — this line is interrupted and does not finish "
        "cleanly.",
    ),
}


# ----------------------------------------------------------------------------
# Text sanitation
# ----------------------------------------------------------------------------
def _sanitize_spoken_text(text: str) -> str:
    """Strip the speaker label and ALL bracketed cues. The v3.3 writer already
    removes brackets; this is defence-in-depth for the fallback generator's
    output so no provider ever reads '[laughs]' aloud."""
    t = (text or "").strip()
    t = re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\[[^\]]*\]", "", t)            # remove every bracketed cue
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ----------------------------------------------------------------------------
# Direction builders
# ----------------------------------------------------------------------------
def _gemini_prompt(text: str, speaker: str, mood: str) -> str:
    transcript = _sanitize_spoken_text(text)
    spk = (speaker or "").strip().upper()
    persona = PERSONA.get(spk, PERSONA["JAMIE"])
    note = MOOD_DIRECTION.get(mood, MOOD_DIRECTION["neutral"])[0]
    return f"""Synthesize speech only. Speak only the exact words in the TRANSCRIPT
section. Do not read headings, labels, speaker names, brackets, markdown, or
quotation marks.

# VOICE
{persona}

# SCENE
A premium daily AI debate podcast, The AI Edge. Three hosts argue through the day's
biggest AI story. The room is fast and alive; you are responding in the moment.

# DIRECTION FOR THIS LINE  (mood: {mood})
{note}

# TRANSCRIPT
{transcript}
""".strip()


def _openai_instructions(speaker: str, mood: str) -> str:
    spk = (speaker or "").strip().upper()
    performance = {
        "ALEX": (
            "You are Alex, the high-agency lead host. Use confident, lived-in podcast "
            "timing: conversational swagger, varied pace, crisp pressure questions, and "
            "brief pauses before the consequence. Drive the room without sounding like "
            "a radio announcer or reading copy."
        ),
        "JAMIE": (
            "You are Jamie, a highly intelligent, opinionated female co-host. Be quick, "
            "warm, competitive, and emotionally alive. Be the trio's comic catalyst: "
            "an earned laugh, surprised guffaw, small snicker or sarcastic chuckle, "
            "with varied intensity. React to the other hosts and recover into the "
            "point quickly. No canned laugh after every line; keep sponsor copy clear."
        ),
        "RUFUS": (
            "You are Rufus, a precise British analyst. Keep a natural contemporary British "
            "accent and unhurried cadence, with clean emphasis on money, liability, and "
            "power. Land euphemisms and dry wit through restraint, never caricature."
        ),
    }.get(spk, f"You are {PERSONA_SHORT.get(spk, 'a podcast co-host')}.")
    overlay = MOOD_DIRECTION.get(mood, MOOD_DIRECTION["neutral"])[1]
    return (
        f"{performance} You are mid-conversation on a premium daily AI debate podcast. "
        f"{overlay} Sound responsive to the other two people in the room, not like a narrator."
    )


# ----------------------------------------------------------------------------
# Audio helpers
# ----------------------------------------------------------------------------
def _write_wave(filename: Path, pcm: bytes, channels: int = 1,
                rate: int = 24000, sample_width: int = 2) -> None:
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def _ffmpeg_wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libmp3lame",
         "-b:a", os.getenv("SEGMENT_EXPORT_BITRATE", "192k"), str(mp3_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _silence_mp3(out_path: Path, ms: int = 350) -> None:
    """Render a short silent clip so an empty line never crashes the stitcher."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r=24000:cl=mono:d={max(0.05, ms / 1000.0)}",
         "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


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


def _cache_key(text: str, speaker: str, voice: str, model: str, mood: str) -> str:
    raw = json.dumps(
        {"speaker": speaker, "voice": voice, "model": model, "mood": mood,
         "text": _sanitize_spoken_text(text)},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ----------------------------------------------------------------------------
# Gemini render path (generalised from v3.2's Jamie-only path)
# ----------------------------------------------------------------------------
_GEMINI_VOICE_ENV = {
    "ALEX": ("GEMINI_TTS_VOICE_ALEX", "Charon"),
    "JAMIE": ("GEMINI_TTS_VOICE_JAMIE", "Sulafat"),
    "RUFUS": ("GEMINI_TTS_VOICE_RUFUS", "Iapetus"),
}


def _gemini_tts_to_file(text: str, speaker: str, mood: str, out_path: Path) -> None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; cannot render with Gemini TTS")
    spk = (speaker or "").strip().upper()
    model = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview").strip()
    env_name, default_voice = _GEMINI_VOICE_ENV.get(spk, ("GEMINI_TTS_VOICE_JAMIE", "Sulafat"))
    voice = os.getenv(env_name, default_voice).strip()
    retries = max(1, int(os.getenv("GEMINI_TTS_MAX_RETRIES", "2")))
    use_cache = _bool_env("GEMINI_TTS_CACHE", "true")

    clean = _sanitize_spoken_text(text)
    if not clean:
        _silence_mp3(out_path)
        STATS["fallbacks"].append({"speaker": spk, "reason": "empty line -> silence"})
        _write_report()
        return

    if spk == "JAMIE":
        STATS["jamie_chars_requested"] += len(clean)

    cache_dir = CACHE_DIR / "gemini"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_cache_key(clean, spk, voice, model, mood)}.mp3"
    if use_cache and cache_file.exists() and cache_file.stat().st_size > 1000:
        shutil.copyfile(cache_file, out_path)
        if spk == "JAMIE":
            STATS["jamie_cache_hits"] += 1
        STATS["calls"].append({"speaker": spk, "provider": "gemini", "mood": mood,
                               "cache": True, "chars": len(clean)})
        _write_report()
        return

    prompt = _gemini_prompt(text, spk, mood)
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        wav_path = out_path.with_suffix(f".gemini_{attempt}.wav")
        try:
            from google import genai          # type: ignore
            from google.genai import types    # type: ignore
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
                STATS["gemini_successes"] += 1
                if spk == "JAMIE":
                    STATS["jamie_gemini_successes"] += 1
                STATS["calls"].append({"speaker": spk, "provider": "gemini", "mood": mood,
                                       "cache": False, "model": model, "voice": voice,
                                       "chars": len(clean), "attempt": attempt})
                _write_report()
                return
            raise RuntimeError("Gemini TTS MP3 output missing or too small")
        except Exception as e:
            last_err = e
            if spk == "JAMIE":
                STATS["jamie_gemini_failures"] += 1
            _safe_print(f"   ⚠️ Gemini TTS failed for {spk} attempt {attempt}/{retries}: {e}")
            time.sleep(min(6, 1.5 * attempt))
        finally:
            try:
                if wav_path.exists():
                    wav_path.unlink()
            except Exception:
                pass
    raise RuntimeError(f"Gemini TTS failed for {spk} after {retries} attempts: {last_err}")


# ----------------------------------------------------------------------------
# OpenAI render path — router-owned, so Alex/Rufus get per-line direction
# ----------------------------------------------------------------------------
_OPENAI_VOICE_ENV = {
    "ALEX": ("OPENAI_TTS_VOICE_ALEX", "onyx"),
    "JAMIE": ("OPENAI_TTS_VOICE_JAMIE", "marin"),
    "RUFUS": ("OPENAI_TTS_VOICE_RUFUS", "fable"),
}
_OPENAI_MODEL_ENV = {
    "ALEX": "VOICE_MODEL_ALEX",
    "JAMIE": "VOICE_MODEL_JAMIE",
    "RUFUS": "VOICE_MODEL_RUFUS",
}


def _openai_tts_to_file(text: str, speaker: str, mood: str, out_path: Path) -> None:
    client = _RT.get("openai_client")
    if client is None:
        raise RuntimeError("No OpenAI client available for router-owned OpenAI TTS")
    spk = (speaker or "").strip().upper()
    fallback_model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip()
    model_env = _OPENAI_MODEL_ENV.get(spk, "OPENAI_TTS_MODEL")
    model = os.getenv(model_env, fallback_model).strip()
    env_name, default_voice = _OPENAI_VOICE_ENV.get(spk, ("OPENAI_TTS_VOICE_ALEX", "onyx"))
    voice = os.getenv(env_name, default_voice).strip()

    clean = _sanitize_spoken_text(text)
    if not clean:
        _silence_mp3(out_path)
        STATS["fallbacks"].append({"speaker": spk, "reason": "empty line -> silence"})
        _write_report()
        return

    instructions = _openai_instructions(spk, mood)
    base = dict(model=model, voice=voice, input=clean, response_format="mp3")

    # The recovered Alex/Rufus voices use tts-1-hd, whose inherent character is
    # stronger than per-line prompting. Only instruction-capable models get the
    # mood overlay; this avoids an extra rejected request on every legacy-HD line.
    candidates = (
        ({**base, "instructions": instructions}, base)
        if model.startswith("gpt-4o")
        else (base,)
    )
    for kwargs in candidates:
        try:
            try:
                with client.audio.speech.with_streaming_response.create(**kwargs) as resp:
                    resp.stream_to_file(str(out_path))
            except AttributeError:
                resp = client.audio.speech.create(**kwargs)
                content = getattr(resp, "content", None)
                if content:
                    out_path.write_bytes(content)
                else:
                    resp.stream_to_file(str(out_path))  # legacy SDK
            if out_path.exists() and out_path.stat().st_size > 1000:
                STATS["openai_router_calls"] += 1
                STATS["characters_by_speaker"][spk] = (
                    int(STATS["characters_by_speaker"].get(spk) or 0) + len(clean)
                )
                STATS["calls"].append({
                    "speaker": spk, "provider": "openai_router", "mood": mood,
                    "model": model, "voice": voice, "chars": len(clean),
                    "directed": "instructions" in kwargs,
                })
                _write_report()
                return
            raise RuntimeError("OpenAI TTS output missing or too small")
        except Exception as e:
            last_err = e  # noqa: F841 — retried without instructions, then raised
            continue
    raise RuntimeError(f"Router-owned OpenAI TTS failed for {spk}")


# ----------------------------------------------------------------------------
# Routing
# ----------------------------------------------------------------------------
def _provider_for(speaker: str) -> str:
    spk = (speaker or "").strip().upper()
    return {
        "ALEX": os.getenv("ALEX_TTS_PROVIDER", "openai"),
        "JAMIE": os.getenv("JAMIE_TTS_PROVIDER", "grok"),
        "RUFUS": os.getenv("RUFUS_TTS_PROVIDER", "openai"),
    }.get(spk, "openai").strip().lower()


def _note_mood(mood: str) -> None:
    STATS["mood_distribution"][mood] = STATS["mood_distribution"].get(mood, 0) + 1


def route_text_to_file(text: str, speaker: str, out_path: Path) -> None:
    """Infer mood, route each host, and record every fallback and cost."""
    spk = (speaker or "").strip().upper()
    out = Path(out_path)
    mood = infer_mood(text, spk)
    _note_mood(mood)
    provider = _provider_for(spk)

    # 1. Jamie on Grok: Ursa primary, Celeste automatic voice fallback.
    if provider == "grok":
        try:
            from grok_tts_v4 import render_jamie as _render_grok_jamie

            result = _render_grok_jamie(text, mood, out)
            for expression in result.get("expressions") or []:
                counts = STATS["jamie_expression_distribution"]
                counts[expression] = int(counts.get(expression) or 0) + 1
            STATS["jamie_chars_requested"] += int(result.get("characters") or 0)
            STATS["characters_by_speaker"][spk] = (
                int(STATS["characters_by_speaker"].get(spk) or 0)
                + int(result.get("characters") or 0)
            )
            STATS["jamie_grok_successes"] += 1
            STATS["jamie_grok_episode_successes"] += 1
            if result.get("primary_voice"):
                STATS["jamie_grok_primary_successes"] += 1
            else:
                STATS["jamie_grok_fallback_successes"] += 1
                STATS["fallbacks"].append({
                    "speaker": spk, "mood": mood,
                    "from": os.getenv("GROK_TTS_VOICE_JAMIE", "ursa"),
                    "to": result.get("voice", "celeste"),
                    "reason": "Grok primary voice failed; approved voice fallback used",
                })
            STATS["jamie_grok_cost_estimate_usd"] = round(
                float(STATS.get("jamie_grok_cost_estimate_usd") or 0.0)
                + float(result.get("estimated_cost_usd") or 0.0),
                6,
            )
            STATS["calls"].append({
                "speaker": spk,
                "provider": "grok",
                "voice": result.get("voice"),
                "primary_voice": bool(result.get("primary_voice")),
                "mood": mood,
                "cache": bool(result.get("cache")),
                "expressions": list(result.get("expressions") or []),
                "chars": int(result.get("characters") or 0),
                "estimated_cost_usd": float(result.get("estimated_cost_usd") or 0.0),
            })
            _write_report()
            return
        except Exception as e:
            STATS["jamie_grok_failures"] += 1
            STATS["fallbacks"].append({
                "speaker": spk, "mood": mood,
                "from": "grok_ursa_celeste", "to": "openai",
                "reason": str(e)[:500],
            })
            _write_report()
            _safe_print(f"   ⚠️ {spk}: Grok Ursa/Celeste failed, falling back to OpenAI — {e}")

    # 2. Gemini remains available as an explicit emergency route.
    if provider == "gemini":
        try:
            _gemini_tts_to_file(text, spk, mood, out)
            return
        except Exception as e:
            STATS["fallbacks"].append({"speaker": spk, "mood": mood,
                                       "from": "gemini", "to": "openai",
                                       "reason": str(e)[:400]})
            _write_report()
            _safe_print(f"   ⚠️ {spk}: Gemini failed, falling back to OpenAI — {e}")

    # 3. Router-owned OpenAI path for Alex/Rufus and final Jamie fallback.
    if _bool_env("ROUTER_OWN_OPENAI", "true"):
        try:
            _openai_tts_to_file(text, spk, mood, out)
            return
        except Exception as e:
            STATS["fallbacks"].append({"speaker": spk, "mood": mood,
                                       "from": "openai_router", "to": "passthrough",
                                       "reason": str(e)[:400]})
            _write_report()
            _safe_print(f"   ⚠️ {spk}: router OpenAI failed, using main.py path — {e}")

    # 4. Last-resort pass-through to the proven production spine.
    original = _RT.get("original_tts")
    if callable(original):
        STATS["openai_passthrough_calls"] += 1
        STATS["characters_by_speaker"][spk] = (
            int(STATS["characters_by_speaker"].get(spk) or 0)
            + len(_sanitize_spoken_text(text))
        )
        STATS["calls"].append({"speaker": spk, "provider": "openai_passthrough",
                               "mood": mood, "chars": len(_sanitize_spoken_text(text))})
        _write_report()
        original(text, speaker, out)
        return
    raise RuntimeError(f"No TTS path succeeded for {spk} and no passthrough available")


# ----------------------------------------------------------------------------
# SMOKE TEST — prove Jamie's Gemini voice works BEFORE a full episode is paid for.
# v3_1_runner.py calls this when REQUIRE_GEMINI_JAMIE=true.
# ----------------------------------------------------------------------------
def smoke_test_jamie_voice(out_path: Any) -> None:
    """Prove Jamie's configured primary provider before full-episode spend."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    provider = _provider_for("JAMIE")
    line = (
        "JAMIE: Okay, quick voice check. If the boys are going to call risk "
        "an efficiency gain, somebody in this room has to read the fine print."
    )
    mood = "amused"
    _safe_print(f"   🎙️  Jamie {provider} smoke test (mood: {mood}) ...")

    if provider == "grok":
        from grok_tts_v4 import smoke_test as _smoke_test_grok

        result = _smoke_test_grok(out)
        STATS["jamie_grok_successes"] += 1
        STATS["jamie_grok_primary_successes"] += 1
        STATS["jamie_chars_requested"] += int(result.get("characters") or 0)
        STATS["jamie_grok_cost_estimate_usd"] = round(
            float(STATS.get("jamie_grok_cost_estimate_usd") or 0.0)
            + float(result.get("estimated_cost_usd") or 0.0),
            6,
        )
        STATS["calls"].append({
            "speaker": "JAMIE", "provider": "grok_smoke",
            "voice": result.get("voice"), "primary_voice": True,
            "mood": mood, "chars": int(result.get("characters") or 0),
        })
    elif provider == "gemini":
        _gemini_tts_to_file(line, "JAMIE", mood, out)
    else:
        raise RuntimeError(f"Jamie smoke test requires Grok or Gemini, got {provider!r}")

    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"Jamie {provider} smoke test produced no usable MP3")
    STATS["jamie_primary_smoke_test"] = {
        "passed": True, "provider": provider,
        "voice": os.getenv("GROK_TTS_VOICE_JAMIE", "ursa") if provider == "grok" else
                 os.getenv("GEMINI_TTS_VOICE_JAMIE", "Sulafat"),
        "path": str(out), "bytes": out.stat().st_size,
    }
    _write_report()
    _safe_print(f"   ✅ Jamie {provider} smoke test passed -> {out}")


# ----------------------------------------------------------------------------
# INSTALLER — entry point, called by main.py. Signature unchanged.
# ----------------------------------------------------------------------------
def install(g: Dict[str, Any]) -> None:
    """Install mood-aware hybrid TTS routing into main.py's globals dictionary."""
    original_tts_to_file = g.get("tts_to_file")
    if not callable(original_tts_to_file):
        raise RuntimeError("hybrid_tts_router_v3_3 could not find main.py tts_to_file() to wrap")

    _RT["original_tts"] = original_tts_to_file
    _RT["openai_client"] = g.get("openai_client")
    if _RT["openai_client"] is None:
        # Build one if main.py did not expose a client.
        try:
            from openai import OpenAI
            if os.getenv("OPENAI_API_KEY", "").strip():
                _RT["openai_client"] = OpenAI()
        except Exception:
            _RT["openai_client"] = None

    original_render_spoken = g.get("_render_spoken_chunk_to_file")
    original_backend = g.get("_speaker_audio_backend")

    # Keep main.py off ElevenLabs scene rendering.
    os.environ["AUDIO_BACKEND"] = "openai"
    os.environ["ELEVENLABS_ENABLED"] = "false"
    os.environ["ELEVEN_USE_DIALOGUE_SCENES"] = "false"
    os.environ.setdefault("ALEX_TTS_PROVIDER", "openai")
    os.environ.setdefault("JAMIE_TTS_PROVIDER", "grok")
    os.environ.setdefault("RUFUS_TTS_PROVIDER", "openai")
    os.environ.setdefault("ROUTER_OWN_OPENAI", "true")
    os.environ.setdefault("GROK_TTS_VOICE_JAMIE", "ursa")
    os.environ.setdefault("GROK_TTS_VOICE_JAMIE_FALLBACK", "celeste")
    os.environ.setdefault("GROK_TTS_MAX_RETRIES", "2")
    os.environ.setdefault("GROK_TTS_CACHE", "true")
    os.environ.setdefault("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    os.environ.setdefault("GEMINI_TTS_VOICE_JAMIE", "Sulafat")
    os.environ.setdefault("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    os.environ.setdefault("GEMINI_TTS_MAX_RETRIES", "2")
    os.environ.setdefault("GEMINI_TTS_CACHE", "true")

    g["AUDIO_BACKEND"] = "openai"
    if "ELEVEN_USE_DIALOGUE_SCENES" in g:
        g["ELEVEN_USE_DIALOGUE_SCENES"] = False

    def hybrid_tts_to_file(text: str, speaker: str, out_path: Path) -> None:
        return route_text_to_file(text, speaker, Path(out_path))

    def hybrid_render_spoken_chunk_to_file(text: str, speaker: str, out_path: Path) -> None:
        return route_text_to_file(text, speaker, Path(out_path))

    def hybrid_speaker_audio_backend(speaker: str) -> str:
        spk = (speaker or "").strip().upper()
        if spk in {"ALEX", "JAMIE", "RUFUS"}:
            return "openai"   # prevents ElevenLabs dialogue-scene bundling
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

    STATS["routing"] = {
        "ALEX": _provider_for("ALEX"),
        "JAMIE": _provider_for("JAMIE"),
        "RUFUS": _provider_for("RUFUS"),
        "ELEVENLABS": "disabled",
    }
    STATS["installed"] = True
    STATS["router_owned_openai"] = _bool_env("ROUTER_OWN_OPENAI", "true")
    STATS["openai_client_available"] = _RT["openai_client"] is not None
    _write_report()
    _safe_print(">> ✅ Installed mood-aware hybrid TTS router v3.3 — "
                f"Alex={STATS['routing']['ALEX']}, Jamie={STATS['routing']['JAMIE']}, "
                f"Rufus={STATS['routing']['RUFUS']}, ElevenLabs=OFF")
    g["V3_3_MOOD_TTS_ROUTER_INSTALLED"] = True


# ----------------------------------------------------------------------------
# NOTE ON A GENUINELY BRITISH RUFUS
# ----------------------------------------------------------------------------
# The directed OpenAI path now explicitly preserves Rufus's contemporary British
# delivery. Gemini remains an opt-in audition path, but it is not placed in the
# autonomous production chain until a by-ear episode test proves continuity.
