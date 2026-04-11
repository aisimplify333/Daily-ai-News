# -*- coding: utf-8 -*-
"""
Daily AI News: "The AI Edge" (fully automated)

Production upgrades (Jan 2026) — listener-first producer package:
- Guaranteed audible INTRO STINGER after cold open [MUSIC] marker (cannot be skipped by ducking)
- Optional INTRO BED ducked under first spoken chunk after intro marker
- Clean, deterministic audio assembly loop (prevents indentation / duplicate-loop bugs)
- SAVE_SCRIPT support (script_YYYY-MM-DD.txt) when SAVE_SCRIPT=true

Paste this entire file as main.py.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

from growth_engine import (
    MODEL_VERSION,
    apply_sponsor_variant,
    attach_story_scores,
    build_episode_tracking_payload,
    build_story_debug_table,
    choose_episode_experiments,
    load_show_memory,
    select_story_candidates,
)

# ----------------------------
# ENV
# ----------------------------
load_dotenv()

# ----------------------------
# CONFIG (RSS identity)
# ----------------------------
RSS_SETTINGS: Dict[str, str] = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily AI News Drama: raw, human, high-stakes conversations about the future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
}

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)

TMP_AUDIO_DIR = BASE_DIR / "_tmp_audio"
TMP_AUDIO_DIR.mkdir(exist_ok=True)

FEED_XML_PATH = BASE_DIR / "feed.xml"
SPONSORS_PATH = BASE_DIR / "sponsors.json"
STORY_SCORES_PATH = BASE_DIR / "story_scores.json"
TRACKING_SUMMARY_PATH = BASE_DIR / "tracking_summary.json"
FORWARDABLE_MOMENTS_PATH = BASE_DIR / "forwardable_moments.json"

AUDIO_BRANDKIT_DIR = BASE_DIR / "audio_brandkit"
BRANDKIT_SFX_DIR = AUDIO_BRANDKIT_DIR / "sfx"
BRANDKIT_BEDS_DIR = AUDIO_BRANDKIT_DIR / "beds"
AUDIO_BRANDKIT_MANIFEST = AUDIO_BRANDKIT_DIR / "manifest.json"
for _p in [AUDIO_BRANDKIT_DIR, BRANDKIT_SFX_DIR, BRANDKIT_BEDS_DIR]:
    _p.mkdir(parents=True, exist_ok=True)

THELEDGR_SUBSCRIBE_URL = "https://theledgr.io"
THELEDGR_SPOKEN_URL = "T-H-E-L-E-D-G-R dot I-O"
THELEDGR_DEFAULT_SPONSORS: List[Dict[str, str]] = [
    {
        "name": "TheLEDGR",
        "tagline": "Daily AI intelligence that helps you make better decisions in real life.",
        "cta": "If AI affects your work, you should already be subscribed. TheLEDGR helps you cut through noise, stay ahead, and walk into your day sharper. Subscribe at T-H-E-L-E-D-G-R dot I-O.",
    },
    {
        "name": "TheLEDGR",
        "tagline": "Five daily AI briefings across strategy, tools, health AI, enterprise agents, and code.",
        "cta": "This is not more AI noise. It is signal you can actually use in real life. Subscribe now at T-H-E-L-E-D-G-R dot I-O.",
    },
    {
        "name": "TheLEDGR",
        "tagline": "Built for serious people who need AI signal, not hype.",
        "cta": "TheLEDGR helps you make better decisions faster, avoid bad calls, and not be the last person in the room to know. Subscribe at T-H-E-L-E-D-G-R dot I-O.",
    },
]

AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/",
).rstrip("/") + "/"

LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/",
).rstrip("/") + "/"

PUBLIC_SUBSCRIBE_URL = os.getenv(
    "PUBLIC_SUBSCRIBE_URL",
    "https://theledgr.io?utm_source=podcast",
).strip()

PRIMARY_LLM = os.getenv("PRIMARY_LLM", "openai").strip().lower()  # gemini | openai
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")

AUDIO_BACKEND = os.getenv("AUDIO_BACKEND", "eleven").strip().lower()  # openai | eleven
ELEVEN_API_KEY = (os.getenv("AI_EDGE_PODCAST_ELEVENLABS", "") or os.getenv("ELEVENLABS_API_KEY", "")).strip()
ELEVEN_OUTPUT_FORMAT = os.getenv("ELEVEN_OUTPUT_FORMAT", "mp3_44100_128").strip()
ELEVEN_MODEL_ALEX = os.getenv("ELEVEN_MODEL_ALEX", "eleven_v3").strip()
ELEVEN_MODEL_JAMIE = os.getenv("ELEVEN_MODEL_JAMIE", "eleven_v3").strip()
ELEVEN_MODEL_RUFUS = os.getenv("ELEVEN_MODEL_RUFUS", "eleven_v3").strip()
ELEVEN_VOICE_ID_ALEX = os.getenv("ELEVEN_VOICE_ID_ALEX", "vDchjyOZZytffNeZXfZK").strip()
ELEVEN_VOICE_ID_JAMIE = os.getenv("ELEVEN_VOICE_ID_JAMIE", "kdnRe2koJdOK4Ovxn2DI").strip()
ELEVEN_VOICE_ID_RUFUS = os.getenv("ELEVEN_VOICE_ID_RUFUS", "Fahco4VZzobUeiPqni1S").strip()
ELEVEN_STABILITY_ALEX = float(os.getenv("ELEVEN_STABILITY_ALEX", "0.38"))
ELEVEN_STABILITY_JAMIE = float(os.getenv("ELEVEN_STABILITY_JAMIE", "0.34"))
ELEVEN_STABILITY_RUFUS = float(os.getenv("ELEVEN_STABILITY_RUFUS", "0.40"))
ELEVEN_SIMILARITY_ALEX = float(os.getenv("ELEVEN_SIMILARITY_ALEX", "0.82"))
ELEVEN_SIMILARITY_JAMIE = float(os.getenv("ELEVEN_SIMILARITY_JAMIE", "0.80"))
ELEVEN_SIMILARITY_RUFUS = float(os.getenv("ELEVEN_SIMILARITY_RUFUS", "0.84"))
ELEVEN_STYLE_ALEX = float(os.getenv("ELEVEN_STYLE_ALEX", "0.28"))
ELEVEN_STYLE_JAMIE = float(os.getenv("ELEVEN_STYLE_JAMIE", "0.33"))
ELEVEN_STYLE_RUFUS = float(os.getenv("ELEVEN_STYLE_RUFUS", "0.24"))
ELEVEN_USE_SPEAKER_BOOST = os.getenv("ELEVEN_USE_SPEAKER_BOOST", "true").strip().lower() in ("1","true","yes")
AUTO_BUILD_AUDIO_BRANDKIT = os.getenv("AUTO_BUILD_AUDIO_BRANDKIT", "true").strip().lower() in ("1","true","yes")
REBUILD_AUDIO_BRANDKIT = os.getenv("REBUILD_AUDIO_BRANDKIT", "false").strip().lower() in ("1","true","yes")
ELEVEN_USE_DIALOGUE_SCENES = os.getenv("ELEVEN_USE_DIALOGUE_SCENES", "true").strip().lower() in ("1","true","yes")
ELEVEN_SCENE_MAX_TURNS = int(os.getenv("ELEVEN_SCENE_MAX_TURNS", "6"))
ELEVEN_SCENE_MAX_CHARS = int(os.getenv("ELEVEN_SCENE_MAX_CHARS", "1200"))
ELEVEN_SCENE_PAUSE_MS = int(os.getenv("ELEVEN_SCENE_PAUSE_MS", "140"))

# Episode length gates (minutes)
MIN_MINUTES = float(os.getenv("MIN_MINUTES", "19"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "24"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "22"))

# Script pacing (WPM)
WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "175"))
SEGMENT_ATTEMPTS = int(os.getenv("SEGMENT_ATTEMPTS", "5"))

SCRIPT_MAX_TOKENS = int(os.getenv("SCRIPT_MAX_TOKENS", "2200"))
JSON_MAX_TOKENS = int(os.getenv("JSON_MAX_TOKENS", "1800"))

CLEANUP_TEMP = os.getenv("CLEANUP_TEMP", "true").strip().lower() in ("1", "true", "yes")
KEEP_LAST_EPISODES = int(os.getenv("KEEP_LAST_EPISODES", "60"))

RUN_MARKETING_ASSETS = os.getenv("RUN_MARKETING_ASSETS", "true").strip().lower() in ("1", "true", "yes")
PUBLISH_SOCIAL = os.getenv("PUBLISH_SOCIAL", "false").strip().lower() in ("1", "true", "yes")

SAVE_SCRIPT = os.getenv("SAVE_SCRIPT", "false").strip().lower() in ("1", "true", "yes")

# Idempotency
FORCE_REBUILD = os.getenv("FORCE_REBUILD", "false").strip().lower() in ("1", "true", "yes")

# Voices
# OpenAI fallback voice routing. Option B uses ElevenLabs as the primary performance layer.
VOICE_MODEL_MAP: Dict[str, str] = {
    "ALEX": os.getenv("VOICE_MODEL_ALEX", "tts-1-hd"),
    "JAMIE": os.getenv("VOICE_MODEL_JAMIE", "gpt-4o-mini-tts"),
    "RUFUS": os.getenv("VOICE_MODEL_RUFUS", "tts-1-hd"),
}

VOICE_MAP: Dict[str, str] = {
    "ALEX": os.getenv("VOICE_ALEX", "onyx"),
    "JAMIE": os.getenv("VOICE_JAMIE", "marin"),
    "RUFUS": os.getenv("VOICE_RUFUS", "fable"),
}

VOICE_INSTRUCTIONS: Dict[str, str] = {
    "ALEX": (
        "Sound like a high-agency host with bigger emotional contrast and sharper pacing. "
        "He should not sound flat or evenly pleasant. He needs real swings: skeptical, excited, amused, urgent, annoyed, impressed. "
        "He should tee up tension, step on the gas when a stat lands, and sound like he actually cares about the consequence. "
        "Use short bursts, sharper emphasis, quick resets, and real host energy. Never sleepy, never monotone, never polished like a generic narrator."
    ),
    "JAMIE": (
        "Sound like a sharp, emotionally intelligent woman in her mid-20s who is part co-host, part color commentator, and part human conscience. "
        "She is not an announcer and never sounds like she is reading copy. She is in the conversation. "
        "She reacts quickly to Alex, cuts in naturally, teases him lightly, and pushes back when Rufus gets too cold, cynical, or detached. "
        "Her emotional range should be wide and clearly different from the others: amused, incredulous, warm, offended, delighted, worried, stunned. "
        "Use light laughs, breathy disbelief, quick pivots, and interruption energy when it fits. "
        "Keep it human, emotionally responsive, and never level or sleepy for too long."
    ),
    "RUFUS": (
        "Sound like a dry British analyst with stronger contrast and sharper emotional edges than before. "
        "He should sound cool, wry, skeptical, and occasionally wickedly amused, but when the numbers get serious he should tighten and sound genuinely dangerous or impressed. "
        "He is not monotone. Use dry undercuts, clipped emphasis, and a low simmer of disbelief when institutions behave absurdly. "
        "Never sound sleepy, evenly pleasant, or like a neutral explainer."
    ),
}

# TTS tuning
TTS_MERGE_MAX_CHARS = int(os.getenv("TTS_MERGE_MAX_CHARS", "2400"))
TTS_CHUNK_MAX_CHARS = int(os.getenv("TTS_CHUNK_MAX_CHARS", "2800"))
JAMIE_TTS_MERGE_MAX_CHARS = int(os.getenv("JAMIE_TTS_MERGE_MAX_CHARS", "900"))
JAMIE_TTS_CHUNK_MAX_CHARS = int(os.getenv("JAMIE_TTS_CHUNK_MAX_CHARS", "1100"))
TTS_RETRIES = int(os.getenv("TTS_RETRIES", "3"))

# Stitching
STITCH_METHOD = os.getenv("STITCH_METHOD", "pydub").strip().lower()  # pydub | ffmpeg

ALEX_SPEED = float(os.getenv("ALEX_SPEED", "1.03"))
JAMIE_SPEED = float(os.getenv("JAMIE_SPEED", "1.08"))
RUFUS_SPEED = float(os.getenv("RUFUS_SPEED", "0.97"))

# Post-processing thresholds
TRIM_LEADING_MS = int(os.getenv("TRIM_LEADING_MS", "60"))
TRIM_TRAILING_MS = int(os.getenv("TRIM_TRAILING_MS", "140"))
TRIM_THRESH_DB = float(os.getenv("TRIM_THRESH_DB", "-45.0"))
SEGMENT_EXPORT_BITRATE = os.getenv("SEGMENT_EXPORT_BITRATE", "192k")

# Music assets
INTRO_PATH = BASE_DIR / "intro.mp3"
OUTRO_PATH = BASE_DIR / "outro.mp3"
TRANSITION_PATH = BASE_DIR / "transition.mp3"

REQUIRE_INTRO_OUTRO = os.getenv("REQUIRE_INTRO_OUTRO", "true").strip().lower() in ("1", "true", "yes")
REQUIRE_TRANSITIONS = os.getenv("REQUIRE_TRANSITIONS", "true").strip().lower() in ("1", "true", "yes")
TRANSITION_EVERY_SEGMENT = os.getenv("TRANSITION_EVERY_SEGMENT", "true").strip().lower() in ("1", "true", "yes")
TRANSITION_MAX_PER_EPISODE = int(os.getenv("TRANSITION_MAX_PER_EPISODE", "4"))
TRANSITION_SEGMENTS = {int(x) for x in os.getenv("TRANSITION_SEGMENTS", "2,3,4,5").split(",") if x.strip().isdigit()}

# Stinger durations / levels
INTRO_STINGER_MS = int(os.getenv("INTRO_STINGER_MS", "4500"))      # audible bumper (no voice)
INTRO_BED_MS = int(os.getenv("INTRO_BED_MS", "6500"))              # bed under first host line
INTRO_BED_FADE_OUT_MS = int(os.getenv("INTRO_BED_FADE_OUT_MS", "1800"))
SEGMENT_BED_MS = int(os.getenv("SEGMENT_BED_MS", "3400"))
SEGMENT_BED_FADE_OUT_MS = int(os.getenv("SEGMENT_BED_FADE_OUT_MS", "1200"))

OUTRO_MS = int(os.getenv("OUTRO_MS", "12000"))
TRANSITION_MS = int(os.getenv("TRANSITION_MS", "2500"))

STINGER_TARGET_DBFS = float(os.getenv("STINGER_TARGET_DBFS", "-18.0"))

INTRO_FADE_IN_MS = int(os.getenv("INTRO_FADE_IN_MS", "120"))
INTRO_FADE_OUT_MS = int(os.getenv("INTRO_FADE_OUT_MS", "900"))

OUTRO_FADE_IN_MS = int(os.getenv("OUTRO_FADE_IN_MS", "800"))
OUTRO_FADE_OUT_MS = int(os.getenv("OUTRO_FADE_OUT_MS", "1200"))

TRANSITION_FADE_IN_MS = int(os.getenv("TRANSITION_FADE_IN_MS", "120"))
TRANSITION_FADE_OUT_MS = int(os.getenv("TRANSITION_FADE_OUT_MS", "350"))

CROSSFADE_MS = int(os.getenv("CROSSFADE_MS", "0"))  # 40–80 if desired

# Ducking parameters
MUSIC_TARGET_DBFS = float(os.getenv("MUSIC_TARGET_DBFS", "-25.0"))
DUCK_THRESHOLD_DBFS = float(os.getenv("DUCK_THRESHOLD_DBFS", "-34.0"))
DUCK_AMOUNT_DB = float(os.getenv("DUCK_AMOUNT_DB", "12.0"))
DUCK_WINDOW_MS = int(os.getenv("DUCK_WINDOW_MS", "40"))

# ----------------------------
# QUALITY GATES
# ----------------------------
MIN_COLD_OPEN_LINES = int(os.getenv("MIN_COLD_OPEN_LINES", "6"))
MIN_DIGITS_PER_SEGMENT = int(os.getenv("MIN_DIGITS_PER_SEGMENT", "12"))
MIN_DIGITS_PER_EPISODE = int(os.getenv("MIN_DIGITS_PER_EPISODE", "85"))
MIN_NUMERIC_BULLETS_PER_STORY = int(os.getenv("MIN_NUMERIC_BULLETS_PER_STORY", "2"))
FORWARDABLE_MIN_PER_EPISODE = int(os.getenv("FORWARDABLE_MIN_PER_EPISODE", "2"))
FORWARDABLE_PAUSE_MS = int(os.getenv("FORWARDABLE_PAUSE_MS", "240"))

STRICT_EPISODE_FILENAME_RE = re.compile(r"^podcast_\d{4}-\d{2}-\d{2}\.mp3$")
EARLY_SIGNOFF_RE = re.compile(
    r"\b("
    r"see you tomorrow|see you next time|that's the show|that's all for today|"
    r"thanks for listening|until tomorrow|until next time|we'll be back tomorrow|"
    r"good night|signing off|that does it for us|before we go|final thought|that wraps it up"
    r")\b",
    re.IGNORECASE,
)

MONEY_RE = re.compile(r"(\$|€|£)\s?\d")
NUMERIC_TOKEN_RE = re.compile(r"(\d+(\.\d+)?%|\$?\d[\d,]*(\.\d+)?|\b\d{4}\b|\bQ[1-4]\b)", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)

MIN_MP3_BYTES_FEED = int(os.getenv("MIN_MP3_BYTES_FEED", "200000"))
EPISODE_META_MAX_TITLE = int(os.getenv("EPISODE_META_MAX_TITLE", "110"))

# Virality heuristics
VIRAL_KEYWORDS = [
    "leak", "leaked", "whistleblower", "lawsuit", "sues", "ban", "banned", "crackdown", "investigation",
    "antitrust", "fraud", "hack", "breach", "ransomware", "exploit", "backdoor", "spy", "surveillance",
    "layoffs", "fired", "strike", "walkout", "shutdown", "collapse", "panic", "boycott",
    "copycat", "stolen", "copyright", "plagiarism", "deepfake", "election", "misinformation",
    "warning", "urgent", "emergency", "death", "injury", "safety", "weapon", "military",
]
VIRAL_BRANDS = [
    "openai", "anthropic", "nvidia", "microsoft", "google", "deepmind", "meta", "apple",
    "tesla", "amazon", "tiktok", "bytedance", "x", "twitter", "samsung", "intel",
]

FORWARDABLE_HINTS = {
    "why", "because", "means", "consequence", "tomorrow", "next", "market", "security",
    "regulation", "chip", "gpu", "enterprise", "career", "nobody", "everyone", "wins",
    "loses", "caught", "ban", "breaks", "risk", "signal", "pricing", "power",
}

FORWARDABLE_CONSEQUENCE_HINTS = {
    "because", "means", "therefore", "next", "tomorrow", "risk", "consequence", "pressure",
    "security", "regulation", "lawsuit", "exposed", "revealed", "changes", "shift", "power",
    "supply chain", "pricing", "margin", "care", "diagnosis", "agent", "code", "developers",
}

FORWARDABLE_SHOCK_HINTS = {
    "accidentally", "leak", "leaked", "ban", "banned", "caught", "breaks", "fails", "wrong",
    "panic", "warning", "stolen", "exposed", "harder", "monopoly", "vulnerable", "unsafe",
}

MAJOR_HASHTAG_ALLOWLIST = {
    "openai": "#OpenAI", "anthropic": "#Anthropic", "claude": "#Claude", "google": "#Google",
    "gemini": "#Gemini", "meta": "#Meta", "microsoft": "#Microsoft", "nvidia": "#NVIDIA",
    "cursor": "#Cursor", "copilot": "#Copilot", "health": "#HealthAI", "healthcare": "#HealthAI",
    "agents": "#AIAgents", "agent": "#AIAgents", "code": "#AICode", "coding": "#AICode",
    "tools": "#AITools", "security": "#AISecurity",
}

# ----------------------------
# LLM CLIENTS
# ----------------------------
openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not openai_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in GitHub Secrets / env.")
openai_client = OpenAI(api_key=openai_key)

gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
gemini_client = None
genai_types = None
if gemini_key:
    try:
        from google import genai as genai_new  # type: ignore
        from google.genai import types as genai_types  # type: ignore
        gemini_client = genai_new.Client(api_key=gemini_key)
    except Exception:
        gemini_client = None
        genai_types = None


# ----------------------------
# HELPERS
# ----------------------------
def _safe_print(msg: str) -> None:
    print(msg, flush=True)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(cmd: List[str], fail_ok: bool = False) -> int:
    try:
        subprocess.run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError as e:
        if fail_ok:
            return e.returncode
        raise


def _require_intro_outro_if_needed() -> None:
    if REQUIRE_INTRO_OUTRO and not INTRO_PATH.exists():
        raise RuntimeError("intro.mp3 missing. REQUIRE_INTRO_OUTRO=true requires intro.mp3.")
    if REQUIRE_INTRO_OUTRO and not OUTRO_PATH.exists():
        raise RuntimeError("outro.mp3 missing. REQUIRE_INTRO_OUTRO=true requires outro.mp3.")
    if REQUIRE_TRANSITIONS and not TRANSITION_PATH.exists():
        raise RuntimeError("transition.mp3 missing. REQUIRE_TRANSITIONS=true requires transition.mp3.")


# ----------------------------
# AUDIO UTILITIES
# ----------------------------
def match_level(seg: AudioSegment, target_dbfs: float = -18.0) -> AudioSegment:
    if seg.dBFS == float("-inf"):
        return seg
    return seg.apply_gain(target_dbfs - seg.dBFS)


def _pad_to_length(seg: AudioSegment, length_ms: int) -> AudioSegment:
    if len(seg) >= length_ms:
        return seg[:length_ms]
    return seg + AudioSegment.silent(duration=(length_ms - len(seg)))


def duck_music_under_voice(
    voice: AudioSegment,
    music: AudioSegment,
    threshold_dbfs: float = -34.0,
    duck_db: float = 12.0,
    window_ms: int = 40,
) -> AudioSegment:
    voice = voice if voice.channels == 2 else voice.set_channels(2)
    music = music if music.channels == 2 else music.set_channels(2)

    length_ms = len(voice)
    music = _pad_to_length(music, length_ms)

    out_music = AudioSegment.empty()
    for i in range(0, length_ms, window_ms):
        v = voice[i:i + window_ms]
        m = music[i:i + window_ms]
        if v.dBFS != float("-inf") and v.dBFS > threshold_dbfs:
            m = m.apply_gain(-duck_db)
        out_music += m

    return out_music.overlay(voice)


def load_stinger(path: Path, ms: int, target_dbfs: float, fade_in_ms: int, fade_out_ms: int) -> AudioSegment:
    seg = AudioSegment.from_file(path)
    if ms and ms > 0:
        seg = seg[:ms]
    seg = match_level(seg, target_dbfs=target_dbfs)
    if fade_in_ms and fade_in_ms > 0:
        seg = seg.fade_in(fade_in_ms)
    if fade_out_ms and fade_out_ms > 0:
        seg = seg.fade_out(fade_out_ms)
    return seg


def _lead_silence_ms(a: AudioSegment, thresh_db: float) -> int:
    ms = 0
    step = 10
    while ms < len(a):
        chunk = a[ms:ms + step]
        if chunk.dBFS > thresh_db:
            return ms
        ms += step
    return ms


def trim_silence(seg: AudioSegment, leading_ms: int = 60, trailing_ms: int = 140, thresh_db: float = -45.0) -> AudioSegment:
    if len(seg) < 40:
        return seg
    start = min(_lead_silence_ms(seg, thresh_db=thresh_db), leading_ms)
    end = min(_lead_silence_ms(seg.reverse(), thresh_db=thresh_db), trailing_ms)
    if len(seg) <= (start + end + 10):
        return seg
    return seg[start:len(seg) - end]


def post_process_tts_mp3(path: Path) -> None:
    try:
        clip = AudioSegment.from_file(path)
        clip = trim_silence(
            clip,
            leading_ms=TRIM_LEADING_MS,
            trailing_ms=TRIM_TRAILING_MS,
            thresh_db=TRIM_THRESH_DB,
        )
        clip.export(path, format="mp3", bitrate=SEGMENT_EXPORT_BITRATE)
    except Exception as e:
        _safe_print(f"    ⚠️ Post-process failed for {path.name}: {e}")


def master_final_audio_ffmpeg(in_path: Path, out_path: Path) -> None:
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found; required for final mastering.")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-af",
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=120:makeup=4,"
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)


# ----------------------------
# SIDECAR META
# ----------------------------
def _date_from_episode_filename(name: str) -> Optional[str]:
    m = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", name or "")
    return m.group(1) if m else None


def _sidecar_meta_path_for_date(date_str: str) -> Path:
    return AUDIO_DIR / f"podcast_{date_str}.json"


def _load_sidecar_meta_for_date(date_str: str) -> Dict[str, str]:
    p = _sidecar_meta_path_for_date(date_str)
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def _write_sidecar_meta_for_date(date_str: str, title: str, description: str) -> Path:
    p = _sidecar_meta_path_for_date(date_str)
    payload = {"title": (title or "").strip(), "description": (description or "").strip()}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ----------------------------
# LLM HELPERS
# ----------------------------
def _gemini_candidate_models() -> List[str]:
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models: List[str] = []
    if env_model:
        models.append(env_model)
    models += ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash"]
    seen = set()
    out: List[str] = []
    for m in models:
        if m and m not in seen:
            out.append(m)
            seen.add(m)
    return out


def _extract_json_object(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    raw2 = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    raw2 = re.sub(r"\s*```$", "", raw2).strip()
    try:
        obj = json.loads(raw2)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    m = re.search(r"(\{.*\})", raw2, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None



def _json_safe_text(value, max_chars: int = 120000) -> str:
    """
    Force arbitrary prompt content into a JSON-safe UTF-8 string.
    This strips control chars, bad surrogates, and weird payload artifacts
    that can break OpenAI chat.completions.create().
    """
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Keep tabs/newlines; drop most other control chars
    text = "".join(
        ch for ch in text
        if ch == "\n" or ch == "\t" or ord(ch) >= 32
    )

    # Remove invalid unicode safely
    text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

    # Collapse runaway blank lines
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    if len(text) > max_chars:
        text = text[:max_chars]

    return text.strip()



def generate_text(
    prompt,
    temperature: float = 0.7,
    max_tokens: int = 1600,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    """
    Safe wrapper for OpenAI text generation.
    Cleans prompt/system text so malformed RSS/news characters do not break the
    JSON request body sent by the OpenAI Python client.
    """
    chosen_model = (
        model
        or os.getenv("OPENAI_TEXT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or OPENAI_CHAT_MODEL
    )

    safe_system = _json_safe_text(
        system_prompt
        or "You are writing polished, natural spoken-word podcast dialogue."
    )
    safe_prompt = _json_safe_text(prompt)

    last_err = None

    for attempt in range(1, 4):
        try:
            resp = openai_client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": safe_system},
                    {"role": "user", "content": safe_prompt},
                ],
                temperature=float(temperature),
                max_tokens=int(max_tokens),
            )

            content = resp.choices[0].message.content or ""
            return _json_safe_text(content, max_chars=200000)

        except Exception as e:
            last_err = e
            err_text = str(e).lower()

            # JSON-body corruption hard retry
            if "could not parse the json body" in err_text:
                safe_prompt = _json_safe_text(safe_prompt, max_chars=80000)
                safe_prompt = safe_prompt.replace("\\", " ")
                safe_prompt = safe_prompt.replace("\x00", " ")
                safe_prompt = re.sub(r"[^\S\n\t]+", " ", safe_prompt)
                safe_prompt = re.sub(r"\n{3,}", "\n\n", safe_prompt).strip()

                safe_system = _json_safe_text(safe_system, max_chars=8000)

                time.sleep(1.25 * attempt)
                continue

            # Generic retry
            time.sleep(1.25 * attempt)

    raise RuntimeError(f"generate_text failed after 3 attempts: {last_err}")


def _digit_count(s: str) -> int:
    return len(re.findall(r"\d", s or ""))


def _numeric_score(s: str) -> int:
    if not s:
        return 0
    s2 = s.lower()
    score = 0
    score += 3 * _digit_count(s2)
    if "$" in s2 or "€" in s2 or "£" in s2:
        score += 25
    if "%" in s2:
        score += 15
    for w, pts in [("billion", 18), ("million", 14), ("bn", 14), ("ipo", 10), ("funding", 10), ("valuation", 10)]:
        if w in s2:
            score += pts
    return score


def _virality_score(title: str, summary: str) -> int:
    blob = f"{title or ''} {summary or ''}".lower()
    score = 0
    for kw in VIRAL_KEYWORDS:
        if kw in blob:
            score += 10
    for b in VIRAL_BRANDS:
        if b in blob:
            score += 6
    if "!" in (title or ""):
        score += 6
    if "?" in (title or ""):
        score += 4
    return score


def _parse_published_to_dt(published: str) -> Optional[datetime.datetime]:
    if not published:
        return None
    s = published.strip()
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        dt2 = datetime.datetime.strptime(s[:25], "%a, %d %b %Y %H:%M:%S")
        return dt2.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def _recency_boost(published: str) -> int:
    dt = _parse_published_to_dt(published)
    if not dt:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    if age_hours <= 6:
        return 35
    if age_hours <= 12:
        return 20
    if age_hours <= 24:
        return 10
    if age_hours <= 48:
        return 4
    return 0


def _combined_story_score(item: Dict[str, str]) -> int:
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    published = item.get("published") or ""
    return _numeric_score(title + " " + summary) + _virality_score(title, summary) + _recency_boost(published)


def _strip_html(s: str) -> str:
    if not s:
        return ""
    soup = BeautifulSoup(s, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt).strip()


def _split_headline_publisher(title: str) -> Tuple[str, str]:
    if not title:
        return "", ""
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return " - ".join(parts[:-1]).strip(), parts[-1].strip()
    return title.strip(), ""


def _published_iso_from_entry(entry) -> str:
    try:
        tt = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if tt:
            dt = datetime.datetime(*tt[:6], tzinfo=datetime.timezone.utc)
            return dt.isoformat()
    except Exception:
        pass
    try:
        s = (getattr(entry, "published", "") or getattr(entry, "updated", "") or "").strip()
        return s[:64]
    except Exception:
        return ""


# ----------------------------
# NEWS INTEL (RSS)
# ----------------------------
GOOGLE_NEWS_RSS: List[Tuple[str, str]] = [
    # 1) AI Topline / biggest stories
    ("topline", "https://news.google.com/rss/search?q=(AI%20OR%20%22artificial%20intelligence%22%20OR%20OpenAI%20OR%20Anthropic%20OR%20Google%20Gemini%20OR%20Meta%20AI%20OR%20Nvidia)%20(funding%20OR%20lawsuit%20OR%20ban%20OR%20leak%20OR%20security%20OR%20chips%20OR%20datacenter%20OR%20launch%20OR%20deal%20OR%20earnings)%20when:3d&hl=en-US&gl=US&ceid=US:en"),
    ("topline", "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Google%20DeepMind%20OR%20Meta%20OR%20Microsoft%20OR%20Nvidia)%20(AI%20OR%20agentic%20OR%20LLM)%20when:3d&hl=en-US&gl=US&ceid=US:en"),

    # 2) Health AI
    ("health_ai", "https://news.google.com/rss/search?q=(AI%20OR%20generative%20AI%20OR%20LLM)%20(healthcare%20OR%20health%20OR%20hospital%20OR%20clinical%20OR%20diagnostic%20OR%20payer%20OR%20provider%20OR%20EHR%20OR%20FDA)%20when:5d&hl=en-US&gl=US&ceid=US:en"),
    ("health_ai", "https://news.google.com/rss/search?q=(AI%20OR%20machine%20learning)%20(medical%20OR%20clinical%20OR%20hospital%20OR%20pharma%20OR%20radiology%20OR%20diagnosis)%20when:5d&hl=en-US&gl=US&ceid=US:en"),

    # 3) AI Tools
    ("ai_tools", "https://news.google.com/rss/search?q=(AI%20tool%20OR%20AI%20assistant%20OR%20copilot%20OR%20workflow%20OR%20API%20OR%20launch)%20(review%20OR%20release%20OR%20benchmark%20OR%20feature%20OR%20pricing)%20when:4d&hl=en-US&gl=US&ceid=US:en"),
    ("ai_tools", "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Google%20Gemini%20OR%20Perplexity%20OR%20Notion%20OR%20Canva)%20(tool%20OR%20assistant%20OR%20platform%20OR%20workflow)%20when:4d&hl=en-US&gl=US&ceid=US:en"),

    # 4) AI Code
    ("ai_code", "https://news.google.com/rss/search?q=(AI%20coding%20OR%20code%20assistant%20OR%20Copilot%20OR%20Cursor%20OR%20Windsurf%20OR%20repo%20OR%20developer)%20(benchmark%20OR%20bug%20OR%20launch%20OR%20agent%20OR%20security%20OR%20failure)%20when:4d&hl=en-US&gl=US&ceid=US:en"),
    ("ai_code", "https://news.google.com/rss/search?q=(developer%20OR%20engineering%20OR%20repo%20OR%20GitHub)%20(AI%20coding%20OR%20code%20agent%20OR%20Copilot%20OR%20Cursor)%20when:4d&hl=en-US&gl=US&ceid=US:en"),

    # 5) AI Agents
    ("ai_agents", "https://news.google.com/rss/search?q=(AI%20agent%20OR%20agentic%20AI%20OR%20autonomous%20agent%20OR%20multi-agent%20OR%20orchestration)%20(use%20case%20OR%20security%20OR%20deployment%20OR%20failure%20OR%20launch)%20when:4d&hl=en-US&gl=US&ceid=US:en"),
    ("ai_agents", "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Google%20OR%20Meta)%20(agent%20OR%20agentic%20OR%20swarm%20OR%20orchestration)%20when:4d&hl=en-US&gl=US&ceid=US:en"),
]

VERTICAL_ORDER = ["topline", "health_ai", "ai_tools", "ai_code", "ai_agents"]
VERTICAL_FLEX_ORDER = ["ai_agents", "ai_code", "ai_tools", "topline", "health_ai"]
VERTICAL_LABELS = {
    "topline": "AI Topline",
    "health_ai": "Health AI",
    "ai_tools": "AI Tools",
    "ai_code": "AI Code",
    "ai_agents": "AI Agents",
}


DESK_CONTEXT_PER_VERTICAL = int(os.getenv("DESK_CONTEXT_PER_VERTICAL", "7"))
DESK_SHORTLIST_PER_VERTICAL = int(os.getenv("DESK_SHORTLIST_PER_VERTICAL", "3"))
DESK_MIN_WINNERS = int(os.getenv("DESK_MIN_WINNERS", "5"))


def fetch_rss_items(max_per_feed: int = 10) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot; +https://github.com/aisimplify333/Daily-ai-News)"}
    for label, url in GOOGLE_NEWS_RSS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for entry in (feed.entries or [])[:max_per_feed]:
                raw_title = (getattr(entry, "title", "") or "").strip()
                title, publisher = _split_headline_publisher(raw_title)
                link = (getattr(entry, "link", "") or "").strip()
                summary = _strip_html(getattr(entry, "summary", "") or "")[:700]
                published = _published_iso_from_entry(entry)
                if title and link:
                    items.append(
                        {
                            "bucket": label,
                            "title": title,
                            "publisher": publisher,
                            "published": published,
                            "link": link,
                            "summary": summary,
                        }
                    )
        except Exception as e:
            _safe_print(f"    ⚠️ RSS fetch failed ({label}): {e}")

    seen = set()
    deduped: List[Dict[str, str]] = []
    for x in items:
        key = re.sub(r"\s+", " ", (x.get("title") or "").lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(x)
    return deduped


@lru_cache(maxsize=128)
def _resolve_final_url(url: str) -> str:
    if not url:
        return url
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    try:
        r = requests.get(url, headers=headers, timeout=12, allow_redirects=True, stream=True)
        r.close()
        return r.url or url
    except Exception:
        return url


@lru_cache(maxsize=128)
def fetch_url_preview(url: str, max_chars: int = 3800) -> str:
    if not url:
        return ""
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    try:
        final_url = _resolve_final_url(url)
        r = requests.get(final_url, headers=headers, timeout=18)
        r.raise_for_status()

        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return ""

        html = r.text or ""
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()

        meta_desc = ""
        for key in [("name", "description"), ("property", "og:description"), ("name", "twitter:description")]:
            tag = soup.find("meta", attrs={key[0]: key[1]})
            if tag and tag.get("content"):
                meta_desc = (tag.get("content") or "").strip()
                if meta_desc:
                    break

        base = soup.find("article") or soup.body or soup

        chunks: List[str] = []
        if meta_desc:
            chunks.append(meta_desc)

        for h in base.find_all(["h1", "h2", "h3"]):
            txt = h.get_text(" ", strip=True)
            if txt and 20 <= len(txt) <= 180:
                chunks.append(txt)
            if len(chunks) >= 10:
                break

        paras: List[str] = []
        for p in base.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if txt and len(txt) > 40:
                paras.append(txt)
            if len(paras) >= 10:
                break
        chunks.extend(paras)

        lis: List[str] = []
        for li in base.find_all("li"):
            txt = li.get_text(" ", strip=True)
            if txt and 20 <= len(txt) <= 200:
                if NUMERIC_TOKEN_RE.search(txt) or MONEY_RE.search(txt):
                    lis.append(txt)
            if len(lis) >= 10:
                break
        chunks.extend(lis)

        preview = " ".join(chunks)
        preview = re.sub(r"\s+", " ", preview).strip()
        return preview[:max_chars]
    except Exception:
        return ""


# ----------------------------
# SPONSORS / STORIES
# ----------------------------
def _sponsors_look_legacy(sponsors: List[Dict[str, str]]) -> bool:
    blob = json.dumps(sponsors, ensure_ascii=False).lower()
    legacy_markers = [
        "aisimplify333@",
        "sponsor the ai edge",
        "sponsor this show",
        "email aisimplify333",
    ]
    return any(m in blob for m in legacy_markers)


def load_sponsors() -> List[Dict[str, str]]:
    sponsors: Optional[List[Dict[str, str]]] = None
    if SPONSORS_PATH.exists():
        try:
            data = json.loads(SPONSORS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                sponsors = data
            elif isinstance(data, dict) and "sponsors" in data and isinstance(data["sponsors"], list):
                sponsors = data["sponsors"]
        except Exception:
            sponsors = None

    if sponsors:
        cleaned: List[Dict[str, str]] = []
        for s in sponsors:
            if not isinstance(s, dict):
                continue
            cleaned.append(
                {
                    "name": str(s.get("name", "")).strip(),
                    "tagline": str(s.get("tagline", "")).strip(),
                    "cta": str(s.get("cta", "")).strip(),
                }
            )
        if cleaned and not _sponsors_look_legacy(cleaned):
            return cleaned[:3]

    return [dict(x) for x in THELEDGR_DEFAULT_SPONSORS]



def _clean_fact_bullet(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    noise_patterns = [
        r"Comprehensive up-to-date news coverage, aggregated from sources all over the world by Google News\.?$",
        r"\bGoogle News\b",
        r"\baggregated from sources all over the world\b",
    ]
    for pat in noise_patterns:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip(" -;:.")
    return re.sub(r"\s+", " ", t).strip()

def _fact_bullet_is_usable(text: str) -> bool:
    t = _clean_fact_bullet(text)
    if not t:
        return False
    if len(t) < 18:
        return False
    if "comprehensive up-to-date news coverage" in t.lower():
        return False
    return True

def _extract_numeric_sentences(text: str, max_items: int = 6) -> List[str]:
    if not text:
        return []
    sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    hits: List[str] = []
    for s in sents:
        s2 = _clean_fact_bullet(s)
        if not _fact_bullet_is_usable(s2):
            continue
        if NUMERIC_TOKEN_RE.search(s2):
            if 24 <= len(s2) <= 220:
                hits.append(s2)
        if len(hits) >= max_items:
            break
    out: List[str] = []
    seen = set()
    for h in hits:
        key = h.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out[:max_items]


def enrich_stories_with_data(stories: List[Dict[str, str]]) -> List[Dict[str, str]]:
    enriched: List[Dict[str, str]] = []
    for s in stories:
        url = (s.get("source_url") or "").strip()
        rss_summary = (s.get("rss_summary") or "").strip()
        publisher = (s.get("publisher") or "").strip()
        published = (s.get("published") or "").strip()
        preview = fetch_url_preview(url, max_chars=3800)

        prompt = f"""
