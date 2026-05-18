# -*- coding: utf-8 -*-
"""
The AI Edge v3.2.1 preflight guard — hard-debate/Gemini false-positive hotfix.

Paste this entire file as: preflight_guard_v3_1.py

Cheap checks before any LLM/TTS spend:
- Required files exist and compile.
- v3.2 hard-debate/top-events writer room is installed.
- Gemini Jamie router patches both tts_to_file and _render_spoken_chunk_to_file.
- Legacy marketing and ElevenLabs are disabled.

Why v3.2.1 exists:
The v3.2 guard incorrectly failed if writer_room_v3_1.py contained the phrase
"Today’s AI Lesson" anywhere, even when it appeared only as a banned phrase in a
negative instruction. This version checks for active lesson-first title generation
instead of false-positive banned-language instructions.
"""

from __future__ import annotations

import os
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
REQUIRED = [
    "main.py",
    "v3_1_runner.py",
    "writer_room_v3_1.py",
    "growth_overlay_v3_1.py",
    "hybrid_tts_router_v3_1.py",
    "feed_sanitize_v3_1.py",
    "no_repeat_guard_v3_1.py",
    "run_broadcast.py",
]


def fail(reason: str) -> None:
    print(">> ❌ COST-SAFE PREFLIGHT FAILED before expensive generation", flush=True)
    print(f"   - {reason}", flush=True)
    print(">> No LLM/TTS/ElevenLabs spend should happen after this failure.", flush=True)
    sys.exit(1)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def _contains_active_lesson_first_generation(writer: str) -> bool:
    """
    Return True only when the writer appears to actively generate old lesson-first
    public packaging. Do not fail for banned-phrase examples such as:
    - No "Today’s AI Lesson" title/framing.
    - This is NOT an AI lesson show.
    """
    dangerous_patterns = [
        r"published_title\s*[:=]\s*[\"']Today[’']s AI Lesson",
        r"spotify_title\s*[:=]\s*[\"']Today[’']s AI Lesson",
        r"yt_title\s*[:=]\s*[\"']Today[’']s AI Lesson",
        r"youtube_title\s*[:=]\s*[\"']Today[’']s AI Lesson",
        r"return\s+f?[\"']Today[’']s AI Lesson",
        r"title\s*=\s*f?[\"']Today[’']s AI Lesson",
        r"f[\"']Today[’']s AI Lesson:\s*\{",
    ]
    return any(re.search(pat, writer, flags=re.IGNORECASE) for pat in dangerous_patterns)


def main() -> None:
    print(">> STARTING: V3.2.1 hard-debate cost-safe preflight guard", flush=True)

    for name in REQUIRED:
        p = ROOT / name
        if not p.exists():
            fail(f"missing required file: {name}")
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:
            fail(f"compile failed for {name}: {e}")

    runner = _text("v3_1_runner.py")
    writer = _text("writer_room_v3_1.py")
    router = _text("hybrid_tts_router_v3_1.py")
    growth = _text("growth_overlay_v3_1.py")

    if 'RUN_MARKETING_ASSETS"] = "false"' not in runner and "RUN_MARKETING_ASSETS\"] = \"false\"" not in runner:
        fail("v3_1_runner.py does not force RUN_MARKETING_ASSETS=false before main.py import")
    if 'AUDIO_BACKEND"] = "openai"' not in runner and "AUDIO_BACKEND\"] = \"openai\"" not in runner:
        fail("v3_1_runner.py does not force AUDIO_BACKEND=openai before main.py import")
    if 'ELEVENLABS_ENABLED"] = "false"' not in runner and "ELEVENLABS_ENABLED\"] = \"false\"" not in runner:
        fail("v3_1_runner.py does not force ELEVENLABS_ENABLED=false")

    writer_l = writer.lower()
    if "v3.2" not in writer_l or "hard-debate" not in writer_l or "top-events" not in writer_l:
        fail("writer_room_v3_1.py is not the v3.2 hard-debate/top-events version")
    if "pick_top_stories_v3_2" not in writer:
        fail("writer_room_v3_1.py does not override pick_top_stories for top AI events")
    if "not an ai lesson show" not in writer_l or "hard human debate" not in writer_l:
        fail("writer_room_v3_1.py does not contain the hard-debate creative mandate")
    if "today's top ai events" not in writer_l and "top ai events" not in writer_l:
        fail("writer_room_v3_1.py does not contain top AI events framing")
    if _contains_active_lesson_first_generation(writer):
        fail("writer_room_v3_1.py appears to actively generate old lesson-first public packaging")

    if "_render_spoken_chunk_to_file" not in router or "hybrid_render_spoken_chunk_to_file" not in router:
        fail("hybrid_tts_router_v3_1.py does not patch the production render path")
    if "tts_to_file" not in router or "hybrid_tts_to_file" not in router:
        fail("hybrid_tts_router_v3_1.py does not patch tts_to_file")
    if "_speaker_audio_backend" not in router or "gemini" not in router.lower():
        fail("hybrid_tts_router_v3_1.py does not force Jamie Gemini routing")
    if "jamie_gemini_successes" not in router or "GEMINI_TTS_MODEL" not in router:
        fail("hybrid_tts_router_v3_1.py does not expose Jamie Gemini report counters")

    if "top_event_heat" not in growth or "V3_2_TOP_EVENTS_OVERLAY_INSTALLED" not in growth:
        fail("growth_overlay_v3_1.py is not the v3.2 top-events scoring overlay")

    bad_env = []
    if os.getenv("RUN_MARKETING_ASSETS", "false").strip().lower() not in ("false", "0", "no"):
        bad_env.append("RUN_MARKETING_ASSETS must be false")
    if os.getenv("AUDIO_BACKEND", "openai").strip().lower() == "eleven":
        bad_env.append("AUDIO_BACKEND must not be eleven")
    if os.getenv("ELEVENLABS_ENABLED", "false").strip().lower() in ("true", "1", "yes"):
        bad_env.append("ELEVENLABS_ENABLED must be false")
    if os.getenv("JAMIE_TTS_PROVIDER", "gemini").strip().lower() != "gemini":
        bad_env.append("JAMIE_TTS_PROVIDER must be gemini")
    if bad_env:
        fail("; ".join(bad_env))

    print(">> ✅ COST-SAFE PREFLIGHT PASSED", flush=True)
    print(">> ✅ Creative format: v3.2 hard-debate human program", flush=True)
    print(">> ✅ Story selection: top AI events, no forced sector quota", flush=True)
    print(">> ✅ TTS routing: Jamie Gemini forced path + OpenAI fallback; Alex/Rufus OpenAI; ElevenLabs OFF", flush=True)
    print(">> ✅ Preflight guard v3.2.1 false-positive fix active", flush=True)


if __name__ == "__main__":
    main()
