from __future__ import annotations

import datetime as dt
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

BASE_DIR = Path(__file__).parent
EXPERIMENTS_PATH = BASE_DIR / "experiments_state.json"
PERFORMANCE_EVENTS_PATH = BASE_DIR / "performance_events.jsonl"
SHOW_MEMORY_PATH = BASE_DIR / "show_memory.json"

MODEL_VERSION = "podcast-growth-v2.2"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in",
    "into", "is", "it", "its", "of", "on", "or", "that", "the", "their", "this",
    "to", "was", "were", "will", "with", "you", "your", "after", "amid", "new",
}

AUTHORITATIVE_DOMAINS = {
    "openai.com": 100,
    "anthropic.com": 95,
    "google.com": 92,
    "deepmind.google": 92,
    "microsoft.com": 90,
    "meta.com": 88,
    "nvidia.com": 90,
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
    "theverge.com": 80,
    "wired.com": 80,
    "cnbc.com": 76,
    "axios.com": 78,
}

WRAPPER_DOMAINS = {
    "news.google.com",
    "google.com",
    "www.google.com",
}

PUBLISHER_SCORES = {
    "reuters": 96.0,
    "bloomberg": 95.0,
    "financial times": 93.0,
    "ft": 93.0,
    "wall street journal": 93.0,
    "wsj": 93.0,
    "the information": 90.0,
    "techcrunch": 82.0,
    "the verge": 80.0,
    "wired": 80.0,
    "axios": 78.0,
    "cnbc": 76.0,
    "tom's hardware": 72.0,
    "toms hardware": 72.0,
    "yahoo tech": 58.0,
    "yahoo": 55.0,
    "cyber magazine": 50.0,
    "msn": 40.0,
    "indexbox": 32.0,
    "bitget": 18.0,
}

LOW_SIGNAL_PUBLISHERS = {
    "msn",
    "indexbox",
    "bitget",
}

VERTICAL_KEYWORDS = {
    "strategy": ["enterprise", "roadmap", "deployment", "pricing", "procurement", "adoption", "board", "cfo"],
    "tools": ["model", "workflow", "agent", "launch", "api", "assistant", "tool", "copilot"],
    "agents": ["agent", "autonomous", "swarm", "orchestr", "tool use", "memory", "browser"],
    "health_ai": ["hospital", "health", "payer", "provider", "clinical", "ehr", "fda", "diagnostic"],
    "code": ["developer", "coding", "code", "repo", "github", "copilot", "swe", "benchmark"],
}

CONSEQUENCE_KEYWORDS = {
    "regulation", "antitrust", "ban", "fine", "probe", "lawsuit", "export", "security",
    "breach", "outage", "recall", "pricing", "capex", "layoff", "earnings", "margin",
    "enterprise", "health", "defense", "government", "market", "stock", "revenue",
    "valuation", "funding", "ipo", "datacenter", "gpu", "supply chain", "copyright",
}

CLIPABLE_KEYWORDS = {
    "wins", "loses", "kills", "breaks", "banned", "caught", "secret", "panic", "warning",
    "why", "what happens", "nobody", "finally", "crash", "bubble", "surge", "ban", "lawsuit",
}

