#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from growth_engine import build_story_debug_table, choose_variant

BASE_DIR = Path(__file__).parent
META_PATH = BASE_DIR / "episode_metadata.json"
FORWARDABLE_PATH = BASE_DIR / "forwardable_moments.json"

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
OUT_X_THREAD = BASE_DIR / "x_thread.txt"
OUT_X_POSTS = BASE_DIR / "x_posts.json"
OUT_LINKEDIN_POST = BASE_DIR / "linkedin_post.txt"
OUT_CLIP_HOOKS = BASE_DIR / "clip_hooks.json"
OUT_NEWSLETTER_TEASER = BASE_DIR / "theledgr_newsletter_teaser.txt"
OUT_SPONSOR_REPORT = BASE_DIR / "sponsor_marketing_report.json"

BAD_TAGS = {"#googlenews", "#indexbox", "#msn", "#bitget", "#yahootech"}
BAD_OPENERS_RE = re.compile(r"^(yeah,?\s+and\s+speaking\s+of|absolutely\.?|massive,?\s+right\??|exactly,?\s+alex|first up,?|so,?\s+alex)", re.I)
BAD_FRAGMENT_RE = re.compile(r"(\band\s*\||\bcomes\s*\||\bcomes\s+into\.?$|\band\.?$|\bor\.?$|\bwith\.?$|\binto\.?$|\bto\.?$)", re.I)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if path.suffix == ".json" else []


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text((text or "").strip() + "\n", encoding="utf-8")


def _clamp(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" -—:|,") + "…"


def _clean_headline(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"\|\s*(news and statistics|news|statistics|ai infrastructure).*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bcomes into\.?$", "is here", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:and|or|with|into|to|for)\.?$", "", cleaned, flags=re.I)
    return cleaned.strip(" -—:|,")


def _safe_hook(text: str, fallback: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip()).strip(" -—:|,")
    if not t or BAD_OPENERS_RE.search(t) or BAD_FRAGMENT_RE.search(t) or len(t) < 24:
        t = fallback
    return _clamp(t, 140)


