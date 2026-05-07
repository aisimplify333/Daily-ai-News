from __future__ import annotations

import datetime as dt
import json
import math
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

BASE_DIR = Path(__file__).parent
EXPERIMENTS_PATH = BASE_DIR / "experiments_state.json"
PERFORMANCE_EVENTS_PATH = BASE_DIR / "performance_events.jsonl"
SHOW_MEMORY_PATH = BASE_DIR / "show_memory.json"
FEED_XML_PATH = BASE_DIR / "feed.xml"
EPISODE_METADATA_PATH = BASE_DIR / "episode_metadata.json"

MODEL_VERSION = "podcast-growth-v3.0-ai-signal-room"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into", "is", "it",
    "its", "of", "on", "or", "that", "the", "their", "this", "to", "was", "were", "will", "with", "you",
    "your", "after", "amid", "new", "news", "launch", "launches", "announces", "says", "report",
}

AUTHORITATIVE_DOMAINS = {
    "openai.com": 100,
    "anthropic.com": 98,
    "deepmind.google": 96,
    "google.com": 92,
    "microsoft.com": 90,
    "meta.com": 90,
    "nvidia.com": 94,
    "apple.com": 88,
    "amazon.com": 86,
    "sec.gov": 98,
    "ftc.gov": 98,
    "justice.gov": 96,
    "europa.eu": 96,
    "ec.europa.eu": 96,
    "reuters.com": 96,
    "bloomberg.com": 95,
    "ft.com": 93,
    "wsj.com": 93,
    "theinformation.com": 90,
    "techcrunch.com": 82,
    "theverge.com": 82,
    "wired.com": 80,
    "axios.com": 80,
    "cnbc.com": 76,
}

WRAPPER_DOMAINS = {"news.google.com", "google.com", "www.google.com"}

PUBLISHER_SCORES = {
    "reuters": 96.0,
    "bloomberg": 95.0,
    "financial times": 93.0,
    "ft": 93.0,
    "wall street journal": 93.0,
    "wsj": 93.0,
    "the information": 90.0,
    "techcrunch": 82.0,
    "the verge": 82.0,
    "wired": 80.0,
    "axios": 80.0,
    "cnbc": 76.0,
    "fierce healthcare": 74.0,
    "help net security": 72.0,
    "tom's hardware": 72.0,
    "toms hardware": 72.0,
    "venturebeat": 72.0,
    "zdnet": 70.0,
    "yahoo finance": 58.0,
    "yahoo tech": 56.0,
    "yahoo": 54.0,
    "msn": 38.0,
    "openpr": 18.0,
    "openpr.com": 18.0,
    "prnewswire": 28.0,
    "globenewswire": 28.0,
    "ein presswire": 18.0,
    "indexbox": 16.0,
    "bitget": 16.0,
    "the tech buzz": 32.0,
    "medical daily": 36.0,
    "cathay capital": 36.0,
}

LOW_SIGNAL_PUBLISHERS = {
    "msn", "indexbox", "bitget", "openpr", "openpr.com", "prnewswire", "globenewswire", "ein presswire",
    "the tech buzz", "medical daily", "cathay capital",
}

VERTICAL_KEYWORDS = {
    "strategy": ["enterprise", "roadmap", "deployment", "pricing", "procurement", "adoption", "board", "cfo", "strategy"],
    "tools": ["model", "workflow", "agent", "launch", "api", "assistant", "tool", "copilot", "workspace"],
    "agents": ["agent", "autonomous", "swarm", "orchestr", "tool use", "memory", "browser", "permission", "control plane"],
    "health_ai": ["hospital", "health", "payer", "provider", "clinical", "ehr", "fda", "diagnostic", "doctor", "medical", "patient"],
    "code": ["developer", "coding", "code", "repo", "github", "copilot", "swe", "benchmark", "codex", "cursor", "windsurf"],
}

AI_HEAT_TERMS = {
    "openai": 30,
    "anthropic": 30,
    "claude": 24,
    "google deepmind": 28,
    "deepmind": 26,
    "gemini": 20,
    "nvidia": 28,
    "meta ai": 22,
    "llama": 18,
    "xai": 18,
    "grok": 18,
    "model release": 24,
    "frontier model": 28,
    "benchmark": 22,
    "swe-bench": 22,
    "agent failure": 24,
    "ai agent": 10,
    "agentic": 8,
    "safety": 20,
    "regulation": 20,
    "lawsuit": 22,
    "antitrust": 24,
    "chip": 20,
    "gpu": 20,
    "compute": 20,
    "data center": 18,
    "datacenter": 18,
    "developer": 16,
    "code": 14,
    "health ai": 22,
    "healthcare ai": 24,
    "diagnosis": 24,
    "diagnostic": 20,
    "accuracy": 18,
    "liability": 24,
    "clinical": 20,
    "fda": 20,
    "security": 20,
    "attack surface": 24,
    "permission layer": 22,
    "breach": 22,
    "copyright": 18,
    "revenue": 14,
    "earnings": 14,
    "valuation": 18,
    "funding": 14,
    "acquisition": 16,
}