You are extracting HARD FACTS for a daily AI news podcast. Do NOT invent numbers.
Only use numbers/dates/amounts that appear in the provided snippets.

Return ONLY valid JSON (no markdown):
{{
  "why_shocking": "1-2 sentences, urgent, grounded in snippet facts",
  "data_points": ["3-6 bullets. Each bullet MUST include at least one explicit number/date/amount from snippets. If truly none exist, write: 'No explicit figures in snippet.'"],
  "key_entities": ["2-8 proper nouns from snippets"]
}}

Publisher: {publisher}
Published: {published}
URL: {url}

RSS Summary:
{rss_summary}

Article Preview:
{preview}
""".strip()

        raw = generate_text(prompt, temperature=0.20, max_tokens=900)
        j = _extract_json_object(raw) or {}

        dp = j.get("data_points") if isinstance(j.get("data_points"), list) else []
        dp = [_clean_fact_bullet(str(x)) for x in dp if str(x).strip()]
        dp = [x for x in dp if _fact_bullet_is_usable(x)][:8]

        strong_dp = [b for b in dp if NUMERIC_TOKEN_RE.search(b)]
        if len(strong_dp) < MIN_NUMERIC_BULLETS_PER_STORY:
            extracted = _extract_numeric_sentences((rss_summary + " " + preview).strip(), max_items=8)
            dp = []
            seen_dp = set()
            for bullet in (strong_dp + extracted):
                bullet = _clean_fact_bullet(bullet)
                key = bullet.lower()
                if not bullet or key in seen_dp:
                    continue
                seen_dp.add(key)
                dp.append(bullet)
            dp = dp[:6]

        if not dp:
            pub_bullet = _clean_fact_bullet(f"Published on {published[:10]}." if published else "")
            dp = [pub_bullet] if pub_bullet else ["No explicit figures in snippet."]

        why = (j.get("why_shocking") or s.get("why_shocking") or "").strip()
        if not why:
            why = (rss_summary[:240] or "High-stakes implications—details evolving.").strip()

        s2 = dict(s)
        s2["why_shocking"] = why
        s2["data_points"] = dp[:6]
        s2["key_entities"] = j.get("key_entities") if isinstance(j.get("key_entities"), list) else []
        enriched.append(s2)

    return enriched



def _normalize_vertical_bucket(bucket: str) -> str:
    b = (bucket or "").strip().lower()
    if b in VERTICAL_LABELS:
        return b
    aliases = {
        "top line": "topline",
        "health": "health_ai",
        "healthcare": "health_ai",
        "tools": "ai_tools",
        "code": "ai_code",
        "coding": "ai_code",
        "agents": "ai_agents",
        "agent": "ai_agents",
    }
    return aliases.get(b, "topline")


def broaden_intel_pool() -> List[Dict[str, str]]:
    pool = fetch_rss_items(max_per_feed=12)
    if len(pool) < 20:
        pool = fetch_rss_items(max_per_feed=18)
    if len(pool) < 12:
        # one last broader pull using the same queries but higher per-feed depth
        pool = fetch_rss_items(max_per_feed=24)
    return pool


def _candidate_to_story(x: Dict[str, str]) -> Dict[str, str]:
    bucket = _normalize_vertical_bucket(x.get("bucket", ""))
    return {
        "headline": x.get("title", ""),
        "why_shocking": x.get("summary", ""),
        "data_points": _extract_numeric_sentences((x.get("summary", "") or ""), max_items=6) or ["Needs enrichment"],
        "angles": {"alex": "", "jamie": "", "rufus": ""},
        "source_url": x.get("link", ""),
        "publisher": x.get("publisher", ""),
        "published": x.get("published", ""),
        "rss_summary": x.get("summary", ""),
        "tomorrow_hook": "",
        "bucket": bucket,
    }


def _dedupe_story_list(stories: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for s in stories:
        key = (s.get("source_url") or "").strip().lower() or re.sub(r"\s+", " ", (s.get("headline") or "").strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out



def _story_identity_key(item: Dict[str, str]) -> str:
    return (item.get("source_url") or item.get("link") or "").strip().lower() or re.sub(
        r"\s+", " ", (item.get("headline") or item.get("title") or "").strip().lower()
    )

def _story_breakdown(story: Dict[str, str]) -> Dict[str, float]:
    bd = story.get("score_breakdown") or {}
    return bd if isinstance(bd, dict) else {}

def _story_numeric_blob(story: Dict[str, str]) -> str:
    parts = [story.get("headline") or story.get("title") or "", story.get("why_shocking") or story.get("summary") or ""]
    parts.extend([str(x) for x in (story.get("data_points") or [])[:4]])
    return " ".join([p for p in parts if p])

def _editorial_impact_score(story: Dict[str, str]) -> float:
    bd = _story_breakdown(story)
    growth = float(story.get("growth_score") or 0.0)
    authority = float(bd.get("authority", 0.0))
    consequence = float(bd.get("forward_consequence", 0.0))
    numeric = float(bd.get("numeric_density", 0.0))
    clipability = float(bd.get("clipability", 0.0))
    recency = float(bd.get("recency", 0.0))
    cluster = float(story.get("cluster_size") or 0.0)
    publisher = (story.get("publisher") or "").lower()

    score = growth + (0.30 * authority) + (0.35 * consequence) + (0.18 * numeric) + (0.15 * clipability) + (0.08 * recency) + (0.05 * cluster)
    if any(x in publisher for x in ["bloomberg", "reuters", "wsj", "financial times", "ft"]):
        score += 6.0
    return round(score, 2)

def _candidate_quality_pass(item: Dict[str, str]) -> bool:
    bucket = _normalize_vertical_bucket(item.get("bucket", ""))
    bd = _story_breakdown(item)
    authority = float(bd.get("authority", 0.0))
    brand_fit = float(bd.get("brand_fit", 0.0))
    consequence = float(bd.get("forward_consequence", 0.0))
    numeric = float(bd.get("numeric_density", 0.0))
    recency = float(bd.get("recency", 0.0))
    publisher = (item.get("publisher") or "").lower()
    headline = (item.get("title") or item.get("headline") or "").lower()

    low_signal_publishers = ["openpr", "prnewswire", "globenewswire", "ein presswire", "accessnewswire"]
    if any(x in publisher for x in low_signal_publishers):
        return False
    if "market to reach usd" in headline or headline.endswith("to reach usd"):
        return False

    if bucket == "topline":
        return authority >= 60.0 and brand_fit >= 50.0
    if bucket == "health_ai":
        return authority >= 48.0 and brand_fit >= 42.0 and (consequence >= 12.0 or numeric >= 12.0)
    if bucket == "ai_code":
        return authority >= 48.0 and brand_fit >= 48.0 and (consequence >= 8.0 or numeric >= 8.0 or recency >= 35.0)
    if bucket == "ai_tools":
        return authority >= 45.0 and brand_fit >= 50.0
    if bucket == "ai_agents":
        return authority >= 50.0 and brand_fit >= 50.0
    return authority >= 45.0 and brand_fit >= 40.0

def order_stories_for_episode(stories: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not stories:
        return []

    working = [dict(s) for s in stories]
    top_story = max(working, key=_editorial_impact_score)
    top_key = _story_identity_key(top_story)
    ordered: List[Dict[str, str]] = [top_story]
    remaining = [s for s in working if _story_identity_key(s) != top_key]

    def best_from_bucket(bucket: str) -> Optional[Dict[str, str]]:
        candidates = [s for s in remaining if _normalize_vertical_bucket(s.get("bucket", "")) == bucket]
        if not candidates:
            return None
        return max(candidates, key=_editorial_impact_score)

    def add_story(item: Optional[Dict[str, str]]) -> None:
        nonlocal remaining, ordered
        if not item:
            return
        key = _story_identity_key(item)
        if any(_story_identity_key(x) == key for x in ordered):
            return
        ordered.append(item)
        remaining = [s for s in remaining if _story_identity_key(s) != key]

    add_story(best_from_bucket("health_ai"))

    rufus_candidates = [s for s in remaining if _normalize_vertical_bucket(s.get("bucket", "")) in {"ai_agents", "ai_code", "topline"}]
    if rufus_candidates:
        add_story(max(rufus_candidates, key=_editorial_impact_score))

    for bucket in ["ai_tools", "ai_code", "ai_agents", "topline", "health_ai"]:
        add_story(best_from_bucket(bucket))

    for item in sorted(remaining, key=_editorial_impact_score, reverse=True):
        add_story(item)

    out: List[Dict[str, str]] = []
    seen = set()
    for s in ordered:
        key = _story_identity_key(s)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _build_vertical_slate(curated: List[Dict[str, str]], n: int) -> List[Dict[str, str]]:
    by_vertical: Dict[str, List[Dict[str, str]]] = {v: [] for v in VERTICAL_ORDER}
    for item in curated:
        by_vertical.setdefault(_normalize_vertical_bucket(item.get("bucket", "")), []).append(item)

    for vertical in by_vertical:
        by_vertical[vertical].sort(key=_editorial_impact_score, reverse=True)

    selected: List[Dict[str, str]] = []
    used = set()

    def add_item(item: Dict[str, str]) -> None:
        key = _story_identity_key(item)
        if not key or key in used:
            return
        used.add(key)
        selected.append(item)

    if curated:
        add_item(max(curated, key=_editorial_impact_score))

    for vertical in VERTICAL_ORDER:
        for item in by_vertical.get(vertical, []):
            add_item(item)
            if len(selected) and _normalize_vertical_bucket(selected[-1].get("bucket", "")) == vertical:
                break

    if len(selected) < n:
        for item in sorted(curated, key=_editorial_impact_score, reverse=True):
            if len(selected) >= n:
                break
            add_item(item)

    return selected[:n]


def _compact_candidate_for_prompt(item: Dict[str, str]) -> str:
    bd = item.get("score_breakdown") or {}
    return (
        f"REF={_story_identity_key(item)} | TITLE={item.get('title','')} | PUBLISHER={item.get('publisher','')} | "
        f"PUBLISHED={item.get('published','')} | SCORE={item.get('growth_score', 0):.2f} | "
        f"AUTHORITY={bd.get('authority', 0)} | CONSEQUENCE={bd.get('forward_consequence', 0)} | "
        f"NUMERIC={bd.get('numeric_density', 0)} | CLIP={bd.get('clipability', 0)} | SUMMARY={item.get('summary','')}"
    )


def _match_ranked_candidate(ref_or_title: str, candidates: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    needle = (ref_or_title or "").strip().lower()
    if not needle:
        return None
    for c in candidates:
        if _story_identity_key(c) == needle:
            return c
    for c in candidates:
        if (c.get("link") or "").strip().lower() == needle:
            return c
    for c in candidates:
        title = re.sub(r"\s+", " ", (c.get("title") or "").strip().lower())
        if title == needle:
            return c
    for c in candidates:
        title = re.sub(r"\s+", " ", (c.get("title") or "").strip().lower())
        if needle in title or title in needle:
            return c
    return None


def _desk_rank_vertical(date_str: str, vertical: str, candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
    filtered = [x for x in candidates if _candidate_quality_pass(x)]
    ranked = sorted((filtered or candidates), key=_editorial_impact_score, reverse=True)
    if len(ranked) <= DESK_SHORTLIST_PER_VERTICAL:
        return [dict(x) for x in ranked]

    label = VERTICAL_LABELS.get(vertical, vertical)
    candidate_block = "\n".join([f"- {_compact_candidate_for_prompt(x)}" for x in ranked[:DESK_CONTEXT_PER_VERTICAL]])
    prompt = f"""
