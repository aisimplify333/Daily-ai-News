#!/usr/bin/env python3
"""Grounded daily-news selection for The AI Edge."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from google import genai
from google.genai import types


DEFAULT_MODEL = os.getenv("GROUNDED_NEWS_MODEL", "gemini-3.1-flash-lite").strip()
MAX_AGE_HOURS = float(os.getenv("MAX_STORY_AGE_HOURS", "48"))
MIN_TRUSTED_STORIES = int(os.getenv("MIN_TRUSTED_STORIES", "3"))

TIER3_PUBLISHERS = {
    "reuters", "associated press", "ap news", "bloomberg",
    "financial times", "wall street journal", "the new york times",
    "the washington post", "openai", "anthropic", "google",
    "google deepmind", "microsoft", "nvidia", "meta", "apple",
    "amazon", "aws", "github", "cursor",
}
TIER2_PUBLISHERS = {
    "the verge", "wired", "ars technica", "techcrunch", "axios",
    "cnbc", "fortune", "the information", "semianalysis",
    "404 media", "platformer", "mit technology review",
}
TIER3_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com",
    "nytimes.com", "washingtonpost.com", "openai.com", "anthropic.com",
    "google.com", "deepmind.google", "microsoft.com", "nvidia.com",
    "meta.com", "apple.com", "amazon.com", "github.com", "cursor.com",
}
TIER2_DOMAINS = {
    "theverge.com", "wired.com", "arstechnica.com", "techcrunch.com",
    "axios.com", "cnbc.com", "fortune.com", "theinformation.com",
    "technologyreview.com",
}


def _extract_json(text: str, default: Any) -> Any:
    cleaned = re.sub(r"^\x60{3}(?:json)?\s*", "", (text or "").strip(), flags=re.I)
    cleaned = re.sub(r"\s*\x60{3}$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.S)
        if not match:
            return default
        try:
            return json.loads(match.group(1))
        except Exception:
            return default


def _domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _source_tier(publisher: str, url: str) -> int:
    pub = re.sub(r"\s+", " ", (publisher or "").lower()).strip()
    domain = _domain(url)
    if pub in TIER3_PUBLISHERS or any(
        domain == value or domain.endswith("." + value)
        for value in TIER3_DOMAINS
    ):
        return 3
    if pub in TIER2_PUBLISHERS or any(
        domain == value or domain.endswith("." + value)
        for value in TIER2_DOMAINS
    ):
        return 2
    return 1


def _parse_time(value: str) -> Optional[dt.datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _grounded_text(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 7000) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    client = genai.Client(api_key=api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        temperature=1.0,
        max_output_tokens=max_tokens,
        tools=[grounding_tool],
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return str(getattr(response, "text", "") or "").strip()


def _story_prompt(date_str: str, candidate_count: int) -> str:
    episode_date = dt.date.fromisoformat(date_str)
    start = episode_date - dt.timedelta(days=2)
    return f"""Use Google Search to identify the most consequential AI news first
reported between {start.isoformat()} and {date_str}. This is for a daily technology
podcast, not a generic web roundup.

Return STRICT JSON only:
{{
  "stories": [
    {{
      "headline": "plain factual headline",
      "publisher": "original primary source or major newsroom",
      "published_at": "ISO-8601 timestamp from the source page",
      "source_url": "direct canonical article URL, never a search-results URL",
      "summary": "3-5 sentences of confirmed facts only",
      "facts": ["source-backed fact", "source-backed fact"],
      "data_points": ["exact number/date/benchmark only when the source gives it"],
      "limitations_or_qualifiers": ["privacy, availability, geography, access, or safety qualifier"],
      "why_it_matters": "one clearly labeled analytical sentence",
      "original_publication_verified": true
    }}
  ]
}}

Return {candidate_count} ranked candidates so validation can retain the best five.
Rules:
- Verify the ORIGINAL publication date on the source page. Reject an old announcement
  merely resurfaced or republished in the last 48 hours.
- Prefer Reuters/AP/Bloomberg/FT/WSJ/Washington Post/New York Times, respected
  specialist technology press, government filings, court documents, and official
  company announcements for their own products.
- At least five candidates must use a primary source or major newsroom.
- Prioritize legal/policy moves, major model or product releases, safety/security
  events, material deals, compute/chip shifts, and changes affecting work or people.
