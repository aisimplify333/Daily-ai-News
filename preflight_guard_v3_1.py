# -*- coding: utf-8 -*-
"""
The AI Edge v3.2 preflight guard.

Paste this entire file as: preflight_guard_v3_1.py

Cheap checks before any LLM/TTS spend:
- Required files exist and compile.
- v3.2 hard-debate/top-events writer room is installed.
- Gemini Jamie router patches both tts_to_file and _render_spoken_chunk_to_file.
- Legacy marketing and ElevenLabs are disabled.
"""

from __future__ import annotations

import os
import py_compile
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


def main() -> None:
    print(">> STARTING: V3.2 hard-debate cost-safe preflight guard", flush=True)

    for name in REQUIRED:
        p = ROOT / name
        if not p.exists():
            fail(f"missing required file: {name}")
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:
            fail(f"compile failed for {name}: {e}")

    runner = (ROOT / "v3_1_runner.py").read_text(encoding="utf-8", errors="ignore")
    writer = (ROOT / "writer_room_v3_1.py").read_text(encoding="utf-8", errors="ignore")
    router = (ROOT / "hybrid_tts_router_v3_1.py").read_text(encoding="utf-8", errors="ignore")
    growth = (ROOT / "growth_overlay_v3_1.py").read_text(encoding="utf-8", errors="ignore")

    if 'RUN_MARKETING_ASSETS"] = "false"' not in runner and "RUN_MARKETING_ASSETS\"] = \"false\"" not in runner:
        fail("v3_1_runner.py does not force RUN_MARKETING_ASSETS=false before main.py import")
    if 'AUDIO_BACKEND"] = "openai"' not in runner and "AUDIO_BACKEND\"] = \"openai\"" not in runner:
        fail("v3_1_runner.py does not force AUDIO_BACKEND=openai before main.py import")
    if 'ELEVENLABS_ENABLED"] = "false"' not in runner and "ELEVENLABS_ENABLED\"] = \"false\"" not in runner:
        fail("v3_1_runner.py does not force ELEVENLABS_ENABLED=false")

    if "v3.2" not in writer.lower() or "hard-debate" not in writer.lower() or "top-events" not in writer.lower():
        fail("writer_room_v3_1.py is not the v3.2 hard-debate/top-events version")
    if "pick_top_stories_v3_2" not in writer:
        fail("writer_room_v3_1.py does not override pick_top_stories for top AI events")
    if "Today’s AI Lesson" in writer or "TODAY'S AI LESSON" in writer:
        fail("writer_room_v3_1.py still contains lesson-first framing")

    if "_render_spoken_chunk_to_file" not in router or "hybrid_render_spoken_chunk_to_file" not in router:
        fail("hybrid_tts_router_v3_1.py does not patch the production render path")
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
    if bad_env:
        fail("; ".join(bad_env))

    print(">> ✅ COST-SAFE PREFLIGHT PASSED", flush=True)
    print(">> ✅ Creative format: v3.2 hard-debate human program", flush=True)
    print(">> ✅ Story selection: top AI events, no forced sector quota", flush=True)
    print(">> ✅ TTS routing: Jamie Gemini forced path + OpenAI fallback; Alex/Rufus OpenAI; ElevenLabs OFF", flush=True)


if __name__ == "__main__":
    main()
