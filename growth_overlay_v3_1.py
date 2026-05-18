# -*- coding: utf-8 -*-
"""
The AI Edge v3.2 growth/story scoring overlay.

Paste this entire file as: growth_overlay_v3_1.py

v3.2 objective:
- Prefer the top AI news events of the day, not forced sector balance.
- Lift authority, recency, receipts, conflict, consequences, and human stakes.
- Demote SEO/listicle/how-to/alternatives content unless it is genuinely newsworthy.

This patches growth_engine in memory before main.py imports its functions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

TOP_EVENT_TERMS = {
    "lawsuit": 24, "sues": 22, "court": 18, "judge": 18, "antitrust": 22,
    "regulation": 22, "regulator": 22, "ban": 20, "banned": 20, "policy": 16,
    "launch": 18, "launches": 18, "unveils": 18, "releases": 14, "announces": 10,
    "funding": 16, "pledge": 16, "investment": 16, "acquisition": 20, "deal": 16,
    "security": 24, "cybersecurity": 24, "breach": 24, "hack": 24, "vulnerability": 24,
    "health": 20, "healthcare": 22, "clinical": 22, "doctor": 18, "patient": 18,
    "agent": 18, "agents": 18, "coding agent": 22, "benchmark": 12,
    "chip": 18, "gpu": 18, "compute": 18, "data center": 18, "datacenter": 18,
    "job": 18, "jobs": 18, "layoff": 22, "privacy": 22, "scam": 20, "fraud": 20,
    "deepfake": 18, "copyright": 18, "military": 18, "defense": 18, "election": 20,
    "government": 16, "white house": 16, "china": 16,
}

HUMAN_STAKES_TERMS = {
    "job": 16, "jobs": 16, "work": 14, "boss": 14, "paycheck": 16,
    "money": 18, "bank": 16, "banks": 16, "doctor": 20, "health": 20,
    "hospital": 20, "patient": 20, "medicine": 18, "insurance": 18,
    "school": 18, "student": 18, "teacher": 16, "kids": 18, "children": 18,
    "family": 18, "privacy": 20, "phone": 14, "scam": 20, "fraud": 20,
    "safety": 20, "trust": 20, "government": 18, "law": 16, "lawsuit": 20,
    "copyright": 14, "creator": 14, "small business": 16, "who gets sued": 25,
    "who is exposed": 25, "who is watching": 22, "blame": 18, "liability": 22,
    "control": 18, "permission": 20,
}

MAJOR_ACTORS = [
    "openai", "anthropic", "google", "gemini", "deepmind", "microsoft", "nvidia", "meta",
    "apple", "amazon", "aws", "xai", "mistral", "perplexity", "tesla", "oracle",
    "salesforce", "adobe", "github", "cursor", "databricks", "snowflake", "cohere",
    "white house", "eu", "china", "ftc", "doj", "fda", "sec", "gates foundation",
]

AUTHORITY_TERMS = {
    "reuters": 22, "associated press": 20, "ap news": 20, "bloomberg": 22,
    "financial times": 22, "wall street journal": 22, "wsj": 22,
    "new york times": 18, "washington post": 18, "the verge": 14, "wired": 16,
    "techcrunch": 14, "semianalysis": 18, "the information": 20, "axios": 16,
    "cnbc": 14, "fortune": 14, "geekwire": 10,
}

LOW_VALUE_PATTERNS = [
    r"\b\d+\s+best\b", r"\bbest\s+.+alternatives\b", r"\balternatives\b", r"\bhow to\b",
    r"\btips\b", r"\bguide\b", r"\bwebinar\b", r"\bsponsored\b", r"\bguest post\b",
    r"\bwhat is\b", r"\bexplained\b", r"\breview\b", r"\broundup\b",
]

NUMBER_RE = re.compile(r"(?:\$|€|£)\s?\d|\b\d+(?:\.\d+)?%\b|\b\d+(?:\.\d+)?\s?(?:million|billion|trillion|m|b)\b", re.IGNORECASE)


def _title_summary(item: Dict[str, Any]) -> Tuple[str, str]:
    title = str(item.get("title") or item.get("headline") or "")
    summary = str(item.get("summary") or item.get("why_shocking") or item.get("description") or item.get("rss_summary") or "")
    return title, summary


def _blob(item: Dict[str, Any]) -> str:
    title, summary = _title_summary(item)
    return f"{title} {summary} {item.get('publisher') or ''} {item.get('source_url') or item.get('link') or ''}".lower()


def listener_tension_score(title: str, summary: str = "") -> float:
    blob = f"{title} {summary}".lower()
    score = 0.0
    for term, pts in HUMAN_STAKES_TERMS.items():
        if term in blob:
            score += pts
    if "?" in title:
        score += 8
    if re.search(r"\b(who|why|how|what)\b", title, flags=re.IGNORECASE):
        score += 8
    if NUMBER_RE.search(blob):
        score += 12
    return max(0.0, min(100.0, score))


def top_event_heat_score(item: Dict[str, Any]) -> float:
    blob = _blob(item)
    title, summary = _title_summary(item)
    score = 0.0
    for term, pts in TOP_EVENT_TERMS.items():
        if term in blob:
            score += pts
    score += min(30.0, sum(1 for actor in MAJOR_ACTORS if actor in blob) * 8.0)
    score += min(24.0, len(NUMBER_RE.findall(blob)) * 5.0)
    for key, pts in AUTHORITY_TERMS.items():
        if key in blob:
            score += pts
            break
    if ".gov" in blob or ".edu" in blob:
        score += 20
    if any(re.search(p, title.lower()) for p in LOW_VALUE_PATTERNS):
        score -= 45
    if re.search(r"\b(best|alternatives|guide|tips|how to|review)\b", title, flags=re.IGNORECASE) and not any(x in blob for x in ["lawsuit", "launch", "funding", "security", "regulation"]):
        score -= 35
    return max(0.0, min(100.0, score))


def install() -> None:
    import growth_engine  # type: ignore

    if getattr(growth_engine, "V3_2_TOP_EVENTS_OVERLAY_INSTALLED", False):
        return

    original_story_score_breakdown = getattr(growth_engine, "story_score_breakdown", None)

    if callable(original_story_score_breakdown):
        def story_score_breakdown_v3_2(item, memory=None):
            breakdown = original_story_score_breakdown(item, memory)
            title, summary = _title_summary(item)
            top_heat = top_event_heat_score(item)
            tension = listener_tension_score(title, summary)

            breakdown["top_event_heat"] = round(top_heat, 2)
            breakdown["listener_tension"] = round(max(float(breakdown.get("listener_tension", 0.0) or 0.0), tension), 2)
            breakdown["universal_relevance"] = round(max(float(breakdown.get("universal_relevance", 0.0) or 0.0), tension * 0.75), 2)

            old = float(breakdown.get("weighted", 0.0) or 0.0)
            lift = 0.34 * top_heat + 0.18 * tension
            if float(breakdown.get("authority", 0.0) or 0.0) < 35 and top_heat < 40:
                lift *= 0.55
            if top_heat < 25 and tension < 18:
                lift -= 18
            breakdown["weighted"] = round(max(0.0, min(100.0, old + lift)), 2)
            return breakdown

        growth_engine.story_score_breakdown = story_score_breakdown_v3_2

    growth_engine.MODEL_VERSION = "podcast-growth-v3.2-hard-debate-top-ai-events"
    growth_engine.V3_2_TOP_EVENTS_OVERLAY_INSTALLED = True
