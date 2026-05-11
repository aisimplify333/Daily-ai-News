# -*- coding: utf-8 -*-
"""
The AI Edge v3.1 growth/story scoring overlay.

Paste this entire file as: growth_overlay_v3_1.py

This does not replace growth_engine.py. It patches growth_engine in memory before
main.py imports its functions. The goal is to preserve the stable production code
while improving story selection toward universal audience relevance, data, and
human stakes.
"""

from __future__ import annotations

import re
from typing import Any, Dict


HUMAN_STAKES_TERMS = {
    "power": 12, "money": 14, "job": 14, "jobs": 14, "trust": 14,
    "health": 18, "doctor": 18, "doctors": 18, "patient": 18,
    "privacy": 18, "security": 18, "lawsuit": 18, "liability": 18,
    "government": 16, "white house": 16, "china": 16,
    "openai": 10, "google": 9, "anthropic": 9, "nvidia": 10,
    "agents": 14, "agent": 14, "boss": 16, "banks": 16, "bank": 16,
    "kids": 16, "school": 16, "copyright": 14,
    "who gets sued": 22, "who is watching": 22, "keys to": 18,
    "control": 16, "permission": 18, "scam": 18, "fraud": 18,
}

UNIVERSAL_RELEVANCE_TERMS = {
    "job": 16, "jobs": 16, "work": 14, "boss": 14, "paycheck": 16,
    "money": 18, "bank": 16, "banks": 16, "mortgage": 14, "rent": 12,
    "shopping": 14, "doctor": 20, "health": 20, "hospital": 20,
    "patient": 20, "medicine": 18, "insurance": 18, "school": 18,
    "student": 18, "teacher": 16, "kids": 18, "children": 18,
    "family": 18, "privacy": 20, "phone": 14, "scam": 20, "fraud": 20,
    "safety": 20, "trust": 20, "government": 18, "law": 16, "lawsuit": 20,
    "copyright": 14, "car": 12, "home": 14, "small business": 16,
    "creator": 14, "create": 10, "music": 8, "video": 8, "camera": 8,
}

TITLE_TENSION_PATTERNS = [
    r"\bhow\b.+\bwins?\b",
    r"\bwho\b.+\bwatching\b",
    r"\bwho\b.+\bsued\b",
    r"\bmirage\b.+\brevolution\b",
    r"\bwhat if\b",
    r"\bwhy\b.+\bmatters?\b",
    r"\bproblem\b",
    r"\brace\b",
    r"\bwar\b",
    r"\btrust\b",
    r"\bliability\b",
    r"\bkeys?\s+to\b",
    r"\bapprove\b.+\bmodels?\b",
]

INSIDER_ONLY_TERMS = [
    "benchmark", "parameters", "api", "latency", "model card", "token",
    "embedding", "context window", "fine-tuning", "inference",
]


def _blob(title: str, summary: str = "") -> str:
    return f"{title or ''} {summary or ''}".lower()


def listener_tension_score(title: str, summary: str = "") -> float:
    blob = _blob(title, summary)
    score = 0.0
    for term, pts in HUMAN_STAKES_TERMS.items():
        if term in blob:
            score += pts
    for pat in TITLE_TENSION_PATTERNS:
        if re.search(pat, blob, flags=re.IGNORECASE):
            score += 12
    if "?" in (title or ""):
        score += 8
    if 38 <= len(title or "") <= 96:
        score += 6
    if re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d+\s?(?:million|billion|trillion)\b", blob):
        score += 12
    return max(0.0, min(100.0, score))


def universal_relevance_score(title: str, summary: str = "") -> float:
    blob = _blob(title, summary)
    score = 0.0
    for term, pts in UNIVERSAL_RELEVANCE_TERMS.items():
        if term in blob:
            score += pts

    if "agent" in blob and any(x in blob for x in ["bank", "shopping", "work", "email", "calendar", "phone", "privacy", "security"]):
        score += 18
    if "ai" in blob and any(x in blob for x in ["doctor", "health", "school", "job", "government", "safety", "scam"]):
        score += 20

    public_terms = set(UNIVERSAL_RELEVANCE_TERMS.keys())
    if any(x in blob for x in INSIDER_ONLY_TERMS) and not any(x in blob for x in public_terms):
        score -= 24

    return max(0.0, min(100.0, score))


def _get_title_summary(item: Dict[str, Any]) -> tuple[str, str]:
    title = str(item.get("title") or item.get("headline") or "")
    summary = str(item.get("summary") or item.get("why_shocking") or item.get("description") or "")
    return title, summary


def install() -> None:
    import growth_engine  # type: ignore

    if getattr(growth_engine, "V3_1_EXPANSION_OVERLAY_INSTALLED", False):
        return

    original_story_score_breakdown = getattr(growth_engine, "story_score_breakdown", None)

    if callable(original_story_score_breakdown):
        def story_score_breakdown_v3_1(item, memory=None):
            breakdown = original_story_score_breakdown(item, memory)
            title, summary = _get_title_summary(item)
            tension = listener_tension_score(title, summary)
            universal = universal_relevance_score(title, summary)

            breakdown["listener_tension"] = round(tension, 2)
            breakdown["universal_relevance"] = round(universal, 2)

            old_weighted = float(breakdown.get("weighted", 0.0))
            authority = float(breakdown.get("authority", 0.0))
            lift = (0.14 * tension) + (0.18 * universal)

            if authority < 40:
                lift *= 0.45
            if float(breakdown.get("ai_heat", 0.0)) >= 50 and universal < 16:
                lift -= 8
            if float(breakdown.get("numeric_density", 0.0)) <= 0 and float(breakdown.get("forward_consequence", 0.0)) < 20:
                lift *= 0.55

            breakdown["weighted"] = round(max(0.0, min(100.0, old_weighted + lift)), 2)
            return breakdown

        growth_engine.story_score_breakdown = story_score_breakdown_v3_1

    growth_engine.MODEL_VERSION = "podcast-growth-v3.1-expansion-ready-universal-data-purpose"
    growth_engine.V3_1_EXPANSION_OVERLAY_INSTALLED = True