- Exclude SEO explainers, listicles, commentary presented as news, conference promotion,
  rumor without attribution, and routine content marketing.
- One event per item. Do not combine unrelated stories into a thesis.
- Access/retrieval is not model training. For health, enterprise, workspace, or other
  connected data, explicitly include the vendor's current training/privacy/retention
  qualifiers from an official source. Never imply training when the source says no.
- Do not invent customers, deployments, partnerships, incidents, numbers, quotes,
  benchmarks, regulation, or causal links.
""".strip()


def _normalize_story(raw: Dict[str, Any], now: dt.datetime) -> Optional[Dict[str, Any]]:
    headline = str(raw.get("headline") or "").strip()
    publisher = str(raw.get("publisher") or "").strip()
    published_at = str(raw.get("published_at") or "").strip()
    source_url = str(raw.get("source_url") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    facts = [
        str(value).strip() for value in (raw.get("facts") or [])
        if str(value).strip()
    ]
    data_points = [
        str(value).strip() for value in (raw.get("data_points") or [])
        if str(value).strip()
    ]
    qualifiers = [
        str(value).strip() for value in (raw.get("limitations_or_qualifiers") or [])
        if str(value).strip()
    ]
    published = _parse_time(published_at)
    if not all((headline, publisher, source_url, summary, published)):
        return None
    if not source_url.startswith("https://") or "news.google.com" in source_url:
        return None
    age_hours = (now - published).total_seconds() / 3600.0
    if age_hours < -6 or age_hours > MAX_AGE_HOURS:
        return None
    if len(summary) < 90 or len(facts) < 2:
        return None
    if raw.get("original_publication_verified") is not True:
        return None
    return {
        "headline": headline,
        "title": headline,
        "publisher": publisher,
        "published": published.isoformat().replace("+00:00", "Z"),
        "published_at": published.isoformat().replace("+00:00", "Z"),
        "source_url": source_url,
        "link": source_url,
        "summary": summary,
        "facts": facts[:8],
        "data_points": data_points[:8],
        "limitations_or_qualifiers": qualifiers[:8],
        "why_it_matters": str(raw.get("why_it_matters") or "").strip(),
        "story_age_hours": round(max(0.0, age_hours), 2),
        "source_tier": _source_tier(publisher, source_url),
        "grounded": True,
    }


@lru_cache(maxsize=8)
def build_grounded_story_slate(
    date_str: str,
    n: int = 5,
    model: str = DEFAULT_MODEL,
) -> List[Dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    candidate_count = max(n + 3, 8)
    payload = _extract_json(
        _grounded_text(_story_prompt(date_str, candidate_count), model=model),
        {},
    )
    rows = payload.get("stories") if isinstance(payload, dict) else []
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        story = _normalize_story(raw, now)
        if not story:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", story["headline"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(story)
        if len(normalized) >= n:
            break
    trusted = sum(1 for story in normalized if int(story["source_tier"]) >= 2)
    if len(normalized) != n:
        raise RuntimeError(f"Grounded search returned {len(normalized)} valid stories; {n} required")
    if int(normalized[0]["source_tier"]) < 2:
        raise RuntimeError("Grounded lead did not come from a primary or trusted source")
    if trusted < min(n, MIN_TRUSTED_STORIES):
        raise RuntimeError(
            f"Grounded search returned only {trusted} trusted stories; "
            f"{MIN_TRUSTED_STORIES} required"
        )
    for rank, story in enumerate(normalized, start=1):
        story["rank"] = rank
        story["story_role"] = "top_ai_event"
        story["story_tier"] = "primary" if rank <= 3 else "supporting"
        story["bucket"] = "grounded_top_ai_event"
    return normalized


def _fact_check_prompt(script: str, stories: List[Dict[str, Any]], date_str: str) -> str:
    evidence = [
        {
            "rank": story.get("rank"),
            "headline": story.get("headline"),
            "publisher": story.get("publisher"),
            "published_at": story.get("published_at"),
            "source_url": story.get("source_url"),
            "summary": story.get("summary"),
            "facts": story.get("facts") or [],
            "data_points": story.get("data_points") or [],
            "limitations_or_qualifiers": story.get("limitations_or_qualifiers") or [],
        }
        for story in stories
    ]
    return f"""Fact-check this podcast script for the episode dated {date_str} using
