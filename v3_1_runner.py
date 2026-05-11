# -*- coding: utf-8 -*-
"""
The AI Edge v3.1 runner.

This file intentionally preserves the existing main.py production spine.
It loads main.py without executing its __main__ block, installs the v3.1
creative/story/marketing overlays in memory, then calls produce_episode().

Paste this entire file as: v3_1_runner.py
"""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path


BASE_DIR = Path(__file__).parent
MAIN_PATH = BASE_DIR / "main.py"


def _safe_print(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    if not MAIN_PATH.exists():
        raise RuntimeError("main.py not found. v3_1_runner.py must live in the repo root next to main.py.")

    # Default v3.1 env values. The workflow can override any of these.
    os.environ.setdefault("PODCAST_SHOW_TITLE", "The AI Edge")
    os.environ.setdefault(
        "PODCAST_SHOW_DESCRIPTION",
        "The daily AI show that explains the one story today that could touch your work, money, health, privacy, family, school, safety, or trust.",
    )
    os.environ.setdefault("WRITERS_ROOM_MODE", "budget_plus")
    os.environ.setdefault("NO_REPEAT_TITLE_WINDOW", "14")
    os.environ.setdefault("PRE_TTS_MIN_SCORE", "84")

    _safe_print(">> STARTING: The AI Edge v3.1 runner")
    _safe_print(">> Preserving existing main.py production spine")

    try:
        import growth_overlay_v3_1
        growth_overlay_v3_1.install()
        _safe_print(">> ✅ Installed v3.1 growth/story scoring overlay")
    except Exception as e:
        _safe_print(f">> ⚠️ Growth overlay failed; continuing with existing story scoring: {e}")

    # Load main.py as a module dictionary without triggering if __name__ == "__main__".
    # Functions defined by runpy keep this dictionary as their global namespace.
    g = runpy.run_path(str(MAIN_PATH), run_name="__v3_1_main__")

    try:
        from writer_room_v3_1 import install_v3_1
        install_v3_1(g)
        _safe_print(">> ✅ Installed v3.1 writer room overlay")
    except Exception as e:
        _safe_print(f">> ❌ V3.1 writer room install failed: {e}")
        traceback.print_exc()
        raise

    produce_episode = g.get("produce_episode")
    if not callable(produce_episode):
        raise RuntimeError("main.py did not expose produce_episode(). Cannot run production build.")

    _safe_print(">> HANDOFF: running main.py produce_episode() under v3.1 overlay")
    produce_episode()
    _safe_print(">> ✅ COMPLETE: The AI Edge v3.1 runner")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
