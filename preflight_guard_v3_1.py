# -*- coding: utf-8 -*-
"""
The AI Edge v3.1 cost-safe preflight guard.

Paste this entire file as: preflight_guard_v3_1.py

Purpose:
- Fail fast before LLM/TTS/ElevenLabs spend.
- Catch simple setup/branding/pipeline mistakes before a full episode is generated.
- Prevent same-day duplicate rebuilds unless explicitly allowed.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

SHOW_TITLE = "The AI Edge"
OLD_BRAND_RE = re.compile(r"\b(?:The\s+AI\s+Signal\s+Room|AI\s+Signal\s+Room|Signal\s+Room)\b", re.IGNORECASE)

REQUIRED_FILES = [
    "main.py",
    "v3_1_runner.py",
    "writer_room_v3_1.py",
    "growth_overlay_v3_1.py",
    "feed_sanitize_v3_1.py",
    "hybrid_tts_router_v3_1.py",
    "no_repeat_guard_v3_1.py",
    "run_broadcast.py",
    "requirements.txt",
]

PUBLIC_GENERATED_FILES = [
    "feed.xml",
    "episode_metadata.json",
    "marketing_pack.json",
    "marketing_blurb.txt",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _today_slug() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


def _contains(cmd_text: str, needle: str) -> bool:
    return needle in cmd_text


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def main() -> int:
    failures: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []

    def fail(reason: str, **detail: object) -> None:
        row = {"reason": reason}
        row.update(detail)
        failures.append(row)

    def warn(reason: str, **detail: object) -> None:
        row = {"reason": reason}
        row.update(detail)
        warnings.append(row)

    print(">> STARTING: V3.1 cost-safe preflight guard", flush=True)

    for file_name in REQUIRED_FILES:
        if not Path(file_name).exists():
            fail("required_file_missing", file=file_name)

    run_broadcast = Path("run_broadcast.py")
    if run_broadcast.exists():
        rb = _read(run_broadcast)
        if "python main.py" in rb:
            fail("run_broadcast_calls_main_directly", fix="run_broadcast.py must call python v3_1_runner.py, not python main.py")
        required_order = [
            "python preflight_guard_v3_1.py",
            "python v3_1_runner.py",
            "python feed_sanitize_v3_1.py",
            "python no_repeat_guard_v3_1.py",
        ]
        positions = []
        for needle in required_order:
            pos = rb.find(needle)
            if pos < 0:
                fail("run_broadcast_missing_required_step", step=needle)
            positions.append(pos)
        if all(p >= 0 for p in positions) and positions != sorted(positions):
            fail("run_broadcast_wrong_gate_order", expected=required_order)

    runner = Path("v3_1_runner.py")
    if runner.exists():
        rt = _read(runner)
        if "RUN_MARKETING_ASSETS" not in rt:
            fail("v3_1_runner_does_not_disable_legacy_marketing", fix="set RUN_MARKETING_ASSETS=false before main.py import")
        if "PODCAST_SHOW_TITLE" not in rt or SHOW_TITLE not in rt:
            fail("v3_1_runner_missing_show_title_override")
        if "hybrid_tts_router_v3_1" not in rt:
            fail("v3_1_runner_missing_hybrid_tts_router", fix="install hybrid_tts_router_v3_1 before produce_episode()")
        if "AUDIO_BACKEND" not in rt or "openai" not in rt:
            fail("v3_1_runner_does_not_force_openai_backend", fix="set AUDIO_BACKEND=openai before main.py import so ElevenLabs is not used")
        if "ELEVENLABS_ENABLED" not in rt or "false" not in rt:
            fail("v3_1_runner_does_not_disable_elevenlabs", fix="set ELEVENLABS_ENABLED=false before main.py import")

    workflow = Path(".github/workflows/daily_podcast.yml")
    if workflow.exists():
        wf = _read(workflow)
        if "python preflight_guard_v3_1.py" not in wf and "python run_broadcast.py" not in wf:
            warn("workflow_preflight_not_visible_directly", note="preflight may still run inside run_broadcast.py")
        if 'RUN_MARKETING_ASSETS: "false"' not in wf and "RUN_MARKETING_ASSETS: 'false'" not in wf:
            fail("workflow_legacy_marketing_assets_not_disabled", fix='set RUN_MARKETING_ASSETS: "false" for tomorrow')
        if 'AUDIO_BACKEND: "eleven"' in wf or "AUDIO_BACKEND: 'eleven'" in wf:
            fail("workflow_still_uses_elevenlabs_backend", fix='set AUDIO_BACKEND: "openai" and route only JAMIE to Gemini')
        if 'AUDIO_BACKEND: "openai"' not in wf and "AUDIO_BACKEND: 'openai'" not in wf:
            fail("workflow_missing_openai_backend", fix='set AUDIO_BACKEND: "openai"')
        if 'JAMIE_TTS_PROVIDER: "gemini"' not in wf and "JAMIE_TTS_PROVIDER: 'gemini'" not in wf:
            fail("workflow_missing_jamie_gemini_route", fix='set JAMIE_TTS_PROVIDER: "gemini"')
        if "gemini-3.1-flash-tts-preview" not in wf:
            fail("workflow_missing_gemini_3_1_tts_model", fix="set GEMINI_TTS_MODEL to gemini-3.1-flash-tts-preview")
        if "AI_EDGE_PODCAST_ELEVENLABS" in wf or "ELEVENLABS_API_KEY" in wf:
            fail("workflow_still_passes_elevenlabs_secret", fix="remove ElevenLabs secret from production env until audience economics justify it")
        if 'FORCE_REBUILD: "true"' in wf or "FORCE_REBUILD: 'true'" in wf:
            fail("workflow_force_rebuild_true", fix='set FORCE_REBUILD: "false" so manual reruns do not duplicate spend')
        if "Upload production artifacts" not in wf and "actions/upload-artifact" not in wf:
            fail("workflow_missing_always_upload_artifacts", fix="add upload-artifact step with if: always()")

    run_marketing = os.getenv("RUN_MARKETING_ASSETS", "false").strip().lower()
    if run_marketing not in ("false", "0", "no") and not _bool_env("ALLOW_LEGACY_MARKETING_ASSETS"):
        fail(
            "legacy_marketing_assets_enabled_before_tts",
            value=run_marketing,
            fix="set RUN_MARKETING_ASSETS=false until the old v3.0 marketing engine is replaced",
        )

    audio_backend = os.getenv("AUDIO_BACKEND", "openai").strip().lower()
    if audio_backend == "eleven" and not _bool_env("ALLOW_ELEVENLABS_PRODUCTION"):
        fail("runtime_audio_backend_is_eleven", value=audio_backend, fix="set AUDIO_BACKEND=openai; Jamie routes to Gemini through hybrid_tts_router_v3_1")

    jamie_provider = os.getenv("JAMIE_TTS_PROVIDER", "gemini").strip().lower()
    if jamie_provider != "gemini":
        fail("runtime_jamie_not_routed_to_gemini", value=jamie_provider, fix="set JAMIE_TTS_PROVIDER=gemini")

    force_rebuild = os.getenv("FORCE_REBUILD", "false").strip().lower()
    if force_rebuild in ("true", "1", "yes") and not _bool_env("ALLOW_FORCE_REBUILD"):
        fail("force_rebuild_enabled", value=force_rebuild, fix="set FORCE_REBUILD=false for cost-safe scheduled production")

    today = _today_slug()
    today_audio = Path("episode_audio") / f"podcast_{today}.mp3"
    if today_audio.exists() and not _bool_env("ALLOW_DUPLICATE_DATE_REBUILD"):
        fail(
            "todays_episode_audio_already_exists",
            file=str(today_audio),
            fix="do not regenerate the same day; set ALLOW_DUPLICATE_DATE_REBUILD=true only if you intentionally want to spend again",
        )

    # Stale public files should not block tomorrow by themselves, because feed_sanitize_v3_1.py cleans them after generation.
    # They are warnings here so the preflight is not blocked by old 5/08 public history.
    for file_name in PUBLIC_GENERATED_FILES:
        path = Path(file_name)
        if not path.exists():
            continue
        hits = OLD_BRAND_RE.findall(_read(path))
        if hits:
            warn("existing_generated_file_contains_old_brand", file=file_name, hits=len(hits))

    report = {
        "version": "v3.1-cost-safe-hybrid-tts-preflight",
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "cost_protection": {
            "runs_before_llm_and_tts": True,
            "blocks_legacy_marketing_before_generation": True,
            "blocks_same_day_duplicate_audio": True,
            "requires_artifact_upload_on_failure": True,
            "requires_jamie_gemini_route": True,
            "requires_elevenlabs_disabled": True,
        },
    }
    Path("preflight_report_v3_1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(">> ❌ COST-SAFE PREFLIGHT FAILED before expensive generation", flush=True)
        for row in failures:
            print(f"   - {row}", flush=True)
        print(">> No LLM/TTS/ElevenLabs spend should happen after this failure.", flush=True)
        return 2

    if warnings:
        print(">> ⚠️ PREFLIGHT WARNINGS:", flush=True)
        for row in warnings:
            print(f"   - {row}", flush=True)

    print(">> ✅ Cost-safe preflight passed. It is safe to enter generation.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
