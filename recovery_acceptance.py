#!/usr/bin/env python3
"""Objective acceptance gate for a nonpublishing The AI Edge recovery episode."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from pydub import AudioSegment

ROOT = Path(__file__).parent
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
REPORT_PATH = ROOT / "recovery_acceptance_report.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def main() -> int:
    today = dt.date.today().isoformat()
    script_path = ROOT / f"script_{today}.txt"
    audio_path = ROOT / "episode_audio" / f"podcast_{today}.mp3"
    failures: List[str] = []
    warnings: List[str] = []

    if not script_path.exists():
        failures.append(f"missing {script_path.name}")
        script = ""
    else:
        script = script_path.read_text(encoding="utf-8", errors="replace")

    if not audio_path.exists():
        failures.append(f"missing {audio_path}")
        duration_minutes = 0.0
    else:
        duration_minutes = len(AudioSegment.from_file(audio_path)) / 60000.0
        if not 24.0 <= duration_minutes <= 30.0:
            failures.append(f"duration {duration_minutes:.2f} outside 24-30 minutes")

    segment_count = len(re.findall(
        r"^###\s*SEGMENT\s*[1-5]\b", script,
        flags=re.IGNORECASE | re.MULTILINE,
    ))
    if segment_count != 5:
        failures.append(f"expected 5 segments, found {segment_count}")
    if script.count("[MUSIC]") != 1:
        failures.append(f"expected exactly one [MUSIC], found {script.count('[MUSIC]')}")

    seg2_match = re.search(
        r"^###\s*SEGMENT\s*2\b(.*?)^###\s*SEGMENT\s*3\b",
        script, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    seg2_text = seg2_match.group(1) if seg2_match else ""
    seg2_speakers = {
        match.group(1).upper()
        for line in seg2_text.splitlines()
        if (match := SPEAKER_RE.match(line.strip()))
    }
    if seg2_speakers != {"ALEX", "JAMIE"}:
        failures.append(f"Segment 2 speakers were {sorted(seg2_speakers)}, expected Alex/Jamie only")

    seg3_match = re.search(
        r"^###\s*SEGMENT\s*3\b(.*?)^###\s*SEGMENT\s*4\b",
        script, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if not seg3_match or "RUFUS:" not in seg3_match.group(1).upper():
        failures.append("Segment 3 did not include Rufus's money/power desk")

    sponsor_block_match = re.search(
        r"\[MUSIC\]\s*(.*?)^###\s*SEGMENT\s*2\b",
        script, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    sponsor_block = sponsor_block_match.group(1) if sponsor_block_match else ""
    sponsor_matches = [
        match
        for line in sponsor_block.splitlines()
        if (match := SPEAKER_RE.match(line.strip()))
    ]
    sponsor_lines = [match.group(2) for match in sponsor_matches]
    sponsor_speakers = [match.group(1).upper() for match in sponsor_matches]
    sponsor_window = " ".join(sponsor_lines)
    sponsor_window_low = sponsor_window.lower()
    sponsor_words = _words(sponsor_window)
    if sponsor_speakers != ["ALEX", "ALEX"]:
        failures.append(
            f"primary sponsor must be exactly two Alex lines; found {sponsor_speakers}"
        )
    if "the ledger" not in sponsor_window_low:
        failures.append("primary sponsor was not named immediately after music")
    if "t-h-e-l-e-d-g-r dot i-o" not in sponsor_window_low:
        failures.append("primary sponsor CTA was not immediately after music")
    if script.lower().count("t-h-e-l-e-d-g-r dot i-o") != 1:
        failures.append("The Ledger spoken CTA must appear exactly once")
    if not 45 <= sponsor_words <= 65:
        failures.append(f"sponsor read was {sponsor_words} words; expected 45-65")
    if any(p in script.lower() for p in ("sponsor the ai edge", "sponsor this show", "aisimplify333@")):
        failures.append("legacy sponsor solicitation language appeared")
    if "ai signal room" in script.lower():
        failures.append("legacy AI Signal Room branding appeared in the script")

    tts = _read_json(ROOT / "hybrid_tts_report.json")
    episode_grok = int(tts.get("jamie_grok_episode_successes") or 0)
    ursa_successes = int(tts.get("jamie_grok_primary_successes") or 0)
    celeste_successes = int(tts.get("jamie_grok_fallback_successes") or 0)
    if episode_grok <= 0:
        failures.append("no Grok Jamie chunks were proven in the episode")
    if ursa_successes <= 0:
        failures.append("Ursa was not proven")
    provider_fallbacks = [
        item for item in (tts.get("fallbacks") or [])
        if isinstance(item, dict)
        and item.get("from") == "grok_ursa_celeste"
        and item.get("to") == "openai"
    ]
    if provider_fallbacks:
        failures.append(f"Jamie fell through both Grok voices {len(provider_fallbacks)} time(s)")

    slate = _read_json(ROOT / "story_slate_decision.json")
    selected = slate.get("selected") or []
    if len(selected) < 3:
        failures.append(f"only {len(selected)} stories selected")
    stale = [
        item for item in selected
        if isinstance(item, dict)
        and item.get("story_age_hours") is not None
        and float(item["story_age_hours"]) > 48.0
    ]
    if stale:
        failures.append(f"{len(stale)} selected stories were older than 48 hours")
    unknown_age = sum(
        1 for item in selected
        if isinstance(item, dict) and item.get("story_age_hours") is None
    )
    if unknown_age:
        warnings.append(f"{unknown_age} selected stories had no machine-readable timestamp")

    report = {
        "version": "recovery-acceptance-v2",
        "date": today,
        "pass": not failures,
        "human_listening_approval_required": True,
        "failures": failures,
        "warnings": warnings,
        "runtime": {
            "duration_minutes": round(duration_minutes, 3),
            "minimum": 24.0,
            "target": 27.0,
            "maximum": 30.0,
        },
        "structure": {
            "segments": segment_count,
            "segment2_speakers": sorted(seg2_speakers),
            "sponsor_window_words": sponsor_words,
            "sponsor_speakers": sponsor_speakers,
            "sponsor_cta_count": script.lower().count("t-h-e-l-e-d-g-r dot i-o"),
        },
        "voice": {
            "provider": "grok",
            "primary": "ursa",
            "fallback": "celeste",
            "episode_chunks": episode_grok,
            "ursa_successes": ursa_successes,
            "celeste_fallback_successes": celeste_successes,
            "estimated_cost_usd": tts.get("jamie_grok_cost_estimate_usd"),
        },
        "stories": {
            "selected_count": len(selected),
            "older_than_48_hours": len(stale),
            "unknown_age": unknown_age,
        },
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