VARIANT_DEFAULTS: Dict[str, List[str]] = {
    "title_style": ["hard_number", "operator_consequence", "tomorrow_tension"],
    "cta_style": ["operator", "career", "contrarian"],
    "sponsor_style": ["decision_signal", "career_edge", "less_noise"],
    "clip_style": ["contrarian", "fear_greed", "operator_take"],
    "voice_profile": ["control", "marin_cedar", "cedar_sage"],
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
        return 80.0
    if age_hours <= 24:
        return 60.0
    if age_hours <= 48:
        return 35.0
    if age_hours <= 96:
        return 15.0
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


def numeric_density_score(title: str, summary: str) -> float:
    blob = f"{title} {summary}".lower()
    digits = len(re.findall(r"\d", blob))
    money = 12 if re.search(r"(?:\$|€|£)\s?\d", blob) else 0
    pct = 8 if "%" in blob else 0
    return min(100.0, digits * 5.0 + money + pct)


def brand_fit_score(title: str, summary: str) -> float:
    blob = f"{title} {summary}".lower()

    ai_terms = [
        "ai", "artificial intelligence", "chatgpt", "llm", "model",
        "agent", "copilot", "openai", "anthropic", "nvidia", "gemini",
    ]
    if not any(term in blob for term in ai_terms):
        return 0.0

    score = 0.0
    vertical_hits = 0
    for keywords in VERTICAL_KEYWORDS.values():
        if any(k in blob for k in keywords):
            vertical_hits += 1
    score += min(54.0, vertical_hits * 18.0)

    if any(k in blob for k in [
        "enterprise", "developer", "health", "clinical", "hospital",
        "regulation", "lawsuit", "export", "security", "breach",
        "agent", "api", "model", "chip", "gpu", "datacenter",
    ]):
        score += 20.0

    if any(k in blob for k in [
        "forecast", "statistics", "stock growth", "market forecast",
        "industry statistics",
    ]):
        score -= 18.0

    if any(k in blob for k in ["crypto", "meme coin", "nft"]) and not any(
        k in blob for k in ["ai agent", "ai startup", "ai chip", "ai infrastructure"]
    ):
        score -= 35.0

    if any(k in blob for k in ["earnings", "stock", "valuation", "funding"]):
        if not any(k in blob for k in [
            "enterprise", "regulation", "security", "developer",
            "chip", "gpu", "agent", "deployment", "inference",
        ]):
            score -= 12.0

    return max(0.0, min(100.0, score))


def novelty_score(item: Dict[str, Any], memory: Dict[str, Any]) -> float:
    title = str(item.get("title") or item.get("headline") or "")
    title_fp = headline_fingerprint(title)
    recent = memory.get("recent_headlines") or []
    recent_fps = [headline_fingerprint(str(x.get("title") or x.get("headline") or x)) for x in recent]
    if title_fp in recent_fps:
        return 0.0
    tokens = _tokenize(title)
    best_overlap = 0.0
    for fp in recent_fps[:25]:
        overlap = _jaccard(tokens, fp.split())
        best_overlap = max(best_overlap, overlap)
    return max(0.0, 100.0 - best_overlap * 100.0)


def forward_consequence_score(title: str, summary: str) -> float:
    blob = f"{title} {summary}".lower()
    hits = sum(1 for k in CONSEQUENCE_KEYWORDS if k in blob)
    if any(k in blob for k in ["tomorrow", "next week", "coming months", "2026", "guidance"]):
        hits += 2
    return min(100.0, hits * 12.0)


def clipability_score(title: str, summary: str) -> float:
    blob = f"{title} {summary}".lower()
    hits = sum(1 for k in CLIPABLE_KEYWORDS if k in blob)
    question_bonus = 10.0 if "?" in title else 0.0
    brevity_bonus = 10.0 if 45 <= len(title) <= 90 else 0.0
    return min(100.0, hits * 12.0 + question_bonus + brevity_bonus)


def story_score_breakdown(item: Dict[str, Any], memory: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    memory = memory or {}
    title = str(item.get("title") or item.get("headline") or "")
    summary = str(item.get("summary") or item.get("why_shocking") or "")
    breakdown = {
        "brand_fit": round(brand_fit_score(title, summary), 2),
        "authority": round(authority_score(item), 2),
        "novelty": round(novelty_score(item, memory), 2),
        "forward_consequence": round(forward_consequence_score(title, summary), 2),
        "numeric_density": round(numeric_density_score(title, summary), 2),
        "clipability": round(clipability_score(title, summary), 2),
        "recency": round(recency_score(str(item.get("published") or "")), 2),
    }
    weighted = (
        0.30 * breakdown["brand_fit"]
        + 0.22 * breakdown["authority"]
        + 0.10 * breakdown["novelty"]
        + 0.18 * breakdown["forward_consequence"]
        + 0.10 * breakdown["numeric_density"]
        + 0.08 * breakdown["clipability"]
        + 0.02 * breakdown["recency"]
    )
    breakdown["weighted"] = round(weighted, 2)
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
        leader["cluster_publishers"] = sorted({
            str(x.get("publisher") or "").strip()
            for x in cluster["items"]
            if str(x.get("publisher") or "").strip()
        })
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
    publisher = _publisher_name(item)

    low_signal = publisher in LOW_SIGNAL_PUBLISHERS

    if (
        brand_fit >= 55.0
        and authority >= 48.0
        and (forward >= 10.0 or numeric >= 18.0 or clipability >= 12.0 or recency >= 35.0)
        and not (low_signal and brand_fit < 72.0)
    ):
        return "primary"

    if (
        brand_fit >= 42.0
        and authority >= 40.0
        and (forward >= 6.0 or numeric >= 10.0 or clipability >= 8.0 or recency >= 25.0)
        and not (low_signal and brand_fit < 65.0)
    ):
        return "support"

    if (
        brand_fit >= 34.0
        and authority >= 35.0
        and (forward >= 0.0 or numeric >= 6.0 or clipability >= 4.0 or recency >= 15.0)
        and not (low_signal and brand_fit < 78.0)
    ):
        return "fill"

    return None


def is_story_eligible(item: Dict[str, Any]) -> bool:
    return story_tier(item) is not None


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

    ranked.sort(
        key=lambda x: (
            {"primary": 3, "support": 2, "fill": 1, None: 0}.get(x.get("story_tier"), 0),
            x.get("growth_score") or 0.0,
            x.get("score_breakdown", {}).get("authority", 0.0),
            x.get("cluster_size") or 0,
        ),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    selected_keys = set()
    bucket_counts: Dict[str, int] = {}

    def item_key(item: Dict[str, Any]) -> str:
        key = canonicalize_url(str(item.get("link") or item.get("source_url") or ""))
        if not key:
            key = headline_fingerprint(str(item.get("title") or item.get("headline") or ""))
        return key

    def add_candidate(item: Dict[str, Any], ignore_bucket_cap: bool = False) -> bool:
        bucket = str(item.get("bucket") or "general").strip().lower()
        if not ignore_bucket_cap and bucket_counts.get(bucket, 0) >= bucket_cap:
            return False
        key = item_key(item)
        if not key or key in selected_keys:
            return False
        selected.append(item)
        selected_keys.add(key)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        return True

    for tier_name in ("primary", "support", "fill"):
        for item in ranked:
            if item.get("story_tier") != tier_name:
                continue
            add_candidate(item)
            if len(selected) >= n:
                return selected[:n]

    # Relax bucket caps if the slate is still thin.
    if len(selected) < n:
        for item in ranked:
            if item.get("story_tier") is None:
                continue
            add_candidate(item, ignore_bucket_cap=True)
            if len(selected) >= n:
                return selected[:n]

    # Final starvation guard: keep AI-relevant stories even if they are weaker.
    if len(selected) < min(5, n):
        for item in ranked:
            breakdown = item.get("score_breakdown") or {}
            if float(breakdown.get("brand_fit", 0.0)) < 28.0:
                continue
            if float(breakdown.get("authority", 0.0)) < 30.0:
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
        "subscribe_linkedin": build_tracking_url(
            subscribe_url,
            source="podcast",
            medium="linkedin",
            campaign=campaign,
            content="linkedin_post",
        ),
        "subscribe_x": build_tracking_url(
            subscribe_url,
            source="podcast",
            medium="x",
            campaign=campaign,
            content="x_post",
        ),
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
            "cluster_size": item.get("cluster_size"),
        })
    return rows