def _top_stories(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    stories = [s for s in (meta.get("stories") or []) if isinstance(s, dict)]
    return stories[:5]


def _forwardable_moments() -> List[Dict[str, Any]]:
    payload = _read_json(FORWARDABLE_PATH)
    if not isinstance(payload, list):
        return []
    cleaned = []
    for m in payload:
        txt = str((m or {}).get("text") or "").strip()
        if not txt or BAD_OPENERS_RE.search(txt) or len(txt) < 30:
            continue
        cleaned.append(m)
    return cleaned[:5]


def _entity_label(stories: List[Dict[str, Any]]) -> str:
    blob = " ".join([str(s.get("headline") or "") for s in stories[:3]]).lower()
    for name, aliases in {
        "OpenAI": ["openai", "chatgpt", "sora"],
        "Anthropic": ["anthropic", "claude"],
        "NVIDIA": ["nvidia", "gpu", "blackwell"],
        "Google": ["google", "deepmind", "gemini"],
        "Microsoft": ["microsoft", "copilot", "azure"],
        "Meta": ["meta", "llama"],
    }.items():
        if any(a in blob for a in aliases):
            return name
    return "AI"


def _audience_angle(stories: List[Dict[str, Any]]) -> str:
    blob = " ".join([str(s.get("headline") or "") + " " + str(s.get("why_shocking") or "") for s in stories[:5]]).lower()
    if any(x in blob for x in ["health", "clinical", "patient", "diagnosis", "hospital"]):
        return "liability"
    if any(x in blob for x in ["security", "breach", "exploit", "vulnerability"]):
        return "security"
    if any(x in blob for x in ["agent", "workflow", "copilot", "assistant", "orchestration"]):
        return "agents"
    if any(x in blob for x in ["chip", "gpu", "compute", "datacenter", "data center"]):
        return "compute"
    if any(x in blob for x in ["developer", "code", "github", "cursor"]):
        return "developer"
    return "leverage"


def _master_hook(stories: List[Dict[str, Any]]) -> str:
    angle = _audience_angle(stories)
    if angle == "liability":
        return "The question is no longer whether AI can help. It is who gets blamed when it is wrong."
    if angle == "security":
        return "Every AI agent that can act also becomes a new thing that can break."
    if angle == "agents":
        return "AI agents are not becoming software features. They are becoming permission layers."
    if angle == "compute":
        return "The AI race is not just models anymore. It is power, chips, and who can afford the next answer."
    if angle == "developer":
        return "AI coding tools are no longer autocomplete. They are becoming leverage over the software team itself."
    return "Most AI coverage stops at the headline. The real story is who just gained leverage."


def _hashtags(stories: List[Dict[str, Any]], max_tags: int = 8) -> List[str]:
    tags = ["#AI", "#TheAIEdge", "#AINews"]
    blob = " ".join([str(s.get("headline") or "") for s in stories]).lower()
    for key, tag in [("agent", "#AIAgents"), ("health", "#HealthAI"), ("code", "#AICode"), ("developer", "#AICode"), ("security", "#AISecurity"), ("nvidia", "#NVIDIA"), ("openai", "#OpenAI"), ("anthropic", "#Anthropic")]:
        if key in blob:
            tags.append(tag)
    seen, out = set(), []
    for tag in tags:
        if tag.lower() in seen or tag.lower() in BAD_TAGS:
            continue
        seen.add(tag.lower())
        out.append(tag)
    return out[:max_tags]


def _story_summary_lines(stories: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for story in stories[:5]:
        headline = _clean_headline(story.get("headline", ""))
        data = [str(x) for x in (story.get("data_points") or [])[:2] if "No explicit" not in str(x)]
        suffix = f" — {'; '.join(data)}" if data else ""
        lines.append(f"- {headline}{suffix}")
    return "\n".join(lines)


def _title(meta: Dict[str, Any], stories: List[Dict[str, Any]]) -> str:
    existing = _clean_headline(str(meta.get("title") or ""))
    angle = _audience_angle(stories)
    ent = _entity_label(stories)
    candidates = {
        "liability": f"{ent} Pushes AI Into Higher-Stakes Territory",
        "security": "AI Agents Are Now a Security Problem, Not a Productivity Feature",
        "agents": "The AI Agent Stack Is Becoming a Land Grab",
        "compute": "The AI Compute Fight Is Becoming the Real Platform War",
        "developer": "AI Coding Tools Are Turning Into a Developer Power Shift",
        "leverage": "The AI Story Everyone Misread Today",
    }
    title = candidates.get(angle, existing or "The AI Story Everyone Misread Today")
    if BAD_FRAGMENT_RE.search(title) or len(title) < 24:
        title = "The AI Story Everyone Misread Today"
    return _clamp(title, 90)


def _clip_candidates(meta: Dict[str, Any], stories: List[Dict[str, Any]], moments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tracking = meta.get("tracking") or {}
    hook = _master_hook(stories)
    clips: List[Dict[str, Any]] = []
    for i, story in enumerate(stories[:5], start=1):
        quote = moments[i - 1].get("text") if i - 1 < len(moments) else ""
        line = _safe_hook(quote, hook if i == 1 else f"What changes if {_clean_headline(story.get('headline','this story'))} is not just a headline, but a leverage shift?")
        clips.append({
            "rank": i,
            "story": _clean_headline(story.get("headline") or ""),
            "hook": _clamp(line, 130),
            "subhook": _clamp((story.get("why_shocking") or "").strip(), 150),
            "cta": tracking.get("subscribe_clip_primary" if i == 1 else "subscribe_clip_secondary", meta.get("listen_url", "")),
            "visual_angle": "host face + bold consequence line + source headline receipt",
        })
    return clips


def build_assets(meta: Dict[str, Any]) -> Dict[str, Any]:
    stories = _top_stories(meta)
    moments = _forwardable_moments()
    tracking = meta.get("tracking") or {}
    show_notes_url = tracking.get("subscribe_show_notes") or "https://theledgr.io"
    x_url = tracking.get("subscribe_x") or show_notes_url
    linkedin_url = tracking.get("subscribe_linkedin") or show_notes_url
    listen_url = tracking.get("listen") or meta.get("listen_url", "")
    hashtags = _hashtags(stories)
    bullets = _story_summary_lines(stories)
    hook = _master_hook(stories)
    hook = _safe_hook(hook, "Most AI coverage stops at the headline. The real story is who just gained leverage.")
    title = _title(meta, stories)
    clips = _clip_candidates(meta, stories, moments)
    cta = f"Subscribe to TheLEDGR: {show_notes_url}"

    x_thread_lines = [
        f"1/ {hook}",
        "2/ The headline tells you what launched. The important part is who gained leverage, who took on risk, and who has to change the plan tomorrow.",
        f"3/ What we covered:\n{bullets}",
        f"4/ TheLEDGR Readout: what changed, who wins, who is exposed, and what serious operators should do tomorrow. {cta}",
    ]
    x_posts = {
        "post_1": _clamp(f"{hook}\n\nListen: {listen_url}", 280),
        "post_2": _clamp(f"The question is not whether AI moved today. The question is who has to react tomorrow.\n\n{cta}", 280),
        "post_3": _clamp("Headlines tell you what launched. TheLEDGR tells you what it changes.", 280),
        "thread": [_clamp(x, 280) for x in x_thread_lines],
    }
    yt = {
        "title": title,
        "description": _clamp(f"{hook}\n\nWhat we covered:\n{bullets}\n\nTheLEDGR Readout: what changed, who wins, who is exposed, and what operators should do tomorrow.\n\n{cta}", 1200),
        "shorts_hooks": [c["hook"] for c in clips],
    }
    linkedin = (
        f"{hook}\n\n"
        "Most AI coverage stops at the headline. The AI Edge does not.\n\n"
        f"Today we broke down:\n{bullets}\n\n"
        "The operator question: who gained leverage, who is exposed, and what changes tomorrow?\n\n"
        f"If AI affects your budget, workflow, hiring, roadmap, risk, or competitive position, subscribe to TheLEDGR: {linkedin_url}"
    )
    instagram = f"{hook}\n\nSerious AI people do not need more noise. They need the consequence.\n\n{cta}\n\n{' '.join(hashtags)}"
    blurb = f"The AI Edge turns today's biggest AI stories into operator-grade signal: {hook}"
    tags = {"tags_6": " ".join(hashtags[:6]), "tags_12": " ".join(hashtags[:12]), "seo_keywords": [_clean_headline(s.get("headline") or "") for s in stories if s.get("headline")] + ["AI news podcast", "TheLEDGR", "AI strategy", "AI agents", "AI regulation"]}
    pack = {
        "hook": hook,
        "yt_title": title,
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
        "linkedin": linkedin,
        "instagram": instagram,
        "tiktok": instagram,
        "blurb": blurb,
        "tags": tags,
        "clips": clips,
        "distribution": {
            "primary_goal": "newsletter_signups_and_show_follows",
            "primary_cta": show_notes_url,
            "channel_priority": ["spotify", "x", "linkedin", "youtube_shorts", "rss_show_notes"],
            "publish_order": ["Drop episode", "Post X thread", "Post strongest quote", "Post LinkedIn", "Clip best Jamie/Rufus exchange"],
        },
        "story_scores": build_story_debug_table(stories),
        "newsletter_teaser": f"TheLEDGR Readout: {hook} What changed, who wins, who is exposed, and what operators should do tomorrow.",
        "sponsor_report": {"hook": hook, "cta": cta, "recommended_sponsor_angle": "premium operator intelligence bundled with podcast + newsletter + social"},
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
    _write_text(OUT_X_THREAD, "\n\n".join(assets["x"]["thread"]))
    _write_json(OUT_X_POSTS, {"posts": [assets["x"]["post_1"], assets["x"]["post_2"], assets["x"]["post_3"]]})
    _write_text(OUT_LINKEDIN_POST, assets["linkedin"])
    _write_json(OUT_CLIP_HOOKS, {"hooks": [c["hook"] for c in assets["clips"]]})
    _write_text(OUT_NEWSLETTER_TEASER, assets["newsletter_teaser"])
    _write_json(OUT_SPONSOR_REPORT, assets["sponsor_report"])
    print("marketing_engine.py: wrote v2.24 competitive marketing assets", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
