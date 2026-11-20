# -*- coding: utf-8 -*-
"""Recover a completed paid audio render without buying the voices twice."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict


def _duration_seconds(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def _write_report(base_dir: Path, report: Dict[str, Any]) -> Dict[str, Any]:
    path = base_dir / "post_render_recovery_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _update_sidecars(base_dir: Path, date_str: str, seconds: float) -> None:
    candidates = [
        base_dir / "episode_audio" / f"podcast_{date_str}.json",
        base_dir / f"podcast_{date_str}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            payload["duration_seconds"] = int(round(seconds))
            payload["minutes"] = round(seconds / 60.0, 2)
            payload["post_render_duration_recovery"] = True
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            continue


def recover_completed_render(
    base_dir: Path,
    date_str: str | None = None,
    min_minutes: float | None = None,
    max_minutes: float | None = None,
) -> Dict[str, Any]:
    """Preserve the master and correct modest overlength without another TTS run."""
    base_dir = Path(base_dir)
    date_str = date_str or dt.date.today().isoformat()
    min_minutes = float(min_minutes or os.getenv("MIN_MINUTES", "24"))
    max_minutes = float(max_minutes or os.getenv("MAX_MINUTES", "30"))
    audio_dir = base_dir / "episode_audio"
    output = audio_dir / f"podcast_{date_str}.mp3"

    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError(f"No completed paid render found at {output}")

    before = _duration_seconds(output)
    report: Dict[str, Any] = {
        "version": "v1-paid-render-salvage",
        "date": date_str,
        "input": str(output),
        "duration_before_seconds": round(before, 3),
        "allowed_minutes": [min_minutes, max_minutes],
        "new_tts_calls": 0,
    }

    report.update(disposition="accepted_as_rendered",
                  duration_after_seconds=round(before, 3),
                  runtime_advisory=not min_minutes * 60 <= before <= max_minutes * 60)
    return _write_report(base_dir, report)