You are the Editor-in-Chief of The AI Edge on {date_str}.
You are selecting the strongest {label} stories for today's show.

Choose the top {DESK_SHORTLIST_PER_VERTICAL} candidates from the list below.
Selection priorities:
- strongest real-world consequence
- strongest authority / source credibility
- strongest operator or builder relevance
- strongest shareability / forwardable potential
- avoid weak rewrites and thin summaries

Return ONLY valid JSON:
{{
  "winner_ref": "REF value of the best candidate",
  "top_refs": ["REF1", "REF2", "REF3"],
  "editor_reason": "one sharp sentence on why the winner belongs",
  "share_angle": "one sentence someone would want to forward",
  "tomorrow_hook": "one sentence about what changes next"
}}

Candidates:
{candidate_block}
""".strip()
    try:
        raw = generate_text(prompt, temperature=0.15, max_tokens=700)
        j = _extract_json_object(raw) or {}
    except Exception:
        j = {}

    selected: List[Dict[str, str]] = []
    seen = set()
    for ref in (j.get("top_refs") or []):
        match = _match_ranked_candidate(str(ref), ranked)
        if not match:
            continue
        key = _story_identity_key(match)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(match))
        if len(selected) >= DESK_SHORTLIST_PER_VERTICAL:
            break

    if not selected:
        selected = [dict(x) for x in ranked[:DESK_SHORTLIST_PER_VERTICAL]]

    winner_ref = str(j.get("winner_ref") or "").strip()
    if winner_ref:
        winner_match = _match_ranked_candidate(winner_ref, selected) or _match_ranked_candidate(winner_ref, ranked)
        if winner_match:
            key = _story_identity_key(winner_match)
            selected.sort(key=lambda x: 1 if _story_identity_key(x) == key else 0, reverse=True)

    if selected:
        selected[0]["editor_reason"] = (j.get("editor_reason") or "").strip()
        selected[0]["share_angle"] = (j.get("share_angle") or "").strip()
        selected[0]["tomorrow_hook"] = (j.get("tomorrow_hook") or "").strip()
    return selected


def _editor_in_chief_slate(date_str: str, curated: List[Dict[str, str]], n: int) -> List[Dict[str, str]]:
    by_vertical: Dict[str, List[Dict[str, str]]] = {v: [] for v in VERTICAL_ORDER}
    for item in curated:
        by_vertical.setdefault(_normalize_vertical_bucket(item.get("bucket", "")), []).append(item)
    for vertical in by_vertical:
        by_vertical[vertical].sort(key=_editorial_impact_score, reverse=True)

    desk_winners: List[Dict[str, str]] = []
    used = set()
    for vertical in VERTICAL_ORDER:
        ranked = _desk_rank_vertical(date_str, vertical, by_vertical.get(vertical, [])[:DESK_CONTEXT_PER_VERTICAL])
        if not ranked:
            continue
        winner = dict(ranked[0])
        winner["bucket"] = _normalize_vertical_bucket(winner.get("bucket", vertical))
        key = _story_identity_key(winner)
        if key and key not in used:
            desk_winners.append(winner)
            used.add(key)

    if len(desk_winners) < DESK_MIN_WINNERS:
        for item in _build_vertical_slate(curated, n=max(n, DESK_MIN_WINNERS)):
            key = _story_identity_key(item)
            if key in used:
                continue
            desk_winners.append(dict(item))
            used.add(key)
            if len(desk_winners) >= max(n, DESK_MIN_WINNERS):
                break

    if len(desk_winners) < n:
        for item in sorted(curated, key=_editorial_impact_score, reverse=True):
            key = _story_identity_key(item)
            if key in used:
                continue
            desk_winners.append(dict(item))
            used.add(key)
            if len(desk_winners) >= n:
                break

    return desk_winners[:max(n, DESK_MIN_WINNERS)]


def pick_top_stories(intel_items: List[Dict[str, str]], n: int = 5, date_str: Optional[str] = None) -> List[Dict[str, str]]:
    if not intel_items:
        return []

    date_str = date_str or datetime.date.today().isoformat()
    memory = load_show_memory()
    curated = select_story_candidates(intel_items, n=max(n * 6, 30), memory=memory, bucket_cap=3)
    if not curated:
        ranked = sorted(intel_items, key=_combined_story_score, reverse=True)
        curated = ranked[:max(n * 6, 30)]

    slate_candidates = _editor_in_chief_slate(date_str, curated, n=max(n, 5))
    if len(slate_candidates) < max(n, 5):
        ranked = sorted(intel_items, key=_combined_story_score, reverse=True)
        existing = {_story_identity_key(x) for x in slate_candidates}
        for item in ranked:
            if len(slate_candidates) >= max(n, 5):
                break
            key = _story_identity_key(item)
            if key in existing:
                continue
            slate_candidates.append(item)
            existing.add(key)

    stories = [_candidate_to_story(x) for x in slate_candidates[:max(n, 5)]]
    stories = _dedupe_story_list(stories)

    if len(stories) < max(n, 5):
        ranked = sorted(intel_items, key=_combined_story_score, reverse=True)
        for x in ranked:
            if len(stories) >= max(n, 5):
                break
            st = _candidate_to_story(x)
            merged = _dedupe_story_list(stories + [st])
            if len(merged) > len(stories):
                stories = merged

    enriched = enrich_stories_with_data(stories[:max(n, 5)])
    enriched = attach_story_scores(enriched, curated)

    raw_by_key = {_story_identity_key(x): x for x in slate_candidates}
    for s in enriched:
        raw = raw_by_key.get(_story_identity_key(s))
        if raw:
            if raw.get("tomorrow_hook") and not s.get("tomorrow_hook"):
                s["tomorrow_hook"] = raw.get("tomorrow_hook", "")
            if raw.get("share_angle"):
                s["share_angle"] = raw.get("share_angle", "")
            if raw.get("editor_reason"):
                s["editor_reason"] = raw.get("editor_reason", "")

    if len(enriched) < max(n, 5):
        present = {_story_identity_key(s) for s in enriched}
        for x in curated:
            if len(enriched) >= max(n, 5):
                break
            key = _story_identity_key(x)
            if key in present:
                continue
            extra = enrich_stories_with_data([_candidate_to_story(x)])
            extra = attach_story_scores(extra, curated)
            if extra:
                enriched.extend(extra)
                present.add(key)

    ordered = order_stories_for_episode(_dedupe_story_list(enriched)[:max(n, 5)])
    return ordered[:max(n, 5)]

# ----------------------------
# SCRIPTING (structured 5 segments)
# ----------------------------
# SCRIPTING (structured 5 segments)
# ----------------------------
def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))


def estimate_minutes_from_text(script: str) -> float:
    return _word_count(script) / max(1.0, WORDS_PER_MINUTE)


def _script_targets() -> Tuple[int, int, int]:
    min_words = int(MIN_MINUTES * WORDS_PER_MINUTE * 1.02)
    target_words = int(TARGET_MINUTES * WORDS_PER_MINUTE * 1.00)
    max_words = int(MAX_MINUTES * WORDS_PER_MINUTE * 1.10)
    return min_words, target_words, max_words


def _segment_word_targets() -> List[int]:
    min_words, target_words, max_words = _script_targets()

    # Segment weights tuned for the 5-part show structure:
    # cold open/topline, Jamie human desk, Rufus desk, builder/operator block, close
    weights = [0.13, 0.24, 0.18, 0.29, 0.16]

    # For the Eleven-backed show, pauses, transitions, beds, and more natural pacing
    # add meaningful runtime. We therefore target a tighter script than the legacy build.
    backend = os.getenv("AUDIO_BACKEND", "openai").strip().lower()
    compression = 0.88 if backend == "eleven" else 0.96

    effective_target = max(min_words, int(target_words * compression))
    effective_target = min(effective_target, max_words)

    seg = [max(320, int(effective_target * w)) for w in weights]

    # Put any remainder into Segment 4, the most flexible desk.
    remainder = effective_target - sum(seg)
    seg[3] += remainder

    # Absolute ceilings by segment to stop the old long-form drift.
    hard_caps = [620, 980, 760, 1120, 620]
    seg = [min(seg[i], hard_caps[i]) for i in range(5)]

    # Rebalance after caps while respecting hard caps.
    deficit = effective_target - sum(seg)
    flex_order = [3, 1, 2, 4, 0]
    for idx in flex_order:
        if deficit <= 0:
            break
        room = hard_caps[idx] - seg[idx]
        if room <= 0:
            continue
        add = min(room, deficit)
        seg[idx] += add
        deficit -= add

    return seg


def _segment_header(i: int) -> str:
    return f"### SEGMENT {i}"


def _story_block(stories: List[Dict[str, str]]) -> str:
    out = []
    for i, s in enumerate(stories[:5]):
        dp = s.get("data_points") if isinstance(s.get("data_points"), list) else []
        dp_txt = "; ".join([str(x).strip() for x in dp if str(x).strip()][:6])
        pub = (s.get("publisher") or "").strip()
        pdate = (s.get("published") or "").strip()
        why = (s.get("why_shocking") or "").strip()
        url = (s.get("source_url") or "").strip()
        tomorrow = (s.get("tomorrow_hook") or "").strip()
        out.append(
            f"{i+1}. {s.get('headline','')}\n"
            f"   Publisher: {pub}\n"
            f"   Published: {pdate}\n"
            f"   Why it matters: {why}\n"
            f"   Data points: {dp_txt}\n"
            f"   Tomorrow hook: {tomorrow}\n"
            f"   Source: {url}"
        )
    return "\n".join(out).strip()


def _strict_dialogue_rules() -> str:
    return (
        'HARD FORMAT RULES (non-negotiable):\n'
        '- Output MUST be dialogue lines only using EXACT labels: "ALEX:", "JAMIE:", "RUFUS:"\n'
        '- Every spoken line MUST start with one of those labels. No unlabeled narration.\n'
        '- Keep lines SHORT: 1–2 sentences per line. Prefer one thought per line.\n'
        '- Segment markers are allowed as lines starting with "###" and will NOT be spoken.\n'
        '- "[MUSIC]" may appear as a standalone line.\n'
        '- Do not add any other headings, bullets, or markdown.\n'
    )


def _segment_assignment(seg_num: int) -> str:
    if seg_num == 1:
        return (
            "Cold open hook: start mid-argument with real heat. Then [MUSIC]. "
            "Immediately after [MUSIC], Alex gives a short premium TheLEDGR sponsor hit, then welcomes the audience and fires off today's 5-story lineup in rapid summary. "
            "Make it feel rich, current, interruptive, and addictive, with at least one unresolved consequence that makes tomorrow feel necessary."
        )
    if seg_num == 2:
        return (
            "Studio segment: ONLY Alex + Jamie (no Rufus). Deep dive Story 1 + Story 2 with human stakes, operator consequence, "
            "and at least one quick interruption plus one emotionally intelligent Jamie pushback."
        )
    if seg_num == 3:
        return (
            "Rufus on location: money, politics, regulation, and geopolitical edge. Focus Story 3 with filings, trading, regulatory, or power-structure consequence. "
            "Rufus should land one hard receipt and one dry British undercut that listeners would forward."
        )
    if seg_num == 4:
        return (
            "All three together: dread/greed forecast + lightning round. Cover Story 4 + Story 5 with one callback, one listener-facing pick-a-side question, "
            "and one line sharp enough that a listener would send it to a friend or co-worker."
        )
    return (
        "Closing: Alex closes hard with the practical takeaway, Jamie lands empathy, Rufus delivers a cynical prophecy, "
        "and Alex ends on one unresolved question, risk, or consequence that makes tomorrow feel necessary."
    )


def _sanitize_segment_speakers(seg_text: str, allowed: Optional[set] = None) -> str:
    if not seg_text:
        return ""
    allowed_set = {a.upper() for a in (allowed or set())}
    out: List[str] = []
    for raw in seg_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            out.append("[MUSIC]" if line.upper() == "[MUSIC]" else line)
            continue
        m = SPEAKER_RE.match(line)
        if not m:
            continue
        spk = m.group(1).upper()
        txt = m.group(2).strip()
        if allowed_set and spk not in allowed_set:
            continue
        if txt:
            out.append(f"{spk}: {txt}")
    return "\n".join(out).strip()




def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()

def _story_anchor_terms(stories: Optional[List[Dict[str, str]]]) -> set[str]:
    anchors: set[str] = set()
    for story in stories or []:
        for blob in [
            story.get("headline") or "",
            story.get("why_shocking") or "",
            " ".join([str(x) for x in (story.get("data_points") or [])[:4]]),
            " ".join([str(x) for x in (story.get("key_entities") or [])[:6]]),
            story.get("share_angle") or "",
            story.get("editor_reason") or "",
        ]:
            for tok in re.findall(r"[A-Za-z0-9€$%][A-Za-z0-9€$%\-_]{2,}", blob):
                low = tok.lower().strip(".,:;!?")
                if len(low) >= 4:
                    anchors.add(low)
    return anchors

def _forwardable_line_score(text: str) -> int:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return 0
    low = cleaned.lower()
    score = 0
    if 55 <= len(cleaned) <= 175:
        score += 1
    if re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d{4}\b|\b\d+[mkb]?\b", cleaned, flags=re.IGNORECASE):
        score += 3
    if any(h in low for h in FORWARDABLE_HINTS):
        score += 1
    if any(h in low for h in FORWARDABLE_CONSEQUENCE_HINTS):
        score += 3
    if any(h in low for h in FORWARDABLE_SHOCK_HINTS):
        score += 2
    if any(p in low for p in [
        "this means", "what happens", "the real", "the problem", "the risk", "the edge",
        "the question is", "the truth is", "the blunt truth", "here's the catch",
        "that means", "which means", "what that tells you"
    ]):
        score += 2
    if re.search(r"\b(not .* but|more than|less than|instead of|so you're telling me|the real risk|the real question)\b", low):
        score += 1
    if cleaned.endswith("?"):
        score += 1
    return score

def is_forwardable_line_text(text: str) -> bool:
    low = (text or "").lower()
    has_number = bool(re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d{4}\b|\b\d+[mkb]?\b", text or "", flags=re.IGNORECASE))
    has_consequence = any(h in low for h in FORWARDABLE_CONSEQUENCE_HINTS)
    has_shock = any(h in low for h in FORWARDABLE_SHOCK_HINTS)
    return _forwardable_line_score(text) >= 6 and (has_number or has_consequence or has_shock)

def extract_forwardable_moments(script: str, stories: Optional[List[Dict[str, str]]] = None, max_items: int = 4) -> List[Dict[str, str]]:
    anchors = _story_anchor_terms(stories)
    candidates: List[Dict[str, str]] = []
    seen: set[str] = set()
    for raw in script.splitlines():
        line = raw.strip()
        m = SPEAKER_RE.match(line)
        if not m:
            continue
        speaker = m.group(1).upper()
        text = m.group(2).strip()
        score = _forwardable_line_score(text)
        if score < 4:
            continue
        key = normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        low = text.lower()
        tokens = {tok.lower().strip(".,:;!?") for tok in re.findall(r"[A-Za-z0-9€$%][A-Za-z0-9€$%\-_]{2,}", text)}
        anchor_hits = len(tokens & anchors) if anchors else 0
        candidates.append({
            "speaker": speaker,
            "text": text,
            "score": score + min(anchor_hits, 3),
            "has_number": bool(re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d{4}\b|\b\d+[mkb]?\b", text, flags=re.IGNORECASE)),
            "has_consequence": any(h in low for h in FORWARDABLE_CONSEQUENCE_HINTS),
            "has_shock": any(h in low for h in FORWARDABLE_SHOCK_HINTS),
            "anchor_hits": anchor_hits,
        })

    candidates.sort(
        key=lambda x: (
            1 if (x["has_number"] or x["has_consequence"] or x["has_shock"]) else 0,
            1 if x["anchor_hits"] > 0 else 0,
            x["score"],
            len(x["text"]),
        ),
        reverse=True,
    )
    out: List[Dict[str, str]] = []
    used_speakers = set()
    for c in candidates:
        if len(out) >= max_items:
            break
        if len(out) < 2 and c["anchor_hits"] == 0:
            continue
        if c["score"] < 7 and len(out) < 2:
            continue
        if len(out) < 2 and c["speaker"] in used_speakers and len({cand["speaker"] for cand in candidates}) > 1:
            continue
        out.append({"speaker": c["speaker"], "text": c["text"], "score": c["score"]})
        used_speakers.add(c["speaker"])
    if len(out) < max_items:
        existing = {normalize_text(x["text"]) for x in out}
        for c in candidates:
            if len(out) >= max_items:
                break
            if normalize_text(c["text"]) in existing:
                continue
            out.append({"speaker": c["speaker"], "text": c["text"], "score": c["score"]})
            existing.add(normalize_text(c["text"]))
    return out[:max_items]

def _segment_prompt(seg_num: int, seg_words_min: int, seg_words_target: int, date_str: str,
                    stories: List[Dict[str, str]], sponsors: List[Dict[str, str]]) -> str:
    sponsor_1 = sponsors[0] if len(sponsors) > 0 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_2 = sponsors[1] if len(sponsors) > 1 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_3 = sponsors[2] if len(sponsors) > 2 else {"name": "Sponsor", "tagline": "", "cta": ""}

    extra = ""
    if seg_num in (1, 2, 3, 4):
        extra += (
            "- DO NOT sign off.\n"
            "- DO NOT say goodbye, thanks for listening, until tomorrow, or anything that sounds like the end of the show.\n"
            "- Keep the energy open and forward-moving. This is not the close.\n"
        )

    if seg_num == 1:
        extra += (
            "Start mid-argument (hook). Then a standalone line: [MUSIC]. "
            "Immediately after [MUSIC], Alex must deliver a short, premium TheLEDGR sponsor line before the welcome and lineup.\n"
            "- The sponsor should feel useful, sharp, and native to the show, not like a generic ad break.\n"
            f"- Alex must say the brand as 'The Ledger' and the URL exactly as {THELEDGR_SPOKEN_URL}.\n"
            "- The sponsor must make listeners feel that TheLEDGR helps them make better daily decisions, cut through noise, and stay ahead at work.\n"
            "- CRITICAL: In the cold open and lineup, say at least 3 explicit numbers, dates, dollar amounts, or benchmark figures out loud naturally.\n"
            "- Alex should ask the listener-question everybody is already thinking.\n"
            "- Include at least one interruption or amused undercut.\n"
            "- Include at least one line with genuine tomorrow tension.\n"
            "- Alex must welcome the audience and set up the rest of the episode, not close it.\n"
        )
    elif seg_num == 2:
        extra += (
            "IMPORTANT: This segment must contain ONLY ALEX and JAMIE lines. Do NOT output any RUFUS lines.\n"
            "- Alex must open the segment with a clear setup or turn.\n"
            "- Jamie must not sound like a presenter. She must react to Alex in real time, cut in naturally, and help create banter.\n"
            "- Include at least two moments where Jamie interrupts, challenges, or reframes Alex in a warm but confident way.\n"
            "- Jamie should sound emotionally alive: amused, incredulous, impressed, concerned, or lightly offended when the line calls for it.\n"
            "- She should feel like the Bartlett-style color voice: human, fast, intuitive, and strong on the emotional or real-world implication.\n"
            "- Let there be at least one line that feels instantly clip-worthy because Jamie made the story feel personal, dangerous, or absurd.\n"
        )
    elif seg_num == 3:
        extra += (
            "Alex must throw to Rufus in the first spoken exchange, then Rufus takes over.\n"
            "Rufus should sound like he is on location somewhere real in the world before landing the core receipt.\n"
            "He must connect the money, the politics, and the geopolitical consequence.\n"
            "Include one dry British quip or undercut that only Rufus would say.\n"
            "Weave the sponsor naturally only if it feels native to the insight.\n"
            "This segment should hand momentum forward, not sound like the end of the episode.\n"
            f"Sponsor: {sponsor_1['name']}\n"
            f"Tagline: {sponsor_1.get('tagline','')}\n"
            f"CTA: {sponsor_1.get('cta','')}\n"
        )
    elif seg_num == 4:
        extra += (
            "Alex must tee up the turn. Include ONE woven-in host-read sponsor naturally if it fits the conversation.\n"
            f"Sponsor: {sponsor_2['name']}\n"
            f"Tagline: {sponsor_2.get('tagline','')}\n"
            f"CTA: {sponsor_2.get('cta','')}\n"
            "- Include one callback to something said earlier in the episode.\n"
            "- Jamie must actively play off both Alex and Rufus. She should challenge Rufus if he becomes too cold or purely strategic.\n"
            "- Include one moment where Jamie reacts with genuine offense, disbelief, or frustration at the human cost of the story.\n"
            "- Include one quick interjection and one listener-facing 'pick a side' question.\n"
            "- This segment must contain one line strong enough that a listener would forward it.\n"
        )
    elif seg_num == 5:
        extra += (
            "Alex must open the closing segment and land the practical takeaway.\n"
            "Jamie should leave the audience with the human implication and must sound emotionally invested, not polished.\n"
            "She should respond directly to Rufus if he lands a cynical or detached prediction.\n"
            "Rufus should leave one sharp, slightly cynical prediction.\n"
            "End with a final micro sponsor tag or aside only if it feels native.\n"
            "The final 2-3 lines must make tomorrow feel necessary.\n"
            f"Sponsor: {sponsor_3['name']}\n"
            f"Tagline: {sponsor_3.get('tagline','')}\n"
            f"CTA: {sponsor_3.get('cta','')}\n"
        )

    story_block = _story_block(stories)
    assignment = _segment_assignment(seg_num)

    return f"""
