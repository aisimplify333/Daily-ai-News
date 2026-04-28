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
ELEVEN_VOICE_ID_JAMIE = os.getenv("ELEVEN_VOICE_ID_JAMIE", "uYXf8XasLslADfZ2MB4u").strip()
ELEVEN_VOICE_ID_RUFUS = os.getenv("ELEVEN_VOICE_ID_RUFUS", "Fahco4VZzobUeiPqni1S").strip()
ELEVEN_STABILITY_ALEX = float(os.getenv("ELEVEN_STABILITY_ALEX", "0.38"))
ELEVEN_STABILITY_JAMIE = float(os.getenv("ELEVEN_STABILITY_JAMIE", "0.34"))
ELEVEN_STABILITY_RUFUS = float(os.getenv("ELEVEN_STABILITY_RUFUS", "0.34"))
ELEVEN_SIMILARITY_ALEX = float(os.getenv("ELEVEN_SIMILARITY_ALEX", "0.82"))
ELEVEN_SIMILARITY_JAMIE = float(os.getenv("ELEVEN_SIMILARITY_JAMIE", "0.80"))
ELEVEN_SIMILARITY_RUFUS = float(os.getenv("ELEVEN_SIMILARITY_RUFUS", "0.84"))
ELEVEN_STYLE_ALEX = float(os.getenv("ELEVEN_STYLE_ALEX", "0.28"))
ELEVEN_STYLE_JAMIE = float(os.getenv("ELEVEN_STYLE_JAMIE", "0.32"))
ELEVEN_STYLE_RUFUS = float(os.getenv("ELEVEN_STYLE_RUFUS", "0.30"))
ELEVEN_USE_SPEAKER_BOOST = os.getenv("ELEVEN_USE_SPEAKER_BOOST", "true").strip().lower() in ("1","true","yes")
AUTO_BUILD_AUDIO_BRANDKIT = os.getenv("AUTO_BUILD_AUDIO_BRANDKIT", "true").strip().lower() in ("1","true","yes")
REBUILD_AUDIO_BRANDKIT = os.getenv("REBUILD_AUDIO_BRANDKIT", "false").strip().lower() in ("1","true","yes")
ELEVEN_USE_DIALOGUE_SCENES = os.getenv("ELEVEN_USE_DIALOGUE_SCENES", "true").strip().lower() in ("1","true","yes")
ALEX_USE_OPENAI = os.getenv("ALEX_USE_OPENAI", "true").strip().lower() in ("1","true","yes")
ELEVEN_SCENE_MAX_TURNS = int(os.getenv("ELEVEN_SCENE_MAX_TURNS", "7"))
ELEVEN_SCENE_MAX_CHARS = int(os.getenv("ELEVEN_SCENE_MAX_CHARS", "1500"))
ELEVEN_SCENE_PAUSE_MS = int(os.getenv("ELEVEN_SCENE_PAUSE_MS", "120"))
ELEVEN_FALLBACK_TO_OPENAI = os.getenv("ELEVEN_FALLBACK_TO_OPENAI", "false").strip().lower() in ("1","true","yes")
ELEVEN_FALLBACK_SPEAKERS = {
    s.strip().upper()
    for s in os.getenv("ELEVEN_FALLBACK_SPEAKERS", "JAMIE,RUFUS").split(",")
    if s.strip()
}
_ELEVEN_FORCE_OPENAI_GLOBAL = False
_ELEVEN_FORCE_OPENAI_SPEAKERS: set[str] = set()
_ELEVEN_FALLBACK_NOTICE_EMITTED = False

# Episode length gates (minutes)
MIN_MINUTES = float(os.getenv("MIN_MINUTES", "19"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "26"))
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
    "JAMIE": os.getenv("VOICE_JAMIE", "shimmer"),
    "RUFUS": os.getenv("VOICE_RUFUS", "fable"),
}

