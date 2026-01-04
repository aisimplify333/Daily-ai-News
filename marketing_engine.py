#!/usr/bin/env python3
"""
marketing_engine.py

Purpose:
- Turn mani.py outputs (episode_metadata.json) into viral marketing assets:
  - X/Twitter posts + thread
  - YouTube title/description + Shorts hooks
  - LinkedIn post
  - Instagram/TikTok captions
  - Viral tag sets (<= 6, <= 12, SEO keywords)
  - A "press-style" blurb + email copy (optional use)

Inputs (expected from mani.py):
- episode_metadata.json (required)
  includes: date, title, listen_url, stories[], marketing_pack{}, etc.

Outputs (repo files; align with your .gitignore choices):
- marketing_pack.json                (expanded, platform-ready)
- marketing_x.json                   (X posts/thread)
- marketing_youtube.json             (YT title/desc/shorts)
- marketing_linkedin.txt
- marketing_instagram.txt
- marketing_tiktok.txt
- viral_tags.txt                     (multiple tag sets)
- seo_keywords.txt
- marketing_blurb.txt

Notes:
- Safe fallbacks if OpenAI key is missing or request fails.
- Keep content AI-edge: policy, markets, security, frontier models, chips, jobs.
"""

import os
import re
import json
import sys
import textwrap
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ----------------------------
# PATHS
# ----------------------------
BASE_DIR = Path(__file__).parent
META_PATH_DEFAULT = BASE_DIR / "episode_metadata.json"

OUT_MARKETING_PACK = BASE_DIR / "marketing_pack.json"
OUT_X = BASE_DIR / "marketing_x.json"
OUT_YT = BASE_DIR / "marketing_youtube.json"
OUT_LI = BASE_DIR / "marketing_linkedin.txt"
OUT_IG = BASE_DIR / "marketing_instagram.txt"
OUT_TT = BASE_DIR / "marketing_tiktok.txt"
OUT_TAGS = BASE_DIR / "viral_tags.txt"
OUT_SEO = BASE_DIR / "seo_keywords.txt"
OUT_BLURB = BASE_DIR / "marketing_blurb.txt"

# ----------------------------
# LLM CONFIG
# ----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o").strip()
PRIMARY_LLM = os.getenv("PRIMARY_LLM", "openai").strip().lower()

# Tone knobs
MAX_STORIES = int(os.getenv("MARKETING_MAX_STORIES", "5"))
FORCE_AI_PURITY = os.getenv("MARKETING_FORCE_AI_PURITY", "true").strip().lower() in ("1", "true", "yes")
AGGRESSIVE = os.getenv("MARKETING_AGGRESSIVE", "true").strip().lower() in ("1", "true", "yes")

# ----------------------------
# UTILS
# ----------------------------
def _safe_print(msg: str) -> None:
    print(msg, flush=True)

def _read_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_text(p: Path, s: str) -> None:
    p.write_text((s or "").strip() + "\n", encoding="utf-8")

def _write_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _clamp(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: max(0, n - 1)].rstrip() + "…"