You are writing a DAILY podcast episode called "The AI Edge" for {date_str}.
This is ONLY {_segment_header(seg_num)} of the episode.

PERSONAS:
- ALEX (Host): high-agency host energy. He asks the listener-question everybody is already thinking, calls out BS, cuts through waffle, and keeps the room moving.
- JAMIE (Co-host): empathetic, emotionally intelligent, bright side of the room. She raises the energy, makes AI feel human, and occasionally disarms the room with a smile or laugh.
- RUFUS (Analyst): British dry wit, finance/policy/regulatory edge, always tracking the money, incentives, and geopolitical consequence. He is the receipts machine and often the funniest line in the room.

{_strict_dialogue_rules()}

SEGMENT REQUIREMENTS:
- The FIRST line MUST be exactly: "{_segment_header(seg_num)}"
- Segment length MUST be at least {seg_words_min} words (target ~{seg_words_target} words).
- Avoid filler openers like “let’s dive in”.

DATA REQUIREMENTS (non-negotiable):
- For every story you discuss in THIS segment, you MUST speak at least 2 explicit data points
  (numbers/dates/amounts) from the provided "Data points" lines in TODAY'S STORIES.
- Mention the publisher at least once when introducing a story.
- Do NOT invent numbers. If a story has "No explicit figures in snippet", say that plainly.