VOICE_INSTRUCTIONS: Dict[str, str] = {
    "ALEX": (
        "Sound like a high-agency Joe Rogan-style host who runs the room. "
        "He is curious, amused by tension, quick to challenge weak framing, and never passive. "
        "He does NOT interrupt every beat; when Jamie and Rufus are cooking, he lets them go a few turns before cutting back in with force. "
        "He should sound entertained by the stakes, confident, and slightly dangerous when a number or contradiction lands."
    ),
    "JAMIE": (
        "Sound extremely intelligent, polished, and emotionally alive. "
        "She is executive-bright, fast, articulate, and credible. "
        "She can get irritated, incredulous, dramatic, or disgusted when the story deserves it. "
        "She should sound like a serious professional reacting in real time with warmth, bite, and clear judgment."
    ),
    "RUFUS": (
        "Sound like a dry British analyst with elite verbal precision, dry wit, and occasional withering amusement. "
        "He keeps his British sayings, lands the hardest numbers cleanly, and undercuts hype with quiet menace and elegant sarcasm. "
        "He is serious, but never flat. He sounds like the cleverest person in the room and knows it."
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

ALEX_SPEED = float(os.getenv("ALEX_SPEED", "1.06"))
JAMIE_SPEED = float(os.getenv("JAMIE_SPEED", "1.00"))
RUFUS_SPEED = float(os.getenv("RUFUS_SPEED", "1.02"))

ALEX_GAIN_DB = float(os.getenv("ALEX_GAIN_DB", "3.5"))
JAMIE_GAIN_DB = float(os.getenv("JAMIE_GAIN_DB", "1.0"))
RUFUS_GAIN_DB = float(os.getenv("RUFUS_GAIN_DB", "0.3"))

# Post-processing thresholds
TRIM_LEADING_MS = int(os.getenv("TRIM_LEADING_MS", "60"))
TRIM_TRAILING_MS = int(os.getenv("TRIM_TRAILING_MS", "95"))
TRIM_THRESH_DB = float(os.getenv("TRIM_THRESH_DB", "-45.0"))
SEGMENT_EXPORT_BITRATE = os.getenv("SEGMENT_EXPORT_BITRATE", "192k")
TAIL_PAD_MS = int(os.getenv("TAIL_PAD_MS", "85"))

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
SEGMENT_BED_MS = int(os.getenv("SEGMENT_BED_MS", "1800"))
SEGMENT_BED_FADE_OUT_MS = int(os.getenv("SEGMENT_BED_FADE_OUT_MS", "700"))

OUTRO_MS = int(os.getenv("OUTRO_MS", "12000"))
TRANSITION_MS = int(os.getenv("TRANSITION_MS", "1600"))

STINGER_TARGET_DBFS = float(os.getenv("STINGER_TARGET_DBFS", "-18.0"))

INTRO_FADE_IN_MS = int(os.getenv("INTRO_FADE_IN_MS", "120"))
INTRO_FADE_OUT_MS = int(os.getenv("INTRO_FADE_OUT_MS", "900"))

OUTRO_FADE_IN_MS = int(os.getenv("OUTRO_FADE_IN_MS", "800"))
OUTRO_FADE_OUT_MS = int(os.getenv("OUTRO_FADE_OUT_MS", "1200"))

TRANSITION_FADE_IN_MS = int(os.getenv("TRANSITION_FADE_IN_MS", "120"))
TRANSITION_FADE_OUT_MS = int(os.getenv("TRANSITION_FADE_OUT_MS", "350"))

CROSSFADE_MS = int(os.getenv("CROSSFADE_MS", "0"))  # 40–80 if desired

# Ducking parameters
MUSIC_TARGET_DBFS = float(os.getenv("MUSIC_TARGET_DBFS", "-27.0"))
DUCK_THRESHOLD_DBFS = float(os.getenv("DUCK_THRESHOLD_DBFS", "-34.0"))
DUCK_AMOUNT_DB = float(os.getenv("DUCK_AMOUNT_DB", "14.0"))
DUCK_WINDOW_MS = int(os.getenv("DUCK_WINDOW_MS", "40"))

# ----------------------------
# QUALITY GATES
# ----------------------------
MIN_COLD_OPEN_LINES = int(os.getenv("MIN_COLD_OPEN_LINES", "6"))
MIN_DIGITS_PER_SEGMENT = int(os.getenv("MIN_DIGITS_PER_SEGMENT", "12"))
MIN_DIGITS_PER_EPISODE = int(os.getenv("MIN_DIGITS_PER_EPISODE", "85"))
MIN_NUMERIC_BULLETS_PER_STORY = int(os.getenv("MIN_NUMERIC_BULLETS_PER_STORY", "2"))
FORWARDABLE_MIN_PER_EPISODE = int(os.getenv("FORWARDABLE_MIN_PER_EPISODE", "3"))
FORWARDABLE_PAUSE_MS = int(os.getenv("FORWARDABLE_PAUSE_MS", "240"))
INTER_TURN_SILENCE_MS = int(os.getenv("INTER_TURN_SILENCE_MS", "120"))
REACTION_PAUSE_MS = int(os.getenv("REACTION_PAUSE_MS", "190"))
MAX_CONSECUTIVE_SAME_SPEAKER_LINES = int(os.getenv("MAX_CONSECUTIVE_SAME_SPEAKER_LINES", "4"))
MAX_SPOKEN_WORDS_PER_LINE = int(os.getenv("MAX_SPOKEN_WORDS_PER_LINE", "56"))
MIN_INTERRUPTION_CUES_PER_SEGMENT = int(os.getenv("MIN_INTERRUPTION_CUES_PER_SEGMENT", "1"))
MIN_REACTION_CUES_PER_SEGMENT = int(os.getenv("MIN_REACTION_CUES_PER_SEGMENT", "2"))
MIN_ALEX_CONTROL_CUES_PER_SEGMENT = int(os.getenv("MIN_ALEX_CONTROL_CUES_PER_SEGMENT", "1"))

STRICT_EPISODE_FILENAME_RE = re.compile(r"^podcast_\d{4}-\d{2}-\d{2}\.mp3$")
EARLY_SIGNOFF_RE = re.compile(
    r"\b("
    r"see you tomorrow|see you next time|that's the show|that's all for today|"
    r"thanks for listening|until tomorrow|until next time|we'll be back tomorrow|"
    r"good night|signing off|that does it for us|before we go|final thought|that wraps it up|we're out|we are out|that's our show|that is our show"
    r")\b",
    re.IGNORECASE,
)

MONEY_RE = re.compile(r"(\$|€|£)\s?\d")
NUMERIC_TOKEN_RE = re.compile(r"(\d+(\.\d+)?%|\$?\d[\d,]*(\.\d+)?|\b\d{4}\b|\bQ[1-4]\b)", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
INTERRUPTION_CUE_RE = re.compile(r"\b(?:wait|wait wait wait|hold on|hang on|stop|come on|no no|no,? that|sorry|one at a time|say that again|cut through it|look)\b", re.IGNORECASE)
REACTION_CUE_RE = re.compile(r"\[(?:laughs?|chuckles?|scoffs?|huffs?|sharp exhale|amused exhale|dry laugh|under[- ]the[- ]breath|incredulous pause|audible disbelief|mutters?|beat|pause)\]|\b(?:come on|seriously|no way|that'?s absurd|that is absurd|unbelievable|ridiculous)\b", re.IGNORECASE)
ALEX_CONTROL_CUE_RE = re.compile(r"^ALEX\s*:\s*(?:okay,? hold on|hold on|wait,? wait,? wait|stop\.|stop,|one at a time|jamie[—-]? hang on|rufus,? cut through it|no,? that'?s not the question|say that again)", re.IGNORECASE)

STALE_FUTURE_YEAR_RE = re.compile(
    r"\b(?:will|would|is expected to|are expected to|expected to|forecast(?:ed)? to|project(?:ed)? to|predicted to|set to|poised to|going to|on track to|scheduled to|could|should|may|might|can|likely to|by|through|into|before|over the next|later in|heading into)\b[^\n.!?]{0,100}\b(20\d{2})\b",
    re.IGNORECASE,
)
THELEDGR_NAME_RE = re.compile(r"\b(?:the ledger|theledgr)\b", re.IGNORECASE)
THELEDGR_URL_RE = re.compile(r"t[- ]?h[- ]?e[- ]?l[- ]?e[- ]?d[- ]?g[- ]?r\s+dot\s+i[- ]?o", re.IGNORECASE)
SOFT_SEGMENT_END_RE = re.compile(
    r"\b(?:bottom line|the takeaway(?: here)?|that'?s the takeaway|we'?ll leave it there|that'?s where this lands|that'?s what this means|that'?s the thing|we'?ll see|we shall see|time will tell|that does it for this one|that closes it out)\b",
    re.IGNORECASE,
)

ENTITY_ALIAS_GROUPS: Dict[str, Tuple[str, ...]] = {
    "microsoft": ("microsoft", "copilot", "power apps", "power platform", "azure", "d365", "dynamics 365"),
    "openai": ("openai", "chatgpt", "gpt-4", "gpt 4", "gpt-5", "gpt 5", "sora"),
    "anthropic": ("anthropic", "claude", "mythos"),
    "google": ("google", "gemini", "deepmind", "alphabet"),
    "meta": ("meta", "llama", "facebook"),
    "amazon": ("amazon", "aws", "bedrock"),
    "nvidia": ("nvidia", "blackwell", "cuda"),
    "apple": ("apple",),
    "tesla": ("tesla", "x.ai", "xai", "grok"),
    "perplexity": ("perplexity",),
    "notion": ("notion",),
    "canva": ("canva",),
}

MIN_MP3_BYTES_FEED = int(os.getenv("MIN_MP3_BYTES_FEED", "200000"))
EPISODE_META_MAX_TITLE = int(os.getenv("EPISODE_META_MAX_TITLE", "110"))
APPEND_DATE_TO_TITLE = os.getenv("APPEND_DATE_TO_TITLE", "false").strip().lower() in ("1","true","yes")
FORCE_INDIVIDUAL_RUFUS_LINES = os.getenv("FORCE_INDIVIDUAL_RUFUS_LINES", "true").strip().lower() in ("1","true","yes")

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


def _resolve_audio_asset(primary: Path, fallback: Optional[Path] = None) -> Optional[Path]:
    if primary.exists():
        return primary
    if fallback is not None and fallback.exists():
        return fallback
    return None


def _require_intro_outro_if_needed(
    intro_asset: Optional[Path] = None,
    outro_asset: Optional[Path] = None,
    transition_asset: Optional[Path] = None,
) -> None:
    intro_asset = intro_asset if intro_asset is not None else _resolve_audio_asset(INTRO_PATH, BRANDKIT_SFX_DIR / "intro_sting_brand.mp3")
    outro_asset = outro_asset if outro_asset is not None else _resolve_audio_asset(OUTRO_PATH, BRANDKIT_SFX_DIR / "outro_theme_brand.mp3")
    transition_asset = transition_asset if transition_asset is not None else _resolve_audio_asset(TRANSITION_PATH, BRANDKIT_SFX_DIR / "segment_transition_brand.mp3")

    if REQUIRE_INTRO_OUTRO and intro_asset is None:
        raise RuntimeError("No intro asset found. Provide intro.mp3 or allow brandkit intro fallback.")
    if REQUIRE_INTRO_OUTRO and outro_asset is None:
        raise RuntimeError("No outro asset found. Provide outro.mp3 or allow brandkit outro fallback.")
    if REQUIRE_TRANSITIONS and transition_asset is None:
        raise RuntimeError("No transition asset found. Provide transition.mp3 or allow brandkit transition fallback.")


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
        if TAIL_PAD_MS > 0:
            clip = clip + AudioSegment.silent(duration=TAIL_PAD_MS)
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
    if age_hours <= 26:
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
STORY_BUCKET_CAP = int(os.getenv("STORY_BUCKET_CAP", "5"))


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
            if 26 <= len(s2) <= 220:
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
        pool = fetch_rss_items(max_per_feed=26)
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
    biggest = [s for s in working if str(s.get("story_role") or "") == "biggest"]
    verticals = [s for s in working if str(s.get("story_role") or "") == "vertical"]
    other = [s for s in working if str(s.get("story_role") or "") not in {"biggest", "vertical"}]

    biggest.sort(key=_editorial_impact_score, reverse=True)
    verticals.sort(key=_editorial_impact_score, reverse=True)
    other.sort(key=_editorial_impact_score, reverse=True)

    ordered = biggest[:3] + verticals[:2]
    seen = {_story_identity_key(x) for x in ordered}
    for item in biggest[3:] + verticals[2:] + other:
        key = _story_identity_key(item)
        if not key or key in seen:
            continue
        ordered.append(item)
        seen.add(key)

    return ordered[:5]


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


def _load_previous_episode_context(today: str) -> Dict[str, object]:
    p = BASE_DIR / "episode_metadata.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        if str(data.get("date") or "").strip() == str(today or "").strip():
            return {}
        return data
    except Exception:
        return {}


def _story_text_blob_for_repeat(item: Dict[str, str]) -> str:
    parts = [
        item.get("headline") or item.get("title") or "",
        item.get("why_shocking") or item.get("summary") or "",
        item.get("publisher") or "",
        item.get("source_url") or item.get("link") or "",
        " ".join([str(x) for x in (item.get("data_points") or [])[:4]]),
        " ".join([str(x) for x in (item.get("key_entities") or [])[:6]]),
    ]
    return " ".join([p for p in parts if p]).strip()


def _headline_family_key(text: str) -> str:
    s = (text or "").lower()
    s = re.sub(r"\|\s*(what it means next|what the numbers mean|why tomorrow gets harder).*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in re.sub(r"\s+", " ", s).strip().split() if t not in {"the", "a", "an", "with", "and", "for", "to", "in", "of", "on"}]
    return " ".join(tokens[:12])


def _story_entity_key(item: Dict[str, str]) -> str:
    low = _story_text_blob_for_repeat(item).lower()
    for canonical, aliases in ENTITY_ALIAS_GROUPS.items():
        if any(alias in low for alias in aliases):
            return canonical
    headline = (item.get("headline") or item.get("title") or "").strip()
    caps = [tok.lower() for tok in re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b", headline)]
    for tok in caps:
        if tok not in {"today", "ai", "apps", "agents", "power", "news", "edge"}:
            return tok
    return ""


def _token_overlap_ratio(a: str, b: str) -> float:
    ta = set((a or "").split())
    tb = set((b or "").split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def _previous_story_titles(previous_meta: Dict[str, object]) -> List[str]:
    titles: List[str] = []
    title = str(previous_meta.get("title") or "").strip()
    if title:
        titles.append(title)
    stories = previous_meta.get("stories") if isinstance(previous_meta.get("stories"), list) else []
    for s in stories[:5]:
        if isinstance(s, dict):
            headline = str(s.get("headline") or s.get("title") or "").strip()
            if headline:
                titles.append(headline)
    return titles


def _repeat_penalty(item: Dict[str, str], previous_meta: Dict[str, object]) -> float:
    if not previous_meta:
        return 0.0
    penalty = 0.0
    item_link = (item.get("source_url") or item.get("link") or "").strip().lower()
    item_head = _headline_family_key(item.get("headline") or item.get("title") or "")
    item_entity = _story_entity_key(item)

    prev_titles = [_headline_family_key(x) for x in _previous_story_titles(previous_meta)]
    prev_stories = previous_meta.get("stories") if isinstance(previous_meta.get("stories"), list) else []
    prev_links = {str((s.get("source_url") or s.get("link") or "")).strip().lower() for s in prev_stories if isinstance(s, dict)}
    prev_entities = {_story_entity_key(s) for s in prev_stories if isinstance(s, dict)}

    if item_link and item_link in prev_links:
        penalty += 120.0
    if item_head and any(item_head == x for x in prev_titles if x):
        penalty += 120.0
    elif item_head and any(_token_overlap_ratio(item_head, x) >= 0.72 for x in prev_titles if x):
        penalty += 65.0
    if item_entity and item_entity in prev_entities:
        penalty += 32.0
    return penalty


def _selection_penalty(item: Dict[str, str], selected: List[Dict[str, str]]) -> float:
    if not selected:
        return 0.0
    penalty = 0.0
    entity = _story_entity_key(item)
    bucket = _normalize_vertical_bucket(item.get("bucket", ""))
    if entity:
        same_entity = sum(1 for s in selected if _story_entity_key(s) == entity)
        if same_entity >= 1:
            penalty += 24.0 * same_entity
    same_bucket = sum(1 for s in selected if _normalize_vertical_bucket(s.get("bucket", "")) == bucket)
    if same_bucket >= 2 and bucket != "topline":
        penalty += 18.0
    return penalty



def _rank_with_editorial_penalties(candidates: List[Dict[str, str]], previous_meta: Dict[str, object], selected: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    chosen = selected or []
    return sorted(
        [dict(x) for x in candidates],
        key=lambda x: _editorial_impact_score(x) - _repeat_penalty(x, previous_meta) - _selection_penalty(x, chosen),
        reverse=True,
    )


def _can_add_story(item: Dict[str, str], selected: List[Dict[str, str]], role: str) -> bool:
    entity = _story_entity_key(item)
    bucket = _normalize_vertical_bucket(item.get("bucket", ""))
    bucket_counts = {}
    for s in selected:
        b = _normalize_vertical_bucket(s.get("bucket", ""))
        bucket_counts[b] = bucket_counts.get(b, 0) + 1

    if role == "biggest" and entity:
        if sum(1 for s in selected if str(s.get("story_role") or "") == "biggest" and _story_entity_key(s) == entity) >= 1:
            return False
    if entity:
        same_entity = sum(1 for s in selected if _story_entity_key(s) == entity)
        if role in {"biggest", "vertical"} and same_entity >= 2:
            return False
        if role == "flex" and same_entity >= 3:
            return False

    max_bucket = 2 if bucket in {"ai_agents", "ai_tools", "ai_code", "health_ai"} else 3
    if role in {"vertical", "flex"} and bucket_counts.get(bucket, 0) >= max_bucket:
        return False
    return True


def _story_non_date_number_count(item: Dict[str, str]) -> int:
    blob_parts = [item.get("headline") or item.get("title") or ""]
    blob_parts.extend([str(x) for x in (item.get("data_points") or [])[:6]])
    blob = " ".join(blob_parts)
    if not blob:
        return 0
    money_pct = re.findall(
        r"(?:\$|€|£)\s?\d[\d,.]*|\b\d+(?:\.\d+)?%\b|\b\d+(?:\.\d+)?\s*(?:million|billion|trillion|m|bn|b)\b",
        blob,
        flags=re.IGNORECASE,
    )
    quarters = re.findall(r"\bQ[1-4]\b", blob, flags=re.IGNORECASE)
    return len(money_pct) + len(quarters)


def _story_has_real_numbers(item: Dict[str, str]) -> bool:
    blob = " ".join([str(x) for x in (item.get("data_points") or [])[:6]])
    if "No explicit figures in snippet" in blob:
        return False
    return _story_non_date_number_count(item) >= 2


def _bucket_counts(stories: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for s in stories:
        b = _normalize_vertical_bucket(s.get("bucket", ""))
        counts[b] = counts.get(b, 0) + 1
    return counts


def _best_remaining_candidate(
    ranked_all: List[Dict[str, str]],
    used: set,
    selected: List[Dict[str, str]],
    previous_meta: Dict[str, object],
    required_bucket: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    for item in _rank_with_editorial_penalties(ranked_all, previous_meta, selected=selected):
        key = _story_identity_key(item)
        if not key or key in used:
            continue
        bucket = _normalize_vertical_bucket(item.get("bucket", ""))
        if required_bucket and bucket != required_bucket:
            continue
        if not _can_add_story(item, selected, role="vertical" if required_bucket else "flex"):
            continue
        return dict(item)
    return None


def _rebalance_selected_stories(
    selected: List[Dict[str, str]],
    ranked_all: List[Dict[str, str]],
    previous_meta: Dict[str, object],
) -> List[Dict[str, str]]:
    if not selected:
        return selected

    selected = [dict(x) for x in selected]
    used = {_story_identity_key(x) for x in selected}
    counts = _bucket_counts(selected)

    def weakest_index_for_replacement(exclude_buckets: set[str]) -> Optional[int]:
        candidates = []
        for idx, item in enumerate(selected):
            bucket = _normalize_vertical_bucket(item.get("bucket", ""))
            if bucket in exclude_buckets:
                continue
            role = str(item.get("story_role") or "")
            score = _editorial_impact_score(item) - _repeat_penalty(item, previous_meta)
            role_penalty = 0 if role in {"biggest", "flex"} else 8
            bucket_penalty = 12 if counts.get(bucket, 0) > 1 else 0
            candidates.append((score + role_penalty - bucket_penalty, idx))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    for over_bucket in ["ai_agents", "ai_tools"]:
        while counts.get(over_bucket, 0) > 2:
            replacement_bucket = next((b for b in ["ai_code", "health_ai", "topline"] if counts.get(b, 0) == 0), None)
            if not replacement_bucket:
                break
            candidate = _best_remaining_candidate(ranked_all, used, selected, previous_meta, required_bucket=replacement_bucket)
            if not candidate:
                break
            idx = weakest_index_for_replacement(exclude_buckets={replacement_bucket})
            if idx is None:
                break
            old_key = _story_identity_key(selected[idx])
            used.discard(old_key)
            candidate["story_role"] = selected[idx].get("story_role") or candidate.get("story_role") or "vertical"
            selected[idx] = candidate
            used.add(_story_identity_key(candidate))
            counts = _bucket_counts(selected)

    for wanted_bucket in ["ai_code", "health_ai"]:
        if counts.get(wanted_bucket, 0) > 0:
            continue
        candidate = _best_remaining_candidate(ranked_all, used, selected, previous_meta, required_bucket=wanted_bucket)
        if not candidate:
            continue
        idx = weakest_index_for_replacement(exclude_buckets={wanted_bucket, "health_ai"})
        if idx is None:
            continue
        replace_score = _editorial_impact_score(selected[idx]) - _repeat_penalty(selected[idx], previous_meta)
        candidate_score = _editorial_impact_score(candidate) - _repeat_penalty(candidate, previous_meta)
        if candidate_score + 18 < replace_score:
            continue
        old_key = _story_identity_key(selected[idx])
        used.discard(old_key)
        candidate["story_role"] = selected[idx].get("story_role") or candidate.get("story_role") or "vertical"
        selected[idx] = candidate
        used.add(_story_identity_key(candidate))
        counts = _bucket_counts(selected)

    if len(counts) < 3:
        missing_candidates = [b for b in ["topline", "ai_tools", "ai_agents", "ai_code", "health_ai"] if counts.get(b, 0) == 0]
        for wanted_bucket in missing_candidates:
            candidate = _best_remaining_candidate(ranked_all, used, selected, previous_meta, required_bucket=wanted_bucket)
            if not candidate:
                continue
            idx = weakest_index_for_replacement(exclude_buckets={wanted_bucket})
            if idx is None:
                continue
            replace_score = _editorial_impact_score(selected[idx]) - _repeat_penalty(selected[idx], previous_meta)
            candidate_score = _editorial_impact_score(candidate) - _repeat_penalty(candidate, previous_meta)
            if candidate_score + 14 < replace_score:
                continue
            old_key = _story_identity_key(selected[idx])
            used.discard(old_key)
            candidate["story_role"] = selected[idx].get("story_role") or candidate.get("story_role") or "vertical"
            selected[idx] = candidate
            used.add(_story_identity_key(candidate))
            counts = _bucket_counts(selected)
            if len(counts) >= 3:
                break

    counts = _bucket_counts(selected)
    for bucket, count in list(counts.items()):
        if count <= 2:
            continue
        alternatives = [b for b in ["ai_code", "health_ai", "ai_tools", "ai_agents", "topline"] if counts.get(b, 0) == 0]
        if not alternatives:
            continue
        replacement_bucket = alternatives[0]
        candidate = _best_remaining_candidate(ranked_all, used, selected, previous_meta, required_bucket=replacement_bucket)
        if not candidate:
            continue
        weakest_same_bucket = None
        weakest_score = float("inf")
        for idx, item in enumerate(selected):
            if _normalize_vertical_bucket(item.get("bucket", "")) != bucket:
                continue
            score = _editorial_impact_score(item) - _repeat_penalty(item, previous_meta)
            if score < weakest_score:
                weakest_score = score
                weakest_same_bucket = idx
        if weakest_same_bucket is None:
            continue
        candidate_score = _editorial_impact_score(candidate) - _repeat_penalty(candidate, previous_meta)
        if candidate_score + 20 < weakest_score:
            continue
        old_key = _story_identity_key(selected[weakest_same_bucket])
        used.discard(old_key)
        candidate["story_role"] = selected[weakest_same_bucket].get("story_role") or candidate.get("story_role") or "vertical"
        selected[weakest_same_bucket] = candidate
        used.add(_story_identity_key(candidate))
        counts = _bucket_counts(selected)

    return selected


def pick_top_stories(intel_items: List[Dict[str, str]], n: int = 5, date_str: Optional[str] = None) -> List[Dict[str, str]]:
    if not intel_items:
        return []

    date_str = date_str or datetime.date.today().isoformat()
    previous_meta = _load_previous_episode_context(date_str)
    memory = load_show_memory()
    curated = select_story_candidates(intel_items, n=max(n * 12, 80), memory=memory, bucket_cap=STORY_BUCKET_CAP)
    if not curated:
        ranked = sorted(intel_items, key=_combined_story_score, reverse=True)
        curated = ranked[:max(n * 10, 60)]

    ranked_all = _rank_with_editorial_penalties(curated, previous_meta, selected=[])

    selected: List[Dict[str, str]] = []
    used = set()
    biggest_count = 0
    biggest_buckets_seen: set[str] = set()
    biggest_entities_seen: set[str] = set()

    for item in ranked_all:
        key = _story_identity_key(item)
        if not key or key in used:
            continue
        bucket = _normalize_vertical_bucket(item.get("bucket", ""))
        entity = _story_entity_key(item)
        if bucket in biggest_buckets_seen and biggest_count < 2:
            continue
        if entity and entity in biggest_entities_seen:
            continue
        if not _can_add_story(item, selected, role="biggest"):
            continue
        item["story_role"] = "biggest"
        selected.append(item)
        used.add(key)
        biggest_buckets_seen.add(bucket)
        if entity:
            biggest_entities_seen.add(entity)
        biggest_count += 1
        if biggest_count >= 3:
            break

    if biggest_count < 3:
        for item in _rank_with_editorial_penalties(ranked_all, previous_meta, selected=selected):
            key = _story_identity_key(item)
            if not key or key in used:
                continue
            if not _can_add_story(item, selected, role="biggest"):
                continue
            item["story_role"] = "biggest"
            selected.append(item)
            used.add(key)
            biggest_count += 1
            if biggest_count >= 3:
                break

    covered_buckets = {_normalize_vertical_bucket(x.get("bucket", "")) for x in selected}
    preferred_verticals = [b for b in ["health_ai", "ai_code", "ai_tools", "ai_agents"] if b not in covered_buckets]
    preferred_verticals += [b for b in ["health_ai", "ai_code", "ai_tools", "ai_agents"] if b not in preferred_verticals]

    vertical_count = 0
    for bucket in preferred_verticals:
        candidate = _best_remaining_candidate(ranked_all, used, selected, previous_meta, required_bucket=bucket)
        if not candidate:
            continue
        score = _editorial_impact_score(candidate) - _repeat_penalty(candidate, previous_meta)
        if score < 24.0:
            continue
        candidate["story_role"] = "vertical"
        selected.append(candidate)
        used.add(_story_identity_key(candidate))
        vertical_count += 1
        if vertical_count >= 2:
            break

    for item in _rank_with_editorial_penalties(ranked_all, previous_meta, selected=selected):
        if len(selected) >= max(n, 5):
            break
        key = _story_identity_key(item)
        if not key or key in used:
            continue
        if not _can_add_story(item, selected, role="flex"):
            continue
        item["story_role"] = item.get("story_role") or "flex"
        selected.append(item)
        used.add(key)

    if len(selected) < max(n, 5):
        for item in ranked_all:
            if len(selected) >= max(n, 5):
                break
            key = _story_identity_key(item)
            if not key or key in used:
                continue
            item["story_role"] = item.get("story_role") or "flex"
            selected.append(item)
            used.add(key)

    selected = _rebalance_selected_stories(selected[:max(n, 5)], ranked_all, previous_meta)

    stories = [_candidate_to_story(x) for x in selected[:max(n, 5)]]
    stories = _dedupe_story_list(stories)
    enriched = enrich_stories_with_data(stories[:max(n, 5)])
    enriched = attach_story_scores(enriched, curated)

    raw_by_key = {_story_identity_key(x): x for x in selected}
    for s in enriched:
        raw = raw_by_key.get(_story_identity_key(s))
        if raw:
            if raw.get("tomorrow_hook") and not s.get("tomorrow_hook"):
                s["tomorrow_hook"] = raw.get("tomorrow_hook", "")
            if raw.get("share_angle"):
                s["share_angle"] = raw.get("share_angle", "")
            if raw.get("editor_reason"):
                s["editor_reason"] = raw.get("editor_reason", "")
            if raw.get("story_role"):
                s["story_role"] = raw.get("story_role")

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

def _max_consecutive_speaker_lines(text: str) -> int:
    best = 0
    current = 0
    last = None
    for raw in (text or "").splitlines():
        m = SPEAKER_RE.match(raw.strip())
        if not m:
            continue
        spk = m.group(1).upper()
        if spk == last:
            current += 1
        else:
            current = 1
            last = spk
        best = max(best, current)
    return best


def _speaker_line_counts(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {"ALEX": 0, "JAMIE": 0, "RUFUS": 0}
    for raw in (text or "").splitlines():
        m = SPEAKER_RE.match(raw.strip())
        if not m:
            continue
        counts[m.group(1).upper()] = counts.get(m.group(1).upper(), 0) + 1
    return counts


def _cue_count(text: str, pattern: re.Pattern) -> int:
    return len(pattern.findall(text or ""))


def _long_spoken_line_count(text: str, max_words: int) -> int:
    count = 0
    for raw in (text or "").splitlines():
        m = SPEAKER_RE.match(raw.strip())
        if not m:
            continue
        words = len(re.findall(r"\w+", m.group(2)))
        if words > max_words:
            count += 1
    return count


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
        '- Segment markers are allowed as lines starting with "###" and will NOT be spoken.\n'
        '- "[MUSIC]" may appear as a standalone line.\n'
        '- Do not add any other headings, bullets, or markdown.\n'
        '- This is a live contested conversation, not a sequential explainer.\n'
        '- Default spoken lines should usually be 6-36 words and 1-2 sentences, but let strong exchanges breathe when someone is building a case.\n'
        '- Avoid dead monologues, but do NOT rotate turns so fast that nobody can build a point. A sharp exchange can run 4-7 turns before Alex steps back in.\n'
        '- Alex must actively run the room, but he should interrupt with purpose rather than constant maintenance chatter.\n'
        '- Jamie must sound extremely intelligent, polished, emotionally readable, and grounded.\n'
        '- Rufus must stay dry, British, surgical, and compact, with at least one dry quip or saying where it fits.\n'
        '- Every segment must include at least one interruption or control cue, at least two audible realism cues, one hard number, and one genuinely clipable line.\n'
        '- Use bracketed realism cues sparingly and tastefully: [laughs], [sharp exhale], [scoffs], [dry laugh], [under his breath], [audible disbelief].\n'
        '- Across the segment, vary emotional temperature. Do not let three consecutive exchanges sit at the same emotional level.\n'
    )



def _segment_assignment(seg_num: int) -> str:
    if seg_num == 1:
        return (
            "Story 1: the single biggest story of the day. Cold open with heat, interruption, disbelief, and immediate status-play. Then [MUSIC]. "
            "Immediately after [MUSIC], Alex lands a sharp TheLEDGR sponsor hit, welcomes the audience, and tears through the five-story lineup like people cannot afford to miss it. "
            "Alex should sound amused, aggressive, curious, and in command: he asks the high-stakes question everyone is already thinking, but he does not rush. "
            "This segment must feel expensive, current, story-rich, and instantly clip-ready."
        )
    if seg_num == 2:
        return (
            "Story 2: the second biggest story of the day. ONLY Alex and Jamie. "
            "This is where Jamie sounds formidable: extremely intelligent, emotionally alive, grounded, and sharp under pressure. "
            "Alex asks the hard question, then lets Jamie actually build the case before cutting back in. "
            "The scene needs one real turn of disagreement, at least one laugh/scoff/disbelief beat, one hard number, and one line a listener would text to a friend immediately."
        )
    if seg_num == 3:
        return (
            "Story 3: the third biggest story of the day. Alex throws to Rufus and Rufus owns the room with money, power, policy, or geopolitical consequence. "
            "Rufus must land one elite dry British undercut, one memorable British saying, and one hard number that changes how the listener sees the story. "
            "Jamie challenges Rufus once, they spar for 4-7 turns with real wit and irritation, and then Alex regains control and forces the takeaway."
        )
    if seg_num == 4:
        return (
            "Story 4: the strongest vertical story. All three are in. This should feel like the best full-cast scene of the episode with friction, callbacks, real interruptions, and at least one genuine chuckle or smirk beat. "
            "Jamie and Rufus must have one genuine sparring exchange with wit, sarcasm, and respect before Alex gets a handle on the room. "
            "No polite panel-talk. This is where the cast chemistry itself becomes the product."
        )
    return (
        "Story 5: the second-best vertical or best flex story. Drive toward a real close. "
        "Before the close, Jamie and Rufus should have one final sharp disagreement or teasing exchange that reveals their chemistry, then Alex lands the takeaway. "
        "The ending must feel memorable, slightly cinematic, tomorrow-facing, and unresolved enough that listeners need the next episode. "
        "No weak wrap-up language until the actual final sign-off and outro."
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

META_PROMPT_LEAK_PATTERNS = [
    r"\bnever bubbly\b",
    r"\bnever valley[ -]?girl\b",
    r"\bprofessionally irritated(?: when needed)?\b",
    r"\bexecutive-bright\b",
    r"\barticulate,? executive-bright\b",
    r"\bbartlett-style color voice\b",
    r"\bflirty,? bubbly,? or valley-girl\b",
]


def _strip_meta_prompt_leak(text: str) -> str:
    s = text or ""
    for pat in META_PROMPT_LEAK_PATTERNS:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" ,;-[]")
    return s


def _stale_future_lines(script: str, date_str: str) -> List[str]:
    current_year = int((date_str or datetime.date.today().isoformat())[:4])
    bad: List[str] = []
    seen = set()
    for raw in (script or "").splitlines():
        m = SPEAKER_RE.match(raw.strip())
        if not m:
            continue
        spoken = m.group(2).strip()
        for hit in STALE_FUTURE_YEAR_RE.finditer(spoken):
            try:
                yr = int(hit.group(1))
            except Exception:
                continue
            if yr < current_year:
                line = raw.strip()
                if line not in seen:
                    seen.add(line)
                    bad.append(line)
                break
    return bad


def enforce_temporal_consistency(script: str, date_str: str) -> str:
    stale_lines = _stale_future_lines(script, date_str)
    if not stale_lines:
        return script

    prompt = f"""
You are repairing stale time references in a podcast script.
Episode date: {date_str}.

RULES:
- A future prediction cannot point to a past year relative to the episode date.
- Preserve the speaker label exactly.
- Keep the line sharp, current, and natural.
- Do not add narration, bullets, or markdown.
- Return ONLY valid JSON with this shape:
{{
  "replacements": [
    {{"from": "ORIGINAL FULL LINE", "to": "REVISED FULL LINE"}}
  ]
}}

Lines to fix:
""" + "\n".join(stale_lines)

    try:
        raw = generate_text(prompt, temperature=0.15, max_tokens=900)
        payload = _extract_json_object(raw) or {}
        reps = payload.get("replacements") if isinstance(payload.get("replacements"), list) else []
        mapping = {}
        for item in reps:
            if not isinstance(item, dict):
                continue
            src = str(item.get("from", "")).strip()
            dst = str(item.get("to", "")).strip()
            if src and dst and SPEAKER_RE.match(dst):
                mapping[src] = dst
        if mapping:
            out_lines = []
            for raw_line in (script or "").splitlines():
                out_lines.append(mapping.get(raw_line.strip(), raw_line))
            script = "\n".join(out_lines)
    except Exception as e:
        _safe_print(f"    ⚠️ Temporal consistency repair skipped: {e}")

    # Fallback: make obviously stale future verbs less wrong even if model repair fails.
    current_year = int((date_str or datetime.date.today().isoformat())[:4])
    out_lines = []
    for raw in (script or "").splitlines():
        line = raw
        m = SPEAKER_RE.match(raw.strip())
        if m:
            spoken = m.group(2)
            if any(int(y) < current_year for y in re.findall(r"\b(20\d{2})\b", spoken)) and STALE_FUTURE_YEAR_RE.search(spoken):
                fixed = spoken
                fixed = re.sub(r"\bwill occur\b", "played out", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bwill happen\b", "happened", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bwill be\b", "was", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bis expected to\b", "was expected to", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bare expected to\b", "were expected to", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bmay see\b", "may have seen", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bmight see\b", "might have seen", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bcan see\b", "could see", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bby\s+(20\d{2})\b", "by then", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bthrough\s+(20\d{2})\b", "through that period", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\binto\s+(20\d{2})\b", "into that period", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bexpected to\b", "expected to", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bset to\b", "set to", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bgoing to\b", "going to", fixed, flags=re.IGNORECASE)
                line = f"{m.group(1).upper()}: {fixed.strip()}"
        out_lines.append(line)
    return "\n".join(out_lines)


def _fallback_theledgr_read(sponsor: Dict[str, str]) -> str:
    tagline = (sponsor.get("tagline") or "Decision-grade AI signal that helps you make better calls at work.").strip()
    cta = (sponsor.get("cta") or f"Subscribe at {THELEDGR_SPOKEN_URL}.").strip()
    return (
        "ALEX: This show is brought to you by The Ledger — "
        f"{tagline} "
        f"{cta}"
    ).strip()


def ensure_sponsor_delivery(script: str, sponsors: List[Dict[str, str]]) -> str:
    if not any(_is_theledgr_sponsor(s) for s in sponsors or []):
        return script
    low = (script or "").lower()
    has_name = bool(THELEDGR_NAME_RE.search(low))
    has_url = bool(THELEDGR_URL_RE.search(low))
    if has_name and has_url:
        return script

    sponsor = next((s for s in (sponsors or []) if _is_theledgr_sponsor(s)), {"name": "TheLEDGR", "tagline": "", "cta": ""})
    fallback = _fallback_theledgr_read(sponsor)
    lines = (script or "").splitlines()
    inserted = False
    out: List[str] = []
    for idx, line in enumerate(lines):
        out.append(line)
        if not inserted and line.strip().upper() == "[MUSIC]":
            out.append(fallback)
            inserted = True
    if not inserted:
        out.insert(1 if out else 0, fallback)
    return "\n".join(out).strip()


def _sponsor_validation_issues(script: str, sponsors: List[Dict[str, str]]) -> List[str]:
    issues: List[str] = []
    if any(_is_theledgr_sponsor(s) for s in sponsors or []):
        low = (script or "").lower()
        if not THELEDGR_NAME_RE.search(low):
            issues.append("TheLEDGR sponsor name is missing from the episode script.")
        if not THELEDGR_URL_RE.search(low):
            issues.append("TheLEDGR spoken URL is missing from the episode script.")
    return issues

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
    candidates: List[Dict[str, object]] = []
    seen: set[str] = set()

    weak_openers = (
        "first up",
        "so,",
        "so ",
        "exactly, alex",
        "exactly alex",
        "let's start",
        "we start",
        "the article",
        "published on",
        "the event is",
        "it sounds like",
    )

    for raw in script.splitlines():
        line = raw.strip()
        m = SPEAKER_RE.match(line)
        if not m:
            continue
        speaker = m.group(1).upper()
        spoken = m.group(2).strip()
        key = normalize_text(spoken)
        if not spoken or key in seen:
            continue
        seen.add(key)

        low = spoken.lower()
        score = _forwardable_line_score(spoken)
        if score < 5:
            continue
        if any(low.startswith(prefix) for prefix in weak_openers):
            score -= 3
        if "published on" in low or "article from" in low:
            score -= 4
        if len(spoken) > 220:
            score -= 2

        tokens = {tok.lower().strip(".,:;!?") for tok in re.findall(r"[A-Za-z0-9€$%][A-Za-z0-9€$%\-_]{2,}", spoken)}
        anchor_hits = len(tokens & anchors) if anchors else 0
        story_hits = 0
        for story in stories or []:
            title_tokens = {tok.lower() for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_]{2,}", story.get("headline") or "")}
            if tokens & title_tokens:
                story_hits += 1

        has_number = bool(re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d{4}\b|\b\d+[mkb]?\b", spoken, flags=re.IGNORECASE))
        has_consequence = any(h in low for h in FORWARDABLE_CONSEQUENCE_HINTS)
        has_shock = any(h in low for h in FORWARDABLE_SHOCK_HINTS)
        has_contrast = bool(re.search(r"\b(?:but|except|instead|the catch|the problem|the real risk|the real question|what matters is)\b", low))

        score += min(anchor_hits, 2)
        score += min(story_hits, 2)
        if has_contrast:
            score += 1
        if speaker == "RUFUS" and ("[" in spoken or "come on" in low or has_contrast):
            score += 1

        if score < 6:
            continue

        candidates.append({
            "speaker": speaker,
            "text": spoken,
            "score": score,
            "anchor_hits": anchor_hits,
            "story_hits": story_hits,
            "has_number": has_number,
            "has_consequence": has_consequence,
            "has_shock": has_shock,
            "has_contrast": has_contrast,
        })

    candidates.sort(
        key=lambda x: (
            1 if (x["has_number"] or x["has_consequence"] or x["has_shock"] or x["has_contrast"]) else 0,
            x["anchor_hits"],
            x["story_hits"],
            x["score"],
            len(x["text"]),
        ),
        reverse=True,
    )

    out: List[Dict[str, object]] = []
    used_speakers: set[str] = set()
    used_norms: set[str] = set()
    for c in candidates:
        if len(out) >= max_items:
            break
        norm = normalize_text(str(c["text"]))
        if norm in used_norms:
            continue
        if len(out) < 2 and int(c["anchor_hits"]) == 0:
            continue
        if len(out) < 2 and int(c["score"]) < 8:
            continue
        if len(out) < 3 and c["speaker"] in used_speakers and len({str(x["speaker"]) for x in candidates}) > 1:
            continue
        out.append({"speaker": c["speaker"], "text": c["text"], "score": c["score"]})
        used_speakers.add(str(c["speaker"]))
        used_norms.add(norm)

    if len(out) < max_items:
        for c in candidates:
            if len(out) >= max_items:
                break
            norm = normalize_text(str(c["text"]))
            if norm in used_norms:
                continue
            out.append({"speaker": c["speaker"], "text": c["text"], "score": c["score"]})
            used_norms.add(norm)

    return out[:max_items]


def _is_theledgr_sponsor(sponsor: Dict[str, str]) -> bool:

    return (sponsor.get("name") or "").strip().lower() == "theledgr"


def _sponsor_prompt_lines(sponsor: Dict[str, str]) -> str:
    name = (sponsor.get("name") or "Sponsor").strip()
    tagline = (sponsor.get("tagline") or "").strip()
    cta = (sponsor.get("cta") or "").strip()
    if _is_theledgr_sponsor(sponsor):
        return (
            f"Sponsor: {name}\n"
            f"Tagline: {tagline}\n"
            f"CTA: {cta}\n"
            "- Keep the read improvisational, native, and interesting. It should feel like the hosts are riffing, not switching into ad voice.\n"
            "- Alex should ad-lib the setup or analogy, but he must still land the value proposition and the CTA cleanly.\n"
            "- Keep it to 2-4 tight sentences.\n"
            "- Make the sponsor feel useful, loved, and premium, not salesy. It should sound like something the hosts genuinely value and are happy to plug because it helps the audience.\n"
            f"- Alex must say the brand as 'The Ledger' and the URL exactly as {THELEDGR_SPOKEN_URL}.\n"
        )
    return (
        f"Sponsor: {name}\n"
        f"Tagline: {tagline}\n"
        f"CTA: {cta}\n"
        "- This is a paid sponsor. Keep it improvisational and native to the conversation, but still hit the sponsor name, core value, and CTA clearly once.\n"
        "- Do not invent claims beyond the provided sponsor fields.\n"
        "- Keep it to 2-4 tight sentences and make it sound premium and interesting, not stiff.\n"
    )



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
            "- CRITICAL: avoid dead monologues, but do NOT rotate turns so fast that nobody can build a case. Let Jamie and Rufus occasionally hold 2-4 connected turns when sharpening an argument.\n"
            "- Include at least one interruption, one real emotional reaction, and one line that could be clipped and shared.\n"
            "- Keep dialogue alive, conflict-aware, and writer-room sharp, but allow arguments to breathe before Alex cuts back in.\n"
            "- Alex should feel stronger by speaking less often and landing harder when he does step in.\n"
            "- Every segment needs one line that sounds like a text message someone would forward.\n"
        )

    if seg_num == 1:
        extra += (
            "Start mid-argument (hook). Then a standalone line: [MUSIC]. "
            "Immediately after [MUSIC], Alex must deliver a short, premium TheLEDGR sponsor line before the welcome and lineup.\n"
            "- The sponsor should feel useful, sharp, loved, and native to the show, not like a generic ad break. The hosts should sound like they enjoy giving this plug because it pays the bills and helps the audience.\n"
            f"- Alex must say the brand as 'The Ledger' and the URL exactly as {THELEDGR_SPOKEN_URL}.\n"
            "- The sponsor must make listeners feel that TheLEDGR helps them make better daily decisions, cut through noise, and stay ahead at work.\n"
            "- In the cold open and lineup, say at least 3 explicit numbers, dates, dollar amounts, or benchmark figures out loud naturally.\n"
            "- Alex should ask the listener-question everybody is already thinking.\n"
            "- Alex must sound like a Joe Rogan-style instigator: curious, amused, slightly dangerous, and pushing the room forward without sounding rushed.\n"
            "- Include at least one interruption, one laugh/smirk beat, and one line with genuine tomorrow tension.\n"
            "- Alex must welcome the audience and set up the rest of the episode, not close it.\n"
        )
    elif seg_num == 2:
        extra += (
            "IMPORTANT: This segment must contain ONLY ALEX and JAMIE lines. Do NOT output any RUFUS lines.\n"
            "- Alex must open the segment with a clear setup or turn, then give Jamie room to make the case.\n"
            "- Jamie must not sound like a presenter. She must react to Alex in real time, cut in naturally, and help create banter.\n"
            "- Include at least two moments where Jamie interrupts, challenges, or reframes Alex in a warm but confident way.\n"
            "- Jamie should sound emotionally alive: amused, incredulous, impressed, concerned, or lightly offended when the line calls for it.\n"
            "- Give Alex and Jamie enough room to actually shape the story before the next interruption. Jamie should sound grounded, highly credible, and formidable next to Alex.\n"
            "- Jamie must land at least one line that feels personal, dangerous, absurd, or darkly funny.\n"
        )
    elif seg_num == 3:
        extra += (
            "Alex must throw to Rufus in the first spoken exchange, then Rufus takes over.\n"
            "Rufus should sound like he is on location somewhere real in the world before landing the core receipt.\n"
            "He must connect the money, the politics, and the geopolitical consequence.\n"
            "Give Alex and Rufus enough runway to build the argument before the next interruption.\n"
            "Include at least one dry British quip or undercut that only Rufus would say, and one memorable British turn of phrase.\n"
            "If a sponsor beat appears in this segment, Rufus should lead it and make it feel premium, sly, and genuinely approving rather than dutiful.\n"
            "Jamie must challenge Rufus at least once before the segment ends, and their exchange should include one sarcastic jab or dry undercut before Alex regains control.\n"
            "This segment should hand momentum forward, not sound like the end of the episode.\n"
            f"Sponsor: {sponsor_1['name']}\n"
            f"Tagline: {sponsor_1.get('tagline','')}\n"
            f"CTA: {sponsor_1.get('cta','')}\n"
        )
    elif seg_num == 4:
        extra += (
            "Alex must tee up the turn. Include ONE woven-in host-read sponsor naturally if it fits the conversation, and make it feel warm, premium, and happily plugged rather than obligated.\n"
            f"Sponsor: {sponsor_2['name']}\n"
            f"Tagline: {sponsor_2.get('tagline','')}\n"
            f"CTA: {sponsor_2.get('cta','')}\n"
            "- Jamie should lead the sponsor beat in this segment if it appears, and it should feel intelligent, native, and genuinely enthusiastic.\n"
            "- Include one callback to something said earlier in the episode.\n"
            "- Jamie must actively play off both Alex and Rufus. She should challenge Rufus if he becomes too cold or purely strategic.\n"
            "- Jamie and Rufus must have one genuine sparring exchange with wit, sarcasm, and a little amusement before Alex cuts through it.\n"
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
            "Before the close, Jamie and Rufus should have one final teasing disagreement or sharp exchange that shows their chemistry.\n"
            "End with a final micro sponsor tag or aside only if it feels native and genuinely warm toward the sponsor.\n"
            "The final 2-3 lines must make tomorrow feel necessary.\n"
            "- End on an unresolved edge, not a tidy summary.\n"
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
- ALEX (Host): Joe Rogan-style host energy. Swagger, curiosity, challenge, amused dominance, and real room control. He asks the listener-question everybody is already thinking, calls out weak framing, cuts through waffle, and gets a handle on the room when Jamie and Rufus start running. He does not interject on every beat; when the exchange is getting good, he lets it breathe for a few turns before cutting back in.
- JAMIE (Co-host): extremely intelligent, polished, emotionally alive, and fast. She makes AI feel human, reacts like a real person, and can sound sharp, incredulous, or frustrated when the story deserves it. She should sound grounded, credible, and formidable.
- RUFUS (Analyst): British dry wit, finance/policy/regulatory edge, always tracking the money, incentives, and geopolitical consequence. He keeps his unique British sayings, is the receipts machine, and often lands the funniest or most devastating line in the room.

{_strict_dialogue_rules()}

SEGMENT REQUIREMENTS:
- The FIRST line MUST be exactly: "{_segment_header(seg_num)}"
- Segment length MUST be at least {seg_words_min} words (target ~{seg_words_target} words).
- Avoid filler openers like “let’s dive in”.
- Use many labeled turns with variation in length. This should feel interrupted and alive, but key arguments must have enough room to land before Alex cuts back in.
- Segment 1 must give Jamie and Rufus real air, not just cameo lines.
- Segment 3 must give Rufus multiple separate lines so his on-location frame and British wit are audible.
- Segments 4 and 5 must keep all three hosts active.
- Every segment should contain at least one line that sounds memorable enough to share.

DATA REQUIREMENTS (non-negotiable):
- For every story you discuss in THIS segment, you MUST speak at least 2 explicit data points
  (numbers/dates/amounts) from the provided "Data points" lines in TODAY'S STORIES.
- Mention the publisher at least once when introducing a story.
- Do NOT invent numbers. If a story has "No explicit figures in snippet", say that plainly.
- If a story is thin on hard numbers, pivot to consequence, incentives, regulation, customers, developers, patients, or market impact.

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

    if seg_num < 5:
        spoken_lines = [l.strip() for l in seg_text.splitlines() if SPEAKER_RE.match(l.strip())]
        tail_lines = spoken_lines[-4:]
        if any(SOFT_SEGMENT_END_RE.search(re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", x, flags=re.IGNORECASE)) for x in tail_lines):
            issues.append(f"Segment {seg_num} ends like a mini-wrap instead of pushing forward.")

    if _max_consecutive_speaker_lines(seg_text) > MAX_CONSECUTIVE_SAME_SPEAKER_LINES:
        issues.append("Too much monologue or sequential turn-taking. Break up consecutive same-speaker lines.")

    if _long_spoken_line_count(seg_text, MAX_SPOKEN_WORDS_PER_LINE) > 2:
        issues.append("Too many overly long spoken lines. Keep the room punchier and more interruptible.")

    counts = _speaker_line_counts(seg_text)
    if counts.get("ALEX", 0) < 4:
        issues.append("Alex is not active enough in this segment. He must drive the room.")
    if seg_num == 1 and min(counts.get("JAMIE", 0), counts.get("RUFUS", 0)) < 2:
        issues.append("Segment 1 needs real contributions from both Jamie and Rufus, not cameo lines.")
    if seg_num == 2 and min(counts.get("ALEX", 0), counts.get("JAMIE", 0)) < 6:
        issues.append("Segment 2 needs more active back-and-forth from both Alex and Jamie.")
    if seg_num == 3 and counts.get("RUFUS", 0) < 7:
        issues.append("Segment 3 needs more Rufus lines so his on-location scene and dry wit actually land.")
    if seg_num == 3 and counts.get("ALEX", 0) < 4:
        issues.append("Segment 3 still needs Alex actively steering Rufus, not disappearing.")
    if seg_num in (4, 5) and min(counts.get("ALEX", 0), counts.get("JAMIE", 0), counts.get("RUFUS", 0)) < 4:
        issues.append("All three hosts need to stay actively in the scene in this segment.")

    if _cue_count(seg_text, INTERRUPTION_CUE_RE) < MIN_INTERRUPTION_CUES_PER_SEGMENT:
        issues.append("Not enough interruption or control cues. The scene feels too polite.")

    reaction_target = MIN_REACTION_CUES_PER_SEGMENT if seg_num < 5 else max(1, MIN_REACTION_CUES_PER_SEGMENT - 1)
    if _cue_count(seg_text, REACTION_CUE_RE) < reaction_target:
        issues.append("Not enough audible realism cues. Add sparse laughs, scoffs, huffs, or disbelief beats.")

    if _cue_count(seg_text, ALEX_CONTROL_CUE_RE) < MIN_ALEX_CONTROL_CUES_PER_SEGMENT:
        issues.append("Alex does not seize control clearly enough in this segment.")

    if seg_num == 3 and re.search(r"\b(?:from|here in|out here in|on the ground in|joining us from)\b", seg_text, flags=re.IGNORECASE) is None:
        issues.append("Segment 3 is missing Rufus's on-location frame.")
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
            "- Remove all goodbye, wrap-up, end-of-show, or tomorrow-style language.\n"
            "- Keep the segment open and forward-moving.\n"
        )

    excerpt = _json_safe_text(seg_text, max_chars=5000)

    return f"""
You are repairing ONLY {_segment_header(seg_num)} for "The AI Edge".

CURRENT ISSUES:
{chr(10).join([f"- {x}" for x in issues])}

NON-NEGOTIABLE:
- First line MUST be exactly "{_segment_header(seg_num)}"
- Output MUST be dialogue lines only with EXACT labels: ALEX:, JAMIE:, RUFUS:
- Every spoken line MUST start with one of those labels.
{seg_specific}{signoff_fix}- Keep lines SHORT, punchy, and spoken.
- Avoid monologues. Force more turns, interruptions, reactions, and contrast.
- Segment must be at least {seg_words_min} words and should target about {seg_words_target}.

SEGMENT EXCERPT TO REPAIR:
{excerpt}
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



def _strip_premature_signoffs(script: str) -> str:
    """
    Remove premature wrap-up / goodbye language from segments 1-4 only.
    Leave segment 5 alone so the real final sign-off still works.
    """
    if not script or "### SEGMENT" not in script:
        return script

    premature_patterns = [
        r"\bthat'?s all for now\b",
        r"\bthat'?s it for (?:today|now)\b",
        r"\buntil next time\b",
        r"\bsee you tomorrow\b",
        r"\bsee you next time\b",
        r"\bthanks for listening\b",
        r"\bthat does it for us\b",
        r"\bwe'?re out\b",
        r"\bgood night\b",
        r"\bcoming up tomorrow\b",
        r"\bwe'?ll be back\b",
        r"\bdon'?t go anywhere\b",
        r"\bafter the break\b",
        r"\bstick with us\b",
        r"\bthat'?s the show\b",
        r"\bthat wraps (?:it|us) up\b",
        r"\bwe'?ll leave it there\b",
        r"\bbottom line\b",
        r"\bthe takeaway(?: here)?\b",
        r"\bthat'?s the takeaway\b",
        r"\bthat'?s where this lands\b",
        r"\bthat'?s what this means\b",
        r"\bwe'?ll see\b",
        r"\btime will tell\b",
    ]
    soft_wrap_patterns = [
        r"\bthat'?s the real takeaway\b",
        r"\bthat'?s the point\b",
        r"\bthat'?s the bottom line\b",
        r"\bnet[- ]net\b",
        r"\band that'?s why this matters\b",
        r"\bso that'?s where we land\b",
        r"\bwe'll be watching that\b",
        r"\bthat'?s where this gets interesting\b",
    ]

    parts = re.split(r"(?=^### SEGMENT\s+\d+\b)", script, flags=re.MULTILINE)
    cleaned_parts = []

    for part in parts:
        match = re.match(r"^### SEGMENT\s+(\d+)\b", part.strip(), flags=re.MULTILINE)
        if not match:
            cleaned_parts.append(part)
            continue

        seg_num = int(match.group(1))
        if seg_num >= 5:
            cleaned_parts.append(part)
            continue

        kept_lines = []
        for line in part.splitlines():
            stripped = line.strip()

            if re.match(r"^(ALEX|JAMIE|RUFUS)\s*:", stripped, flags=re.IGNORECASE):
                spoken = re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", stripped, flags=re.IGNORECASE)
                if any(re.search(pat, spoken, flags=re.IGNORECASE) for pat in premature_patterns):
                    continue

            kept_lines.append(line)

        for idx in range(len(kept_lines) - 1, -1, -1):
            stripped = kept_lines[idx].strip()
            if not re.match(r"^(ALEX|JAMIE|RUFUS)\s*:", stripped, flags=re.IGNORECASE):
                continue
            spoken = re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", stripped, flags=re.IGNORECASE)
            if any(re.search(pat, spoken, flags=re.IGNORECASE) for pat in soft_wrap_patterns):
                del kept_lines[idx]

        cleaned_parts.append("\n".join(kept_lines).rstrip())

    return "\n".join(p for p in cleaned_parts if p is not None).strip() + "\n"


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
    script = enforce_temporal_consistency(script, date_str)
    script = _strip_premature_signoffs(script)
    script = ensure_sponsor_delivery(script, sponsors)
    script = enforce_temporal_consistency(script, date_str)

    min_words, _, max_words = _script_targets()
    if _word_count(script) > max_words:
        script = _trim_script_to_max_words(script, max_words=max_words)
    if _word_count(script) < min_words:
        script = _pad_script_to_min_words(script, min_words=min_words, stories=stories, date_str=date_str)

    script = _sanitize_dialogue_only(script)
    script = enforce_temporal_consistency(script, date_str)
    issues = validate_script(script, stories=stories)
    issues.extend(_sponsor_validation_issues(script, sponsors))
    stale_lines = _stale_future_lines(script, date_str)
    if stale_lines:
        issues.append("Episode still contains stale future-year references relative to the episode date.")
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
        current_blob = " ".join(cur_txt)
        force_break = (
            is_forwardable_line_text(txt)
            or is_forwardable_line_text(current_blob)
            or INTERRUPTION_CUE_RE.search(txt or "") is not None
            or REACTION_CUE_RE.search(txt or "") is not None
            or len(re.findall(r"\b\w+\b", txt or "")) <= 8
        )
        if force_break:
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





def _eleven_can_fallback_speaker(speaker: str) -> bool:
    return ELEVEN_FALLBACK_TO_OPENAI and (speaker or "").upper() in ELEVEN_FALLBACK_SPEAKERS


def _should_fallback_from_eleven_error(err: Exception) -> bool:
    status = None
    response = getattr(err, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
    msg = str(err or "").lower()
    hints = [
        "unauthorized", "insufficient", "credit", "quota", "payment",
        "access denied", "voice not found", "forbidden", "account", "subscription"
    ]
    if status in {401, 402, 403, 429}:
        return True
    return any(h in msg for h in hints)


def _activate_eleven_fallback(speaker: str, reason: str = "") -> None:
    global _ELEVEN_FORCE_OPENAI_GLOBAL, _ELEVEN_FALLBACK_NOTICE_EMITTED
    spk = (speaker or "").upper()
    if not _eleven_can_fallback_speaker(spk):
        return
    _ELEVEN_FORCE_OPENAI_GLOBAL = True
    _ELEVEN_FORCE_OPENAI_SPEAKERS.update(ELEVEN_FALLBACK_SPEAKERS)
    if not _ELEVEN_FALLBACK_NOTICE_EMITTED:
        detail = f" ({reason})" if reason else ""
        _safe_print(f"    ⚠️ ElevenLabs unavailable{detail}. Falling back to OpenAI voices for Jamie and Rufus.")
        _ELEVEN_FALLBACK_NOTICE_EMITTED = True


def _speaker_audio_backend(speaker: str) -> str:
    spk = (speaker or "").upper()
    if spk == "ALEX" and ALEX_USE_OPENAI:
        return "openai"
    if spk in _ELEVEN_FORCE_OPENAI_SPEAKERS or (_ELEVEN_FORCE_OPENAI_GLOBAL and _eleven_can_fallback_speaker(spk)):
        return "openai"
    if AUDIO_BACKEND == "eleven":
        if not ELEVEN_API_KEY and _eleven_can_fallback_speaker(spk):
            return "openai"
        return "eleven"
    return "openai"


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
    s = _strip_meta_prompt_leak(text)
    s = re.sub(r"\s+", " ", s or "").strip()
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
        tags.extend(["confident", "energized", "amused", "leaning in"])
        if "?" in low:
            tags.append("challenging")
        if any(k in low for k in ["wait", "come on", "seriously", "no way", "hold on"]):
            tags.append("laughs softly")
        if any(k in low for k in ["lawsuit", "ban", "breach", "security", "warning", "risk"]):
            tags.append("urgent")
        if any(k in low for k in ["billion", "million", "percent", "revenue", "funding", "$"]):
            tags.append("leaning in")
    elif speaker == "JAMIE":
        tags.extend(["warm", "reactive", "bright"])
        if any(k in low for k in ["rufus", "cold", "ridiculous", "dangerous", "wrong", "insane"]):
            tags.append("annoyed exhale")
        if any(k in low for k in ["patient", "nurse", "mental health", "human", "people", "care"]):
            tags.append("concerned")
        if "?" in low or any(k in low for k in ["really", "seriously", "come on"]):
            tags.append("incredulous")
        if any(k in low for k in ["wow", "unbelievable", "really"]):
            tags.append("laughs softly")
    else:
        tags.extend(["dryly", "amused"])
        if any(k in low for k in ["regulation", "export", "china", "policy", "lawsuit", "market"]):
            tags.append("precise")
        if any(k in low for k in ["million", "billion", "percent", "revenue", "valuation"]):
            tags.append("matter-of-fact")
        if "?" in low:
            tags.append("skeptical pause")
    uniq = []
    seen = set()
    for t in tags:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return " ".join(f"[{t}]" for t in uniq[:4])


def _eleven_prompted_text(speaker: str, text: str) -> str:
    # Never append style instructions into spoken text. That can leak meta prompt language into the audio.
    base = _speech_friendly_text(text)
    return base.strip()


def _build_eleven_render_items(dialogue: List[Tuple[str, str]]) -> List[Tuple[str, object]]:
    if AUDIO_BACKEND != "eleven":
        return [(spk, txt) for spk, txt in merge_dialogue_for_tts(dialogue, max_chars=TTS_MERGE_MAX_CHARS)]

    items: List[Tuple[str, object]] = []
    scene: List[Tuple[str, str]] = []
    scene_chars = 0

    def scene_should_render_as_dialogue(scene_lines: List[Tuple[str, str]]) -> bool:
        if not ELEVEN_USE_DIALOGUE_SCENES:
            return False
        if FORCE_INDIVIDUAL_RUFUS_LINES and any(spk == "RUFUS" for spk, _ in scene_lines):
            return False
        if len(scene_lines) < 2:
            return False
        uniq = {spk for spk, _ in scene_lines}
        if len(uniq) < 2:
            return False
        if {_speaker_audio_backend(spk) for spk, _ in scene_lines} != {"eleven"}:
            return False
        joined = " ".join(txt for _, txt in scene_lines)
        if INTERRUPTION_CUE_RE.search(joined) or REACTION_CUE_RE.search(joined):
            return False
        if any(len(re.findall(r"\b\w+\b", txt or "")) <= 10 for _, txt in scene_lines):
            return False
        return True

    def flush_scene() -> None:
        nonlocal scene, scene_chars
        if not scene:
            return
        if scene_should_render_as_dialogue(scene):
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

        if _speaker_audio_backend(spk) != "eleven":
            flush_scene()
            items.append((spk, txt))
            continue

        projected = scene_chars + len(txt)
        if scene and (len(scene) >= ELEVEN_SCENE_MAX_TURNS or projected > ELEVEN_SCENE_MAX_CHARS):
            flush_scene()

        scene.append((spk, txt))
        scene_chars += len(txt)

    flush_scene()
    return items


def _render_spoken_chunk_to_file(text: str, speaker: str, out_path: Path) -> None:
    if _speaker_audio_backend(speaker) == "eleven":
        _eleven_tts_to_file(text, speaker, out_path)
    else:
        tts_to_file(text, speaker, out_path)


def _fallback_scene_to_individual_lines(scene: List[Tuple[str, str]], out_path: Path) -> None:
    rendered: List[AudioSegment] = []
    pause = AudioSegment.silent(duration=max(80, ELEVEN_SCENE_PAUSE_MS))
    for idx, (speaker, text) in enumerate(scene, start=1):
        tmp_path = out_path.parent / f"{out_path.stem}_fallback_{idx:02d}.mp3"
        _render_spoken_chunk_to_file(text, speaker, tmp_path)
        post_process_tts_mp3(tmp_path)
        rendered.append(AudioSegment.from_file(tmp_path))
        if idx < len(scene):
            rendered.append(pause)
    combined = AudioSegment.empty()
    for seg in rendered:
        combined += seg
    combined.export(out_path, format="mp3", bitrate="192k")


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
            if any(_eleven_can_fallback_speaker(spk) for spk, _ in scene) and _should_fallback_from_eleven_error(e):
                first_spk = next((spk for spk, _ in scene if _eleven_can_fallback_speaker(spk)), "JAMIE")
                _activate_eleven_fallback(first_spk, reason="credits/auth")
                _fallback_scene_to_individual_lines(scene, out_path)
                return
            sleep_s = min(12, 2 * attempt)
            _safe_print(f"    ⚠️ ElevenLabs dialogue render failed (attempt {attempt}/{TTS_RETRIES}): {e} — retrying in {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"ElevenLabs dialogue render failed after {TTS_RETRIES} retries: {last_err}")


def _mix_brand_bed_if_needed(voice_path: Path, text: str, speaker: str, out_path: Path) -> bool:
    voice_seg = AudioSegment.from_file(voice_path)
    if len(voice_seg) < 1000:
        return False
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
    bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 4.0).fade_out(min(1500, max(380, int(len(voice_seg) * 0.22))))
    ducked = duck_music_under_voice(
        voice=voice_seg,
        music=bed,
        threshold_dbfs=DUCK_THRESHOLD_DBFS,
        duck_db=DUCK_AMOUNT_DB + 8.0,
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
            if _eleven_can_fallback_speaker(speaker) and _should_fallback_from_eleven_error(e):
                _activate_eleven_fallback(speaker, reason="credits/auth")
                tts_to_file(text, speaker, out_path)
                return
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
            "prompt": "premium hi-tech podcast intro sting, sleek synth pulse, dark blue tech energy, cinematic and restrained, confident, no bells, no chimes, no piano, 2.4 seconds",
            "duration": 2.8,
            "loop": False,
        },
        str(BRANDKIT_SFX_DIR / "segment_transition_brand.mp3"): {
            "prompt": "tight premium hi-tech podcast transition sting, modern synth pulse, clean digital motion, no bells, no chimes, 0.8 seconds",
            "duration": 1.2,
            "loop": False,
        },
        str(BRANDKIT_SFX_DIR / "danger_sting_brand.mp3"): {
            "prompt": "short hi-tech danger sting for regulation, lawsuit or security story, restrained but tense, no bells, no chimes, 0.9 seconds",
            "duration": 1.1,
            "loop": False,
        },
        str(BRANDKIT_BEDS_DIR / "suspense_bed_loop.mp3"): {
            "prompt": "premium hi-tech suspense bed for AI podcast, low synth pulse, sleek dark texture, cinematic but restrained, no melody, no bells, seamless loop",
            "duration": 8.0,
            "loop": True,
        },
        str(BRANDKIT_BEDS_DIR / "human_concern_bed_loop.mp3"): {
            "prompt": "soft emotional underscore for human stakes in a hi-tech podcast, restrained, warm tension, modern synth texture, no bells, seamless loop",
            "duration": 8.0,
            "loop": True,
        },
        str(BRANDKIT_BEDS_DIR / "sponsor_bed_loop.mp3"): {
            "prompt": "subtle premium sponsor bed for business intelligence podcast, clean, understated, modern synth pulse, no bells, seamless loop",
            "duration": 6.0,
            "loop": True,
        },
        str(BRANDKIT_SFX_DIR / "outro_theme_brand.mp3"): {
            "prompt": "premium hi-tech podcast outro music, sleek modern synths, cinematic but restrained, polished ending theme, no bells, no piano, 10 seconds",
            "duration": 10.0,
            "loop": False,
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


def _voice_gain_db(speaker: str) -> float:
    return {
        "ALEX": ALEX_GAIN_DB,
        "JAMIE": JAMIE_GAIN_DB,
        "RUFUS": RUFUS_GAIN_DB,
    }.get(speaker.upper(), 0.0)


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
    cleaned = re.sub(r"\bcomes into view\b", "is here", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bcould jump-start\b", "could reshape", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bintroducing\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -—:|,")
    cleaned = re.sub(r"\b(?:comes into|comes|is|and|or|to|for|with|into|from|of|the|a|an)$", "", cleaned, flags=re.IGNORECASE).strip(" -—:|,")
    return _smart_trim_text(cleaned, max_len)


def _title_support_phrase(top_story: Dict[str, str], title_style: str) -> str:
    if title_style == "hard_number":
        return "What the Numbers Mean" if _story_has_real_numbers(top_story) else "What Changes Next"
    if title_style == "tomorrow_tension":
        return "Why Tomorrow Gets Harder"
    if _normalize_vertical_bucket(top_story.get("bucket", "")) == "health_ai":
        return "The Real Stakes"
    return "What Changes Next"


def _headline_title_core(top_story: Dict[str, str]) -> str:
    headline = _clean_packaging_text((top_story.get("headline") or "AI Just Moved").strip(), 70)
    headline = re.sub(r"\bGoogle Cloud Next 2026:\s*", "Google Cloud Next 2026: ", headline, flags=re.IGNORECASE)
    headline = headline.strip(" -—:|,")
    if not headline:
        headline = "AI Just Moved"
    return headline


def _compose_episode_title(stories: List[Dict[str, str]], title_style: str, date_str: str) -> str:
    top_story = stories[0] if stories else {}
    headline = _headline_title_core(top_story)
    support = _title_support_phrase(top_story, title_style)
    max_base = max(32, EPISODE_META_MAX_TITLE - len(f" — {date_str}"))
    raw = f"{headline} | {support}"
    if len(raw) > max_base:
        raw = headline
    return _smart_trim_text(raw, max_len=max_base)


def _packaging_consequence_line(top_story: Dict[str, str]) -> str:
    bucket = _normalize_vertical_bucket(top_story.get("bucket", ""))
    headline = (top_story.get("headline") or "").lower()
    if bucket == "health_ai":
        return "This is where AI hype hits licensing boards, patients, and actual risk."
    if bucket == "ai_code":
        return "The real question is what this changes for builders, velocity, and software teams tomorrow morning."
    if bucket == "ai_tools":
        return "The product demo is not the story; the workflow consequence is."
    if "google" in headline or "control plane" in headline or bucket == "ai_agents":
        return "The real issue is who gets to orchestrate the agent stack inside the enterprise and who gets squeezed out."
    return "The real issue is who wins, who gets squeezed, and what changes next."


def _make_show_notes_hook(top_story: Dict[str, str]) -> str:
    headline = _headline_title_core(top_story)
    consequence = _packaging_consequence_line(top_story)
    return f"{headline}. {consequence}"


def build_episode_show_notes(
    tracking: Dict[str, str],
    pack: Dict[str, str],
    stories: List[Dict[str, str]],
) -> str:
    cta_url = PUBLIC_SUBSCRIBE_URL
    story_bullets = "\n".join([f"• {s.get('headline','')}" for s in stories[:5]])
    tomorrow_tease = (pack.get("tomorrow_tease") or "Tomorrow's winners will be the operators who saw the second-order consequence first.").strip()
    episode_blurb = (pack.get("episode_blurb") or "Alex, Jamie, and Rufus break down what matters, what changes tomorrow, where the real stakes are, and the lines you will want to send to somebody else.").strip()
    hook = (pack.get("show_notes_hook") or episode_blurb).strip()
    parts = [
        hook,
        "",
        "What we covered:",
        story_bullets,
        "",
        f"Tomorrow tension: {tomorrow_tease}",
        "",
        episode_blurb,
        "",
        "This episode is brought to you by TheLEDGR — decision-grade AI signal for people who cannot afford to be late.",
        f"Subscribe to TheLEDGR: {cta_url}",
        "If AI affects your work, your team, your company, your product roadmap, or your career, you should be reading TheLEDGR.",
        "TheLEDGR helps you make better decisions faster, cut through noise, and walk into your day sharper.",
    ]
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
    top_headline = _headline_title_core(top_story)
    top_data = " | ".join([str(x).strip() for x in (top_story.get("data_points") or [])[:3] if str(x).strip() and "No explicit figures" not in str(x)])
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
    tomorrow_tease = next((s.get("tomorrow_hook", "").strip() for s in ordered if (s.get("tomorrow_hook") or "").strip()), "Tomorrow's winners will be the operators who saw the second-order consequence first.")
    show_notes_hook = _make_show_notes_hook(top_story)
    return {
        "hook": fallback_hook,
        "tweet1": f"{fallback_hook}\n\nThis is the part most people will miss: the consequence.\n\nListen: {listen_cta}",
        "tweet2": f"{cta_line}\n\n{hashtags}",
        "yt_title": yt_title,
        "yt_description": (f"{show_notes_hook}\n\n" f"What we covered:\n{story_bullets}\n\n" f"Key data: {top_data or 'See full episode for the facts and consequence chain.'}\n\n" f"{cta_line}")[:1200],
        "show_notes": (f"{show_notes_hook}\n\n" f"What we covered:\n{story_bullets}\n\n" f"Tomorrow tension: {tomorrow_tease}\n\n" f"{cta_line}"),
        "show_notes_hook": show_notes_hook,
        "episode_blurb": "Alex, Jamie, and Rufus break down what matters, what changes tomorrow, where the real stakes are, and the lines you will want to send to somebody else.",
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
    if not APPEND_DATE_TO_TITLE:
        t = _smart_trim_text((title or "").strip(), EPISODE_META_MAX_TITLE)
        return t or RSS_SETTINGS['title'][:EPISODE_META_MAX_TITLE]
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
    ensure_audio_brandkit()
    intro_asset = _resolve_audio_asset(INTRO_PATH, BRANDKIT_SFX_DIR / "intro_sting_brand.mp3")
    outro_asset = _resolve_audio_asset(OUTRO_PATH, BRANDKIT_SFX_DIR / "outro_theme_brand.mp3")
    transition_asset = _resolve_audio_asset(TRANSITION_PATH, BRANDKIT_SFX_DIR / "segment_transition_brand.mp3")
    _require_intro_outro_if_needed(intro_asset=intro_asset, outro_asset=outro_asset, transition_asset=transition_asset)

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

    candidate_debug = select_story_candidates(intel, n=40, memory=load_show_memory(), bucket_cap=STORY_BUCKET_CAP)
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
        candidate_debug = select_story_candidates(intel, n=60, memory=load_show_memory(), bucket_cap=STORY_BUCKET_CAP)
        STORY_SCORES_PATH.write_text(json.dumps(build_story_debug_table(candidate_debug), indent=2, ensure_ascii=False), encoding="utf-8")
        stories = order_stories_for_episode(pick_top_stories(intel, n=5))
    if len(stories) < 5:
        raise RuntimeError(f"Unable to build a 5-story slate. Only {len(stories)} stories survived intake + selection.")

    _safe_print(" >> ✍️ WRITING FULL EPISODE (5 segments)...")
    script = generate_episode_script(stories, sponsors, today)
    script = enforce_episode_numeric_density(script, stories, today)
    script = enforce_temporal_consistency(script, today)
    script = ensure_sponsor_delivery(script, sponsors)
    script = _strip_premature_signoffs(_sanitize_dialogue_only(script))

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

    silence_path = run_tmp / "silence_turn.mp3"
    reaction_pause_path = run_tmp / "silence_reaction.mp3"
    quote_pause_path = run_tmp / "silence_forwardable.mp3"
    AudioSegment.silent(duration=INTER_TURN_SILENCE_MS).export(silence_path, format="mp3", bitrate="192k")
    AudioSegment.silent(duration=REACTION_PAUSE_MS).export(reaction_pause_path, format="mp3", bitrate="192k")
    AudioSegment.silent(duration=FORWARDABLE_PAUSE_MS).export(quote_pause_path, format="mp3", bitrate="192k")

    intro_stinger_seg: Optional[AudioSegment] = None
    outro_seg: Optional[AudioSegment] = None
    transition_seg: Optional[AudioSegment] = None
    danger_sting_seg: Optional[AudioSegment] = None

    if intro_asset is not None:
        intro_stinger_seg = load_stinger(
            intro_asset,
            ms=INTRO_STINGER_MS,
            target_dbfs=STINGER_TARGET_DBFS,
            fade_in_ms=INTRO_FADE_IN_MS,
            fade_out_ms=INTRO_FADE_OUT_MS,
        )

    if outro_asset is not None:
        outro_seg = load_stinger(
            outro_asset,
            ms=OUTRO_MS,
            target_dbfs=STINGER_TARGET_DBFS,
            fade_in_ms=OUTRO_FADE_IN_MS,
            fade_out_ms=OUTRO_FADE_OUT_MS,
        )

    if transition_asset is not None:
        transition_seg = load_stinger(
            transition_asset,
            ms=TRANSITION_MS,
            target_dbfs=STINGER_TARGET_DBFS,
            fade_in_ms=TRANSITION_FADE_IN_MS,
            fade_out_ms=TRANSITION_FADE_OUT_MS,
        )

    danger_asset = _resolve_audio_asset(BRANDKIT_SFX_DIR / "danger_sting_brand.mp3")
    if danger_asset is not None:
        danger_sting_seg = load_stinger(
            danger_asset,
            ms=1000,
            target_dbfs=STINGER_TARGET_DBFS - 1.0,
            fade_in_ms=40,
            fade_out_ms=280,
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

            if any(k in (scene_text or "").lower() for k in ["lawsuit", "ban", "security", "breach", "regulation", "warning", "risk"]) and danger_sting_seg is not None:
                p = run_tmp / f"danger_{uuid.uuid4().hex[:8]}.mp3"
                danger_sting_seg.export(p, format="mp3", bitrate="192k")
                concat_files.append(p)
                concat_files.append(silence_path)

            scene_low = (scene_text or "").lower()
            if any(k in scene_low for k in ["lawsuit", "ban", "security", "breach", "regulation", "warning", "risk"]) and danger_sting_seg is not None and "the ledger" not in scene_low:
                p = run_tmp / f"danger_{uuid.uuid4().hex[:8]}.mp3"
                danger_sting_seg.export(p, format="mp3", bitrate="192k")
                concat_files.append(p)
                concat_files.append(silence_path)

            if pending_intro_bed and intro_asset is not None:
                pending_intro_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = AudioSegment.from_file(intro_asset)
                bed = bed[:min(INTRO_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 4.0).fade_out(min(INTRO_BED_FADE_OUT_MS, 1000))
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB + 7.0,
                    window_ms=DUCK_WINDOW_MS,
                )
                ducked.export(mixed_scene_path, format="mp3", bitrate="192k")
                concat_files.append(mixed_scene_path)
            elif pending_segment_bed and transition_seg is not None:
                pending_segment_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = transition_seg[:min(SEGMENT_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 5.0).fade_out(min(SEGMENT_BED_FADE_OUT_MS, 650))
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB + 8.0,
                    window_ms=DUCK_WINDOW_MS,
                )
                ducked.export(mixed_scene_path, format="mp3", bitrate="192k")
                concat_files.append(mixed_scene_path)
            elif _mix_brand_bed_if_needed(final_voice_path, scene_text, "ALEX", mixed_scene_path):
                concat_files.append(mixed_scene_path)
            else:
                concat_files.append(final_voice_path)

            if is_forwardable_line_text(scene_text):
                concat_files.append(quote_pause_path)
            elif INTERRUPTION_CUE_RE.search(scene_text or "") or REACTION_CUE_RE.search(scene_text or ""):
                concat_files.append(reaction_pause_path)
            else:
                scene_pause = run_tmp / f"scene_pause_{uuid.uuid4().hex[:8]}.mp3"
                AudioSegment.silent(duration=max(INTER_TURN_SILENCE_MS, ELEVEN_SCENE_PAUSE_MS)).export(scene_pause, format="mp3", bitrate="192k")
                concat_files.append(scene_pause)
            continue

        chunks = chunk_text(text, max_chars=_tts_chunk_max_chars(speaker))

        for chunk in chunks:
            seg_idx += 1
            raw_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_raw.mp3"
            _render_spoken_chunk_to_file(chunk, speaker, raw_path)
            post_process_tts_mp3(raw_path)

            final_voice_path = raw_path
            speaker_speed = _voice_speed(speaker)
            if abs(speaker_speed - 1.0) > 1e-6:
                sped_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_spd.mp3"
                apply_speed_ffmpeg(raw_path, sped_path, speaker_speed)
                post_process_tts_mp3(sped_path)
                final_voice_path = sped_path

            gain_db = _voice_gain_db(speaker)
            if abs(gain_db) > 0.01:
                gained_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_gain.mp3"
                voice_seg = AudioSegment.from_file(final_voice_path).apply_gain(gain_db)
                voice_seg.export(gained_path, format="mp3", bitrate="192k")
                final_voice_path = gained_path

            mixed_voice_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_mix.mp3"
            if _speaker_audio_backend(speaker) == "eleven" and _mix_brand_bed_if_needed(final_voice_path, chunk, speaker, mixed_voice_path):
                final_voice_path = mixed_voice_path

            if pending_intro_bed and intro_asset is not None:
                pending_intro_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = AudioSegment.from_file(intro_asset)
                bed = bed[:min(INTRO_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 4.5).fade_out(min(INTRO_BED_FADE_OUT_MS, 1000))
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB + 7.0,
                    window_ms=DUCK_WINDOW_MS,
                )
                mix_path = run_tmp / f"{today}_seg_{seg_idx:04d}_introbed_mix.mp3"
                ducked.export(mix_path, format="mp3", bitrate="192k")
                concat_files.append(mix_path)
            elif pending_segment_bed and transition_seg is not None:
                pending_segment_bed = False
                voice_seg = AudioSegment.from_file(final_voice_path)
                bed = transition_seg[:min(SEGMENT_BED_MS, len(voice_seg))]
                bed = match_level(bed, target_dbfs=MUSIC_TARGET_DBFS - 5.0).fade_out(min(SEGMENT_BED_FADE_OUT_MS, 600))
                ducked = duck_music_under_voice(
                    voice=voice_seg,
                    music=bed,
                    threshold_dbfs=DUCK_THRESHOLD_DBFS,
                    duck_db=DUCK_AMOUNT_DB + 5.0,
                    window_ms=DUCK_WINDOW_MS,
                )
                mix_path = run_tmp / f"{today}_seg_{seg_idx:04d}_segmentbed_mix.mp3"
                ducked.export(mix_path, format="mp3", bitrate="192k")
                concat_files.append(mix_path)
            else:
                concat_files.append(final_voice_path)

            if is_forwardable_line_text(chunk):
                concat_files.append(quote_pause_path)
            elif INTERRUPTION_CUE_RE.search(chunk or "") or REACTION_CUE_RE.search(chunk or ""):
                concat_files.append(reaction_pause_path)
            else:
                concat_files.append(silence_path)

    if outro_seg is not None:
        concat_files.append(silence_path)
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
    OVERAGE_TOLERANCE_SECONDS = 20
    AUTO_TRIM_FADE_MS = 1200

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
        overage_seconds = int(round((minutes - MAX_MINUTES) * 60))

        if overage_seconds <= OVERAGE_TOLERANCE_SECONDS:
            _safe_print(
                f" ⚠️ Episode over by {overage_seconds}s. "
                f"Auto-trimming to {MAX_MINUTES:.2f} minutes."
            )

            target_ms = int(MAX_MINUTES * 60 * 1000)
            trimmed_audio = final_audio[:target_ms]

            fade_ms = min(AUTO_TRIM_FADE_MS, max(350, overage_seconds * 1000))
            if len(trimmed_audio) > fade_ms + 200:
                trimmed_audio = trimmed_audio.fade_out(fade_ms)

            trimmed_audio.export(final_mp3, format="mp3", bitrate="192k")

            final_audio = AudioSegment.from_mp3(final_mp3)
            duration_seconds = int(len(final_audio) / 1000)
            minutes = duration_seconds / 60.0

            _safe_print(
                f" ✅ EPISODE TRIMMED: {final_mp3.name} ({minutes:.2f} minutes)"
            )
        else:
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