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

    if min_minutes * 60 <= before <= max_minutes * 60:
        report.update({
            "disposition": "accepted_as_rendered",
            "duration_after_seconds": round(before, 3),
        })
        return _write_report(base_dir, report)

    if before < min_minutes * 60:
        report.update({
            "disposition": "held_for_editorial_review",
            "reason": "completed render is too short; audio padding would reduce quality",
            "duration_after_seconds": round(before, 3),
        })
        return _write_report(base_dir, report)

    target_seconds = max_minutes * 60 - float(
        os.getenv("POST_RENDER_HEADROOM_SECONDS", "10")
    )
    speed_factor = before / target_seconds
    max_speed_factor = float(os.getenv("POST_RENDER_MAX_SPEED_FACTOR", "1.13"))
    if speed_factor > max_speed_factor:
        report.update({
            "disposition": "held_for_editorial_review",
            "reason": (
                f"required speed factor {speed_factor:.4f} exceeds "
                f"quality cap {max_speed_factor:.4f}"
            ),
            "duration_after_seconds": round(before, 3),
        })
        return _write_report(base_dir, report)

    master = audio_dir / f"podcast_{date_str}_full_render.mp3"
    if not master.exists():
        shutil.copy2(output, master)

    temp = audio_dir / f".podcast_{date_str}_duration_recovery.mp3"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(master), "-map", "0:a:0",
            "-filter:a", f"atempo={speed_factor:.8f}",
            "-map_metadata", "0", "-codec:a", "libmp3lame", "-b:a", "192k",
            str(temp),
        ],
        check=True,
    )
    after = _duration_seconds(temp)
    if not (min_minutes * 60 <= after <= max_minutes * 60):
        temp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Duration recovery produced {after / 60:.2f} minutes, still outside bounds"
        )
    os.replace(temp, output)
    _update_sidecars(base_dir, date_str, after)

    report.update({
        "disposition": "salvaged_without_new_tts",
        "master": str(master),
        "output": str(output),
        "speed_factor": round(speed_factor, 6),
        "duration_after_seconds": round(after, 3),
        "pitch_preserved": True,
    })
    return _write_report(base_dir, report)


if __name__ == "__main__":
    result = recover_completed_render(Path(__file__).parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