CONSEQUENCE_KEYWORDS = {
    "regulation", "antitrust", "ban", "fine", "probe", "lawsuit", "export", "security", "breach", "outage",
    "recall", "pricing", "capex", "layoff", "earnings", "margin", "enterprise", "health", "defense", "government",
    "market", "stock", "revenue", "valuation", "funding", "ipo", "datacenter", "data center", "gpu", "chip", "supply chain",
    "copyright", "source code", "accuracy", "developers", "health systems", "diagnosis", "privacy", "workflow", "liability",
    "risk", "permission", "control", "compliance", "audit", "deployment", "procurement",
}

CLIPABLE_KEYWORDS = {
    "wins", "loses", "kills", "breaks", "banned", "caught", "secret", "panic", "warning", "why", "what happens",
    "nobody", "finally", "crash", "bubble", "surge", "ban", "lawsuit", "accidentally", "source code", "accuracy",
    "security", "diagnosis", "developers", "liability", "exposed", "power", "permission", "control",
}

ROUTINE_ENTERPRISE_TERMS = {
    "generally available", "now available", "available today", "expands capabilities", "new capabilities", "integrations",
    "copilot studio", "workspace", "workflow", "control plane", "enterprise control plane", "platform update", "product update",
    "introducing", "announces", "launches", "extends support", "support for", "feature", "preview", "ga",
}

EXCEPTIONAL_CONSEQUENCE_TERMS = {
    "lawsuit", "regulation", "antitrust", "ban", "security", "breach", "vulnerability", "earnings", "revenue", "valuation",
    "funding", "acquisition", "chip", "gpu", "compute", "data center", "datacenter", "openai", "anthropic", "deepmind",
    "benchmark", "model", "health", "clinical", "patient", "fda", "developer", "liability", "privacy", "copyright",
    "export", "china", "defense", "government", "safety", "audit", "compliance", "millions", "billion", "$",
}

FRONTIER_COMPANIES = [
    "OpenAI", "Anthropic", "Google", "DeepMind", "NVIDIA", "Meta", "Microsoft", "Amazon", "Apple", "xAI", "Tesla",
]

VARIANT_DEFAULTS: Dict[str, List[str]] = {
    "title_style": ["lesson_curiosity", "hard_number", "operator_consequence", "power_shift"],
    "cta_style": ["operator", "career", "contrarian"],
    "sponsor_style": ["decision_signal", "career_edge", "less_noise", "readout"],
    "clip_style": ["today_lesson", "contrarian", "operator_take", "power_shift"],
    "voice_profile": ["ai_signal_room_dynamic", "mike_archer_eryn_dialogue"],
}


def _safe_read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _safe_write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def slugify(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^a-z0-9\s-]", "", (text or "").lower())
    text = re.sub(r"\s+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-") or "episode"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", normalize_text(text)) if t not in STOPWORDS and len(t) > 2]


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    canonical = parsed._replace(scheme="https", netloc=netloc, params="", query=urlencode(query), fragment="")
    return urlunparse(canonical)


def headline_fingerprint(title: str) -> str:
    tokens = _tokenize(title)
    return " ".join(tokens[:12])


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _publisher_name(item: Dict[str, Any]) -> str:
    return normalize_text(str(item.get("publisher") or ""))


def _publisher_domain(item: Dict[str, Any]) -> str:
    raw_url = canonicalize_url(str(item.get("link") or item.get("source_url") or ""))
    if raw_url:
        domain = urlparse(raw_url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain in WRAPPER_DOMAINS:
            return ""
        return domain
    return ""


def parse_published(published: str) -> Optional[dt.datetime]:
    if not published:
        return None
    s = published.strip()
    try:
        parsed = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def recency_score(published: str) -> float:
    parsed = parse_published(published)
    if not parsed:
        return 0.0
    age_hours = max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 3600.0)
    if age_hours <= 6:
        return 100.0
    if age_hours <= 12:
        return 82.0
    if age_hours <= 24:
        return 65.0
    if age_hours <= 48:
        return 42.0
    if age_hours <= 96:
        return 18.0
    return 0.0


def authority_score(item: Dict[str, Any]) -> float:
    publisher = _publisher_name(item)
    for key, score in PUBLISHER_SCORES.items():
        if key in publisher:
            return score
    domain = _publisher_domain(item)
    if domain:
        for known, score in AUTHORITATIVE_DOMAINS.items():
            if domain.endswith(known):
                return float(score)
        if domain.endswith(".gov"):
            return 92.0
        if domain.endswith(".edu"):
            return 84.0
        return 55.0
    if publisher:
        return 50.0
    return 35.0


