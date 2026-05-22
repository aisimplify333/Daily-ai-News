# -*- coding: utf-8 -*-
"""
The AI Edge v3.3.4 clean runner — no new files, no main.py replacement.

Paste this entire file as: v3_1_runner.py

Purpose:
- Preserve the existing full main.py production spine.
- Keep orchestration simple and readable.
- Install the existing overlays in a deterministic order.
- Prove Jamie Gemini voice before expensive generation and after final render when required.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import runpy
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).parent
MAIN_PATH = BASE_DIR / "main.py"
REPORT_PATH = BASE_DIR / "hybrid_tts_report.json"


def _safe_print(msg: str) -> None:
    print(msg, flush=True)


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _set_default_env() -> None:
    """Set stable defaults before main.py import because main.py reads env at import time."""
    os.environ["PODCAST_SHOW_TITLE"] = "The AI Edge"
    os.environ[
        "PODCAST_SHOW_DESCRIPTION"
    ] = "A sharp daily AI debate about what changed, who gained power, who is exposed, and what to watch next."

    # Cost and reliability defaults.
    os.environ.setdefault("SAVE_SCRIPT", "true")
    os.environ.setdefault("RUN_MARKETING_ASSETS", "false")
    os.environ.setdefault("PUBLISH_SOCIAL", "false")
    os.environ.setdefault("HARD_FAIL_PRE_TTS", "false")
    os.environ.setdefault("ALLOW_DUPLICATE_DATE_REBUILD", "false")
    os.environ.setdefault("RECOVERY_ALLOW_DETERMINISTIC_SCRIPT", "true")

    # Voice path. Jamie Gemini is the differentiator; Alex/Rufus stay on OpenAI for stability.
    os.environ["AUDIO_BACKEND"] = "openai"
    os.environ["ELEVENLABS_ENABLED"] = "false"
    os.environ["ELEVEN_USE_DIALOGUE_SCENES"] = "false"
    os.environ.setdefault("ALEX_TTS_PROVIDER", "openai")
    os.environ.setdefault("JAMIE_TTS_PROVIDER", "gemini")
    os.environ.setdefault("RUFUS_TTS_PROVIDER", "openai")
    os.environ.setdefault("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    os.environ.setdefault("GEMINI_TTS_VOICE_JAMIE", "Sulafat")
    os.environ.setdefault("GEMINI_TTS_MAX_RETRIES", "2")
    os.environ.setdefault("GEMINI_TTS_CACHE", "true")

    # Default: require Gemini proof so we do not claim a voice upgrade that did not happen.
    # Emergency override: REQUIRE_GEMINI_JAMIE=false lets Jamie fall back to OpenAI to save a daily publish.
    os.environ.setdefault("REQUIRE_GEMINI_JAMIE", "true")
    if _truthy("REQUIRE_GEMINI_JAMIE", "true"):
        os.environ["GEMINI_TTS_FALLBACK_PROVIDER"] = "none"
    else:
        os.environ.setdefault("GEMINI_TTS_FALLBACK_PROVIDER", "openai")

    # Keep the score gate realistic while the system stabilizes. The show target remains 88+.
    os.environ.setdefault("PRE_TTS_MIN_SCORE", "82")
    os.environ.setdefault("TOP_EVENT_MIN_SCORE", "34")
    os.environ.setdefault("NO_REPEAT_TITLE_WINDOW", "14")


def _load_main_namespace() -> Dict[str, Any]:
    if not MAIN_PATH.exists():
        raise RuntimeError("main.py not found. v3_1_runner.py must live in the repo root next to main.py.")
    return runpy.run_path(str(MAIN_PATH), run_name="__the_ai_edge_main__")


def _install_growth_overlay() -> None:
    try:
        import growth_overlay_v3_1

        growth_overlay_v3_1.install()
        _safe_print(">> ✅ Installed growth/story scoring overlay")
    except Exception as exc:
        _safe_print(f">> ⚠️ Growth overlay unavailable; continuing with main.py scoring: {exc}")


def _install_writer_room(g: Dict[str, Any]) -> None:
    from writer_room_v3_1 import install_v3_1

    install_v3_1(g)
    _safe_print(">> ✅ Installed clean v3.3.4 hard-debate writer room")


def _install_tts_router(g: Dict[str, Any]) -> Any:
    import hybrid_tts_router_v3_1

    hybrid_tts_router_v3_1.install(g)
    _safe_print(">> ✅ Installed Gemini Jamie / OpenAI host voice router")
    return hybrid_tts_router_v3_1


def _run_jamie_gemini_smoke_test(router_module: Any) -> None:
    if not _truthy("REQUIRE_GEMINI_JAMIE", "true"):
        _safe_print(">> ℹ️ Gemini Jamie proof not required by env; skipping smoke test.")
        return
    if os.getenv("JAMIE_TTS_PROVIDER", "gemini").strip().lower() != "gemini":
        raise RuntimeError("REQUIRE_GEMINI_JAMIE=true but JAMIE_TTS_PROVIDER is not gemini.")
    if not hasattr(router_module, "smoke_test_jamie_voice"):
        raise RuntimeError("hybrid_tts_router_v3_1.py does not expose smoke_test_jamie_voice().")
    today = _dt.date.today().isoformat()
    out_path = BASE_DIR / "episode_audio" / f"jamie_gemini_voice_proof_{today}.mp3"
    router_module.smoke_test_jamie_voice(out_path)
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError("Gemini Jamie smoke test did not produce a usable MP3 proof file.")
    _safe_print(f">> ✅ Gemini Jamie smoke proof created: {out_path}")


def _enforce_gemini_jamie_report() -> None:
    if not _truthy("REQUIRE_GEMINI_JAMIE", "true"):
        _safe_print(">> ℹ️ Gemini Jamie proof not required by env; skipping post-render gate.")
        return
    if not REPORT_PATH.exists():
        raise RuntimeError("Gemini Jamie required, but hybrid_tts_report.json was not created.")
    try:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read hybrid_tts_report.json: {exc}")
    successes = int(report.get("jamie_gemini_successes") or 0)
    chars = int(report.get("jamie_chars_requested") or 0)
    fallbacks = report.get("fallbacks") or []
    if successes <= 0 or chars <= 0:
        raise RuntimeError(
            "Gemini Jamie was required but not proven in the episode. "
            f"jamie_gemini_successes={successes}, jamie_chars_requested={chars}, fallbacks={fallbacks}"
        )
    if fallbacks and os.getenv("GEMINI_TTS_FALLBACK_PROVIDER", "none").strip().lower() == "none":
        raise RuntimeError(f"Gemini Jamie fallback occurred while fallback is disabled: {fallbacks}")
    _safe_print(f">> ✅ Gemini Jamie proven in episode: {successes} Gemini chunks, {chars} chars")


def main() -> None:
    _safe_print(">> STARTING: The AI Edge v3.3.4 clean stable runner")
    _safe_print(">> Preserving existing main.py production spine")

    _set_default_env()
    _safe_print(">> ✅ Stable env locked before main.py import")
    _safe_print(">> ✅ No embedded code, no new modules, no main.py replacement")

    _install_growth_overlay()
    g = _load_main_namespace()
    _install_writer_room(g)
    router = _install_tts_router(g)
    _run_jamie_gemini_smoke_test(router)

    produce_episode = g.get("produce_episode")
    if not callable(produce_episode):
        raise RuntimeError("main.py did not expose produce_episode(). Cannot run production build.")

    _safe_print(">> HANDOFF: running main.py produce_episode() under clean v3.3.4 overlays")
    produce_episode()
    _enforce_gemini_jamie_report()
    _safe_print(">> ✅ COMPLETE: The AI Edge v3.3.4 clean stable runner")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