WHAT THIS SEGMENT MUST DO:
{assignment}

SPECIAL INSTRUCTIONS FOR THIS SEGMENT:
{extra}

TODAY'S STORIES:
{story_block}

NOW OUTPUT ONLY THIS SEGMENT.
""".strip()


def _segment_validate(seg_text: str, seg_num: int, seg_words_min: int, seg_words_max: int) -> List[str]:
    issues: List[str] = []
    if not seg_text.strip().startswith(_segment_header(seg_num)):
        issues.append(f"Segment {seg_num} missing required first line '{_segment_header(seg_num)}'.")

    for ln in seg_text.splitlines():
        line = ln.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            continue
        if not SPEAKER_RE.match(line):
            issues.append("Found non-labeled spoken line(s).")
            break

    if seg_num == 2 and re.search(r"^RUFUS\s*:", seg_text, flags=re.IGNORECASE | re.MULTILINE):
        issues.append("SEGMENT 2 contains RUFUS lines; it must be ONLY ALEX + JAMIE.")

    wc = _word_count(seg_text)
    if wc < seg_words_min:
        issues.append(f"Segment too short ({wc} words). Minimum is {seg_words_min}.")
    if wc > seg_words_max:
        issues.append(f"Segment too long ({wc} words). Maximum is {seg_words_max}.")

    if seg_num == 1:
        lines = [l.strip() for l in seg_text.splitlines() if l.strip()]
        try:
            music_idx = next(i for i, l in enumerate(lines) if l.upper() == "[MUSIC]")
        except StopIteration:
            issues.append("Segment 1 missing required [MUSIC] marker.")
            music_idx = None

        if music_idx is not None:
            pre_music_dialogue = [l for l in lines[1:music_idx] if SPEAKER_RE.match(l)]
            if len(pre_music_dialogue) < MIN_COLD_OPEN_LINES:
                issues.append(
                    f"Cold open too short before [MUSIC] ({len(pre_music_dialogue)} lines). Minimum is {MIN_COLD_OPEN_LINES}."
                )

    if _digit_count(seg_text) < MIN_DIGITS_PER_SEGMENT:
        issues.append(
            f"Low numeric density in segment (digits={_digit_count(seg_text)}). Minimum is {MIN_DIGITS_PER_SEGMENT}."
        )
    if seg_num < 5 and EARLY_SIGNOFF_RE.search(seg_text or ""):
        issues.append(f"Segment {seg_num} contains premature sign-off language.")
    return issues


def _segment_repair_prompt(seg_num: int, seg_words_min: int, seg_words_target: int,
                           issues: List[str], seg_text: str) -> str:
    seg_specific = ""
    if seg_num == 2:
        seg_specific = (
            "- SEGMENT 2 MUST contain ONLY ALEX and JAMIE lines.\n"
            "- Delete ANY RUFUS lines and do NOT reintroduce RUFUS.\n"
        )

    signoff_fix = ""
    if any("premature sign-off" in (x or "").lower() for x in issues):
        signoff_fix = (
            "- CRITICAL FIX: Remove all goodbye, wrap-up, end-of-show, or tomorrow-style language.\n"
            "- Keep the segment open and forward-moving.\n"
        )

    return f"""
You are repairing ONLY {_segment_header(seg_num)} for "The AI Edge".

CURRENT ISSUES (fix all):
{chr(10).join([f"- {x}" for x in issues])}

NON-NEGOTIABLE:
- First line MUST be exactly "{_segment_header(seg_num)}"
- Output MUST be dialogue lines only with EXACT labels: ALEX:, JAMIE:, RUFUS:
- Every spoken line MUST start with one of those labels.
{seg_specific}{signoff_fix}- Keep lines SHORT (1–2 sentences).
- Segment length MUST be at least {seg_words_min} words (target ~{seg_words_target}).

HERE IS THE SEGMENT TO EXPAND/REPAIR:
{seg_text}
""".strip()


def _sanitize_dialogue_only(text: str, allowed_speakers: Optional[set] = None) -> str:
    if not text:
        return ""
    out: List[str] = []
    last_speaker: Optional[str] = None

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue

        if line.startswith("###"):
            out.append(line)
            last_speaker = None
            continue

        if line.upper() == "[MUSIC]":
            out.append("[MUSIC]")
            last_speaker = None
            continue

        m = SPEAKER_RE.match(line)
        if m:
            spk = m.group(1).upper()
            txt = m.group(2).strip()
            if allowed_speakers is not None and spk not in allowed_speakers:
                last_speaker = None
                continue
            if txt:
                out.append(f"{spk}: {txt}")
                last_speaker = spk
            else:
                last_speaker = None
            continue

        if last_speaker:
            if allowed_speakers is not None and last_speaker not in allowed_speakers:
                continue
            out.append(f"{last_speaker}: {line}")

    return "\n".join(out).strip()


def _generate_segment(seg_num: int, seg_words_min: int, seg_words_target: int, date_str: str,
                      stories: List[Dict[str, str]], sponsors: List[Dict[str, str]]) -> str:
    seg_words_max = max(seg_words_min + 120, int(seg_words_target * 1.10))
    prompt = _segment_prompt(seg_num, seg_words_min, seg_words_target, date_str, stories, sponsors)
    seg_text = ""

    for attempt in range(1, SEGMENT_ATTEMPTS + 1):
        seg_text = generate_text(prompt, temperature=0.72, max_tokens=2200)

        if seg_num == 2:
            seg_text = _sanitize_segment_speakers(seg_text, allowed={"ALEX", "JAMIE"})
            if not seg_text.strip().startswith(_segment_header(seg_num)):
                seg_text = f"{_segment_header(seg_num)}\n{seg_text}".strip()

        wc = _word_count(seg_text)
        issues = _segment_validate(seg_text, seg_num, seg_words_min, seg_words_max)
        _safe_print(
            f"    ✍️ Segment {seg_num} attempt {attempt}/{SEGMENT_ATTEMPTS} "
            f"(min {seg_words_min}, max {seg_words_max}): {wc} words"
        )

        if not issues:
            return seg_text.strip()

        prompt = _segment_repair_prompt(seg_num, seg_words_min, seg_words_target, issues, seg_text)

    # Last-resort trim if the model keeps overshooting.
    if _word_count(seg_text) > seg_words_max:
        lines = seg_text.splitlines()
        kept = []
        word_total = 0
        for line in lines:
            kept.append(line)
            if not line.strip().startswith("###"):
                word_total += len(re.findall(r"\b\w+\b", line))
            if word_total >= seg_words_max:
                break
        seg_text = "\n".join(kept).strip()

    return seg_text.strip()


def _trim_script_to_max_words(script: str, max_words: int) -> str:
    if _word_count(script) <= max_words:
        return script

    trimmed = script.strip()
    while _word_count(trimmed) > max_words:
        tl = trimmed.splitlines()
        removed = False
        for k in range(len(tl) - 1, 0, -1):
            if SPEAKER_RE.match(tl[k].strip()):
                del tl[k]
                removed = True
                break
        trimmed = "\n".join(tl).strip()
        if not removed or len(tl) < 80:
            break
    return trimmed


def _pad_script_to_min_words(script: str, min_words: int, stories: List[Dict[str, str]], date_str: str) -> str:
    wc = _word_count(script)
    if wc >= min_words:
        return script

    need = min_words - wc
    add_words = min(900, max(260, need + 160))
    story_block = _story_block(stories)

    m = re.search(r"^###\s*SEGMENT\s*5\b", script, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return script

    prompt = f"""
Write an ADD-ON block to extend SEGMENT 4 of "The AI Edge" ({date_str}).

RULES:
- Output ONLY dialogue lines labeled ALEX:, JAMIE:, RUFUS:
- NO segment markers.
- Add ~{add_words} words.
- MUST include at least 6 explicit data points from the story block below.

STORY BLOCK:
{story_block}
""".strip()

    addon = generate_text(prompt, temperature=0.65, max_tokens=1800)
    addon = _sanitize_dialogue_only(addon)

    insert_at = m.start()
    return (script[:insert_at].rstrip() + "\n" + addon.strip() + "\n\n" + script[insert_at:].lstrip()).strip()


def validate_script(script: str, stories: Optional[List[Dict[str, str]]] = None) -> List[str]:
    issues: List[str] = []
    for i in range(1, 6):
        if not re.search(rf"^###\s*SEGMENT\s*{i}\b", script, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(f"Missing segment marker: ### SEGMENT {i}")

    for ln in script.splitlines():
        line = ln.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            continue
        if not SPEAKER_RE.match(line):
            issues.append("Found non-labeled spoken line(s).")
            break

    seg2_block = re.search(
        r"^###\s*SEGMENT\s*2\b(.*?)(^###\s*SEGMENT\s*3\b|\Z)",
        script,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if seg2_block and re.search(r"^RUFUS\s*:", seg2_block.group(1), flags=re.IGNORECASE | re.MULTILINE):
        issues.append("SEGMENT 2 contains RUFUS lines; it must be ONLY ALEX + JAMIE.")

    min_words, _, max_words = _script_targets()
    wc = _word_count(script)
    if wc < min_words:
        issues.append(f"Script too short ({wc} words). Minimum is {min_words}.")
    if wc > max_words:
        issues.append(f"Script too long ({wc} words). Maximum is {max_words}.")

    if re.search(r"```|<html|<body|^Title:|^Podcast:", script, flags=re.IGNORECASE | re.MULTILINE):
        issues.append("Contains non-dialogue formatting blocks.")

    if len(extract_forwardable_moments(script, stories=stories, max_items=FORWARDABLE_MIN_PER_EPISODE)) < FORWARDABLE_MIN_PER_EPISODE:
        issues.append(f"Episode needs at least {FORWARDABLE_MIN_PER_EPISODE} forwardable moments.")
    return issues


def enforce_episode_numeric_density(script: str, stories: List[Dict[str, str]], date_str: str) -> str:
    if _digit_count(script) >= MIN_DIGITS_PER_EPISODE:
        return script

    deficit = MIN_DIGITS_PER_EPISODE - _digit_count(script)
    add_words = min(900, max(320, deficit * 6))
    story_block = _story_block(stories)

    prompt = f"""