def _blob(title: str, summary: str) -> str:
    return f"{title or ''} {summary or ''}".lower()


def numeric_density_score(title: str, summary: str) -> float:
    blob = _blob(title, summary)
    digits = len(re.findall(r"\d", blob))
    money = 18 if re.search(r"(?:\$|€|£)\s?\d", blob) else 0
    pct = 12 if "%" in blob else 0
    scale = 8 if any(w in blob for w in ["billion", "million", "trillion", "revenue", "valuation", "funding"]) else 0
    return min(100.0, digits * 5.0 + money + pct + scale)


def ai_heat_score(title: str, summary: str, publisher: str = "") -> float:
    blob = _blob(title, summary) + " " + normalize_text(publisher)
    score = 0.0
    for term, pts in AI_HEAT_TERMS.items():
        if term in blob:
            score += pts
    if "microsoft" in blob and not any(k in blob for k in ["openai", "security", "lawsuit", "revenue", "earnings", "chip", "gpu", "developer", "health", "benchmark", "model", "anthropic", "deepmind", "nvidia"]):
        score -= 16.0
    if any(term in blob for term in ROUTINE_ENTERPRISE_TERMS) and not any(term in blob for term in EXCEPTIONAL_CONSEQUENCE_TERMS):
        score -= 22.0
    if any(k in blob for k in ["market forecast", "market size", "industry report", "to reach usd", "cagr"]):
        score -= 35.0
    if any(k in blob for k in ["whistleblower", "court", "trial", "shuts down", "urges state", "unsafe", "safety"]):
        score += 18.0
    return max(0.0, min(100.0, score))


def brand_fit_score(title: str, summary: str) -> float:
    blob = _blob(title, summary)
    ai_terms = ["ai", "artificial intelligence", "chatgpt", "llm", "model", "agent", "copilot", "openai", "anthropic", "nvidia", "gemini", "deepmind"]
    if not any(term in blob for term in ai_terms):
        return 0.0
    score = 22.0
    vertical_hits = 0
    for keywords in VERTICAL_KEYWORDS.values():
        if any(k in blob for k in keywords):
            vertical_hits += 1
    score += min(42.0, vertical_hits * 14.0)
    if ai_heat_score(title, summary) >= 35:
        score += 18.0
    if any(k in blob for k in CONSEQUENCE_KEYWORDS):
        score += 14.0
    if any(k in blob for k in ["forecast", "statistics", "stock growth", "market forecast", "industry statistics", "cagr"]):
        score -= 22.0
    if any(k in blob for k in ["crypto", "meme coin", "nft"]) and not any(k in blob for k in ["ai agent", "ai startup", "ai chip", "ai infrastructure"]):
        score -= 35.0
    return max(0.0, min(100.0, score))


def _recent_titles_from_feed(limit: int = 7) -> List[str]:
    titles: List[str] = []
    if FEED_XML_PATH.exists():
        try:
            root = ET.fromstring(FEED_XML_PATH.read_text(encoding="utf-8", errors="ignore"))
            for item in root.findall(".//item"):
                title = item.findtext("title") or ""
                if title.strip():
                    titles.append(title.strip())
                if len(titles) >= limit:
                    break
        except Exception:
            pass
    if len(titles) < limit and EPISODE_METADATA_PATH.exists():
        data = _safe_read_json(EPISODE_METADATA_PATH, {})
        if isinstance(data, dict) and data.get("title"):
            titles.append(str(data.get("title")))
    memory = load_show_memory()
    for row in memory.get("recent_headlines", [])[:limit]:
        if isinstance(row, dict) and row.get("title"):
            titles.append(str(row.get("title")))
        elif isinstance(row, str):
            titles.append(row)
        if len(titles) >= limit:
            break
    seen: set[str] = set()
    out: List[str] = []
    for t in titles:
        key = normalize_text(t)
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out[:limit]


def primary_entity(text: str) -> str:
    blob = text or ""
    for ent in FRONTIER_COMPANIES:
        if re.search(rf"\b{re.escape(ent)}\b", blob, flags=re.IGNORECASE):
            if ent == "Google" and re.search(r"\bGoogle News\b", blob, flags=re.IGNORECASE):
                continue
            return ent
    return ""


def company_fatigue_counts(limit: int = 7) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for title in _recent_titles_from_feed(limit=limit):
        ent = primary_entity(title)
        if ent:
            counts[ent] = counts.get(ent, 0) + 1
    return counts


