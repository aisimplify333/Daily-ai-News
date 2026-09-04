# -*- coding: utf-8 -*-
"""
The AI Edge v3.1 feed/public-copy sanitizer.

Paste this entire file as: feed_sanitize_v3_1.py

Purpose:
- The episode can complete successfully but still be blocked if old public metadata
  leaks "Signal Room" from the legacy main.py / marketing layer.
- This file sanitizes public generated files AFTER v3_1_runner.py and BEFORE
  no_repeat_guard_v3_1.py.
- It does not bypass the guard. It cleans stale branding, then the guard still decides.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

OLD_BRAND_RE = re.compile(r"\b(?:The\s+AI\s+Signal\s+Room|AI\s+Signal\s+Room|Signal\s+Room)\b", re.IGNORECASE)
SHOW_TITLE = "The AI Edge"
SHOW_DESCRIPTION = (
    "The AI Edge is the weekday artificial intelligence news and analysis podcast where "
    "Alex, Jamie, and Rufus tell you what changed in AI, who wins, and what you do next. "
    "Each episode debates one lead story from the last 24–48 hours, using the other top "
    "AI events as evidence, complications, or counterarguments. Follow The AI Edge for "
    "new episodes Monday through Friday. What changed. Who wins. What you do next."
)

GENERATED_TEXT_FILES = [
    "feed.xml",
    "marketing_blurb.txt",
]

GENERATED_JSON_FILES = [
    "episode_metadata.json",
    "marketing_pack.json",
    "script_aircheck.json",
    "episode_aircheck.json",
    "episode_lesson_card.json",
    "scene_cards.json",
    "story_slate_decision.json",
    "listener_takeaways.json",
    "final_button.json",
    "seo_discovery_brief.json",
    "tracking_summary.json",
    "sponsor_delivery_report.json",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _sanitize_text(text: str) -> str:
    text = OLD_BRAND_RE.sub(SHOW_TITLE, text)
    text = text.replace(
        "The daily AI show that makes you smarter before tomorrow — one concept, one laugh, one sharp takeaway.",
        SHOW_DESCRIPTION,
    )
    text = text.replace(
        "The daily AI show that makes you smarter before tomorrow - one concept, one laugh, one sharp takeaway.",
        SHOW_DESCRIPTION,
    )
    return text


def _sanitize_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"path": str(path), "exists": False, "changed": False, "old_brand_hits_before": 0, "old_brand_hits_after": 0}
    before = _read(path)
    hits_before = len(OLD_BRAND_RE.findall(before))
    after = _sanitize_text(before)

    # Hard-set the channel title/description when feed.xml is present.
    if path.name == "feed.xml":
        after = re.sub(
            r"(<channel>\s*<title>)(.*?)(</title>)",
            rf"\1{SHOW_TITLE}\3",
            after,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )
        after = re.sub(
            r"(<channel>.*?<description>)(.*?)(</description>)",
            rf"\1{SHOW_DESCRIPTION}\3",
            after,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )

    changed = before != after
    if changed:
        _write(path, after)
    hits_after = len(OLD_BRAND_RE.findall(after))
    return {"path": str(path), "exists": True, "changed": changed, "old_brand_hits_before": hits_before, "old_brand_hits_after": hits_after}


def _sanitize_episode_audio_json() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    audio_dir = Path("episode_audio")
    if not audio_dir.exists():
        return rows
    for path in sorted(audio_dir.glob("*.json")):
        rows.append(_sanitize_file(path))
    return rows


def _scan_public_leaks(paths: List[Path]) -> List[Dict[str, object]]:
    leaks: List[Dict[str, object]] = []
    for path in paths:
        if not path.exists():
            continue
        text = _read(path)
        hits = OLD_BRAND_RE.findall(text)
        if hits:
            leaks.append({"path": str(path), "hits": len(hits), "examples": sorted(set(hits))[:5]})
    return leaks


def main() -> int:
    print(">> STARTING: V3.1 public-copy sanitizer", flush=True)

    report: Dict[str, object] = {
        "version": "v3.1-public-copy-sanitizer",
        "show_title": SHOW_TITLE,
        "show_description": SHOW_DESCRIPTION,
        "files": [],
        "episode_audio_json": [],
        "passed": True,
        "failures": [],
    }

    text_paths = [Path(p) for p in GENERATED_TEXT_FILES]
    json_paths = [Path(p) for p in GENERATED_JSON_FILES]

    for path in text_paths + json_paths:
        result = _sanitize_file(path)
        report["files"].append(result)
        if result.get("changed"):
            print(f">> ✅ sanitized {path}", flush=True)

    audio_rows = _sanitize_episode_audio_json()
    report["episode_audio_json"] = audio_rows
    for row in audio_rows:
        if row.get("changed"):
            print(f">> ✅ sanitized {row.get('path')}", flush=True)

    feed_path = Path("feed.xml")
    if not feed_path.exists():
        report["passed"] = False
        report["failures"].append({"reason": "feed_xml_missing"})
    else:
        feed_text = _read(feed_path)
        if OLD_BRAND_RE.search(feed_text):
            report["passed"] = False
            report["failures"].append({"reason": "feed_xml_still_contains_signal_room"})
        if f"<title>{SHOW_TITLE}</title>" not in feed_text[:2000]:
            report["passed"] = False
            report["failures"].append({"reason": "channel_title_not_set_to_the_ai_edge"})

    scan_paths = text_paths + json_paths + [p for p in Path("episode_audio").glob("*.json")] if Path("episode_audio").exists() else text_paths + json_paths
    leaks = _scan_public_leaks(scan_paths)
    if leaks:
        # Do not fail for old non-feed generated files, but record them. The feed is the public publish gate.
        report["remaining_generated_file_leaks"] = leaks

    Path("feed_sanitize_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not report["passed"]:
        print(">> ❌ V3.1 sanitizer failed", flush=True)
        for row in report["failures"]:
            print(f"   - {row}", flush=True)
        return 2

    print(">> ✅ V3.1 sanitizer passed. Feed public copy is clean enough for no-repeat guard.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