Write a DATA-DUMP add-on for SEGMENT 4 of "The AI Edge" ({date_str}).

NON-NEGOTIABLE:
- Output ONLY dialogue lines labeled ALEX:, JAMIE:, RUFUS:
- Use story DATA POINTS (numbers/dates/amounts must appear).
- Add ~{add_words} words.
- MUST include at least 12 distinct numeric tokens overall.

STORY BLOCK:
{story_block}
""".strip()

    addon = generate_text(prompt, temperature=0.55, max_tokens=1800)
    addon = _sanitize_dialogue_only(addon)

    m = re.search(r"^###\s*SEGMENT\s*5\b", script, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        script2 = (script.rstrip() + "\n" + addon.strip()).strip()
    else:
        script2 = (script[:m.start()].rstrip() + "\n" + addon.strip() + "\n\n" + script[m.start():].lstrip()).strip()

    min_words, _, max_words = _script_targets()
    if _word_count(script2) > max_words:
        script2 = _trim_script_to_max_words(script2, max_words=max_words)

    return _sanitize_dialogue_only(script2)


def generate_episode_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], date_str: str) -> str:
    seg_targets = _segment_word_targets()
    seg_mins = [max(300, int(t * 0.82)) for t in seg_targets]

    _safe_print(" >> ✍️ WRITING FULL EPISODE (SEGMENTED)...")
    segments: List[str] = []
    for i in range(1, 6):
        seg = _generate_segment(i, seg_mins[i - 1], seg_targets[i - 1], date_str, stories, sponsors)
        seg = _sanitize_dialogue_only(seg, allowed_speakers={"ALEX", "JAMIE"} if i == 2 else None)
        segments.append(seg)

    script = "\n\n".join(segments).strip()
    script = _sanitize_dialogue_only(script)

    min_words, _, max_words = _script_targets()
    if _word_count(script) > max_words:
        script = _trim_script_to_max_words(script, max_words=max_words)
    if _word_count(script) < min_words:
        script = _pad_script_to_min_words(script, min_words=min_words, stories=stories, date_str=date_str)

    script = _sanitize_dialogue_only(script)
    issues = validate_script(script, stories=stories)
    if issues:
        raise RuntimeError("Final script validation failed:\n" + "\n".join(issues))
    return script


# ----------------------------
# DIALOGUE PARSING + AUTO-TRANSITIONS
# ----------------------------
SEGMENT_MARKER_RE = re.compile(r"^###\s*SEGMENT\s*(\d+)\b", re.IGNORECASE)

def iter_dialogue(script: str) -> List[Tuple[str, str]]:
    """
    Parses dialogue into (speaker, text) tuples.
    Also injects a [MUSIC] marker automatically BEFORE segments 2..5 (if enabled),
    so transitions are never forgotten even when the script writer misses them.
    """
    out: List[Tuple[str, str]] = []
    current_speaker: Optional[str] = None
    buf: List[str] = []
    seen_first_segment = False
    last_emitted_was_music = False
    transitions_used = 0

    def flush() -> None:
        nonlocal current_speaker, buf, last_emitted_was_music
        if current_speaker and buf:
            out.append((current_speaker, " ".join(buf).strip()))
            last_emitted_was_music = False
        current_speaker = None
        buf = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        mseg = SEGMENT_MARKER_RE.match(line)
        if mseg:
            flush()
            seg_num = int(mseg.group(1))
            if (
                TRANSITION_EVERY_SEGMENT
                and seen_first_segment
                and seg_num in TRANSITION_SEGMENTS
                and transitions_used < TRANSITION_MAX_PER_EPISODE
                and not last_emitted_was_music
            ):
                out.append(("MUSIC", "[MUSIC]"))
                last_emitted_was_music = True
                transitions_used += 1
            seen_first_segment = True
            continue

        if line.upper() == "[MUSIC]":
            flush()
            out.append(("MUSIC", "[MUSIC]"))
            last_emitted_was_music = True
            continue

        m = SPEAKER_RE.match(line)
        if m:
            flush()
            current_speaker = m.group(1).upper()
            buf = [m.group(2).strip()]
            continue

        if current_speaker:
            buf.append(line)

    flush()
    return out



def _tts_merge_max_chars(speaker: str) -> int:
    if (speaker or "").upper() == "JAMIE":
        return JAMIE_TTS_MERGE_MAX_CHARS
    return TTS_MERGE_MAX_CHARS


def _tts_chunk_max_chars(speaker: str) -> int:
    if (speaker or "").upper() == "JAMIE":
        return JAMIE_TTS_CHUNK_MAX_CHARS
    return TTS_CHUNK_MAX_CHARS


def merge_dialogue_for_tts(dialogue: List[Tuple[str, str]], max_chars: int = 2400) -> List[Tuple[str, str]]:
    merged: List[Tuple[str, str]] = []
    cur_spk: Optional[str] = None
    cur_txt: List[str] = []

    def flush() -> None:
        nonlocal cur_spk, cur_txt
        if cur_spk and cur_txt:
            merged.append((cur_spk, "\n".join(cur_txt).strip()))
        cur_spk = None
        cur_txt = []

    for spk, txt in dialogue:
        if spk == "MUSIC":
            flush()
            merged.append(("MUSIC", "[MUSIC]"))
            continue

        if cur_spk is None:
            cur_spk = spk
            cur_txt = [txt]
            continue

        if spk != cur_spk:
            flush()
            cur_spk = spk
            cur_txt = [txt]
            continue

        candidate = ("\n".join(cur_txt) + "\n" + txt).strip()
        speaker_limit = _tts_merge_max_chars(spk)
        if is_forwardable_line_text(txt) or is_forwardable_line_text(" ".join(cur_txt)):
            flush()
            cur_spk = spk
            cur_txt = [txt]
        elif len(candidate) <= speaker_limit:
            cur_txt.append(txt)
        else:
            flush()
            cur_spk = spk
            cur_txt = [txt]

    flush()
    return merged


# ----------------------------
# TTS + STITCHING
# ----------------------------
def chunk_text(s: str, max_chars: int = 2800) -> List[str]:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_chars:
        return [s]
    chunks: List[str] = []
    while len(s) > max_chars:
        cut = s.rfind(". ", 0, max_chars)
        if cut < 600:
            cut = max_chars
        chunks.append(s[:cut].strip())
        s = s[cut:].strip()
    if s:
        chunks.append(s)
    return chunks




def _eleven_headers() -> Dict[str, str]:
    if not ELEVEN_API_KEY:
        raise RuntimeError("AI_EDGE_PODCAST_ELEVENLABS is missing. Add it to GitHub Secrets / env.")
    return {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }


def _eleven_voice_id(speaker: str) -> str:
    mapping = {
        "ALEX": ELEVEN_VOICE_ID_ALEX,
        "JAMIE": ELEVEN_VOICE_ID_JAMIE,
        "RUFUS": ELEVEN_VOICE_ID_RUFUS,
    }
    voice_id = mapping.get((speaker or "").upper(), "")
    if not voice_id or voice_id.startswith("REPLACE_"):
        raise RuntimeError(f"Missing ElevenLabs voice ID for {speaker}. Set ELEVEN_VOICE_ID_{speaker.upper()} in GitHub Secrets / env.")
    return voice_id


def _eleven_model_id(speaker: str) -> str:
    return {
        "ALEX": ELEVEN_MODEL_ALEX,
        "JAMIE": ELEVEN_MODEL_JAMIE,
        "RUFUS": ELEVEN_MODEL_RUFUS,
    }.get((speaker or "").upper(), "eleven_v3")


def _eleven_voice_settings(speaker: str) -> Dict[str, float | bool]:
    spk = (speaker or "").upper()
    if spk == "ALEX":
        return {
            "stability": ELEVEN_STABILITY_ALEX,
            "similarity_boost": ELEVEN_SIMILARITY_ALEX,
            "style": ELEVEN_STYLE_ALEX,
            "speed": ALEX_SPEED,
            "use_speaker_boost": ELEVEN_USE_SPEAKER_BOOST,
        }
    if spk == "JAMIE":
        return {
            "stability": ELEVEN_STABILITY_JAMIE,
            "similarity_boost": ELEVEN_SIMILARITY_JAMIE,
            "style": ELEVEN_STYLE_JAMIE,
            "speed": JAMIE_SPEED,
            "use_speaker_boost": ELEVEN_USE_SPEAKER_BOOST,
        }
    return {
        "stability": ELEVEN_STABILITY_RUFUS,
        "similarity_boost": ELEVEN_SIMILARITY_RUFUS,
        "style": ELEVEN_STYLE_RUFUS,
        "speed": RUFUS_SPEED,
        "use_speaker_boost": ELEVEN_USE_SPEAKER_BOOST,
    }


def _speech_friendly_text(text: str) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    s = s.replace("AI", "A.I.")
    s = s.replace("EHR", "E.H.R.")
    s = s.replace("API", "A.P.I.")
    s = s.replace("GPU", "G.P.U.")
    s = s.replace("LLM", "L.L.M.")
    s = s.replace("TheLEDGR", "The Ledger")
    s = re.sub(r"\b(\d+)%\b", lambda m: f"{m.group(1)} percent", s)
    s = re.sub(r"\$(\d+(?:\.\d+)?)\s*([mbMB]?)", lambda m: "$" + m.group(1) + (" " + {"m":"million","b":"billion","M":"million","B":"billion"}.get(m.group(2), "") if m.group(2) else ""), s)
    return s


def _eleven_emotion_tags(speaker: str, text: str) -> str:
    low = (text or "").lower()
    tags: List[str] = []
    if speaker == "ALEX":
        tags.extend(["confident", "energized"])
        if "?" in low:
            tags.append("challenging")
        if any(k in low for k in ["lawsuit", "ban", "breach", "security", "warning", "risk"]):
            tags.append("urgent")
        if any(k in low for k in ["billion", "million", "percent", "revenue", "funding", "$"]):
            tags.append("leaning in")
    elif speaker == "JAMIE":
        tags.extend(["warm", "reactive"])
        if any(k in low for k in ["rufus", "cold", "ridiculous", "dangerous", "wrong"]):
            tags.append("annoyed")
        if any(k in low for k in ["patient", "nurse", "mental health", "human", "people", "care"]):
            tags.append("concerned")
        if "?" in low:
            tags.append("incredulous")
        if any(k in low for k in ["wow", "unbelievable", "really"]):
            tags.append("amused")
    else:
        tags.extend(["dryly", "amused"])
        if any(k in low for k in ["regulation", "export", "china", "policy", "lawsuit", "market"]):
            tags.append("precise")
        if any(k in low for k in ["million", "billion", "percent", "revenue", "valuation"]):
            tags.append("matter-of-fact")
        if "?" in low:
            tags.append("skeptical")
    uniq = []
    seen = set()
    for t in tags:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return " ".join(f"[{t}]" for t in uniq[:4])


def _eleven_prompted_text(speaker: str, text: str) -> str:
    base = _speech_friendly_text(text)
    tag_text = _eleven_emotion_tags((speaker or "").upper(), base)
    return f"{tag_text} {base}".strip()



def _build_eleven_render_items(dialogue: List[Tuple[str, str]]) -> List[Tuple[str, object]]:
    if AUDIO_BACKEND != "eleven" or not ELEVEN_USE_DIALOGUE_SCENES:
        return [(spk, txt) for spk, txt in merge_dialogue_for_tts(dialogue, max_chars=TTS_MERGE_MAX_CHARS)]

    items: List[Tuple[str, object]] = []
    scene: List[Tuple[str, str]] = []
    scene_chars = 0

    def flush_scene() -> None:
        nonlocal scene, scene_chars
        if not scene:
            return
        uniq = {spk for spk, _ in scene}
        if len(scene) >= 2 and len(uniq) >= 2:
            items.append(("SCENE", list(scene)))
        else:
            for spk, txt in scene:
                items.append((spk, txt))
        scene = []
        scene_chars = 0

    for spk, txt in dialogue:
        if spk == "MUSIC":
            flush_scene()
            items.append(("MUSIC", "[MUSIC]"))
            continue

        txt = (txt or "").strip()
        if not txt:
            continue

        projected = scene_chars + len(txt)
        if scene and (len(scene) >= ELEVEN_SCENE_MAX_TURNS or projected > ELEVEN_SCENE_MAX_CHARS):
            flush_scene()

        scene.append((spk, txt))
        scene_chars += len(txt)

    flush_scene()
    return items


def _eleven_dialogue_to_file(scene: List[Tuple[str, str]], out_path: Path) -> None:
    inputs = []
    for speaker, text in scene:
        inputs.append({
            "text": _eleven_prompted_text(speaker, text),
            "voice_id": _eleven_voice_id(speaker),
        })

    payload = {
        "inputs": inputs,
        "model_id": "eleven_v3",
        "apply_text_normalization": "auto",
    }
    url = f"https://api.elevenlabs.io/v1/text-to-dialogue?output_format={ELEVEN_OUTPUT_FORMAT}"
    last_err = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            r = requests.post(url, headers=_eleven_headers(), json=payload, timeout=240)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            return
        except Exception as e:
            last_err = e
            sleep_s = min(12, 2 * attempt)
            _safe_print(f"    ⚠️ ElevenLabs dialogue render failed (attempt {attempt}/{TTS_RETRIES}): {e} — retrying in {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"ElevenLabs dialogue render failed after {TTS_RETRIES} retries: {last_err}")


def _mix_brand_bed_if_needed(voice_path: Path, text: str, speaker: str, out_path: Path) -> bool:
    voice_seg = AudioSegment.from_file(voice_path)
    low = (text or "").lower()

    bed_path: Optional[Path] = None
    if "the ledger" in low or "subscribe" in low or "t-h-e-l-e-d-g-r" in low:
        candidate = BRANDKIT_BEDS_DIR / "sponsor_bed_loop.mp3"
        if candidate.exists():
            bed_path = candidate
    elif any(k in low for k in ["patient", "mental health", "nurse", "hospital", "people", "human", "care"]):
        candidate = BRANDKIT_BEDS_DIR / "human_concern_bed_loop.mp3"
        if candidate.exists():
            bed_path = candidate
    elif any(k in low for k in ["lawsuit", "regulation", "ban", "security", "risk", "china", "export", "market", "revenue", "funding"]):
        candidate = BRANDKIT_BEDS_DIR / "suspense_bed_loop.mp3"
        if candidate.exists():
            bed_path = candidate

    if bed_path is None:
        return False

    bed = AudioSegment.from_file(bed_path)
    if len(bed) < len(voice_seg):
        loops = int(len(voice_seg) / max(1, len(bed))) + 1
        bed = bed * loops
    bed = bed[:len(voice_seg)]
    bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 2.0).fade_out(min(2200, max(500, int(len(voice_seg) * 0.35))))
    ducked = duck_music_under_voice(
        voice=voice_seg,
        music=bed,
        threshold_dbfs=DUCK_THRESHOLD_DBFS,
        duck_db=DUCK_AMOUNT_DB + 2.0,
        window_ms=DUCK_WINDOW_MS,
    )
    ducked.export(out_path, format="mp3", bitrate="192k")
    return True

def _eleven_tts_to_file(text: str, speaker: str, out_path: Path) -> None:
    voice_id = _eleven_voice_id(speaker)
    model_id = _eleven_model_id(speaker)
    payload = {
        "text": _eleven_prompted_text(speaker, text),
        "model_id": model_id,
        "voice_settings": _eleven_voice_settings(speaker),
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={ELEVEN_OUTPUT_FORMAT}"
    last_err = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            r = requests.post(url, headers=_eleven_headers(), json=payload, timeout=180)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            return
        except Exception as e:
            last_err = e
            sleep_s = min(12, 2 * attempt)
            _safe_print(f"    ⚠️ ElevenLabs TTS failed for {speaker} (attempt {attempt}/{TTS_RETRIES}): {e} — retrying in {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"ElevenLabs TTS failed for {speaker} after {TTS_RETRIES} retries: {last_err}")


def _generate_sound_effect_file(prompt: str, out_path: Path, *, duration_seconds: float | None = None, loop: bool = False, prompt_influence: float = 0.35) -> None:
    payload = {
        "text": prompt,
        "model_id": "eleven_text_to_sound_v2",
        "loop": loop,
        "prompt_influence": prompt_influence,
    }
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    url = "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128"
    r = requests.post(url, headers=_eleven_headers(), json=payload, timeout=180)
    r.raise_for_status()
    out_path.write_bytes(r.content)


def ensure_audio_brandkit() -> None:
    if AUDIO_BACKEND != "eleven":
        return
    if not AUTO_BUILD_AUDIO_BRANDKIT and not REBUILD_AUDIO_BRANDKIT:
        return

    manifest = {}
    if AUDIO_BRANDKIT_MANIFEST.exists():
        try:
            manifest = json.loads(AUDIO_BRANDKIT_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    spec = {
        str(BRANDKIT_SFX_DIR / "intro_sting_brand.mp3"): {
            "prompt": "premium futuristic podcast intro sting, dark blue tech energy, cinematic and restrained, confident, 2.8 seconds",
            "duration": 2.8,
            "loop": False,
        },
        str(BRANDKIT_SFX_DIR / "segment_transition_brand.mp3"): {
            "prompt": "tight premium podcast transition sting, subtle suspense, clean tech pulse, 1.2 seconds",
            "duration": 1.2,
            "loop": False,
        },
        str(BRANDKIT_SFX_DIR / "danger_sting_brand.mp3"): {
            "prompt": "short cinematic danger sting for regulation, lawsuit or security story, restrained but tense, 1.1 seconds",
            "duration": 1.1,
            "loop": False,
        },
        str(BRANDKIT_BEDS_DIR / "suspense_bed_loop.mp3"): {
            "prompt": "subtle suspense bed for premium AI podcast, low pulse, dark but elegant, no melody, seamless loop",
            "duration": 8.0,
            "loop": True,
        },
        str(BRANDKIT_BEDS_DIR / "human_concern_bed_loop.mp3"): {
            "prompt": "soft emotional underscore for human stakes in tech podcast, restrained, warm tension, seamless loop",
            "duration": 8.0,
            "loop": True,
        },
        str(BRANDKIT_BEDS_DIR / "sponsor_bed_loop.mp3"): {
            "prompt": "subtle premium sponsor bed for business intelligence podcast, clean, understated, seamless loop",
            "duration": 6.0,
            "loop": True,
        },
    }

    changed = False
    for path_str, meta in spec.items():
        p = Path(path_str)
        if p.exists() and not REBUILD_AUDIO_BRANDKIT:
            continue
        try:
            _safe_print(f" >> 🎛️ BRANDKIT: generating {p.name}...")
            _generate_sound_effect_file(meta["prompt"], p, duration_seconds=meta["duration"], loop=meta["loop"])
            manifest[p.name] = meta
            changed = True
        except Exception as e:
            _safe_print(f"    ⚠️ Brandkit generation failed for {p.name}: {e}")
    if changed:
        AUDIO_BRANDKIT_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

def _voice_speed(speaker: str) -> float:
    return {
        "ALEX": ALEX_SPEED,
        "JAMIE": JAMIE_SPEED,
        "RUFUS": RUFUS_SPEED,
    }.get(speaker.upper(), 1.0)


def tts_to_file(text: str, speaker: str, out_path: Path) -> None:
    speaker = speaker.upper()
    model = VOICE_MODEL_MAP.get(speaker, OPENAI_TTS_MODEL)
    voice = VOICE_MAP.get(speaker, "onyx")
    instructions = VOICE_INSTRUCTIONS.get(speaker, "").strip()

    last_err = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            if model == "gpt-4o-mini-tts" and instructions:
                with openai_client.audio.speech.with_streaming_response.create(
                    model=model,
                    voice=voice,
                    input=text,
                    instructions=instructions,
                ) as resp:
                    resp.stream_to_file(str(out_path))
            else:
                with openai_client.audio.speech.with_streaming_response.create(
                    model=model,
                    voice=voice,
                    input=text,
                ) as resp:
                    resp.stream_to_file(str(out_path))
            return
        except Exception as e:
            last_err = e
            sleep_s = min(10, 1.5 * attempt)
            _safe_print(f"    ⚠️ TTS failed for {speaker} (attempt {attempt}/{TTS_RETRIES}): {e} — retrying in {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"TTS failed for {speaker} after {TTS_RETRIES} retries: {last_err}")


def apply_speed_ffmpeg(in_path: Path, out_path: Path, speed: float) -> None:
    if abs(speed - 1.0) < 1e-6:
        shutil.copyfile(in_path, out_path)
        return
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found; required for JAMIE speed adjustment.")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-filter:a", f"atempo={speed:.4f}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)


def stitch_with_ffmpeg(file_list: List[Path], out_path: Path) -> None:
    concat_txt = out_path.parent / f"concat_{uuid.uuid4().hex}.txt"

    def esc(p: Path) -> str:
        s = str(p)
        return s.replace("'", "'\\''")

    concat_txt.write_text("\n".join([f"file '{esc(p)}'" for p in file_list]), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-af", "aresample=async=1:first_pts=0",
        "-avoid_negative_ts", "make_zero",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)

    try:
        concat_txt.unlink()
    except Exception:
        pass


def stitch_with_pydub(file_list: List[Path], out_path: Path) -> None:
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found in runner (required by pydub decode).")
    combined = AudioSegment.empty()
    for p in file_list:
        seg = AudioSegment.from_file(p)
        if len(combined) == 0 or CROSSFADE_MS <= 0:
            combined += seg
        else:
            combined = combined.append(seg, crossfade=min(CROSSFADE_MS, len(seg), len(combined)))
    combined.export(out_path, format="mp3", bitrate="192k")


def stitch_audio(file_list: List[Path], out_path: Path) -> None:
    if STITCH_METHOD == "ffmpeg":
        stitch_with_ffmpeg(file_list, out_path)
    else:
        stitch_with_pydub(file_list, out_path)


# ----------------------------
# MARKETING (best-effort)
# ----------------------------
def run_marketing_pipeline() -> None:
    if not RUN_MARKETING_ASSETS:
        _safe_print(" >> 📣 MARKETING: disabled (RUN_MARKETING_ASSETS=false)")
        return

    _safe_print(" >> 📣 MARKETING: generating assets (best-effort)...")
    for script_name in ["marketing_engine.py", "generate_social.py", "animate_social.py", "animate_hook.py"]:
        p = BASE_DIR / script_name
        if p.exists():
            _safe_print(f"    → running {script_name}")
            _run([sys.executable, str(p)], fail_ok=True)

    if PUBLISH_SOCIAL:
        pub = BASE_DIR / "social_publisher.py"
        if pub.exists():
            _safe_print("    → publishing social (PUBLISH_SOCIAL=true)")
            _run([sys.executable, str(pub)], fail_ok=True)


def _hashtags_from_stories(stories: List[Dict[str, str]], max_tags: int = 6) -> str:
    tags: List[str] = ["#AI", "#TheAIEdge"]
    bucket_tags = {"health_ai": "#HealthAI", "ai_tools": "#AITools", "ai_code": "#AICode", "ai_agents": "#AIAgents", "topline": "#AINews"}
    for s in stories[:5]:
        tag = bucket_tags.get(_normalize_vertical_bucket(s.get("bucket", "")))
        if tag:
            tags.append(tag)
    entities: List[str] = []
    for s in stories[:5]:
        if isinstance(s.get("key_entities"), list):
            entities.extend([str(x).strip() for x in s.get("key_entities") if str(x).strip()])
        entities.extend(re.findall(r"\b[A-Z][A-Za-z0-9]+\b", (s.get("headline") or "")))
    for ent in entities:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", ent).lower()
        if cleaned in MAJOR_HASHTAG_ALLOWLIST:
            tags.append(MAJOR_HASHTAG_ALLOWLIST[cleaned])
    seen = set()
    uniq: List[str] = []
    for t in tags:
        if not t or t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    return " ".join(uniq[:max_tags])


def _smart_trim_text(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip().strip(" -—:|,")
    if len(cleaned) <= max_len:
        return cleaned
    cut_zone = cleaned[: max_len + 1]
    cut = max(cut_zone.rfind(" — "), cut_zone.rfind(" | "), cut_zone.rfind(": "), cut_zone.rfind(", "), cut_zone.rfind(" "))
    if cut < int(max_len * 0.65):
        cut = max_len
    return cleaned[:cut].rstrip(" -—:|,")


def _clean_packaging_text(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"\|\s*(news and statistics|news|statistics).*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\|\s*(ai infrastructure).*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" -—:|")
    return _smart_trim_text(cleaned, max_len)


def _title_support_phrase(top_story: Dict[str, str], title_style: str) -> str:
    blob = _story_numeric_blob(top_story)
    has_number = bool(re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d{4}\b|\b\d+[mkb]?\b", blob, flags=re.IGNORECASE))
    if title_style == "hard_number":
        return "What the Numbers Mean" if has_number else "The Real Risk"
    if title_style == "tomorrow_tension":
        return "Why Tomorrow Gets Harder"
    return "What It Means Next"


def _compose_episode_title(stories: List[Dict[str, str]], title_style: str, date_str: str) -> str:
    top_story = stories[0] if stories else {}
    headline = _clean_packaging_text((top_story.get("headline") or "AI Just Moved — Here's What Changed").strip(), 68)
    support = _title_support_phrase(top_story, title_style)
    max_base = max(32, EPISODE_META_MAX_TITLE - len(f" — {date_str}"))
    raw = f"{headline} | {support}"
    if len(raw) > max_base:
        raw = headline
    return _smart_trim_text(raw, max_len=max_base)


def build_episode_show_notes(
    tracking: Dict[str, str],
    pack: Dict[str, str],
    stories: List[Dict[str, str]],
) -> str:
    cta_url = PUBLIC_SUBSCRIBE_URL
    story_bullets = "\n".join([f"• {s.get('headline','')}" for s in stories[:5]])
    tomorrow_tease = (pack.get("tomorrow_tease") or "The second-order consequences are just starting to show.").strip()
    episode_blurb = (pack.get("episode_blurb") or "Today on The AI Edge, Alex, Jamie, and Rufus break down what matters, what changes tomorrow, and what serious operators should watch next.").strip()
    parts = [f"Subscribe to TheLEDGR: {cta_url}", "", "If AI affects your work, your team, your company, your product roadmap, or your career, you should be reading TheLEDGR.", "", "TheLEDGR is a daily AI intelligence network built to help you make better decisions faster, cut through noise, and walk into your day sharper.", "", "This is not more AI content. It is signal you can actually use in real life.", "", episode_blurb, "", "What we covered:", story_bullets, "", "Tomorrow tension:", tomorrow_tease or "The next 24 hours will matter more than the launch headlines."]
    return "\n".join(parts).strip()


def generate_marketing_pack(
    stories: List[Dict[str, str]],
    date_str: str,
    listen_url: str,
    tracking: Optional[Dict[str, str]] = None,
    experiments: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    tracking = tracking or {}
    experiments = experiments or {}
    ordered = order_stories_for_episode(stories[:5])
    top_story = ordered[0] if ordered else {}
    title_style = experiments.get("title_style", "operator_consequence")
    cta_style = experiments.get("cta_style", "operator")
    top_headline = _clean_packaging_text((top_story.get("headline") or "AI JUST MOVED — HERE'S WHAT CHANGED").strip(), 72)
    top_data = " | ".join([str(x).strip() for x in (top_story.get("data_points") or [])[:2] if str(x).strip()])
    subscribe_url = PUBLIC_SUBSCRIBE_URL
    listen_cta = tracking.get("listen", listen_url)
    hashtags = _hashtags_from_stories(ordered, max_tags=6)
    yt_title = _compose_episode_title(ordered, title_style, date_str)
    if cta_style == "career":
        cta_line = f"If AI can affect your role, your team, or your next promotion, subscribe to TheLEDGR: {subscribe_url}"
    elif cta_style == "contrarian":
        cta_line = f"Most people will read the headline and miss the consequence. TheLEDGR is for the people who do not. Subscribe: {subscribe_url}"
    else:
        cta_line = f"If AI affects your work, subscribe to TheLEDGR for decision-grade signal: {subscribe_url}"
    fallback_hook = _smart_trim_text((top_headline if top_headline else "AI JUST MOVED — HERE'S WHAT CHANGED"), 64).upper()
    story_bullets = "\n".join([f"• {s.get('headline','')}" for s in ordered[:5]])
    tomorrow_tease = next((s.get("tomorrow_hook", "").strip() for s in ordered if (s.get("tomorrow_hook") or "").strip()), "The second-order consequences are just starting to show.")
    return {
        "hook": fallback_hook,
        "tweet1": f"{fallback_hook}\n\nThis is the part most people will miss: the consequence.\n\nListen: {listen_cta}",
        "tweet2": f"{cta_line}\n\n{hashtags}",
        "yt_title": yt_title,
        "yt_description": (f"Listen now: {listen_cta}\n\n" f"What we covered:\n{story_bullets}\n\n" f"Key data: {top_data or 'See full episode for the facts and consequence chain.'}\n\n" f"{cta_line}")[:1200],
        "show_notes": (f"What we covered:\n{story_bullets}\n\n" f"Tomorrow tension: {tomorrow_tease}\n\n" f"{cta_line}"),
        "tomorrow_tease": tomorrow_tease,
        "seo_keywords": "AI news, enterprise AI, AI agents, health AI, AI tools, AI coding, AI strategy",
        "hashtags": hashtags,
    }


# ----------------------------
# RSS FEED WRITER
# ----------------------------
def update_feed_xml(meta: Dict) -> None:
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ATOM_NS = "http://www.w3.org/2005/Atom"

    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("atom", ATOM_NS)

    def rfc2822_from_date(datestr: str) -> str:
        try:
            dtx = datetime.datetime.strptime(datestr, "%Y-%m-%d")
            dtx = dtx.replace(hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc)
        except Exception:
            dtx = datetime.datetime.now(datetime.timezone.utc)
        return dtx.strftime("%a, %d %b %Y %H:%M:%S -0000")

    def rfc2822_now() -> str:
        dtx = datetime.datetime.now(datetime.timezone.utc)
        return dtx.strftime("%a, %d %b %Y %H:%M:%S -0000")

    def safe_url_join(base: str, filename: str) -> str:
        return base.rstrip("/") + "/" + quote(filename)

    def is_valid_episode_filename(name: str) -> bool:
        return bool(STRICT_EPISODE_FILENAME_RE.match(name or ""))

    def file_ok_for_feed(p: Path) -> bool:
        try:
            return p.exists() and p.stat().st_size >= MIN_MP3_BYTES_FEED
        except Exception:
            return False

    def make_item(title: str, description: str, audio_filename: str, pubdate_rfc2822: str,
                  duration_seconds: int = 0) -> ET.Element:
        item = ET.Element("item")
        ET.SubElement(item, "title").text = (title or "")[:EPISODE_META_MAX_TITLE]
        ET.SubElement(item, "description").text = (description or "")[:8000]
        ET.SubElement(item, f"{{{ITUNES_NS}}}summary").text = (description or "")[:8000]

        audio_url = safe_url_join(AUDIO_BASE_URL, audio_filename)
        guid_el = ET.SubElement(item, "guid")
        guid_el.set("isPermaLink", "false")
        guid_el.text = audio_url

        ET.SubElement(item, "pubDate").text = pubdate_rfc2822

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", audio_url)
        enclosure.set("type", "audio/mpeg")
        try:
            length_bytes = int((AUDIO_DIR / audio_filename).stat().st_size)
        except Exception:
            length_bytes = 0
        enclosure.set("length", str(length_bytes))

        if duration_seconds and duration_seconds > 0:
            dur = ET.SubElement(item, f"{{{ITUNES_NS}}}duration")
            dur.text = str(int(duration_seconds))

        ep_img = ET.SubElement(item, f"{{{ITUNES_NS}}}image")
        ep_img.set("href", RSS_SETTINGS["image"])
        ET.SubElement(item, f"{{{ITUNES_NS}}}episodeType").text = "full"
        return item

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = LISTEN_URL.rstrip("/") + "/"
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()

    atom_link = ET.SubElement(channel, f"{{{ATOM_NS}}}link")
    feed_href = (LISTEN_URL.rstrip("/") + "/feed.xml").replace("/listen/feed.xml", "/feed.xml")
    atom_link.set("href", feed_href)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = RSS_SETTINGS["author"]
    ET.SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = "no"
    ET.SubElement(channel, f"{{{ITUNES_NS}}}type").text = "episodic"

    cat = ET.SubElement(channel, f"{{{ITUNES_NS}}}category")
    cat.set("text", RSS_SETTINGS["category"])

    img = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    ET.SubElement(owner, f"{{{ITUNES_NS}}}name").text = RSS_SETTINGS["author"]
    ET.SubElement(owner, f"{{{ITUNES_NS}}}email").text = RSS_SETTINGS["email"]

    mp3s = sorted(AUDIO_DIR.glob("podcast_*.mp3"), key=lambda p: p.name, reverse=True)

    items_added = 0
    for mp3 in mp3s:
        if items_added >= KEEP_LAST_EPISODES:
            break
        if not is_valid_episode_filename(mp3.name):
            continue
        if not file_ok_for_feed(mp3):
            continue

        date_str = _date_from_episode_filename(mp3.name) or datetime.date.today().isoformat()
        sidecar = _load_sidecar_meta_for_date(date_str)

        title = (sidecar.get("title") or f"{RSS_SETTINGS['title']} — {date_str}").strip()
        desc = (sidecar.get("description") or f"Listen: {LISTEN_URL}").strip()

        dur = 0
        if meta.get("audio_file") == mp3.name:
            title = (meta.get("title") or title).strip()
            desc = (meta.get("show_notes") or desc).strip()
            dur = int(meta.get("duration_seconds") or 0)

        channel.append(make_item(
            title=title,
            description=desc,
            audio_filename=mp3.name,
            pubdate_rfc2822=rfc2822_from_date(date_str),
            duration_seconds=dur,
        ))
        items_added += 1

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    _safe_print(f"✅ feed.xml rebuilt from local episodes: {items_added} items")


# ----------------------------
# PRODUCER
# ----------------------------
def _maybe_append_date(title: str, date_str: str) -> str:
    t = _smart_trim_text((title or "").strip(), max(24, EPISODE_META_MAX_TITLE - len(f" — {date_str}")))
    if not t:
        return f"{RSS_SETTINGS['title']} — {date_str}"[:EPISODE_META_MAX_TITLE]
    if date_str in t:
        return t[:EPISODE_META_MAX_TITLE].strip()
    return f"{t} — {date_str}"[:EPISODE_META_MAX_TITLE].strip()


def _file_ok_min_bytes(p: Path) -> bool:
    try:
        return p.exists() and p.stat().st_size >= MIN_MP3_BYTES_FEED
    except Exception:
        return False


def produce_episode() -> None:
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg is required for stitching and mastering. Install it on runner/host.")
    _require_intro_outro_if_needed()
    ensure_audio_brandkit()

    today = datetime.date.today().isoformat()
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"

    if final_mp3.exists() and _file_ok_min_bytes(final_mp3) and not FORCE_REBUILD:
        _safe_print(f"🛑 Today's episode already exists ({final_mp3.name}). Set FORCE_REBUILD=true to regenerate.")
        try:
            final_audio = AudioSegment.from_mp3(final_mp3)
            duration_seconds = int(len(final_audio) / 1000)
        except Exception:
            duration_seconds = 0

        sidecar = _load_sidecar_meta_for_date(today)
        meta = {
            "date": today,
            "title": sidecar.get("title") or f"{RSS_SETTINGS['title']} — {today}",
            "listen_url": LISTEN_URL,
            "minutes": round(duration_seconds / 60.0, 2) if duration_seconds else 0,
            "audio_file": final_mp3.name,
            "audio_url": AUDIO_BASE_URL + final_mp3.name,
            "duration_seconds": duration_seconds,
            "show_notes": sidecar.get("description") or f"LISTEN: {LISTEN_URL}",
        }
        update_feed_xml(meta)
        return

    _safe_print(" >> 📰 GATHERING INTEL (RSS PRIMARY)...")
    intel = broaden_intel_pool()
    if not intel:
        _safe_print("    ⚠️ RSS empty. Using test item.")
        intel = [{
            "bucket": "Test",
            "title": "Test: AI model sparks market panic",
            "publisher": "TestWire",
            "published": today,
            "link": "https://example.com",
            "summary": "Simulation. $500M wiped. 24 hours. 3 regulators. 1 leak."
        }]

    candidate_debug = select_story_candidates(intel, n=30, memory=load_show_memory(), bucket_cap=3)
    STORY_SCORES_PATH.write_text(
        json.dumps(build_story_debug_table(candidate_debug), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    experiments = choose_episode_experiments(seed=today)
    sponsors = apply_sponsor_variant(load_sponsors(), experiments=experiments, spoken_url=THELEDGR_SPOKEN_URL)
    stories = order_stories_for_episode(pick_top_stories(intel, n=5))
    if len(stories) < 5:
        _safe_print(f"    ⚠️ Story slate thin after selection ({len(stories)}). Broadening and retrying...")
        intel = broaden_intel_pool()
        candidate_debug = select_story_candidates(intel, n=40, memory=load_show_memory(), bucket_cap=3)
        STORY_SCORES_PATH.write_text(json.dumps(build_story_debug_table(candidate_debug), indent=2, ensure_ascii=False), encoding="utf-8")
        stories = order_stories_for_episode(pick_top_stories(intel, n=5))
    if len(stories) < 5:
        raise RuntimeError(f"Unable to build a 5-story slate. Only {len(stories)} stories survived intake + selection.")

    _safe_print(" >> ✍️ WRITING FULL EPISODE (5 segments)...")
    script = generate_episode_script(stories, sponsors, today)
    script = enforce_episode_numeric_density(script, stories, today)
    script = _sanitize_dialogue_only(script)

    issues = validate_script(script, stories=stories)
    if issues:
        raise RuntimeError("Script validation failed:\n" + "\n".join(issues))

    if SAVE_SCRIPT:
        script_path = BASE_DIR / f"script_{today}.txt"
        script_path.write_text(script, encoding="utf-8")
        _safe_print(f"    ✅ Saved script: {script_path.name}")

    dialogue = iter_dialogue(script)
    render_items = _build_eleven_render_items(dialogue) if AUDIO_BACKEND == "eleven" else merge_dialogue_for_tts(dialogue, max_chars=TTS_MERGE_MAX_CHARS)

    run_tmp = TMP_AUDIO_DIR / today
    if run_tmp.exists():
        shutil.rmtree(run_tmp, ignore_errors=True)
    run_tmp.mkdir(parents=True, exist_ok=True)

    concat_files: List[Path] = []

    silence_path = run_tmp / "silence_80ms.mp3"
    quote_pause_path = run_tmp / "silence_forwardable.mp3"
    AudioSegment.silent(duration=80).export(silence_path, format="mp3", bitrate="192k")
    AudioSegment.silent(duration=FORWARDABLE_PAUSE_MS).export(quote_pause_path, format="mp3", bitrate="192k")

    intro_stinger_seg: Optional[AudioSegment] = None
    outro_seg: Optional[AudioSegment] = None
    transition_seg: Optional[AudioSegment] = None

    if INTRO_PATH.exists():
        intro_stinger_seg = load_stinger(
            INTRO_PATH,
            ms=INTRO_STINGER_MS,
            target_dbfs=STINGER_TARGET_DBFS,
            fade_in_ms=INTRO_FADE_IN_MS,
            fade_out_ms=INTRO_FADE_OUT_MS,
        )

    if OUTRO_PATH.exists():
        outro_seg = load_stinger(
            OUTRO_PATH,
            ms=OUTRO_MS,
            target_dbfs=STINGER_TARGET_DBFS,
            fade_in_ms=OUTRO_FADE_IN_MS,
            fade_out_ms=OUTRO_FADE_OUT_MS,
        )

    if TRANSITION_PATH.exists():
        transition_seg = load_stinger(
            TRANSITION_PATH,
            ms=TRANSITION_MS,
            target_dbfs=STINGER_TARGET_DBFS,
            fade_in_ms=TRANSITION_FADE_IN_MS,
            fade_out_ms=TRANSITION_FADE_OUT_MS,
        )

    _safe_print(" >> 🎙️ RECORDING (TTS + assembly)...")

    seg_idx = 0
    intro_done = False
    pending_intro_bed = False
    pending_segment_bed = False

    for speaker, text in render_items:
        if speaker == "MUSIC":
            if not intro_done:
                # Guaranteed audible intro stinger
                if intro_stinger_seg is not None:
                    p = run_tmp / "intro_stinger.mp3"
                    intro_stinger_seg.export(p, format="mp3", bitrate="192k")
                    concat_files.append(p)
                    concat_files.append(silence_path)
                pending_intro_bed = True
                intro_done = True
            else:
                if transition_seg is not None:
                    p = run_tmp / f"transition_{uuid.uuid4().hex[:8]}.mp3"
                    transition_seg.export(p, format="mp3", bitrate="192k")
                    concat_files.append(p)
                    concat_files.append(silence_path)
                    pending_segment_bed = True
                else:
                    concat_files.append(silence_path)
            continue

        if speaker == "SCENE":
            scene = text
            seg_idx += 1
            raw_path = run_tmp / f"{today}_scene_{seg_idx:04d}_dialogue_raw.mp3"
            _eleven_dialogue_to_file(scene, raw_path)
            post_process_tts_mp3(raw_path)
            final_voice_path = raw_path
            scene_text = " ".join([t for _, t in scene])
            mixed_scene_path = run_tmp / f"{today}_scene_{seg_idx:04d}_mix.mp3"
            if _mix_brand_bed_if_needed(final_voice_path, scene_text, "ALEX", mixed_scene_path):
                final_voice_path = mixed_scene_path

            if pending_intro_bed and INTRO_PATH.exists():
                pending_intro_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = AudioSegment.from_file(INTRO_PATH)
                bed = bed[:min(INTRO_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS).fade_out(INTRO_BED_FADE_OUT_MS)
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB,
                    window_ms=DUCK_WINDOW_MS,
                )
                mix_path = run_tmp / f"{today}_scene_{seg_idx:04d}_introbed_mix.mp3"
                ducked.export(mix_path, format="mp3", bitrate="192k")
                concat_files.append(mix_path)
            elif pending_segment_bed and transition_seg is not None:
                pending_segment_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = transition_seg[:min(SEGMENT_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 1.5).fade_out(SEGMENT_BED_FADE_OUT_MS)
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB + 1.5,
                    window_ms=DUCK_WINDOW_MS,
                )
                mix_path = run_tmp / f"{today}_scene_{seg_idx:04d}_segmentbed_mix.mp3"
                ducked.export(mix_path, format="mp3", bitrate="192k")
                concat_files.append(mix_path)
            else:
                concat_files.append(final_voice_path)

            concat_files.append(quote_pause_path if is_forwardable_line_text(scene_text) else silence_path)
            continue

        chunks = chunk_text(text, max_chars=_tts_chunk_max_chars(speaker))

        for chunk in chunks:
            seg_idx += 1
            raw_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_raw.mp3"
            tts_to_file(chunk, speaker, raw_path)
            post_process_tts_mp3(raw_path)

            final_voice_path = raw_path
            speaker_speed = _voice_speed(speaker)
            if abs(speaker_speed - 1.0) > 1e-6:
                sped_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_spd.mp3"
                apply_speed_ffmpeg(raw_path, sped_path, speaker_speed)
                post_process_tts_mp3(sped_path)
                final_voice_path = sped_path

            mixed_voice_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_mix.mp3"
            if AUDIO_BACKEND == "eleven" and _mix_brand_bed_if_needed(final_voice_path, chunk, speaker, mixed_voice_path):
                final_voice_path = mixed_voice_path

            if pending_intro_bed and INTRO_PATH.exists():
                pending_intro_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = AudioSegment.from_file(INTRO_PATH)
                bed = bed[:min(INTRO_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS).fade_out(INTRO_BED_FADE_OUT_MS)
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB,
                    window_ms=DUCK_WINDOW_MS,
                )
                mix_path = run_tmp / f"{today}_seg_{seg_idx:04d}_introbed_mix.mp3"
                ducked.export(mix_path, format="mp3", bitrate="192k")
                concat_files.append(mix_path)
            elif pending_segment_bed and transition_seg is not None:
                pending_segment_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = transition_seg[:min(SEGMENT_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 1.5).fade_out(SEGMENT_BED_FADE_OUT_MS)
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB + 1.5,
                    window_ms=DUCK_WINDOW_MS,
                )
                mix_path = run_tmp / f"{today}_seg_{seg_idx:04d}_segmentbed_mix.mp3"
                ducked.export(mix_path, format="mp3", bitrate="192k")
                concat_files.append(mix_path)
            else:
                concat_files.append(final_voice_path)

            concat_files.append(quote_pause_path if is_forwardable_line_text(chunk) else silence_path)

    if outro_seg is not None:
        p = run_tmp / "outro.mp3"
        outro_seg.export(p, format="mp3", bitrate="192k")
        concat_files.append(p)

    _safe_print(f" >> 🎚️ STITCHING ({STITCH_METHOD})...")
    stitch_audio(concat_files, final_mp3)

    _safe_print(" >> 🎛️ MASTERING (loudness normalize)...")
    mastered = run_tmp / f"{today}_mastered.mp3"
    master_final_audio_ffmpeg(final_mp3, mastered)
    shutil.copyfile(mastered, final_mp3)

    final_audio = AudioSegment.from_mp3(final_mp3)
    duration_seconds = int(len(final_audio) / 1000)
    minutes = duration_seconds / 60.0
    _safe_print(f" ✅ EPISODE COMPLETE: {final_mp3.name} ({minutes:.2f} minutes)")

    SHORTFALL_TOLERANCE_SECONDS = 30

    if minutes < MIN_MINUTES:
        shortfall_seconds = int(round((MIN_MINUTES - minutes) * 60))

        if shortfall_seconds <= SHORTFALL_TOLERANCE_SECONDS:
            _safe_print(
                f" ⚠️ Episode short by {shortfall_seconds}s. "
                f"Auto-padding to {MIN_MINUTES:.2f} minutes."
            )

            padded_audio = final_audio + AudioSegment.silent(duration=shortfall_seconds * 1000)
            padded_audio.export(final_mp3, format="mp3", bitrate="192k")

            final_audio = AudioSegment.from_mp3(final_mp3)
            duration_seconds = int(len(final_audio) / 1000)
            minutes = duration_seconds / 60.0

            _safe_print(
                f" ✅ EPISODE PADDED: {final_mp3.name} ({minutes:.2f} minutes)"
            )
        else:
            raise RuntimeError(
                f"Episode length out of bounds ({minutes:.2f} min). "
                f"Must be {MIN_MINUTES}-{MAX_MINUTES}."
            )

    elif minutes > MAX_MINUTES:
        raise RuntimeError(
            f"Episode length out of bounds ({minutes:.2f} min). "
            f"Must be {MIN_MINUTES}-{MAX_MINUTES}."
        )

    provisional_tracking = build_episode_tracking_payload(
        date_str=today,
        episode_title=stories[0].get("headline", RSS_SETTINGS["title"]),
        listen_url=LISTEN_URL,
        subscribe_url=THELEDGR_SUBSCRIBE_URL,
        experiments=experiments,
    )
    pack = generate_marketing_pack(stories, today, LISTEN_URL, tracking=provisional_tracking, experiments=experiments)
    feed_title = _maybe_append_date(pack.get("yt_title", RSS_SETTINGS["title"]), today)
    tracking = build_episode_tracking_payload(
        date_str=today,
        episode_title=feed_title,
        listen_url=LISTEN_URL,
        subscribe_url=THELEDGR_SUBSCRIBE_URL,
        experiments=experiments,
    )
    pack = generate_marketing_pack(stories, today, LISTEN_URL, tracking=tracking, experiments=experiments)

    TRACKING_SUMMARY_PATH.write_text(json.dumps(tracking, indent=2, ensure_ascii=False), encoding="utf-8")

    forwardable_moments = extract_forwardable_moments(script, stories=stories, max_items=4)
    FORWARDABLE_MOMENTS_PATH.write_text(json.dumps(forwardable_moments, indent=2, ensure_ascii=False), encoding="utf-8")

    show_notes = build_episode_show_notes(tracking, pack, stories)

    _write_sidecar_meta_for_date(today, title=feed_title, description=show_notes)

    viral_caption = "\n".join([
        (pack.get("tweet1", "") or "").strip(),
        "",
        (pack.get("tweet2", "") or "").strip(),
        "",
        (pack.get("hashtags", "") or "").strip(),
    ]).strip()

    (BASE_DIR / "viral_caption.txt").write_text(viral_caption, encoding="utf-8")
    (BASE_DIR / "marketing_pack.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")

    meta = {
        "date": today,
        "title": feed_title,
        "listen_url": LISTEN_URL,
        "minutes": round(minutes, 2),
        "audio_file": final_mp3.name,
        "audio_url": AUDIO_BASE_URL + final_mp3.name,
        "stories": stories,
        "marketing_pack": pack,
        "duration_seconds": duration_seconds,
        "show_notes": show_notes,
        "tracking": tracking,
        "experiments": experiments,
        "model_version": MODEL_VERSION,
        "forwardable_moments": forwardable_moments,
    }
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    update_feed_xml(meta)
    run_marketing_pipeline()

    if CLEANUP_TEMP:
        shutil.rmtree(run_tmp, ignore_errors=True)


if __name__ == "__main__":
    produce_episode()