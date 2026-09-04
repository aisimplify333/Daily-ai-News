# -*- coding: utf-8 -*-
"""Deterministic final delivery gate for The AI Edge.

Runs after feed sanitation/no-repeat checks and immediately before Git push.
It never calls an LLM or TTS provider. A failure preserves the completed audio
and writes production_delivery_report.json so packaging can be repaired without
regenerating the episode.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from pydub import AudioSegment

GENERIC_TITLE_RE = re.compile(
    r"^(?:the\s+ai\s+edge|daily\s+ai\s+(?:news|brief|update)|ai\s+(?:news|update)|today(?:'s)?\s+ai)(?:\b|\s*[-:])",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b")
URL_RE = re.compile(r"https?://[^\s<]+", re.IGNORECASE)
CTA_RE = re.compile(r"\b(?:subscribe|follow)\b", re.IGNORECASE)
SHOW_FOLLOW_RE = re.compile(r"\bfollow\s+The\s+AI\s+Edge\b", re.IGNORECASE)
AI_RE = re.compile(r"\b(?:AI|artificial intelligence|machine learning|LLM|model)\b", re.IGNORECASE)
COVERAGE_RE = re.compile(
    r"\b(?:what we covered|in this episode|today(?:'s)? stories|inside this episode|"
    r"one lead debate|supporting signals)\b",
    re.IGNORECASE,
)
OLD_BRAND_RE = re.compile(r"\b(?:The\s+AI\s+Signal\s+Room|AI\s+Signal\s+Room|Signal\s+Room)\b", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def clean(value: str | None) -> str:
    value = html.unescape(value or "")
    value = TAG_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def child_text(parent: ET.Element, local_name: str) -> str:
    for child in list(parent):
        if child.tag.rsplit("}", 1)[-1].lower() == local_name.lower():
            return clean(child.text)
    return ""


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def report_says_passed(path: Path) -> bool:
    data = load_json(path)
    return bool(data and data.get("passed") is True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", default="feed.xml")
    parser.add_argument("--report", default="production_delivery_report.json")
    parser.add_argument("--min-minutes", type=float, default=19.0)
    parser.add_argument("--max-minutes", type=float, default=30.0)
    args = parser.parse_args()

    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def fail(reason: str, **detail: Any) -> None:
        failures.append({"reason": reason, **detail})

    def warn(reason: str, **detail: Any) -> None:
        warnings.append({"reason": reason, **detail})

    feed_path = Path(args.feed)
    newest: dict[str, Any] = {}
    audio_path: Path | None = None
    duration_minutes: float | None = None

    if not feed_path.exists():
        fail("feed_missing", path=str(feed_path))
    else:
        try:
            root = ET.fromstring(feed_path.read_text(encoding="utf-8", errors="ignore"))
            channel = next((x for x in root.iter() if x.tag.rsplit("}", 1)[-1] == "channel"), None)
            if channel is None:
                fail("rss_channel_missing")
            else:
                channel_title = child_text(channel, "title")
                channel_description = child_text(channel, "description")
                items = [x for x in list(channel) if x.tag.rsplit("}", 1)[-1] == "item"]
                if channel_title != "The AI Edge":
                    fail("wrong_channel_title", found=channel_title)
                channel_low = channel_description.lower()
                for label, present in (
                    ("artificial_intelligence", "artificial intelligence" in channel_low),
                    ("news_and_analysis", "news" in channel_low and "analysis" in channel_low),
                    ("cast", all(name in channel_low for name in ("alex", "jamie", "rufus"))),
                    ("cadence", "monday through friday" in channel_low),
                    ("follow_cta", "follow the ai edge" in channel_low),
                    (
                        "listener_promise",
                        all(phrase in channel_low for phrase in (
                            "what changed", "who wins", "what you do next",
                        )),
                    ),
                ):
                    if not present:
                        fail("show_description_missing_discovery_element", element=label)
                if not items:
                    fail("rss_has_no_episode")
                else:
                    item = items[0]
                    title = child_text(item, "title")
                    description = child_text(item, "description")
                    summary = child_text(item, "summary")
                    guid = child_text(item, "guid")
                    pub_date = child_text(item, "pubDate")
                    enclosure = next(
                        (x for x in list(item) if x.tag.rsplit("}", 1)[-1] == "enclosure"),
                        None,
                    )
                    enclosure_url = (enclosure.attrib.get("url", "").strip() if enclosure is not None else "")
                    enclosure_length = (enclosure.attrib.get("length", "").strip() if enclosure is not None else "")
                    newest = {
                        "title": title,
                        "description_chars": len(description),
                        "guid": guid,
                        "pub_date": pub_date,
                        "enclosure_url": enclosure_url,
                    }

                    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", title)
                    if not 3 <= len(words) <= 14:
                        fail("title_word_count", found=len(words), expected="3-14")
                    if GENERIC_TITLE_RE.search(title):
                        fail("generic_title", title=title)
                    if DATE_RE.search(title):
                        fail("date_in_title", title=title)
                    meaningful = {w.lower() for w in words if len(w) >= 4 and w.lower() not in {"with", "from", "that", "this", "your", "today"}}
                    if len(meaningful) < 2:
                        fail("title_lacks_specific_hook", title=title)

                    if len(description) < 220:
                        fail("description_too_short", found=len(description), minimum=220)
                    if not COVERAGE_RE.search(description):
                        fail("description_missing_episode_structure")
                    if not AI_RE.search(description):
                        fail("description_missing_ai_discovery_term")
                    if not CTA_RE.search(description):
                        fail("description_missing_subscriber_cta")
                    if not SHOW_FOLLOW_RE.search(description):
                        fail("description_missing_show_follow_cta")
                    description_low = description.lower()
                    if not all(phrase in description_low for phrase in (
                        "what changed", "who wins", "what you do next",
                    )):
                        fail("description_missing_listener_promise")
                    if not URL_RE.search(description):
                        fail("description_missing_listener_url")
                    if OLD_BRAND_RE.search(title + " " + description + " " + summary):
                        fail("legacy_brand_in_public_metadata")
                    if summary and clean(summary) != clean(description):
                        warn("itunes_summary_differs_from_description")
                    if not guid:
                        fail("guid_missing")
                    if not pub_date:
                        fail("publication_date_missing")
                    if not enclosure_url:
                        fail("enclosure_url_missing")
                    if not enclosure_length.isdigit() or int(enclosure_length or 0) <= 0:
                        fail("enclosure_length_invalid", found=enclosure_length)

                    transcript = next(
                        (x for x in list(item) if x.tag.rsplit("}", 1)[-1] == "transcript"),
                        None,
                    )
                    chapters = next(
                        (x for x in list(item) if x.tag.rsplit("}", 1)[-1] == "chapters"),
                        None,
                    )
                    if transcript is None or not transcript.attrib.get("url"):
                        warn("podcast_transcript_missing")
                    if chapters is None or not chapters.attrib.get("url"):
                        warn("podcast_chapters_missing")

                    audio_name = enclosure_url.rsplit("/", 1)[-1] if enclosure_url else ""
                    candidate = Path("episode_audio") / audio_name
                    if audio_name and candidate.exists():
                        audio_path = candidate
                    else:
                        matches = sorted(Path("episode_audio").glob("podcast_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
                        if matches:
                            audio_path = matches[0]
                            fail("enclosure_does_not_match_local_audio", enclosure=audio_name, local=audio_path.name)
                        else:
                            fail("episode_audio_missing")

        except ET.ParseError as exc:
            fail("feed_xml_invalid", error=str(exc))

    if audio_path is not None:
        try:
            duration_minutes = len(AudioSegment.from_mp3(audio_path)) / 60000.0
            if duration_minutes < args.min_minutes or duration_minutes > args.max_minutes:
                fail(
                    "duration_outside_publish_window",
                    found=round(duration_minutes, 3),
                    expected=f"{args.min_minutes:g}-{args.max_minutes:g}",
                )
        except Exception as exc:
            fail("audio_unreadable", path=str(audio_path), error=str(exc))

    for required_report in ("feed_sanitize_report.json", "duplicate_guard_report.json"):
        if not report_says_passed(Path(required_report)):
            fail("required_gate_not_passed", report=required_report)

    poll = load_json(Path("listener_poll.json"))
    if not poll:
        warn("listener_poll_payload_missing")
    else:
        question = clean(str(poll.get("question") or ""))
        options = poll.get("options") if isinstance(poll.get("options"), list) else []
        if not question or len(question) > 140:
            warn("listener_poll_question_invalid", length=len(question))
        if not 2 <= len(options) <= 4:
            warn("listener_poll_options_invalid", found=len(options))

    # This is a producer warning, never a reason to throw away paid audio. The
    # writer identifies a candidate before TTS; this confirms the clip manifest
    # survived packaging and remains usable by the social workflow.
    shareable = load_json(Path("shareable_exchange.json"))
    if not shareable:
        warn("shareable_exchange_manifest_missing")
    else:
        seconds = shareable.get("estimated_seconds")
        if not shareable.get("passed"):
            warn("shareable_exchange_not_confirmed")
        elif not isinstance(seconds, (int, float)) or not 18.0 <= float(seconds) <= 47.0:
            warn("shareable_exchange_duration_unexpected", found=seconds)

    audio_qa = load_json(Path("audio_qa_report.json"))
    if not audio_qa:
        warn("audio_qa_report_missing")
    else:
        if not audio_qa.get("passed"):
            # Preserve the user's rule: a completed paid episode is never discarded
            # or regenerated for a post-render mix warning. Surface it for repair.
            warn("audio_qa_warning_completed_master_preserved", detail=audio_qa)
        if int(audio_qa.get("transition_count") or 0) < 4:
            warn("segment_transitions_below_target", found=audio_qa.get("transition_count"))
        if not audio_qa.get("outro_present"):
            warn("outro_not_confirmed")

    tts_report = load_json(Path("hybrid_tts_report.json"))
    if tts_report:
        if int(tts_report.get("jamie_grok_episode_successes") or 0) <= 0:
            warn("jamie_grok_voice_not_confirmed_completed_master_preserved")
        moods = tts_report.get("mood_distribution") if isinstance(tts_report.get("mood_distribution"), dict) else {}
        active_moods = sum(1 for count in moods.values() if int(count or 0) > 0)
        if active_moods < 5:
            warn("tts_dynamic_range_moods_low", active_moods=active_moods, distribution=moods)

    cost_metrics = {
        "tts_characters_total": int((tts_report or {}).get("total_characters_rendered") or 0),
        "tts_characters_by_speaker": (tts_report or {}).get("characters_by_speaker") or {},
        "grok_estimated_cost_usd": float((tts_report or {}).get("jamie_grok_cost_estimate_usd") or 0.0),
        "grok_cache_hits": int((tts_report or {}).get("jamie_cache_hits") or 0),
        "fallback_count": len((tts_report or {}).get("fallbacks") or []),
        "provider_calls": len((tts_report or {}).get("calls") or []),
    }

    report = {
        "version": "spotify-delivery-v1",
        "passed": not failures,
        "cost": "zero-model-calls",
        "feed": str(feed_path),
        "newest_episode": newest,
        "audio_path": str(audio_path) if audio_path else None,
        "duration_minutes": round(duration_minutes, 3) if duration_minutes is not None else None,
        "cost_metrics": cost_metrics,
        "checks": {
            "stop_scroll_title": "passed" if not any(x["reason"].startswith(("title_", "generic_title", "date_in_title")) for x in failures) else "failed",
            "seo_and_episode_structure": "passed" if not any(x["reason"].startswith("description_") for x in failures) else "failed",
            "subscriber_cta": "passed" if not any(x["reason"] == "description_missing_subscriber_cta" for x in failures) else "failed",
            "show_follow_cta": "passed" if not any(x["reason"] == "description_missing_show_follow_cta" for x in failures) else "failed",
            "transcript_and_chapters": "warning" if any(x["reason"] in {"podcast_transcript_missing", "podcast_chapters_missing"} for x in warnings) else "passed",
            "listener_poll_payload": "warning" if any(x["reason"].startswith("listener_poll_") for x in warnings) else "passed",
            "rss_metadata": "passed" if not any(x["reason"] in {
                "feed_missing", "rss_channel_missing", "rss_has_no_episode", "feed_xml_invalid",
                "guid_missing", "publication_date_missing", "enclosure_url_missing", "enclosure_length_invalid",
                "enclosure_does_not_match_local_audio",
            } for x in failures) else "failed",
            "duplicate_protection": "passed" if report_says_passed(Path("duplicate_guard_report.json")) else "failed",
            "audio_window": "passed" if duration_minutes is not None and args.min_minutes <= duration_minutes <= args.max_minutes else "failed",
        },
        "failures": failures,
        "warnings": warnings,
        "recovery": "Completed audio is preserved. Repair packaging and rerun this gate; do not regenerate TTS.",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(">> HOLD: Spotify delivery package is not ready.", flush=True)
        for row in failures:
            print(f"   - {row}", flush=True)
        print(">> Completed audio remains intact; fix metadata and rerun without TTS.", flush=True)
        return 2

    print(">> READY: required publishing checks passed; companion/voice warnings never discard paid audio.", flush=True)
    for row in warnings:
        print(f"   - warning: {row['reason']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
