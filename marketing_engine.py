#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from growth_engine import build_story_debug_table

BASE_DIR = Path(__file__).parent
META_PATH = BASE_DIR / "episode_metadata.json"
FORWARDABLE_PATH = BASE_DIR / "forwardable_moments.json"
LESSON_CARD_PATH = BASE_DIR / "episode_lesson_card.json"
SCENE_CARDS_PATH = BASE_DIR / "scene_cards.json"

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
OUT_LEARNING_PROMISE = BASE_DIR / "episode_learning_promise.txt"
OUT_SPONSOR_REPORT = BASE_DIR / "sponsor_marketing_report.json"
OUT_SEO_BRIEF = BASE_DIR / "seo_discovery_brief.json"

BAD_TAGS = {"#googlenews", "#indexbox", "#msn", "#bitget", "#yahootech"}
BAD_OPENERS_RE = re.compile(r"^(yeah,?\s+and\s+speaking\s+of|absolutely\.?|massive,?\s+right\??|exactly,?\s+alex|first up,?|so,?\s+alex|and while|meanwhile)", re.I)
BAD_FRAGMENT_RE = re.compile(r"(\band\s*\||\bcomes\s*\||\bcomes\s+into\.?$|\band\.?$|\bor\.?$|\bwith\.?$|\binto\.?$|\bto\.?$)", re.I)
SUMMARY_LINE_RE = re.compile(r"\b(?:published today|published on|according to|and speaking of|another big development|that(?:'|’)s a significant risk|huge leap|exactly, alex)\b", re.I)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text((text or "").strip() + "\n", encoding="utf-8")


def _clamp(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" -—:|,") + "…"


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"\|\s*(?:news and statistics|news|statistics|ai infrastructure).*$", "", t, flags=re.I)
    t = re.sub(r"\b(?:and|or|with|into|to|for)\.?$", "", t, flags=re.I).strip(" -—:|,")
    return t


def _story_headline(story: Dict[str, Any]) -> str:
    return _clean(str(story.get("headline") or story.get("title") or ""))