Google Search and the supplied source records. Be strict about factual assertions,
dates, product capabilities, privacy/training claims, deployments, customers,
benchmarks, regulation, quotations, causal links, and whether an item is truly new.

Return STRICT JSON only:
{{
  "pass": true,
  "critical_errors": [
    {{
      "exact_line": "the complete ALEX:, JAMIE:, or RUFUS: line exactly as written",
      "reason": "specific factual problem",
      "replacement_line": "a complete corrected line, same speaker, no more than 55 words",
      "source_url": "direct verifying URL"
    }}
  ],
  "warnings": ["noncritical uncertainty"],
  "verified_source_urls": ["direct URL"]
}}

Rules:
- pass is false when critical_errors is non-empty.
- Every replacement must preserve the exact speaker label and conversational intent.
- Correct only the factual defect; do not flatten humor, disagreement, or host voice.
- Do not treat access, retrieval, a connector, or an enterprise workspace as model training
  unless a current official source explicitly says the data is used to train the model.
- Flag an old announcement resurfacing in a recent feed as old, even if the feed date is new.
- Flag unsupported claims connecting separate stories or products.
- Do not demand citations in spoken dialogue and do not rewrite opinions clearly framed as opinions.
- Never invent a source. Use a direct publisher, official, filing, court, or government URL.

SOURCE RECORDS:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

SCRIPT:
{script}
""".strip()


def fact_check_script(
    script: str,
    stories: List[Dict[str, Any]],
    date_str: str,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    payload = _extract_json(
        _grounded_text(
            _fact_check_prompt(script, stories, date_str),
            model=model,
            max_tokens=7000,
        ),
        {},
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Grounded fact audit did not return an object")
    errors = payload.get("critical_errors") or []
    warnings = payload.get("warnings") or []
    if not isinstance(errors, list) or not isinstance(warnings, list):
        raise RuntimeError("Grounded fact audit returned an invalid schema")
    clean_errors: List[Dict[str, str]] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        exact = str(item.get("exact_line") or "").strip()
        replacement = str(item.get("replacement_line") or "").strip()
        reason = str(item.get("reason") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        if not exact or not replacement or not reason:
            continue
        if not re.match(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", exact, flags=re.I):
            continue
        if not re.match(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", replacement, flags=re.I):
            continue
        spoken = re.sub(r"^(ALEX|JAMIE|RUFUS)\s*:\s*", "", replacement, flags=re.I)
        if len(re.findall(r"\b[\w'-]+\b", spoken)) > 55:
            continue
        clean_errors.append({
            "exact_line": exact,
            "replacement_line": replacement,
            "reason": reason,
            "source_url": source_url,
        })
    return {
        "version": "grounded-fact-check-v1",
        "date": date_str,
        "pass": not clean_errors and bool(payload.get("pass", True)),
        "critical_errors": clean_errors,
        "warnings": [str(value).strip() for value in warnings if str(value).strip()],
        "verified_source_urls": [
            str(value).strip() for value in (payload.get("verified_source_urls") or [])
            if str(value).strip()
        ],
    }


def apply_fact_replacements(script: str, report: Dict[str, Any]) -> tuple[str, int]:
    updated = script
    applied = 0
    for item in report.get("critical_errors") or []:
        exact = str(item.get("exact_line") or "").strip()
        replacement = str(item.get("replacement_line") or "").strip()
        if exact and replacement and updated.count(exact) == 1:
            updated = updated.replace(exact, replacement, 1)
            applied += 1
    return updated, applied


def write_grounded_slate_report(
    stories: List[Dict[str, Any]],
    date_str: str,
    path: Path | str = "grounded_story_slate.json",
) -> None:
    payload = {
        "version": "grounded-story-slate-v1",
        "date": date_str,
        "pass": len(stories) == 5,
        "selected": stories,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    date_str = os.getenv("RECOVERY_RUN_DATE", "").strip() or dt.date.today().isoformat()
    stories = build_grounded_story_slate(date_str, n=5)
    write_grounded_slate_report(stories, date_str)
    print(json.dumps({
        "date": date_str,
        "count": len(stories),
        "trusted": sum(1 for story in stories if int(story.get("source_tier") or 0) >= 2),
        "headlines": [story.get("headline") for story in stories],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