def _extract_json_object(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    raw2 = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    raw2 = re.sub(r"\s*```$", "", raw2).strip()
    try:
        obj = json.loads(raw2)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    m = re.search(r"(\{.*\})", raw2, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def _digits(s: str) -> int:
    return len(re.findall(r"\d", s or ""))

def _slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s[:60].strip("-")

# ----------------------------
# STORY / TAG HEURISTICS
# ----------------------------
AI_ANCHORS = [
    "ai", "artificial intelligence", "generative", "llm", "large language model",
    "openai", "anthropic", "gemini", "xai", "grok", "chatgpt", "nvidia",
    "deepmind", "microsoft", "meta"
]

VIRAL_THEMES = [
    ("leak", 6), ("lawsuit", 5), ("ban", 5), ("outage", 6), ("recall", 5),
    ("breach", 6), ("hack", 6), ("deepfake", 6), ("regulator", 4),
    ("sec", 4), ("ftc", 4), ("eu", 3), ("export", 4), ("sanction", 4),
    ("layoff", 5), ("strike", 4), ("crash", 5), ("collapse", 5),
    ("valuation", 4), ("ipo", 4), ("funding", 4), ("billion", 4), ("million", 3)
]

def _ai_pure(text: str) -> bool:
    t = (text or "").lower()
    return any(a in t for a in AI_ANCHORS)

def _shock_score(story: Dict[str, Any]) -> int:
    head = (story.get("headline") or "")
    why = (story.get("why_shocking") or "")
    dp = story.get("data_points") or []
    blob = " ".join([head, why] + [str(x) for x in dp])
    score = 0
    score += min(60, _digits(blob) * 2)
    t = blob.lower()
    for k, w in VIRAL_THEMES:
        if k in t:
            score += w * 6
    # Reward money/percent tokens
    if re.search(r"(\$|€|£)\s?\d", blob):
        score += 18
    if "%" in blob:
        score += 12
    # Penalize if not AI-pure and we are enforcing purity
    if FORCE_AI_PURITY and not _ai_pure(blob):
        score -= 25
    return score

def _top_stories(meta: Dict[str, Any], n: int = 5) -> List[Dict[str, Any]]:
    stories = meta.get("stories") or []
    if not isinstance(stories, list):
        return []
    stories2 = [s for s in stories if isinstance(s, dict)]
    # Score and rank
    ranked = sorted(stories2, key=_shock_score, reverse=True)
    if FORCE_AI_PURITY:
        # Keep only AI-pure first, then fill if needed
        pure = [s for s in ranked if _ai_pure(" ".join([s.get("headline",""), s.get("why_shocking","")]))]
        rest = [s for s in ranked if s not in pure]
        ranked = pure + rest
    return ranked[:n]

def _entity_keywords(stories: List[Dict[str, Any]]) -> List[str]:
    kws: List[str] = []
    for s in stories:
        ents = s.get("key_entities") or []
        if isinstance(ents, list):
            for e in ents:
                e = str(e).strip()
                if 2 <= len(e) <= 30:
                    kws.append(e)
        # Also mine headline tokens (lightly)
        head = (s.get("headline") or "")
        for tok in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", head):
            kws.append(tok)
    # Dedup preserve order
    out = []
    seen = set()
    for k in kws:
        kk = k.lower()
        if kk in seen:
            continue
        seen.add(kk)
        out.append(k)
    return out[:18]

def _build_tag_sets(stories: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Core show tags + dynamic tags from entities/themes
    core = ["#AI", "#TechNews", "#OpenAI", "#Nvidia", "#AIRegulation", "#AICybersecurity"]
    entities = _entity_keywords(stories)
    # Map entities into hashtags (safe)
    entity_tags = []
    for e in entities:
        tag = "#" + re.sub(r"[^A-Za-z0-9]", "", e)
        if len(tag) >= 3 and len(tag) <= 22:
            entity_tags.append(tag)

    # Theme tags from heuristics
    blob = " ".join([(s.get("headline") or "") + " " + (s.get("why_shocking") or "") for s in stories]).lower()
    theme_tags = []
    if "outage" in blob or "downtime" in blob:
        theme_tags.append("#Outage")
    if "leak" in blob or "breach" in blob or "hack" in blob:
        theme_tags.append("#Cybersecurity")
    if "lawsuit" in blob or "copyright" in blob:
        theme_tags.append("#Copyright")
    if "eu" in blob or "ai act" in blob:
        theme_tags.append("#EUAIACT")
    if "ipo" in blob or "valuation" in blob or "funding" in blob:
        theme_tags.append("#VentureCapital")

    # Build sets
    set6 = (core[:4] + theme_tags + entity_tags)[:6]
    set12 = (core + theme_tags + entity_tags)[:12]

    # SEO keywords (not hashtags)
    seo = []
    for s in stories:
        seo.append((s.get("headline") or "").strip())
    seo += [e for e in entities]
    seo = [x for x in seo if x]
    # Dedup
    seo_out, seen = [], set()
    for k in seo:
        kk = k.lower()
        if kk in seen:
            continue
        seen.add(kk)
        seo_out.append(k)
    return {"tags_6": set6, "tags_12": set12, "seo_keywords": seo_out[:25]}

# ----------------------------
# LLM CALL (OPTIONAL)
# ----------------------------
def _llm_enabled() -> bool:
    return bool(OPENAI_API_KEY) and PRIMARY_LLM == "openai"

def _openai_client():
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)

def _generate_with_llm(prompt: str, temperature: float = 0.55, max_tokens: int = 900) -> str:
    client = _openai_client()
    resp = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": "You are a direct-response growth marketer for a daily AI news show. Output exactly what is requested."},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

# ----------------------------
# COPY GENERATORS
# ----------------------------
def _story_lines(stories: List[Dict[str, Any]]) -> str:
    lines = []
    for i, s in enumerate(stories, start=1):
        head = (s.get("headline") or "").strip()
        pub = (s.get("publisher") or "").strip()
        url = (s.get("source_url") or "").strip()
        dp = s.get("data_points") or []
        dp_txt = "; ".join([str(x).strip() for x in dp[:4] if str(x).strip()])
        lines.append(f"{i}) {head} ({pub})")
        if dp_txt:
            lines.append(f"   Data: {dp_txt}")
        if url:
            lines.append(f"   Source: {url}")
    return "\n".join(lines).strip()

def _fallback_pack(date_str: str, title: str, listen_url: str, stories: List[Dict[str, Any]], tags: Dict[str, Any]) -> Dict[str, Any]:
    top_head = (stories[0].get("headline") if stories else "AI JUST SHIFTED AGAIN").strip()
    hook = _clamp(top_head.upper(), 64)

    # Make a sharper hook if we have numbers
    blob = " ".join([top_head] + [str(x) for x in (stories[0].get("data_points") or [])])
    if _digits(blob) >= 3:
        hook = _clamp((top_head + " — " + re.sub(r"\s+", " ", blob)[:30]).upper(), 64)

    x1 = _clamp(f"{hook}\n\nIf this trend holds, what breaks first—jobs, markets, or safety?", 260)
    x2 = _clamp(f"Full episode: {listen_url}\n\n" + " ".join(tags["tags_6"]), 260)

    yt_title = _clamp(f"{top_head} | The AI Edge", 90)
    yt_desc = _clamp(
        "Today’s AI Edge breaks down:\n"
        + "\n".join([f"- {s.get('headline','')}" for s in stories[:5]])
        + f"\n\nListen: {listen_url}\n\nSources:\n"
        + "\n".join([s.get("source_url","") for s in stories[:5] if s.get("source_url")]),
        1200,
    )

    return {
        "date": date_str,
        "hook": hook,
        "card_subhook": "THE CONSEQUENCES START NOW",
        "x_post_1": x1,
        "x_post_2": x2,
        "yt_title": yt_title,
        "yt_description": yt_desc,
        "hashtags_6": " ".join(tags["tags_6"]),
        "hashtags_12": " ".join(tags["tags_12"]),
    }

def _make_assets(date_str: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    listen_url = (meta.get("listen_url") or meta.get("LISTEN_URL") or "").strip()
    ep_title = (meta.get("title") or f"The AI Edge — {date_str}").strip()

    stories = _top_stories(meta, n=min(MAX_STORIES, 5))
    tags = _build_tag_sets(stories)

    # If LLM is available, generate richer platform copy
    if _llm_enabled():
        story_block = _story_lines(stories)

        aggression = "Go for high-stakes
::contentReference[oaicite:0]{index=0}