def company_fatigue_penalty(item: Dict[str, Any], counts: Optional[Dict[str, int]] = None) -> float:
    counts = counts or company_fatigue_counts()
    title = str(item.get("title") or item.get("headline") or "")
    summary = str(item.get("summary") or item.get("why_shocking") or "")
    ent = primary_entity(f"{title} {summary}")
    if not ent:
        return 0.0
    n = counts.get(ent, 0)
    if n < 2:
        return 0.0
    heat = ai_heat_score(title, summary, str(item.get("publisher") or ""))
    consequence = forward_consequence_score(title, summary)
    # Fatigue is strong but not a ban. Truly hot stories can still break through.
    if n >= 3 and heat < 78 and consequence < 48:
        return min(36.0, 12.0 + 8.0 * (n - 2))
    if n >= 2 and heat < 60:
        return min(20.0, 8.0 + 5.0 * (n - 1))
    return 0.0


def novelty_score(item: Dict[str, Any], memory: Dict[str, Any]) -> float:
    title = str(item.get("title") or item.get("headline") or "")
    title_fp = headline_fingerprint(title)
    recent = memory.get("recent_headlines") or []
    recent_fps = [headline_fingerprint(str(x.get("title") or x.get("headline") or x)) for x in recent]
    recent_fps.extend(headline_fingerprint(t) for t in _recent_titles_from_feed(limit=7))
    if title_fp and title_fp in recent_fps:
        return 0.0
    tokens = _tokenize(title)
    best_overlap = 0.0
    for fp in recent_fps[:40]:
        if not fp:
            continue
        best_overlap = max(best_overlap, _jaccard(tokens, fp.split()))
    return max(0.0, 100.0 - best_overlap * 100.0)


def forward_consequence_score(title: str, summary: str) -> float:
    blob = _blob(title, summary)
    hits = sum(1 for k in CONSEQUENCE_KEYWORDS if k in blob)
    if any(k in blob for k in ["tomorrow", "next week", "coming months", "2026", "guidance", "next", "will"]):
        hits += 1
    if re.search(r"(?:\$|€|£)\s?\d|\d+%|\b\d+\s?(?:million|billion|trillion)\b", blob):
        hits += 2
    return min(100.0, hits * 10.0)


def clipability_score(title: str, summary: str) -> float:
    blob = _blob(title, summary)
    hits = sum(1 for k in CLIPABLE_KEYWORDS if k in blob)
    question_bonus = 10.0 if "?" in title else 0.0
    brevity_bonus = 10.0 if 45 <= len(title) <= 92 else 0.0
    contradiction_bonus = 10.0 if re.search(r"\b(not|but|instead|actually|real question|real story)\b", blob) else 0.0
    return min(100.0, hits * 10.0 + question_bonus + brevity_bonus + contradiction_bonus)


def is_routine_enterprise_update(title: str, summary: str) -> bool:
    blob = _blob(title, summary)
    routine = any(term in blob for term in ROUTINE_ENTERPRISE_TERMS)
    if not routine:
        return False
    exceptional = any(term in blob for term in EXCEPTIONAL_CONSEQUENCE_TERMS)
    # Generic "AI agent" alone is not enough to make a routine launch lead-worthy.
    if exceptional and not ("ai agent" in blob and len([t for t in EXCEPTIONAL_CONSEQUENCE_TERMS if t in blob]) <= 1):
        return False
    return True