def _top_stories(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    stories = [s for s in (meta.get("stories") or []) if isinstance(s, dict) and _story_headline(s)]
    out: List[Dict[str, Any]] = []
    seen: List[set[str]] = []
    for story in stories:
        head = _story_headline(story)
        toks = set(re.findall(r"[a-z0-9]{4,}", head.lower())) - {"with", "from", "that", "this", "launch", "launches", "building", "help", "news", "will"}
        if any(len(toks & prev) / max(1, min(len(toks), len(prev))) >= 0.62 for prev in seen):
            continue
        out.append(story)
        seen.append(toks)
    return out[:5]


def _safe_hook(text: str, fallback: str) -> str:
    t = _clean(text)
    if not t or len(t) < 28 or BAD_OPENERS_RE.search(t) or BAD_FRAGMENT_RE.search(t) or SUMMARY_LINE_RE.search(t):
        t = fallback
    return _clamp(t, 180)


def _lesson_card(meta: Dict[str, Any], stories: List[Dict[str, Any]]) -> Dict[str, Any]:
    card = _read_json(LESSON_CARD_PATH, {})
    if isinstance(card, dict) and card.get("concept"):
        return card
    lp = meta.get("learning_promise") if isinstance(meta.get("learning_promise"), dict) else {}
    concept = str(lp.get("concept") or "leverage shift")
    plain = str(lp.get("plain_english") or "who gains control, who inherits risk, and what changes tomorrow")
    top = stories[0] if stories else {}
    head = _story_headline(top) or "today's AI story"
    return {
        "show_name": "The AI Signal Room",
        "concept": concept,
        "plain_english": plain,
        "big_question": f"What is the real lesson underneath {head}?",
        "simple_analogy": "a headline that looks like a product launch but behaves like a power shift",
        "operator_lesson": "Do not ask only what launched. Ask what risk, permission, cost, or accountability chain just appeared.",
        "titles": {"spotify_title": str(meta.get("title") or f"Today’s AI Lesson: {concept.title()}")},
    }


def _keywords(stories: List[Dict[str, Any]], card: Dict[str, Any]) -> List[str]:
    kws = ["AI podcast", "AI news", "artificial intelligence", "The AI Signal Room", str(card.get("concept") or "AI strategy")]
    for s in stories[:5]:
        bucket = str(s.get("bucket") or "").replace("_", " ").strip()
        if bucket:
            kws.append(bucket)
        for ent in (s.get("key_entities") or [])[:5]:
            ent_s = str(ent).strip()
            if ent_s and "Google News" not in ent_s:
                kws.append(ent_s)
        h = _story_headline(s).lower()
        for term in ["healthcare AI", "AI diagnosis", "AI agents", "AI security", "OpenAI", "Anthropic", "NVIDIA", "AI coding", "frontier AI", "AI regulation"]:
            if term.lower().split()[0] in h or term.lower() in h:
                kws.append(term)
    out: List[str] = []
    for k in kws:
        k = _clean(str(k))
        if k and k.lower() not in [x.lower() for x in out]:
            out.append(k)
    return out[:22]


def _hashtags(stories: List[Dict[str, Any]], card: Dict[str, Any], max_tags: int = 10) -> List[str]:
    tags = ["#AI", "#AISignalRoom", "#TheLEDGR", "#AINews"]
    blob = " ".join([_story_headline(s) for s in stories]).lower() + " " + str(card.get("concept") or "").lower()
    for key, tag in [("agent", "#AIAgents"), ("health", "#HealthAI"), ("diagnosis", "#HealthAI"), ("code", "#AICode"), ("github", "#AICode"), ("security", "#AISecurity"), ("liability", "#AIRisk"), ("nvidia", "#NVIDIA"), ("openai", "#OpenAI"), ("anthropic", "#Anthropic")]:
        if key in blob:
            tags.append(tag)
    seen: set[str] = set()
    out: List[str] = []
    for tag in tags:
        if tag.lower() in seen or tag.lower() in BAD_TAGS:
            continue
        seen.add(tag.lower())
        out.append(tag)
    return out[:max_tags]


def _story_lines(stories: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for s in stories[:5]:
        h = _story_headline(s)
        if not h:
            continue
        data = []
        for x in (s.get("data_points") or [])[:3]:
            x = str(x).strip()
            if x and not re.fullmatch(r"(?:published|the announcement was published|the article was published).*", x, flags=re.I):
                data.append(x)
        suffix = f" — {'; '.join(data[:2])}" if data else ""
        lines.append(f"- {h}{suffix}")
    return "\n".join(lines)


def _moments() -> List[Dict[str, Any]]:
    payload = _read_json(FORWARDABLE_PATH, [])
    if not isinstance(payload, list):
        return []
    good = []
    for m in payload:
        txt = str((m or {}).get("text") or "").strip()
        if len(txt) < 40 or SUMMARY_LINE_RE.search(txt) or BAD_OPENERS_RE.search(txt):
            continue
        if not re.search(r"\b(?:not .* but|who gets blamed|who owns|the question|the problem|the scary part|liability|permission|attack surface|mistake|risk|control|tomorrow|1%|99%)\b", txt, flags=re.I):
            continue
        good.append(m)
    return good[:5]


def _title(meta: Dict[str, Any], card: Dict[str, Any]) -> str:
    title = str((card.get("titles") or {}).get("spotify_title") or meta.get("title") or f"Today’s AI Lesson: {str(card.get('concept') or 'AI').title()}")
    return _clamp(_safe_hook(title, f"Today’s AI Lesson: {str(card.get('concept') or 'AI').title()}"), 92)


def _lesson_hook(card: Dict[str, Any], stories: List[Dict[str, Any]]) -> str:
    titles = card.get("titles") or {}
    hook = str(titles.get("social_hook") or "").strip()
    if not hook:
        concept = str(card.get("concept") or "AI leverage")
        plain = str(card.get("plain_english") or "who gains control and who inherits risk")
        hook = f"Today’s AI lesson: {concept}. The simple version: {plain}."
    return _safe_hook(hook, f"Today’s AI lesson: {card.get('concept', 'AI leverage')}.")


def _clip_candidates(meta: Dict[str, Any], stories: List[Dict[str, Any]], card: Dict[str, Any], moments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tracking = meta.get("tracking") or {}
    base_hook = _lesson_hook(card, stories)
    hooks = [base_hook]
    for m in moments:
        hooks.append(str(m.get("text") or ""))
    hooks.extend([
        f"The useful way to understand this is {card.get('concept')}: {card.get('plain_english')}.",
        "Signal or Static: real AI shift, hype, or too early?",
        "The Ledger Readout: what changed, who wins, who is exposed, and what operators watch tomorrow.",
    ])
    clips = []
    for i, s in enumerate(stories[:5], start=1):
        hook = _safe_hook(hooks[min(i-1, len(hooks)-1)], base_hook)
        clips.append({
            "rank": i,
            "story": _story_headline(s),
            "hook": _clamp(hook, 145),
            "subhook": _clamp(str(s.get("why_shocking") or ""), 150),
            "cta": tracking.get("subscribe_clip_primary" if i == 1 else "subscribe_clip_secondary", meta.get("listen_url", "")),
            "visual_angle": "host faces + Today’s AI Lesson + one receipt + one question",
        })
    return clips


def build_assets(meta: Dict[str, Any]) -> Dict[str, Any]:
    stories = _top_stories(meta)
    card = _lesson_card(meta, stories)
    moments = _moments()
    tracking = meta.get("tracking") or {}
    listen_url = tracking.get("listen") or meta.get("listen_url", "")
    show_notes_url = tracking.get("subscribe_show_notes") or "https://theledgr.io"
    linkedin_url = tracking.get("subscribe_linkedin") or show_notes_url
    x_url = tracking.get("subscribe_x") or show_notes_url
    title = _title(meta, card)
    hook = _lesson_hook(card, stories)
    bullets = _story_lines(stories)
    keywords = _keywords(stories, card)
    hashtags = _hashtags(stories, card)
    clips = _clip_candidates(meta, stories, card, moments)
    final_button = str((meta.get("episode_aircheck") or {}).get("final_button") or card.get("big_question") or "What changes tomorrow?")
    cta = f"Subscribe to TheLEDGR: {show_notes_url}"

    first_120 = _clamp(f"{hook} {card.get('concept')} explained through today’s biggest AI stories.", 220)
    yt_desc = (
        f"{first_120}\n\n"
        f"What we covered:\n{bullets}\n\n"
        f"Today’s AI Lesson: {card.get('concept')}\n"
        f"Plain English: {card.get('plain_english')}\n"
        f"Operator lesson: {card.get('operator_lesson')}\n\n"
        f"Final Button: {final_button}\n\n"
        f"SEO keywords: {', '.join(keywords)}\n\n{cta}"
    )

    x_thread = [
        f"1/ Today’s AI lesson: {card.get('concept')}",
        f"2/ {hook}",
        f"3/ Plain English: {card.get('plain_english')}",
        f"4/ What we covered:\n{bullets}",
        f"5/ The Ledger Readout: what changed, who wins, who is exposed, and what operators watch tomorrow. {x_url}",
    ]
    x_posts = {
        "post_1": _clamp(f"Today’s AI lesson: {card.get('concept')}\n\n{hook}\n\nListen: {listen_url}", 280),
        "post_2": _clamp(f"The simple version:\n\n{card.get('plain_english')}\n\n{cta}", 280),
        "post_3": _clamp(f"Signal or Static?\n\n{_story_headline(stories[0]) if stories else 'Today’s AI story'}\n\nReal shift, hype, or too early?", 280),
        "thread": [_clamp(x, 280) for x in x_thread],
    }
    linkedin = (
        f"{hook}\n\n"
        f"Today’s AI Signal Room lesson: {card.get('concept')}.\n\n"
        f"Plain English: {card.get('plain_english')}\n\n"
        f"What we covered:\n{bullets}\n\n"
        f"Operator lesson: {card.get('operator_lesson')}\n\n"
        f"If AI affects your budget, roadmap, risk, workflow, or career, subscribe to TheLEDGR: {linkedin_url}"
    )
    instagram = f"{hook}\n\nToday’s AI Lesson: {card.get('concept')}\n\n{cta}\n\n{' '.join(hashtags)}"
    pack = {
        "hook": hook,
        "yt_title": title,
        "youtube_title": str((card.get("titles") or {}).get("youtube_title") or title),
        "spotify_title": title,
        "yt_description": yt_desc[:1400],
        "tweet1": x_posts["post_1"],
        "tweet2": x_posts["post_2"],
        "show_notes": meta.get("show_notes") or yt_desc,
        "hashtags": " ".join(hashtags[:8]),
        "seo_keywords": ", ".join(keywords),
        "tracked_urls": tracking,
        "clip_candidates": clips,
        "today_ai_lesson": card,
    }
    return {
        "pack": pack,
        "x": x_posts,
        "yt": {"title": title, "description": yt_desc[:1400], "shorts_hooks": [c["hook"] for c in clips]},
        "linkedin": linkedin,
        "instagram": instagram,
        "tiktok": instagram,
        "blurb": f"The AI Signal Room teaches {card.get('concept')} through today’s AI stories: {hook}",
        "tags": {"tags_6": " ".join(hashtags[:6]), "tags_12": " ".join(hashtags[:12]), "seo_keywords": keywords},
        "clips": clips,
        "distribution": {
            "primary_goal": "show_follows_and_newsletter_signups",
            "primary_cta": show_notes_url,
            "channel_priority": ["spotify_search", "x", "linkedin", "youtube_shorts", "rss_show_notes"],
            "publish_order": ["Drop episode", "Post Today’s AI Lesson", "Post Signal or Static", "Post LinkedIn operator lesson", "Clip best Jamie/Rufus exchange"],
        },
        "story_scores": build_story_debug_table(stories),
        "newsletter_teaser": f"TheLEDGR Readout: {hook} Today’s lesson is {card.get('concept')}: {card.get('plain_english')}.",
        "sponsor_report": {"hook": hook, "cta": cta, "recommended_sponsor_angle": "The Ledger turns each daily AI lesson into operator-grade intelligence."},
        "seo_brief": {"title": title, "primary_keyword": card.get("concept"), "keywords": keywords, "first_120_chars": first_120[:120], "search_intent": "AI professionals looking for practical context, risks, and lessons behind daily AI news."},
    }


def main() -> int:
    meta = _read_json(META_PATH, {})
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
    _write_text(OUT_LEARNING_PROMISE, f"Today’s AI Lesson: {assets['pack']['today_ai_lesson'].get('concept')}\n{assets['pack']['today_ai_lesson'].get('plain_english')}")
    _write_json(OUT_SPONSOR_REPORT, assets["sponsor_report"])
    _write_json(OUT_SEO_BRIEF, assets["seo_brief"])
    print("marketing_engine.py: wrote v3.0 AI Signal Room marketing assets", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
