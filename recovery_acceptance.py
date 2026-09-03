#!/usr/bin/env python3
"""Objective acceptance gate for a nonpublishing The AI Edge recovery episode."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from pydub import AudioSegment

ROOT = Path(__file__).parent
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
REPORT_PATH = ROOT / "recovery_acceptance_report.json"

GENERIC_PANEL_RE = re.compile(
    r"\b(exactly,\s*(?:alex|jamie|rufus)|absolutely,\s*(?:alex|jamie|rufus)|"
    r"that'?s a great question|game[- ]changer|exciting time|hot month for ai|"
    r"landscape is evolving|momentum continues|transformative era|"
    r"it'?s a lot to take in|and speaking of|keep up with these changes)\b",
    re.IGNORECASE,
)
LEGACY_RITUAL_RE = re.compile(
    r"\b(today[’']s ai lesson|signal or static|ai signal room)\b",
    re.IGNORECASE,
)
MONTHS = {
    name.lower(): number for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"),
        start=1,
    )
}
NUMBER_WORD = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}
RELATIVE_DATE_RE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(?P<year>20\d{2})\s*(?:—|-|,)\s*"
    r"(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)"
    r"\s+months?\s+from\s+(?:today|now)\b",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _relative_date_errors(script: str, date_str: str) -> List[str]:
    try:
        episode_date = dt.date.fromisoformat(date_str)
    except Exception:
        episode_date = dt.date.today()
    errors: List[str] = []
    for match in RELATIVE_DATE_RE.finditer(script or ""):
        raw_count = match.group("count").lower()
        months = int(raw_count) if raw_count.isdigit() else NUMBER_WORD.get(raw_count, 0)
        if months <= 0:
            continue
        total = episode_date.year * 12 + (episode_date.month - 1) + months
        expected_year, expected_month_zero = divmod(total, 12)
        actual_month = MONTHS.get(match.group("month").lower())
        actual_year = int(match.group("year"))
        if (actual_year, actual_month) != (expected_year, expected_month_zero + 1):
            errors.append(match.group(0))
    return errors


def main() -> int:
    today = os.getenv("RECOVERY_RUN_DATE", "").strip() or dt.date.today().isoformat()
    script_path = ROOT / f"script_{today}.txt"
    audio_path = ROOT / "episode_audio" / f"podcast_{today}.mp3"
    failures: List[str] = []
    warnings: List[str] = []

    if not script_path.exists():
        failures.append(f"missing {script_path.name}")
        script = ""
    else:
        script = script_path.read_text(encoding="utf-8", errors="replace")

    pre_tts_path = ROOT / f"script_pre_tts_{today}.txt"
    pre_tts_script = (
        pre_tts_path.read_text(encoding="utf-8", errors="replace")
        if pre_tts_path.exists() else ""
    )
    post_writer_word_delta = (
        abs(_words(script) - _words(pre_tts_script))
        if script and pre_tts_script else None
    )
    if post_writer_word_delta is None:
        warnings.append("pre-TTS script snapshot missing; post-writer drift was not measured")
    elif post_writer_word_delta > 80:
        failures.append(
            f"post-writer mutation changed script length by {post_writer_word_delta} words"
        )

    if not audio_path.exists():
        failures.append(f"missing {audio_path}")
        duration_minutes = 0.0
    else:
        duration_minutes = len(AudioSegment.from_file(audio_path)) / 60000.0
        if not 19.0 <= duration_minutes <= 30.0:
            failures.append(f"duration {duration_minutes:.2f} outside 19-30 minutes")

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
    if GENERIC_PANEL_RE.search(script):
        failures.append("generic panel filler appeared in the script")
    if LEGACY_RITUAL_RE.search(script):
        failures.append("legacy lesson/Signal-or-Static ritual appeared in the script")
    if any(
        re.search(r"\[[^\]]+\]", match.group(2))
        for line in script.splitlines()
        if (match := SPEAKER_RE.match(line.strip()))
    ):
        failures.append("spoken stage direction appeared in the script")
    relative_date_errors = _relative_date_errors(script, today)
    if relative_date_errors:
        failures.append(
            f"{len(relative_date_errors)} internally impossible relative date(s) appeared"
        )

    episode_aircheck = _read_json(ROOT / "episode_aircheck.json")
    writer_assessment = episode_aircheck.get("v3_3_assessment")
    if not isinstance(writer_assessment, dict):
        failures.append("writer assessment missing from episode aircheck")
    elif not writer_assessment.get("pass"):
        failures.append(
            "writer assessment failed: "
            + ", ".join(str(x) for x in (writer_assessment.get("failed") or []))
        )

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
    if len(selected) != 5:
        failures.append(f"expected 5 stories, found {len(selected)}")
    trusted_count = sum(
        1 for item in selected
        if isinstance(item, dict) and int(item.get("source_tier") or 0) >= 2
    )
    lead_source_tier = (
        int(selected[0].get("source_tier") or 0)
        if selected and isinstance(selected[0], dict) else 0
    )
    if trusted_count < 3:
        failures.append(f"only {trusted_count} of 5 stories came from trusted sources")
    if lead_source_tier < 2:
        failures.append("lead story did not come from a primary or trusted source")
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

    grounded_slate = _read_json(ROOT / "grounded_story_slate.json")
    if not grounded_slate.get("pass"):
        failures.append("grounded 24-48 hour story slate report missing or failed")
    grounded_fact = _read_json(ROOT / "grounded_fact_check.json")
    if not grounded_fact.get("pass"):
        failures.append("grounded claim-level fact audit missing or failed")

    report = {
        "version": "recovery-acceptance-v3",
        "date": today,
        "pass": not failures,
        "human_listening_approval_required": True,
        "failures": failures,
        "warnings": warnings,
        "runtime": {
            "duration_minutes": round(duration_minutes, 3),
            "minimum": 19.0,
            "target": 25.0,
            "maximum": 30.0,
        },
        "structure": {
            "segments": segment_count,
            "segment2_speakers": sorted(seg2_speakers),
            "sponsor_window_words": sponsor_words,
            "sponsor_speakers": sponsor_speakers,
            "sponsor_cta_count": script.lower().count("t-h-e-l-e-d-g-r dot i-o"),
            "post_writer_word_delta": post_writer_word_delta,
            "generic_panel_filler": bool(GENERIC_PANEL_RE.search(script)),
            "legacy_ritual": bool(LEGACY_RITUAL_RE.search(script)),
            "relative_date_errors": relative_date_errors,
            "writer_assessment_pass": (
                writer_assessment.get("pass")
                if isinstance(writer_assessment, dict) else None
            ),
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
            "trusted_source_count": trusted_count,
            "lead_source_tier": lead_source_tier,
            "older_than_48_hours": len(stale),
            "unknown_age": unknown_age,
            "grounded_slate_pass": bool(grounded_slate.get("pass")),
            "grounded_fact_check_pass": bool(grounded_fact.get("pass")),
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