def story_score_breakdown(item: Dict[str, Any], memory: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    memory = memory or {}
    title = str(item.get("title") or item.get("headline") or "")
    summary = str(item.get("summary") or item.get("why_shocking") or "")
    publisher = str(item.get("publisher") or "")
    fatigue_counts = company_fatigue_counts()
    breakdown = {
        "brand_fit": round(brand_fit_score(title, summary), 2),
        "authority": round(authority_score(item), 2),
        "novelty": round(novelty_score(item, memory), 2),
        "forward_consequence": round(forward_consequence_score(title, summary), 2),
        "numeric_density": round(numeric_density_score(title, summary), 2),
        "clipability": round(clipability_score(title, summary), 2),
        "recency": round(recency_score(str(item.get("published") or "")), 2),
        "ai_heat": round(ai_heat_score(title, summary, publisher), 2),
        "company_fatigue_penalty": round(company_fatigue_penalty(item, fatigue_counts), 2),
        "routine_enterprise_update": 1.0 if is_routine_enterprise_update(title, summary) else 0.0,
    }
    routine_penalty = 28.0 if breakdown["routine_enterprise_update"] and breakdown["forward_consequence"] < 35.0 and breakdown["ai_heat"] < 72.0 else 0.0
    low_signal_penalty = 22.0 if _publisher_name(item) in LOW_SIGNAL_PUBLISHERS else 0.0
    no_receipts_penalty = 10.0 if breakdown["numeric_density"] <= 0.0 and breakdown["forward_consequence"] < 20.0 else 0.0
    weighted = (
        0.18 * breakdown["brand_fit"]
        + 0.13 * breakdown["authority"]
        + 0.06 * breakdown["novelty"]
        + 0.25 * breakdown["forward_consequence"]
        + 0.10 * breakdown["numeric_density"]
        + 0.12 * breakdown["clipability"]
        + 0.04 * breakdown["recency"]
        + 0.24 * breakdown["ai_heat"]
        - breakdown["company_fatigue_penalty"]
        - routine_penalty
        - low_signal_penalty
        - no_receipts_penalty
    )
    breakdown["routine_penalty"] = round(routine_penalty, 2)
    breakdown["low_signal_penalty"] = round(low_signal_penalty, 2)
    breakdown["no_receipts_penalty"] = round(no_receipts_penalty, 2)
    breakdown["weighted"] = round(max(0.0, min(100.0, weighted)), 2)
    return breakdown


def cluster_story_candidates(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        item["canonical_url"] = canonicalize_url(str(item.get("link") or item.get("source_url") or ""))
        item["fingerprint"] = headline_fingerprint(str(item.get("title") or item.get("headline") or ""))
        item_tokens = item["fingerprint"].split()
        matched = None
        for cluster in clusters:
            if item["canonical_url"] and item["canonical_url"] == cluster["canonical_url"]:
                matched = cluster
                break
            overlap = _jaccard(item_tokens, cluster["tokens"])
            shared = len(set(item_tokens) & set(cluster["tokens"]))
            if overlap >= 0.58 or shared >= 5:
                matched = cluster
                break
        if matched is None:
            clusters.append({
                "canonical_url": item["canonical_url"],
                "tokens": item_tokens,
                "leader": item,
                "items": [item],
            })
            continue
        matched["items"].append(item)
        current = matched["leader"]
        current_score = authority_score(current) + recency_score(str(current.get("published") or ""))
        new_score = authority_score(item) + recency_score(str(item.get("published") or ""))
        if new_score > current_score:
            matched["leader"] = item
            matched["canonical_url"] = item["canonical_url"] or matched["canonical_url"]
            matched["tokens"] = item_tokens or matched["tokens"]
    out: List[Dict[str, Any]] = []
    for cluster in clusters:
        leader = dict(cluster["leader"])
        leader["cluster_size"] = len(cluster["items"])
        leader["cluster_publishers"] = sorted({str(x.get("publisher") or "").strip() for x in cluster["items"] if str(x.get("publisher") or "").strip()})
        out.append(leader)
    return out


def story_tier(item: Dict[str, Any]) -> Optional[str]:
    breakdown = item.get("score_breakdown") or {}
    brand_fit = float(breakdown.get("brand_fit", 0.0))
    authority = float(breakdown.get("authority", 0.0))
    forward = float(breakdown.get("forward_consequence", 0.0))
    numeric = float(breakdown.get("numeric_density", 0.0))
    clipability = float(breakdown.get("clipability", 0.0))
    recency = float(breakdown.get("recency", 0.0))
    heat = float(breakdown.get("ai_heat", 0.0))
    routine = bool(breakdown.get("routine_enterprise_update"))
    publisher = _publisher_name(item)
    bucket = str(item.get("bucket") or "").strip().lower()
    headline = str(item.get("title") or item.get("headline") or "").lower()

    if "market to reach usd" in headline or "cagr" in headline:
        return None
    if any(x in publisher for x in ["openpr", "prnewswire", "globenewswire", "ein presswire", "indexbox", "bitget"]):
        return None
    if authority < 34.0:
        return None
    if brand_fit < 28.0 and heat < 22.0:
        return None
    if routine and heat < 55.0 and forward < 35.0:
        # It may be useful as a fill story, but it should not dominate the slate.
        return "fill" if brand_fit >= 45.0 and authority >= 50.0 else None

    if (
        brand_fit >= 58.0
        and authority >= 50.0
        and (heat >= 42.0 or forward >= 28.0 or numeric >= 22.0 or clipability >= 24.0)
    ):
        return "primary"
    if (
        brand_fit >= 44.0
        and authority >= 45.0
        and (heat >= 25.0 or forward >= 14.0 or numeric >= 12.0 or clipability >= 12.0 or recency >= 45.0)
    ):
        return "support"
    if (
        brand_fit >= 36.0
        and authority >= 40.0
        and (heat >= 14.0 or forward >= 8.0 or numeric >= 8.0 or clipability >= 8.0 or recency >= 60.0)
    ):
        return "fill"
    # Protect critical health/safety items even when the source is mid-tier.
    if bucket == "health_ai" and authority >= 40.0 and ("patient" in headline or "clinical" in headline or "fda" in headline or "medical" in headline):
        return "support"
    return None


def is_story_eligible(item: Dict[str, Any]) -> bool:
    return story_tier(item) is not None


def _item_key(item: Dict[str, Any]) -> str:
    key = canonicalize_url(str(item.get("link") or item.get("source_url") or ""))
    if not key:
        key = headline_fingerprint(str(item.get("title") or item.get("headline") or ""))
    return key


def _bucket_name(item: Dict[str, Any]) -> str:
    return str(item.get("bucket") or "general").strip().lower() or "general"


def select_story_candidates(
    items: Sequence[Dict[str, Any]],
    n: int = 15,
    memory: Optional[Dict[str, Any]] = None,
    bucket_cap: int = 3,
) -> List[Dict[str, Any]]:
    memory = memory or load_show_memory()
    clustered = cluster_story_candidates(items)
    ranked: List[Dict[str, Any]] = []
    for item in clustered:
        item = dict(item)
        item["score_breakdown"] = story_score_breakdown(item, memory)
        item["growth_score"] = item["score_breakdown"]["weighted"]
        item["story_tier"] = story_tier(item)
        ranked.append(item)

    tier_rank = {"primary": 3, "support": 2, "fill": 1, None: 0}
    ranked.sort(
        key=lambda x: (
            tier_rank.get(x.get("story_tier"), 0),
            x.get("growth_score") or 0.0,
            x.get("score_breakdown", {}).get("ai_heat", 0.0),
            x.get("score_breakdown", {}).get("forward_consequence", 0.0),
            x.get("score_breakdown", {}).get("authority", 0.0),
            x.get("cluster_size") or 0,
        ),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    selected_keys: set[str] = set()
    bucket_counts: Dict[str, int] = {}

    def add_candidate(item: Dict[str, Any], ignore_bucket_cap: bool = False) -> bool:
        bucket = _bucket_name(item)
        if not ignore_bucket_cap and bucket_counts.get(bucket, 0) >= bucket_cap:
            return False
        key = _item_key(item)
        if not key or key in selected_keys:
            return False
        selected.append(item)
        selected_keys.add(key)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        return True

    # Round 1: best eligible stories with bucket discipline.
    for tier_name in ("primary", "support", "fill"):
        for item in ranked:
            if item.get("story_tier") != tier_name:
                continue
            add_candidate(item)
            if len(selected) >= n:
                return selected[:n]

    # Round 2: relax bucket caps, but only for eligible stories.
    if len(selected) < n:
        for item in ranked:
            if item.get("story_tier") is None:
                continue
            add_candidate(item, ignore_bucket_cap=True)
            if len(selected) >= n:
                return selected[:n]

    # Round 3 starvation guard: keep AI-relevant non-PR stories so main.py can still build a 5-story slate.
    if len(selected) < min(5, n):
        for item in ranked:
            if float((item.get("score_breakdown") or {}).get("brand_fit", 0.0)) < 26.0:
                continue
            if float((item.get("score_breakdown") or {}).get("authority", 0.0)) < 34.0:
                continue
            add_candidate(item, ignore_bucket_cap=True)
            if len(selected) >= n:
                break
    return selected[:n]


def attach_story_scores(stories: Sequence[Dict[str, Any]], candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        key_url = canonicalize_url(str(item.get("link") or item.get("source_url") or ""))
        if key_url:
            index[key_url] = item
        fp = headline_fingerprint(str(item.get("title") or item.get("headline") or ""))
        if fp:
            index.setdefault(fp, item)
    out: List[Dict[str, Any]] = []
    for story in stories:
        s = dict(story)
        match = index.get(canonicalize_url(str(s.get("source_url") or "")))
        if not match:
            match = index.get(headline_fingerprint(str(s.get("headline") or "")))
        if match:
            s["growth_score"] = match.get("growth_score")
            s["score_breakdown"] = match.get("score_breakdown")
            s["cluster_size"] = match.get("cluster_size")
            s["cluster_publishers"] = match.get("cluster_publishers")
            s["story_tier"] = match.get("story_tier")
        out.append(s)
    return out


def build_tracking_url(
    base_url: str,
    *,
    source: str,
    medium: str,
    campaign: str,
    content: str,
    term: str = "",
    extra: Optional[Dict[str, str]] = None,
) -> str:
    parsed = urlparse(base_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.update({
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
        "utm_content": content,
    })
    if term:
        params["utm_term"] = term
    for key, value in (extra or {}).items():
        if value is not None:
            params[key] = str(value)
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def choose_variant(test_name: str, variants: Optional[Sequence[str]] = None, seed: str = "") -> str:
    state = load_experiments_state()
    variants = list(variants or VARIANT_DEFAULTS.get(test_name, []))
    if not variants:
        raise ValueError(f"No variants configured for {test_name}")
    bucket = state.setdefault(test_name, {})
    for variant in variants:
        bucket.setdefault(variant, {"alpha": 1.0, "beta": 1.0, "impressions": 0, "successes": 0})
    rng = random.Random(seed or f"{test_name}:{dt.datetime.utcnow().isoformat()}")
    scored: List[Tuple[float, str]] = []
    for variant in variants:
        stats = bucket[variant]
        sample = rng.betavariate(max(0.001, stats["alpha"]), max(0.001, stats["beta"]))
        scored.append((sample, variant))
    scored.sort(reverse=True)
    winner = scored[0][1]
    bucket[winner]["impressions"] += 1
    _safe_write_json(EXPERIMENTS_PATH, state)
    return winner


def choose_episode_experiments(seed: str) -> Dict[str, str]:
    return {name: choose_variant(name, seed=f"{seed}:{name}") for name in VARIANT_DEFAULTS}


def record_experiment_result(test_name: str, variant: str, reward: float) -> None:
    state = load_experiments_state()
    bucket = state.setdefault(test_name, {})
    stats = bucket.setdefault(variant, {"alpha": 1.0, "beta": 1.0, "impressions": 0, "successes": 0})
    normalized = max(0.0, min(1.0, reward))
    stats["alpha"] += normalized
    stats["beta"] += 1.0 - normalized
    if normalized >= 0.5:
        stats["successes"] += 1
    _safe_write_json(EXPERIMENTS_PATH, state)


def load_experiments_state() -> Dict[str, Any]:
    state = _safe_read_json(EXPERIMENTS_PATH, {})
    if not isinstance(state, dict):
        state = {}
    for test_name, variants in VARIANT_DEFAULTS.items():
        bucket = state.setdefault(test_name, {})
        for variant in variants:
            bucket.setdefault(variant, {"alpha": 1.0, "beta": 1.0, "impressions": 0, "successes": 0})
    return state


def build_episode_tracking_payload(
    date_str: str,
    episode_title: str,
    listen_url: str,
    subscribe_url: str,
    experiments: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    experiments = experiments or {}
    campaign = f"podcast-{date_str}-{slugify(episode_title, 40)}"
    return {
        "campaign": campaign,
        "listen": build_tracking_url(
            listen_url,
            source="podcast",
            medium="audio",
            campaign=campaign,
            content="episode_listen",
            extra={"model_version": MODEL_VERSION},
        ),
        "subscribe_intro": build_tracking_url(
            subscribe_url,
            source="podcast",
            medium="audio",
            campaign=campaign,
            content="intro_cta",
            extra={"cta_style": experiments.get("cta_style", "")},
        ),
        "subscribe_show_notes": build_tracking_url(
            subscribe_url,
            source="podcast",
            medium="show_notes",
            campaign=campaign,
            content="show_notes_cta",
            extra={"cta_style": experiments.get("cta_style", "")},
        ),
        "subscribe_clip_primary": build_tracking_url(
            subscribe_url,
            source="podcast",
            medium="short_video",
            campaign=campaign,
            content="clip_primary",
            extra={"clip_style": experiments.get("clip_style", "")},
        ),
        "subscribe_clip_secondary": build_tracking_url(
            subscribe_url,
            source="podcast",
            medium="short_video",
            campaign=campaign,
            content="clip_secondary",
            extra={"clip_style": experiments.get("clip_style", "")},
        ),
        "subscribe_linkedin": build_tracking_url(subscribe_url, source="podcast", medium="linkedin", campaign=campaign, content="linkedin_post"),
        "subscribe_x": build_tracking_url(subscribe_url, source="podcast", medium="x", campaign=campaign, content="x_post"),
        "experiments": experiments,
    }


def apply_sponsor_variant(
    sponsors: Sequence[Dict[str, str]],
    experiments: Optional[Dict[str, str]] = None,
    spoken_url: str = "T-H-E-L-E-D-G-R dot I-O",
) -> List[Dict[str, str]]:
    experiments = experiments or {}
    style = experiments.get("sponsor_style", "decision_signal")
    variant_ctas = {
        "decision_signal": (
            "TheLEDGR is daily decision-grade AI signal for people who actually have to make calls, not just consume headlines. "
            f"Subscribe at {spoken_url}."
        ),
        "career_edge": (
            "If AI can change your role, your team, or your next promotion, TheLEDGR helps you see it before the room does. "
            f"Subscribe at {spoken_url}."
        ),
        "less_noise": (
            "TheLEDGR is built for operators who need less noise, more consequences, and a sharper read on what matters next. "
            f"Subscribe at {spoken_url}."
        ),
        "readout": (
            "TheLEDGR is the readout after the headline: what changed, who wins, who is exposed, and what serious operators should do tomorrow. "
            f"Subscribe at {spoken_url}."
        ),
    }
    updated: List[Dict[str, str]] = []
    for idx, sponsor in enumerate(sponsors):
        s = dict(sponsor)
        if (s.get("name") or "").strip().lower() == "theledgr":
            s["cta"] = variant_ctas.get(style, variant_ctas["decision_signal"])
            if idx == 0:
                s["tagline"] = "Decision-grade AI signal for operators, builders, and buyers."
        updated.append(s)
    return updated


def episode_reward(metrics: Dict[str, Any]) -> float:
    signups_per_k = float(metrics.get("newsletter_signups_per_1k_plays", 0.0))
    retention = float(metrics.get("retention_5m", 0.0))
    clip_ctr = float(metrics.get("clip_ctr", 0.0))
    notes_ctr = float(metrics.get("show_notes_ctr", 0.0))
    completion = float(metrics.get("completion_rate", 0.0))
    sponsor_inquiry = float(metrics.get("sponsor_inquiry_rate", 0.0))

    def norm(v: float, ceiling: float) -> float:
        return max(0.0, min(1.0, v / max(0.0001, ceiling)))

    reward = (
        0.35 * norm(signups_per_k, 25.0)
        + 0.20 * norm(retention, 0.65)
        + 0.15 * norm(clip_ctr, 0.08)
        + 0.15 * norm(notes_ctr, 0.05)
        + 0.10 * norm(completion, 0.60)
        + 0.05 * norm(sponsor_inquiry, 0.01)
    )
    return round(max(0.0, min(1.0, reward)), 4)


def load_show_memory() -> Dict[str, Any]:
    memory = _safe_read_json(SHOW_MEMORY_PATH, {})
    if not isinstance(memory, dict):
        memory = {}
    memory.setdefault("recent_headlines", [])
    memory.setdefault("winning_titles", [])
    memory.setdefault("winning_hooks", [])
    memory.setdefault("weak_patterns", [])
    memory.setdefault("last_reward", 0.0)
    return memory


def update_show_memory(
    episode_meta: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None,
    max_items: int = 60,
) -> Dict[str, Any]:
    metrics = metrics or {}
    memory = load_show_memory()
    stories = episode_meta.get("stories") or []
    for story in stories:
        if isinstance(story, dict):
            memory["recent_headlines"].insert(0, {
                "date": episode_meta.get("date"),
                "title": story.get("headline"),
                "growth_score": story.get("growth_score"),
            })
    memory["recent_headlines"] = memory["recent_headlines"][:max_items]
    reward = episode_reward(metrics) if metrics else float(memory.get("last_reward", 0.0))
    memory["last_reward"] = reward
    title = (episode_meta.get("title") or "").strip()
    hook = ((episode_meta.get("marketing_pack") or {}).get("hook") or "").strip()
    if reward >= 0.55 and title:
        memory["winning_titles"].insert(0, {"title": title, "reward": reward, "date": episode_meta.get("date")})
        memory["winning_titles"] = memory["winning_titles"][:20]
    if reward >= 0.55 and hook:
        memory["winning_hooks"].insert(0, {"hook": hook, "reward": reward, "date": episode_meta.get("date")})
        memory["winning_hooks"] = memory["winning_hooks"][:20]
    _safe_write_json(SHOW_MEMORY_PATH, memory)
    return memory


def record_episode_feedback(episode_meta: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    reward = episode_reward(metrics)
    experiments = ((episode_meta.get("tracking") or {}).get("experiments") or {})
    for test_name, variant in experiments.items():
        if variant:
            record_experiment_result(test_name, variant, reward)
    row = {
        "recorded_at": dt.datetime.utcnow().isoformat() + "Z",
        "date": episode_meta.get("date"),
        "title": episode_meta.get("title"),
        "reward": reward,
        "metrics": metrics,
        "experiments": experiments,
        "model_version": episode_meta.get("model_version") or MODEL_VERSION,
    }
    _append_jsonl(PERFORMANCE_EVENTS_PATH, row)
    update_show_memory(episode_meta, metrics)
    return row


def build_story_debug_table(candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in candidates:
        breakdown = item.get("score_breakdown") or {}
        rows.append({
            "title": item.get("title") or item.get("headline"),
            "publisher": item.get("publisher"),
            "bucket": item.get("bucket"),
            "story_tier": item.get("story_tier"),
            "score": item.get("growth_score"),
            "brand_fit": breakdown.get("brand_fit"),
            "authority": breakdown.get("authority"),
            "novelty": breakdown.get("novelty"),
            "forward_consequence": breakdown.get("forward_consequence"),
            "numeric_density": breakdown.get("numeric_density"),
            "clipability": breakdown.get("clipability"),
            "recency": breakdown.get("recency"),
            "ai_heat": breakdown.get("ai_heat"),
            "company_fatigue_penalty": breakdown.get("company_fatigue_penalty"),
            "routine_enterprise_update": bool(breakdown.get("routine_enterprise_update")),
            "routine_penalty": breakdown.get("routine_penalty"),
            "low_signal_penalty": breakdown.get("low_signal_penalty"),
            "cluster_size": item.get("cluster_size"),
        })
    return rows
