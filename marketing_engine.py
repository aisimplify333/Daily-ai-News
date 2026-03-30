#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from growth_engine import build_story_debug_table, choose_variant

BASE_DIR = Path(__file__).parent
META_PATH = BASE_DIR / "episode_metadata.json"

OUT_MARKETING_PACK = BASE_DIR / "marketing_pack.json"
OUT_X = BASE_DIR / "marketing_x.json"
OUT_YT = BASE_DIR / "marketing_youtube.json"
OUT_LI = BASE_DIR / "marketing_linkedin.txt"
OUT_IG = BASE_DIR / "marketing_instagram.txt"
OUT_TT = BASE_DIR / "marketing_tiktok.txt"
OUT_TAGS = BASE_DIR / "viral_tags.txt"
OUT_SEO = BASE_DIR / "seo_keywords.txt"
OUT_BLURB = BASE_DIR / "marketing_blurb.txt"
OUT_CLIPS = BASE_DIR / "clip_candidates.json"
OUT_DISTRIBUTION = BASE_DIR / "distribution_plan.json"
OUT_STORY_SCORES = BASE_DIR / "story_scores.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text((text or "").strip() + "\n", encoding="utf-8")


def _clamp(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _digits(text: str) -> int:
    return len(re.findall(r"\d", text or ""))


def _hashtags(stories: List[Dict[str, Any]], max_tags: int = 8) -> List[str]:
    base = ["#AI", "#TechNews", "#AIAgents", "#EnterpriseAI"]
    extra: List[str] = []
    for story in stories[:5]:
        title = story.get("headline") or ""
        if any(k in title.lower() for k in ["regulat", "ftc", "sec", "eu"]):
            extra.append("#AIRegulation")
        if any(k in title.lower() for k in ["chip", "gpu", "nvidia", "datacenter"]):
            extra.append("#AIInfrastructure")
        for ent in story.get("key_entities") or []:
            tag = "#" + re.sub(r"[^A-Za-z0-9]", "", str(ent))
            if 3 <= len(tag) <= 22:
                extra.append(tag)
    seen, ordered = set(), []
    for tag in base + extra:
        if tag.lower() in seen:
            continue
        seen.add(tag.lower())
        ordered.append(tag)
    return ordered[:max_tags]


def _top_stories(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    stories = [s for s in (meta.get("stories") or []) if isinstance(s, dict)]
    return sorted(stories, key=lambda s: float(s.get("growth_score") or 0.0), reverse=True)[:5]


def _pick_title(meta: Dict[str, Any], stories: List[Dict[str, Any]]) -> str:
    variant = (((meta.get("tracking") or {}).get("experiments") or {}).get("title_style")) or choose_variant("title_style")
    top = stories[0] if stories else {}
    head = (top.get("headline") or meta.get("title") or "AI moved again").strip()
    dp = " | ".join([str(x) for x in (top.get("data_points") or [])[:2]])
    digit_rich = dp if _digits(dp) >= 3 else head
    if variant == "hard_number":
        return _clamp(f"{head} — What the Numbers Mean Now", 90)
    if variant == "operator_consequence":
        return _clamp(f"{head} | The Operator Consequence", 90)
    return _clamp(f"{head} | Why Tomorrow Gets Harder", 90)


def _pick_hook(meta: Dict[str, Any], stories: List[Dict[str, Any]]) -> str:
    variant = (((meta.get("tracking") or {}).get("experiments") or {}).get("clip_style")) or choose_variant("clip_style")
    top = stories[0] if stories else {}
    head = (top.get("headline") or meta.get("title") or "AI just shifted").strip()
    if variant == "contrarian":
        return _clamp(f"THE BIG AI STORY ISN'T WHAT YOU THINK", 64)
    if variant == "fear_greed":
        return _clamp(f"WHO WINS IF THIS TREND HOLDS?", 64)
    return _clamp(head.upper(), 64)


def _story_summary_lines(stories: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for story in stories[:5]:
        data = "; ".join([str(x) for x in (story.get("data_points") or [])[:2]])
        lines.append(f"- {story.get('headline','')}" + (f" ({data})" if data else ""))
    return "\n".join(lines)


def _clip_candidates(meta: Dict[str, Any], stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tracking = meta.get("tracking") or {}
    clips: List[Dict[str, Any]] = []
    for i, story in enumerate(stories[:3], start=1):
        score = float(story.get("growth_score") or 0.0)
        question = story.get("tomorrow_hook") or f"What breaks first if {story.get('headline','this')} keeps accelerating?"
        clips.append({
            "rank": i,
            "story": story.get("headline"),
            "hook": _clamp(question, 120),
            "subhook": _clamp((story.get("why_shocking") or "").strip(), 140),
            "cta": tracking.get("subscribe_clip_primary" if i == 1 else "subscribe_clip_secondary", meta.get("listen_url", "")),
            "predicted_score": round(score, 2),
            "visual_angle": "numbers + consequence + one hard question",
        })
    return clips


def build_assets(meta: Dict[str, Any]) -> Dict[str, Any]:
    stories = _top_stories(meta)
    tracking = meta.get("tracking") or {}
    show_notes_url = tracking.get("subscribe_show_notes") or "https://theledgr.io"
    x_url = tracking.get("subscribe_x") or show_notes_url
    linkedin_url = tracking.get("subscribe_linkedin") or show_notes_url

    title = _pick_title(meta, stories)
    hook = _pick_hook(meta, stories)
    hashtags = _hashtags(stories)
    bullets = _story_summary_lines(stories)

    x_posts = {
        "post_1": _clamp(f"{hook}\n\nThe real question is not whether AI moved. It is who gets caught flat-footed next.\n\nListen: {meta.get('listen_url','')}", 280),
        "post_2": _clamp(f"TheLEDGR is where we turn these headlines into decision-grade signal.\n\nSubscribe: {x_url}", 280),
        "thread": [
            _clamp(f"Today's AI Edge in one line: {hook}", 280),
            _clamp(f"What mattered most:\n{bullets}", 280),
            _clamp(f"Subscribe to TheLEDGR: {x_url}", 280),
        ],
    }

    yt = {
        "title": title,
        "description": _clamp(
            f"Listen now: {meta.get('listen_url','')}\n\nWhat we covered:\n{bullets}\n\nSubscribe to TheLEDGR: {show_notes_url}",
            1200,
        ),
        "shorts_hooks": [c["hook"] for c in _clip_candidates(meta, stories)],
    }

    li = (
        f"{hook}\n\n"
        f"Most AI coverage stops at the headline. We do not.\n\n"
        f"Today on The AI Edge we broke down:\n{bullets}\n\n"
        f"If AI changes how you allocate budget, design workflows, hire, or compete, subscribe to TheLEDGR here: {linkedin_url}"
    )

    ig = (
        f"{hook}\n\n"
        f"Serious AI people do not need more noise. They need the consequence.\n\n"
        f"Subscribe: {show_notes_url}\n\n"
        + " ".join(hashtags)
    )
    tt = ig

    blurb = (
        f"The AI Edge released a new episode focused on the second-order consequences behind the day's biggest AI stories. "
        f"The companion growth engine routes listeners into TheLEDGR using tracked CTAs so the show can learn what actually creates subscribers."
    )

    tags = {
        "tags_6": " ".join(hashtags[:6]),
        "tags_12": " ".join(hashtags[:12]),
        "seo_keywords": [story.get("headline") for story in stories if story.get("headline")],
    }

    clips = _clip_candidates(meta, stories)

    pack = {
        "hook": hook,
        "yt_title": yt["title"],
        "yt_description": yt["description"],
        "tweet1": x_posts["post_1"],
        "tweet2": x_posts["post_2"],
        "show_notes": meta.get("show_notes") or yt["description"],
        "hashtags": tags["tags_6"],
        "tracked_urls": tracking,
        "clip_candidates": clips,
    }

    return {
        "pack": pack,
        "x": x_posts,
        "yt": yt,
        "linkedin": li,
        "instagram": ig,
        "tiktok": tt,
        "blurb": blurb,
        "tags": tags,
        "clips": clips,
        "distribution": {
            "primary_goal": "newsletter_signups",
            "primary_cta": show_notes_url,
            "channel_priority": ["youtube_shorts", "x", "linkedin", "rss_show_notes"],
            "publish_order": [
                "Drop episode",
                "Post clip 1 within 15 minutes",
                "Post X thread within 20 minutes",
                "Post LinkedIn within 45 minutes",
                "Post clip 2 within 4 hours",
            ],
        },
        "story_scores": build_story_debug_table(stories),
    }


def main() -> int:
    meta = _read_json(META_PATH)
    if not meta:
        print("marketing_engine.py: episode_metadata.json missing or unreadable", flush=True)
        return 1

    assets = build_assets(meta)
    _write_json(OUT_MARKETING_PACK, assets["pack"])
    _write_json(OUT_X, assets["x"])
    _write_json(OUT_YT, assets["yt"])
    _write_text(OUT_LI, assets["linkedin"])
    _write_text(OUT_IG, assets["instagram"])
    _write_text(OUT_TT, assets["tiktok"])
    _write_text(OUT_TAGS, assets["tags"]["tags_12"])
    _write_text(OUT_SEO, "\n".join(assets["tags"]["seo_keywords"]))
    _write_text(OUT_BLURB, assets["blurb"])
    _write_json(OUT_CLIPS, assets["clips"])
    _write_json(OUT_DISTRIBUTION, assets["distribution"])
    _write_json(OUT_STORY_SCORES, assets["story_scores"])
    print("marketing_engine.py: wrote upgraded marketing assets", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
