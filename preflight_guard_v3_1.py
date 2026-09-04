# -*- coding: utf-8 -*-
"""
The AI Edge v3.2.2 preflight guard — v3.3 connection-first lineage accepted.

Paste this entire file as: preflight_guard_v3_1.py

Cheap checks before any LLM/TTS spend:
- Required files exist and compile.
- An approved hard-debate/top-events writer room is installed (v3.2 OR v3.3).
- Grok Jamie router patches both tts_to_file and _render_spoken_chunk_to_file.
- Legacy marketing and ElevenLabs are disabled.

Why v3.2.2 exists:
v3.3 ("connection-first") is an approved superset of the v3.2 hard-debate writer:
it keeps top-events story selection and the no-lesson rule, and adds cross-episode
continuity, designed-argument pre-production, and a binary structural gate. The
v3.2.1 guard hard-coded the literal string "v3.2" and the function name
"pick_top_stories_v3_2", so it rejected the v3.3 writer as unrecognized.

v3.2.2 changes ONLY the writer-lineage fingerprint: it now accepts v3.2 OR v3.3,
and accepts either pick_top_stories_v3_2 or pick_top_stories_v3_3. Every other
check — marketing off, ElevenLabs off, lesson-first detection, the router patch
checks, the growth overlay check, the environment checks — is byte-for-byte
unchanged and just as strict. This does not weaken the guard; it teaches it about
an approved version.
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
    "grok_tts_v4.py",
    "feed_sanitize_v3_1.py",
    "no_repeat_guard_v3_1.py",
    "production_delivery_gate.py",
    "production_assets.py",
    "run_broadcast.py",
]
REQUIRED_DATA = [
    "show_memory.json",
    "listener_poll_results.json",
    "show_trailer_script.txt",
    "show_trailer_manifest.json",
    "social_profile_bio.txt",
]

# Approved writer lineages. Adding a future version means adding it here —
# deliberately, in the guard — never by loosening the check to accept anything.
APPROVED_WRITER_VERSIONS = ("v3.2", "v3.3")
APPROVED_PICK_OVERRIDES = ("pick_top_stories_v3_2", "pick_top_stories_v3_3")


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
    print(">> STARTING: V3.2.2 hard-debate cost-safe preflight guard", flush=True)

    for name in REQUIRED:
        p = ROOT / name
        if not p.exists():
            fail(f"missing required file: {name}")
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:
            fail(f"compile failed for {name}: {e}")
    for name in REQUIRED_DATA:
        if not (ROOT / name).exists():
            fail(f"missing relationship-engine asset: {name}")

    runner = _text("v3_1_runner.py")
    writer = _text("writer_room_v3_1.py")
    router = _text("hybrid_tts_router_v3_1.py")
    growth = _text("growth_overlay_v3_1.py")
    workflow = _text(".github/workflows/daily_podcast.yml")

    if 'RUN_MARKETING_ASSETS"] = "false"' not in runner and "RUN_MARKETING_ASSETS\"] = \"false\"" not in runner:
        fail("v3_1_runner.py does not force RUN_MARKETING_ASSETS=false before main.py import")
    if 'AUDIO_BACKEND"] = "openai"' not in runner and "AUDIO_BACKEND\"] = \"openai\"" not in runner:
        fail("v3_1_runner.py does not force AUDIO_BACKEND=openai before main.py import")
    if 'ELEVENLABS_ENABLED"] = "false"' not in runner and "ELEVENLABS_ENABLED\"] = \"false\"" not in runner:
        fail("v3_1_runner.py does not force ELEVENLABS_ENABLED=false")

    writer_l = writer.lower()
    # --- writer lineage fingerprint (the ONLY thing changed in v3.2.2) ---
    if not any(v in writer_l for v in APPROVED_WRITER_VERSIONS):
        fail("writer_room_v3_1.py is not an approved (v3.2/v3.3) hard-debate writer version")
    if "hard-debate" not in writer_l or "top-events" not in writer_l:
        fail("writer_room_v3_1.py is not the hard-debate/top-events writer room")
    if not any(name in writer for name in APPROVED_PICK_OVERRIDES):
        fail("writer_room_v3_1.py does not override pick_top_stories for top AI events")
    # --- everything below is unchanged from v3.2.1, same strictness ---
    if "not an ai lesson show" not in writer_l or "hard human debate" not in writer_l:
        fail("writer_room_v3_1.py does not contain the hard-debate creative mandate")
    if "today's top ai events" not in writer_l and "top ai events" not in writer_l:
        fail("writer_room_v3_1.py does not contain top AI events framing")
    if _contains_active_lesson_first_generation(writer):
        fail("writer_room_v3_1.py appears to actively generate old lesson-first public packaging")

    relationship_contract = {
        "What changed. Who wins. What you do next.": "permanent listener promise is missing",
        "strong_disagreements": "memory does not retain strong disagreements",
        "running_jokes": "memory does not retain running jokes",
        "listener_question": "memory does not retain the daily listener question",
        "poll_result": "memory cannot ingest a real poll result",
        "prior_listener_question_or_poll_acknowledged": "next-episode listener acknowledgement is missing",
        "outcomes_to_revisit": "memory does not retain outcomes to revisit",
        "_find_shareable_exchange": "20–45 second shareable-exchange validation is missing",
        "single_show_cta": "single show-CTA validation is missing",
        "closing_payoff_complete": "closing payoff validation is missing",
    }
    for marker, reason in relationship_contract.items():
        if marker not in writer:
            fail(reason)

    if "_render_spoken_chunk_to_file" not in router or "hybrid_render_spoken_chunk_to_file" not in router:
        fail("hybrid_tts_router_v3_1.py does not patch the production render path")
    if "tts_to_file" not in router or "hybrid_tts_to_file" not in router:
        fail("hybrid_tts_router_v3_1.py does not patch tts_to_file")
    if "_speaker_audio_backend" not in router or "grok_tts_v4" not in router:
        fail("hybrid_tts_router_v3_1.py does not route Jamie through Grok")
    if "jamie_grok_episode_successes" not in router or "GROK_TTS_VOICE_JAMIE" not in router:
        fail("hybrid_tts_router_v3_1.py does not expose Jamie Grok proof counters")

    if "top_event_heat" not in growth or "V3_2_TOP_EVENTS_OVERLAY_INSTALLED" not in growth:
        fail("growth_overlay_v3_1.py is not the v3.2 top-events scoring overlay")

    production_contract = {
        'TRANSITION_EVERY_SEGMENT: "true"': "segment transitions are not enabled",
        'TRANSITION_SEGMENTS: "2,3,4,5"': "all four segment boundaries are not configured",
        'OUTRO_TARGET_DBFS: "-16.5"': "audible outro target is not configured",
        'VOICE_MODEL_ALEX: "tts-1-hd"': "Alex is not on the restored HD voice model",
        'VOICE_MODEL_RUFUS: "tts-1-hd"': "Rufus is not on the restored HD voice model",
        'GROK_TTS_VOICE_JAMIE: "ursa"': "Jamie Ursa primary is not configured",
        'GROK_TTS_VOICE_JAMIE_FALLBACK: "celeste"': "Jamie Celeste fallback is not configured",
    }
    for marker, reason in production_contract.items():
        if marker not in workflow:
            fail(reason)

    bad_env = []
    if os.getenv("RUN_MARKETING_ASSETS", "false").strip().lower() not in ("false", "0", "no"):
        bad_env.append("RUN_MARKETING_ASSETS must be false")
    if os.getenv("AUDIO_BACKEND", "openai").strip().lower() == "eleven":
        bad_env.append("AUDIO_BACKEND must not be eleven")
    if os.getenv("ELEVENLABS_ENABLED", "false").strip().lower() in ("true", "1", "yes"):
        bad_env.append("ELEVENLABS_ENABLED must be false")
    if os.getenv("JAMIE_TTS_PROVIDER", "grok").strip().lower() != "grok":
        bad_env.append("JAMIE_TTS_PROVIDER must be grok")
    if bad_env:
        fail("; ".join(bad_env))

    print(">> ✅ COST-SAFE PREFLIGHT PASSED", flush=True)
    print(">> ✅ Creative format: approved hard-debate human program (v3.2/v3.3)", flush=True)
    print(">> ✅ Story selection: top AI events, no forced sector quota", flush=True)
    print(">> ✅ TTS routing: Jamie Grok Ursa + Celeste fallback + OpenAI provider fallback; Alex/Rufus OpenAI", flush=True)
    print(">> ✅ Preflight guard v3.2.2 — v3.3 connection-first lineage accepted", flush=True)


if __name__ == "__main__":
    main()
