# no_repeat_guard_v3_1.py
# ============================================================
# THE AI EDGE v3.1 — PUBLIC TRUST / NO-REPEAT GUARD
# ============================================================
#
# CREATE this as a new file in the repo root:
#   no_repeat_guard_v3_1.py
#
# Runs after main.py generates feed.xml but BEFORE commit/push.
# If public packaging repeats, the build fails instead of losing subscribers.

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Tuple

SIGNAL_ROOM_RE = re.compile(r"\b(?:AI\s+Signal\s+Room|Signal\s+Room)\b", re.IGNORECASE)
EMPTY_BULLET_RE = re.compile(r"(?m)^\s*[•\-]\s*$")

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "as", "is", "are", "was", "were",
    "it", "this", "that", "today", "tomorrow", "ai", "news", "episode", "alex", "jamie", "rufus",
    "what", "why", "how", "when", "before", "after", "can", "will", "gets", "get", "into", "from",
}


def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _norm(text: str) -> str:
    text = _clean_text(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(text: str) -> List[str]:
    return [t for t in _norm(text).split() if len(t) > 2 and t not in STOPWORDS]


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _lead(text: str, chars: int = 300) -> str:
    return _clean_text(text)[:chars]


def _find_text(elem: ET.Element, tag: str) -> str:
    found = elem.find(tag)
    return _clean_text(found.text if found is not None and found.text else "")


def _find_itunes_summary(elem: ET.Element) -> str:
    for child in list(elem):
        if child.tag.endswith("summary"):
            return _clean_text(child.text or "")
    return ""


def _parse_feed(feed_path: Path) -> Dict[str, Any]:
    if not feed_path.exists():
        raise FileNotFoundError(f"Feed not found: {feed_path}")

    root = ET.fromstring(feed_path.read_text(encoding="utf-8", errors="ignore"))
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Invalid RSS feed: no channel element")

    items: List[Dict[str, Any]] = []
    for item in channel.findall("item"):
        enclosure = item.find("enclosure")
        items.append({
            "title": _find_text(item, "title"),
            "description": _find_text(item, "description"),
            "summary": _find_itunes_summary(item),
            "guid": _find_text(item, "guid"),
            "pubDate": _find_text(item, "pubDate"),
            "enclosure_url": str(enclosure.attrib.get("url") or "").strip() if enclosure is not None else "",
        })

    return {
        "channel_title": _find_text(channel, "title"),
        "channel_description": _find_text(channel, "description"),
        "items": items,
    }


def _title_collision(new_title: str, old_title: str, threshold: float) -> Tuple[bool, str, float]:
    if _norm(new_title) and _norm(new_title) == _norm(old_title):
        return True, "exact_title_match", 1.0
    sim = _jaccard(new_title, old_title)
    if sim >= threshold:
        return True, "high_title_similarity", sim
    return False, "", sim


def _description_collision(new_desc: str, old_desc: str, threshold: float) -> Tuple[bool, str, float]:
    new_lead = _lead(new_desc)
    old_lead = _lead(old_desc)
    if _norm(new_lead) and _norm(new_lead) == _norm(old_lead):
        return True, "exact_description_lead_match", 1.0
    sim = _jaccard(new_lead, old_lead)
    if sim >= threshold:
        return True, "high_description_lead_similarity", sim
    return False, "", sim


def run_guard(
    feed_path: Path,
    report_path: Path,
    window: int = 14,
    title_threshold: float = 0.82,
    description_threshold: float = 0.68,
    fail_on_signal_room: bool = True,
) -> Dict[str, Any]:
    feed = _parse_feed(feed_path)
    items = feed["items"]

    report: Dict[str, Any] = {
        "version": "v3.1-expansion-ready-public-trust-no-repeat-guard",
        "feed_path": str(feed_path),
        "passed": True,
        "failures": [],
        "warnings": [],
        "channel_title": feed.get("channel_title"),
        "newest": items[0] if items else None,
        "comparisons": [],
    }

    def fail(reason: str, detail: Dict[str, Any] | None = None) -> None:
        report["passed"] = False
        row = {"reason": reason}
        if detail:
            row.update(detail)
        report["failures"].append(row)

    def warn(reason: str, detail: Dict[str, Any] | None = None) -> None:
        row = {"reason": reason}
        if detail:
            row.update(detail)
        report["warnings"].append(row)

    if not items:
        fail("no_feed_items")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    newest = items[0]
    recent = items[1: 1 + max(1, window)]

    if fail_on_signal_room:
        if SIGNAL_ROOM_RE.search(feed.get("channel_title") or ""):
            fail("channel_title_still_contains_signal_room", {"channel_title": feed.get("channel_title")})
        if SIGNAL_ROOM_RE.search(newest.get("title") or ""):
            fail("newest_title_contains_signal_room", {"title": newest.get("title")})
        if SIGNAL_ROOM_RE.search(newest.get("description") or "") or SIGNAL_ROOM_RE.search(newest.get("summary") or ""):
            fail("newest_description_contains_signal_room", {"title": newest.get("title")})

    if EMPTY_BULLET_RE.search(newest.get("description") or ""):
        fail("newest_description_contains_empty_story_bullet", {"title": newest.get("title")})

    newest_title = newest.get("title") or ""
    newest_desc = newest.get("description") or newest.get("summary") or ""

    if not newest_title or len(newest_title) < 18:
        fail("newest_title_too_short_or_missing", {"title": newest_title})

    if not newest_desc or len(newest_desc) < 180:
        fail("newest_description_too_short_or_missing", {"description_length": len(newest_desc)})

    for idx, old in enumerate(recent, start=1):
        old_title = old.get("title") or ""
        old_desc = old.get("description") or old.get("summary") or ""

        title_hit, title_reason, title_sim = _title_collision(newest_title, old_title, title_threshold)
        desc_hit, desc_reason, desc_sim = _description_collision(newest_desc, old_desc, description_threshold)

        comparison = {
            "against_rank": idx,
            "against_title": old_title,
            "against_pubDate": old.get("pubDate"),
            "title_similarity": round(title_sim, 3),
            "description_lead_similarity": round(desc_sim, 3),
            "title_reason": title_reason,
            "description_reason": desc_reason,
        }
        report["comparisons"].append(comparison)

        if title_hit:
            fail("duplicate_or_near_duplicate_public_title", comparison)

        if title_sim >= 0.55 and desc_hit:
            fail("duplicate_public_packaging", comparison)

        if newest.get("guid") and newest.get("guid") == old.get("guid"):
            fail("duplicate_guid", {"guid": newest.get("guid"), "against_title": old_title})

        if newest.get("enclosure_url") and newest.get("enclosure_url") == old.get("enclosure_url"):
            fail("duplicate_enclosure_url", {"enclosure_url": newest.get("enclosure_url"), "against_title": old_title})

    if len({i.get("title") for i in items[:5] if i.get("title")}) < min(3, len(items[:5])):
        warn("low_title_variety_in_latest_5", {"latest_titles": [i.get("title") for i in items[:5]]})

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail build if newest podcast item looks like a repeat.")
    parser.add_argument("--feed", default="feed.xml")
    parser.add_argument("--report", default="duplicate_guard_report.json")
    parser.add_argument("--window", type=int, default=14)
    parser.add_argument("--title-threshold", type=float, default=0.82)
    parser.add_argument("--description-threshold", type=float, default=0.68)
    parser.add_argument("--allow-signal-room", action="store_true")
    args = parser.parse_args()

    report = run_guard(
        feed_path=Path(args.feed),
        report_path=Path(args.report),
        window=args.window,
        title_threshold=args.title_threshold,
        description_threshold=args.description_threshold,
        fail_on_signal_room=not args.allow_signal_room,
    )

    print("\n>> NO-REPEAT PUBLIC TRUST GATE", flush=True)
    print(f">> Passed: {report['passed']}", flush=True)

    if report["failures"]:
        print(">> ❌ FAILURES:", flush=True)
        for row in report["failures"]:
            print(f"   - {row.get('reason')}: {row}", flush=True)

    if report["warnings"]:
        print(">> ⚠️ WARNINGS:", flush=True)
        for row in report["warnings"]:
            print(f"   - {row.get('reason')}: {row}", flush=True)

    if not report["passed"]:
        print("\n>> ❌ Refusing to publish. A failed build is better than losing subscribers to a repeated episode.", flush=True)
        return 2

    print(">> ✅ No duplicate public packaging detected.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
