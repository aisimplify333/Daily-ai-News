import os
import re
import json
import uuid
import shutil
import subprocess
import datetime
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv
import feedparser
import requests
from bs4 import BeautifulSoup
from pydub import AudioSegment
from openai import OpenAI

# ----------------------------
# ENV
# ----------------------------
load_dotenv()

# ----------------------------
# CONFIG (Spotify/RSS identity)
# ----------------------------
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily AI News Drama: raw, human, high-stakes conversations about the future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
}

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)

TMP_AUDIO_DIR = BASE_DIR / "_tmp_audio"
TMP_AUDIO_DIR.mkdir(exist_ok=True)

INTRO_PATH = BASE_DIR / "intro.mp3"
OUTRO_PATH = BASE_DIR / "outro.mp3"

FEED_XML_PATH = BASE_DIR / "feed.xml"
SPONSORS_PATH = BASE_DIR / "sponsors.json"

AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/",
).rstrip("/") + "/"

LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/",
).rstrip("/") + "/"

PRIMARY_LLM = os.getenv("PRIMARY_LLM", "openai").strip().lower()  # gemini | openai
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")

MIN_MINUTES = float(os.getenv("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "30"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "28"))

# Script sizing
WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "150"))
SCRIPT_ATTEMPTS = int(os.getenv("SCRIPT_ATTEMPTS", "6"))  # retained, but no longer used for full-script rewrite loops

# Segment generation attempts (segmented scripting is the reliable path)
SEGMENT_ATTEMPTS = int(os.getenv("SEGMENT_ATTEMPTS", "3"))

# Token ceilings
# Segmented scripting means we don't need a single giant output. Keep per-call budgets reasonable.
SCRIPT_MAX_TOKENS = int(os.getenv("SCRIPT_MAX_TOKENS", "2200"))
JSON_MAX_TOKENS = int(os.getenv("JSON_MAX_TOKENS", "1800"))

CLEANUP_TEMP = os.getenv("CLEANUP_TEMP", "true").strip().lower() in ("1", "true", "yes")
KEEP_LAST_EPISODES = int(os.getenv("KEEP_LAST_EPISODES", "60"))

RUN_MARKETING_ASSETS = os.getenv("RUN_MARKETING_ASSETS", "true").strip().lower() in ("1", "true", "yes")
PUBLISH_SOCIAL = os.getenv("PUBLISH_SOCIAL", "false").strip().lower() in ("1", "true", "yes")

VOICE_MAP = {
    "ALEX": os.getenv("VOICE_ALEX", "onyx"),
    "JAMIE": os.getenv("VOICE_JAMIE", "nova"),
    "RUFUS": os.getenv("VOICE_RUFUS", "fable"),
}

# TTS tuning
TTS_MERGE_MAX_CHARS = int(os.getenv("TTS_MERGE_MAX_CHARS", "2400"))
TTS_CHUNK_MAX_CHARS = int(os.getenv("TTS_CHUNK_MAX_CHARS", "2800"))
TTS_RETRIES = int(os.getenv("TTS_RETRIES", "3"))

# Audio stitch method: pydub (recommended) or ffmpeg
STITCH_METHOD = os.getenv("STITCH_METHOD", "pydub").strip().lower()  # pydub | ffmpeg

# ----------------------------
# QUALITY GATES (98% standard)
# ----------------------------
MIN_COLD_OPEN_LINES = int(os.getenv("MIN_COLD_OPEN_LINES", "6"))            # lines before [MUSIC] in Segment 1
MIN_DIGITS_PER_SEGMENT = int(os.getenv("MIN_DIGITS_PER_SEGMENT", "12"))     # numeric density per segment
MIN_DIGITS_PER_EPISODE = int(os.getenv("MIN_DIGITS_PER_EPISODE", "85"))     # numeric density overall
MIN_NUMERIC_BULLETS_PER_STORY = int(os.getenv("MIN_NUMERIC_BULLETS_PER_STORY", "2"))

STRICT_EPISODE_FILENAME_RE = re.compile(r"^podcast_\d{4}-\d{2}-\d{2}\.mp3$")

MONEY_RE = re.compile(r"(\$|€|£)\s?\d")
NUMERIC_TOKEN_RE = re.compile(r"(\d+(\.\d+)?%|\$?\d[\d,]*(\.\d+)?|\b\d{4}\b|\bQ[1-4]\b)", re.IGNORECASE)

def _digit_count(s: str) -> int:
    return len(re.findall(r"\d", s or ""))

def _numeric_score(s: str) -> int:
    """
    Quick heuristic: prefer items with digits, money tokens, %, 'billion/million', etc.
    """
    if not s:
        return 0
    s2 = s.lower()
    score = 0
    score += 3 * _digit_count(s2)
    if "$" in s2 or "€" in s2 or "£" in s2:
        score += 25
    if "%" in s2:
        score += 15
    for w, pts in [("billion", 18), ("million", 14), ("bn", 14), ("m", 6), ("ipo", 10), ("funding", 10)]:
        if w in s2:
            score += pts
    return score

def _extract_numeric_sentences(text: str, max_items: int = 6) -> list[str]:
    """
    Pull short sentences that contain explicit figures (numbers, $, %, years, quarters).
    """
    if not text:
        return []
    sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    hits = []
    for s in sents:
        if NUMERIC_TOKEN_RE.search(s):
            s2 = s.strip()
            if 30 <= len(s2) <= 220:
                hits.append(s2)
        if len(hits) >= max_items:
            break
    # De-dupe while preserving order
    out = []
    seen = set()
    for h in hits:
        key = h.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out[:max_items]

# ----------------------------
# SAFE PRINT
# ----------------------------
def _safe_print(msg: str):
    print(msg, flush=True)

# ----------------------------
# SYSTEM CHECKS
# ----------------------------
def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def _run(cmd: List[str], fail_ok: bool = False) -> int:
    try:
        subprocess.run(cmd, check=True)
        return 0
    except subprocess.CalledProcessError as e:
        if fail_ok:
            return e.returncode
        raise

# ----------------------------
# LLM CLIENTS (OpenAI + Gemini via google-genai)
# ----------------------------
openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not openai_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in GitHub Secrets / env.")

openai_client = OpenAI(api_key=openai_key)

gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
gemini_client = None
genai_types = None

if gemini_key:
    try:
        from google import genai as genai_new  # google-genai
        from google.genai import types as genai_types  # google-genai
        gemini_client = genai_new.Client(api_key=gemini_key)
    except Exception:
        gemini_client = None
        genai_types = None

def _gemini_candidate_models() -> List[str]:
    """
    Prefer stable models. You can override with GEMINI_MODEL env var.
    """
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models = []
    if env_model:
        models.append(env_model)
    models += [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3-flash",
    ]
    seen = set()
    out = []
    for m in models:
        if m and m not in seen:
            out.append(m)
            seen.add(m)
    return out

def _extract_json_object(raw: str) -> Optional[dict]:
    """
    Robust JSON extractor: handles code fences or extra text by pulling the first {...} block.
    """
    if not raw:
        return None
    raw = raw.strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    raw2 = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    raw2 = re.sub(r"\s*```$", "", raw2).strip()

    try:
        obj = json.loads(raw2)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    m = re.search(r"(\{.*\})", raw2, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None

def generate_text(prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """
    Gemini primary (optional) + OpenAI fallback.
    Gemini behavior: fail fast on quota/model errors to avoid burning RPM.
    """
    if PRIMARY_LLM == "gemini" and gemini_key and gemini_client and genai_types:
        for model_name in _gemini_candidate_models()[:2]:
            try:
                resp = gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                txt = getattr(resp, "text", None)
                if txt and txt.strip():
                    return txt.strip()
            except Exception as e:
                _safe_print(f"    ⚠️ Gemini failed on {model_name}: {e}. Falling back to OpenAI...")
                break

    resp = openai_client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a top-tier podcast writer. Follow the requested format exactly. "
                    "Do not add headings except segment markers that begin with ###."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content.strip()

# ----------------------------
# NEWS INTEL (RSS)
# ----------------------------
GOOGLE_NEWS_RSS = [
    # Numbers-first feeds (to guarantee $/%/scale)
    (
        "Numbers & Markets",
        "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Nvidia%20OR%20DeepMind%20OR%20Microsoft)%20(billion%20OR%20million%20OR%20%25%20OR%20%24%20OR%20IPO%20OR%20funding%20OR%20revenue%20OR%20valuation)%20when:2d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "AI Money",
        "https://news.google.com/rss/search?q=(AI%20funding%20OR%20valuation%20OR%20IPO%20OR%20Nvidia%20OR%20chips)%20when:2d&hl=en-US&gl=US&ceid=US:en",
    ),

    # Your original buckets (kept)
    (
        "Frontier Models",
        "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20DeepMind)%20(model%20OR%20release%20OR%20launch)%20when:2d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "AI Regulation",
        "https://news.google.com/rss/search?q=(AI%20regulation%20OR%20EU%20AI%20Act%20OR%20FTC%20OR%20copyright)%20when:2d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "AI Security",
        "https://news.google.com/rss/search?q=(AI%20jailbreak%20OR%20prompt%20injection%20OR%20security%20OR%20leak)%20when:2d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "AI in Work",
        "https://news.google.com/rss/search?q=(AI%20jobs%20OR%20automation%20OR%20productivity%20OR%20enterprise)%20when:2d&hl=en-US&gl=US&ceid=US:en",
    ),
]

def _strip_html(s: str) -> str:
    if not s:
        return ""
    soup = BeautifulSoup(s, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt).strip()

def _split_headline_publisher(title: str) -> Tuple[str, str]:
    """
    Google News RSS often formats as: "Headline - Publisher"
    We extract publisher if present.
    """
    if not title:
        return "", ""
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return " - ".join(parts[:-1]).strip(), parts[-1].strip()
    return title.strip(), ""

def _published_iso_from_entry(entry) -> str:
    """
    Prefer parsed publish time if available.
    """
    try:
        tt = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if tt:
            dt = datetime.datetime(*tt[:6], tzinfo=datetime.timezone.utc)
            return dt.isoformat()
    except Exception:
        pass
    try:
        s = (getattr(entry, "published", "") or getattr(entry, "updated", "") or "").strip()
        return s[:64]
    except Exception:
        return ""

def fetch_rss_items(max_per_feed: int = 10) -> List[Dict[str, str]]:
    """
    UPDATED: includes publisher + published timestamps where possible,
    and captures slightly larger summaries to support data extraction.
    """
    items: List[Dict[str, str]] = []
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot; +https://github.com/aisimplify333/Daily-ai-News)"}

    for label, url in GOOGLE_NEWS_RSS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for entry in (feed.entries or [])[:max_per_feed]:
                raw_title = (getattr(entry, "title", "") or "").strip()
                title, publisher = _split_headline_publisher(raw_title)

                link = (getattr(entry, "link", "") or "").strip()
                summary = _strip_html(getattr(entry, "summary", "") or "")[:700]
                published = _published_iso_from_entry(entry)

                if title and link:
                    items.append(
                        {
                            "bucket": label,
                            "title": title,
                            "publisher": publisher,
                            "published": published,
                            "link": link,
                            "summary": summary,
                        }
                    )
        except Exception as e:
            _safe_print(f"    ⚠️ RSS fetch failed ({label}): {e}")

    seen = set()
    deduped = []
    for x in items:
        key = re.sub(r"\s+", " ", (x.get("title") or "").lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(x)
    return deduped

def _safe_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""

@lru_cache(maxsize=128)
def _resolve_final_url(url: str) -> str:
    """
    Google News often redirects. We try to follow redirects cheaply.
    """
    if not url:
        return url
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    try:
        r = requests.get(url, headers=headers, timeout=12, allow_redirects=True, stream=True)
        r.close()
        return r.url or url
    except Exception:
        return url

@lru_cache(maxsize=128)
def fetch_url_preview(url: str, max_chars: int = 3800) -> str:
    """
    Stronger preview scrape to pull explicit numbers:
    - meta description
    - first paragraphs
    - list items (often where $/% figures are)
    - headings (sometimes contain numeric claims)
    """
    if not url:
        return ""
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    try:
        final_url = _resolve_final_url(url)
        r = requests.get(final_url, headers=headers, timeout=18)
        r.raise_for_status()
        html = r.text or ""
        soup = BeautifulSoup(html, "html.parser")

        for t in soup(["script", "style", "noscript"]):
            t.decompose()

        meta_desc = ""
        for key in [("name", "description"), ("property", "og:description"), ("name", "twitter:description")]:
            tag = soup.find("meta", attrs={key[0]: key[1]})
            if tag and tag.get("content"):
                meta_desc = (tag.get("content") or "").strip()
                if meta_desc:
                    break

        base = soup.find("article") or soup.body or soup

        chunks = []
        if meta_desc:
            chunks.append(meta_desc)

        # Headings (often include “$X”, “Y%”, “Q1 2026”, etc.)
        for h in base.find_all(["h1", "h2", "h3"]):
            txt = h.get_text(" ", strip=True)
            if txt and 20 <= len(txt) <= 180:
                chunks.append(txt)
            if len(chunks) >= 10:
                break

        # Paragraphs
        paras = []
        for p in base.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if txt and len(txt) > 40:
                paras.append(txt)
            if len(paras) >= 10:
                break
        chunks.extend(paras)

        # List items (frequently contain numeric bullet facts)
        lis = []
        for li in base.find_all("li"):
            txt = li.get_text(" ", strip=True)
            if txt and 20 <= len(txt) <= 200:
                if NUMERIC_TOKEN_RE.search(txt) or MONEY_RE.search(txt):
                    lis.append(txt)
            if len(lis) >= 10:
                break
        chunks.extend(lis)

        preview = " ".join(chunks)
        preview = re.sub(r"\s+", " ", preview).strip()
        return preview[:max_chars]
    except Exception:
        return ""

# ----------------------------
# SPONSORS / STORIES
# ----------------------------
def load_sponsors() -> List[Dict[str, str]]:
    if SPONSORS_PATH.exists():
        try:
            data = json.loads(SPONSORS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "sponsors" in data and isinstance(data["sponsors"], list):
                return data["sponsors"]
        except Exception:
            pass
    return [
        {"name": "Sponsor One", "tagline": "Run faster. Think clearer.", "cta": "Link in show notes."},
        {"name": "Sponsor Two", "tagline": "Your edge, automated.", "cta": "Try it free today."},
        {"name": "Sponsor Three", "tagline": "Ship smarter.", "cta": "Join the waitlist."},
    ]

def _fallback_data_points(text: str, max_items: int = 5) -> List[str]:
    """
    Extract explicit numeric/date-like snippets from text as a weak fallback.
    """
    if not text:
        return []
    sents = re.split(r"(?<=[.!?])\s+", text)
    hits = []
    for s in sents:
        if re.search(r"(\d|%|\$|€|£|billion|million|bn|m)\b", s, flags=re.IGNORECASE):
            hits.append(s.strip())
        if len(hits) >= max_items:
            break
    out = []
    for h in hits:
        h2 = h[:140].strip()
        if h2 and h2 not in out:
            out.append(h2)
    return out[:max_items]

def enrich_stories_with_data(stories: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Enrichment pass:
    - Extract explicit numeric bullets from RSS + preview
    - Forbid invented numbers
    - If model output is weak, deterministic numeric sentence extraction kicks in
    """
    enriched: List[Dict[str, str]] = []
    for s in stories:
        url = (s.get("source_url") or "").strip()
        rss_summary = (s.get("rss_summary") or "").strip()
        publisher = (s.get("publisher") or "").strip()
        published = (s.get("published") or "").strip()
        preview = fetch_url_preview(url, max_chars=3800)

        prompt = f"""
You are extracting HARD FACTS for a daily AI news podcast. Do NOT invent numbers.
Only use numbers/dates/amounts that appear in the provided snippets.

Return ONLY valid JSON (no markdown):
{{
  "why_shocking": "1-2 sentences, urgent, grounded in snippet facts",
  "data_points": ["3-6 bullets. Each bullet MUST include at least one explicit number/date/amount from snippets. If truly none exist, write: 'No explicit figures in snippet.'"],
  "key_entities": ["2-8 proper nouns from snippets"]
}}

Publisher: {publisher}
Published: {published}
URL: {url}

RSS Summary:
{rss_summary}

Article Preview:
{preview}
""".strip()

        raw = generate_text(prompt, temperature=0.20, max_tokens=900)
        j = _extract_json_object(raw) or {}

        dp = j.get("data_points") if isinstance(j.get("data_points"), list) else []
        dp = [str(x).strip() for x in dp if str(x).strip()][:8]

        # If model dp is weak, extract numeric sentences deterministically from preview+summary
        strong_dp = [b for b in dp if NUMERIC_TOKEN_RE.search(b)]
        if len(strong_dp) < MIN_NUMERIC_BULLETS_PER_STORY:
            extracted = _extract_numeric_sentences((rss_summary + " " + preview).strip(), max_items=8)
            dp = (strong_dp + extracted)[:6]

        if not dp:
            dp = ["No explicit figures in snippet."]

        why = (j.get("why_shocking") or s.get("why_shocking") or "").strip()
        if not why:
            why = (rss_summary[:240] or "High-stakes implications—details evolving.").strip()

        s2 = dict(s)
        s2["why_shocking"] = why
        s2["data_points"] = dp[:6]
        s2["key_entities"] = j.get("key_entities") if isinstance(j.get("key_entities"), list) else []
        enriched.append(s2)

    return enriched

def pick_top_stories(intel_items: List[Dict[str, str]], n: int = 5) -> List[Dict[str, str]]:
    """
    Numbers-first selection:
    1) Rank candidates by numeric_score(summary+title)
    2) Ask model to pick top n (still)
    3) Enrich and then enforce a numeric minimum; if weak, fall back to top numeric candidates
    """
    if not intel_items:
        return []

    ranked = sorted(
        intel_items,
        key=lambda x: _numeric_score((x.get("title","") or "") + " " + (x.get("summary","") or "")),
        reverse=True,
    )

    # Give the model the best 40 candidates (dense with numeric tokens)
    candidates = ranked[:40]
    intel_compact = "\n".join(
        [
            f"- [{x.get('bucket','')}] {x.get('title','')} | {x.get('publisher','')} | {x.get('published','')} | {x.get('summary','')} | {x.get('link','')}"
            for x in candidates
        ]
    )

    prompt = f"""
Select the TOP {n} stories for a daily AI show that must feel urgent, emotional, and high-stakes.

Return ONLY valid JSON (no markdown), schema:
{{
  "stories": [
    {{
      "headline": "...",
      "why_shocking": "1-2 sentences grounded in snippet facts",
      "data_points": ["3-6 bullets. Each bullet MUST include an explicit number/date/amount from the candidate line if present; if not present write 'Needs enrichment'"],
      "angles": {{
        "alex": "...",
        "jamie": "...",
        "rufus": "..."
      }},
      "source_url": "...",
      "publisher": "...",
      "published": "..."
    }}
  ]
}}

Candidate items:
{intel_compact}
""".strip()

    raw = generate_text(prompt, temperature=0.20, max_tokens=JSON_MAX_TOKENS)
    j = _extract_json_object(raw)

    stories: List[Dict[str, str]] = []
    if j and isinstance(j.get("stories"), list):
        for s in j["stories"][:n]:
            if not isinstance(s, dict):
                continue
            angles = s.get("angles") if isinstance(s.get("angles"), dict) else {}
            dp = s.get("data_points") if isinstance(s.get("data_points"), list) else []

            st = {
                "headline": (s.get("headline") or "").strip(),
                "why_shocking": (s.get("why_shocking") or "").strip(),
                "data_points": [str(x).strip() for x in dp if str(x).strip()][:6],
                "angles": {
                    "alex": (angles.get("alex") or "").strip(),
                    "jamie": (angles.get("jamie") or "").strip(),
                    "rufus": (angles.get("rufus") or "").strip(),
                },
                "source_url": (s.get("source_url") or "").strip(),
                "publisher": (s.get("publisher") or "").strip(),
                "published": (s.get("published") or "").strip(),
            }
            if st["headline"] and st["source_url"]:
                stories.append(st)

    # If model fails, fallback to top numeric candidates directly
    if len(stories) < n:
        stories = []
        for x in candidates[:n]:
            stories.append({
                "headline": x.get("title",""),
                "why_shocking": x.get("summary",""),
                "data_points": _extract_numeric_sentences((x.get("summary","") or ""), max_items=4) or ["Needs enrichment"],
                "angles": {"alex": "", "jamie": "", "rufus": ""},
                "source_url": x.get("link",""),
                "publisher": x.get("publisher",""),
                "published": x.get("published",""),
                "rss_summary": x.get("summary",""),
            })

    # Attach RSS summaries for enrichment
    for st in stories:
        match = next((x for x in intel_items if (x.get("link") or "").strip() == st["source_url"]), None)
        if match:
            st["rss_summary"] = (match.get("summary") or "").strip()
            st["publisher"] = st["publisher"] or (match.get("publisher") or "").strip()
            st["published"] = st["published"] or (match.get("published") or "").strip()
        else:
            st["rss_summary"] = st.get("rss_summary","") or ""

    enriched = enrich_stories_with_data(stories[:n])

    # Numeric enforcement: ensure each story has >= MIN_NUMERIC_BULLETS_PER_STORY bullets with digits/$/%
    def numeric_bullets(dp: list[str]) -> int:
        return sum(1 for b in (dp or []) if NUMERIC_TOKEN_RE.search(b or ""))

    weak = [s for s in enriched if numeric_bullets(s.get("data_points") or []) < MIN_NUMERIC_BULLETS_PER_STORY]

    if weak:
        # Hard fallback: take top numeric candidates and enrich them
        fallback = []
        for x in candidates:
            fb = {
                "headline": x.get("title",""),
                "why_shocking": x.get("summary",""),
                "data_points": _extract_numeric_sentences((x.get("summary","") or ""), max_items=6) or ["Needs enrichment"],
                "angles": {"alex": "", "jamie": "", "rufus": ""},
                "source_url": x.get("link",""),
                "publisher": x.get("publisher",""),
                "published": x.get("published",""),
                "rss_summary": x.get("summary",""),
            }
            fallback.append(fb)
            if len(fallback) >= n:
                break

        enriched = enrich_stories_with_data(fallback[:n])

    return enriched[:n]

# ----------------------------
# SCRIPTING (SOUL + GUARANTEED LENGTH + DATA RICHNESS)
# ----------------------------
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)

def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))

def estimate_minutes_from_text(script: str) -> float:
    return _word_count(script) / max(1.0, WORDS_PER_MINUTE)

def _script_targets() -> Tuple[int, int, int]:
    """
    Returns (min_words, target_words, max_words)
    Buffers help real TTS land inside MIN/MAX.
    """
    min_words = int(MIN_MINUTES * WORDS_PER_MINUTE * 1.02)
    target_words = int(TARGET_MINUTES * WORDS_PER_MINUTE * 1.00)
    max_words = int(MAX_MINUTES * WORDS_PER_MINUTE * 1.10)
    return min_words, target_words, max_words

def _segment_word_targets() -> List[int]:
    """
    Allocate total across 5 segments while preserving your show structure and pacing.
    """
    min_words, _, max_words = _script_targets()

    seg = [650, 1200, 900, 1400, 650]  # total 4800

    total = sum(seg)
    if total > max_words:
        scale = max_words / float(total)
        seg = [max(450, int(x * scale)) for x in seg]

    if sum(seg) < min_words:
        deficit = min_words - sum(seg)
        seg[3] += deficit  # expand Segment 4 first

    return seg

def _segment_header(i: int) -> str:
    return f"### SEGMENT {i}"

def _story_block(stories: List[Dict[str, str]]) -> str:
    """
    UPDATED: includes publisher/published + data_points so the model can cite explicit figures on-air.
    """
    out = []
    for i, s in enumerate(stories[:5]):
        dp = s.get("data_points") if isinstance(s.get("data_points"), list) else []
        dp_txt = "; ".join([str(x).strip() for x in dp if str(x).strip()][:6])
        pub = (s.get("publisher") or "").strip()
        pdate = (s.get("published") or "").strip()
        why = (s.get("why_shocking") or "").strip()
        url = (s.get("source_url") or "").strip()

        out.append(
            f"{i+1}. {s.get('headline','')}\n"
            f"   Publisher: {pub}\n"
            f"   Published: {pdate}\n"
            f"   Why it matters: {why}\n"
            f"   Data points: {dp_txt}\n"
            f"   Source: {url}"
        )
    return "\n".join(out).strip()

def _strict_dialogue_rules() -> str:
    return (
        'HARD FORMAT RULES (non-negotiable):\n'
        '- Output MUST be dialogue lines only using EXACT labels: "ALEX:", "JAMIE:", "RUFUS:"\n'
        '- Every spoken line MUST start with one of those labels. No unlabeled narration.\n'
        '- Keep lines SHORT: 1–2 sentences per line. Prefer one thought per line.\n'
        '- Segment markers are allowed as lines starting with "###" and will NOT be spoken.\n'
        '- "[MUSIC]" may appear as a standalone line.\n'
        '- Do not add any other headings, bullets, or markdown.\n'
    )

def _segment_assignment(seg_num: int, stories: List[Dict[str, str]]) -> str:
    if len(stories) < 5:
        return "Use the available stories. Keep it urgent, emotional, and high-stakes."

    s1, s2, s3, s4, s5 = stories[0], stories[1], stories[2], stories[3], stories[4]

    if seg_num == 1:
        return (
            "Cold open hook: start mid-argument (overheated). Then [MUSIC]. "
            "Then Alex welcomes and fires off today's 5-story lineup in rapid summary. "
            "Make it feel raw and messy, with interruptions."
        )
    if seg_num == 2:
        return (
            f"Studio segment: ONLY Alex + Jamie (no Rufus at all). High chemistry, fast pacing. "
            f"Deep dive Story 1 + Story 2 with human stakes and emotional pushback.\n"
            f"(1) {s1['headline']}\n"
            f"(2) {s2['headline']}"
        )
    if seg_num == 3:
        return (
            f"On-location: Alex throws to Rufus, then Rufus dominates with money/reg angle. "
            f"Primary focus Story 3 with filings/trading/regulatory edge.\n"
            f"(3) {s3['headline']}"
        )
    if seg_num == 4:
        return (
            f"All three together: dread/greed forecast + lightning round. "
            f"Cover Story 4 + Story 5, and callback earlier claims. Interruptions and analogies.\n"
            f"(4) {s4['headline']}\n"
            f"(5) {s5['headline']}"
        )
    return (
        "Closing: Alex closes hard, Jamie lands one empathetic gut-punch, "
        "Rufus delivers one cynical prophecy. Keep it tight and memorable."
    )

def _segment_prompt(
    seg_num: int,
    seg_words_min: int,
    seg_words_target: int,
    date_str: str,
    stories: List[Dict[str, str]],
    sponsors: List[Dict[str, str]],
) -> str:
    sponsor_1 = sponsors[0] if len(sponsors) > 0 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_2 = sponsors[1] if len(sponsors) > 1 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_3 = sponsors[2] if len(sponsors) > 2 else {"name": "Sponsor", "tagline": "", "cta": ""}

    extra = ""
    if seg_num == 1:
        extra = 'Start mid-argument (hook). Then a standalone line: [MUSIC]. Then welcome + lineup.'
    elif seg_num == 2:
        extra = "IMPORTANT: This segment must contain ONLY ALEX and JAMIE lines. Do NOT output any RUFUS lines."
    elif seg_num == 3:
        extra = (
            "Rufus must seamlessly embed a 'native ad' as insider advice:\n"
            f"Sponsor: {sponsor_1['name']}\n"
            f"Tagline: {sponsor_1.get('tagline','')}\n"
            f"CTA: {sponsor_1.get('cta','')}\n"
            "Do it in-character—no 'this episode is sponsored by' stiffness."
        )
    elif seg_num == 4:
        extra = (
            "Include ONE woven-in host-read sponsor naturally during the chaos:\n"
            f"Sponsor: {sponsor_2['name']} | {sponsor_2.get('tagline','')} | {sponsor_2.get('cta','')}"
        )
    elif seg_num == 5:
        extra = (
            "End with a final micro sponsor tag as a joke/aside (in-character):\n"
            f"Sponsor: {sponsor_3['name']} | {sponsor_3.get('tagline','')} | {sponsor_3.get('cta','')}"
        )

    story_block = _story_block(stories)
    assignment = _segment_assignment(seg_num, stories)

    return f"""
You are writing a DAILY podcast episode called "The AI Edge" for {date_str}.
This is ONLY {_segment_header(seg_num)} of the episode.

It must feel like a raw, overheated conversation between THREE distinct personalities.
NO corporate speak. They interrupt, argue, laugh, get angry, get quiet, then spike again.

PERSONAS (distinct voice is mandatory):
- ALEX (Host): Rogan energy + frantic curiosity. Drives pace. Calls out BS. Summarizes fast.
- JAMIE (Co-host): Bartlett vibe. Vulnerable, empathetic, human stakes. Pushes back emotionally.
- RUFUS (Analyst): cynical, money/regulatory edge. Cold, sharp. Sounds like filings + trades.

{_strict_dialogue_rules()}

SEGMENT REQUIREMENTS:
- The FIRST line MUST be exactly: "{_segment_header(seg_num)}"
- Segment length MUST be at least {seg_words_min} words (target ~{seg_words_target} words).
- Make the “soul” real: fear, awe, greed, betrayal, humor, sudden silence.
- Use concrete examples, “what this means tomorrow”, and specific stakes (jobs, markets, power, safety).
- Avoid filler openers like “let’s dive in”.

DATA REQUIREMENTS (non-negotiable):
- This show is data-rich. For every story you discuss in THIS segment, you MUST speak at least 2 explicit data points
  (numbers/dates/amounts) from the provided "Data points" lines in TODAY'S STORIES.
- Mention the publisher at least once when introducing a story (e.g., "Bloomberg says..." / "The Verge reports...").
- Do NOT invent numbers. If a story has "No explicit figures in snippet", say that plainly and focus on consequences.

WHAT THIS SEGMENT MUST DO:
{assignment}

SPECIAL INSTRUCTIONS FOR THIS SEGMENT:
{extra}

TODAY'S STORIES (must be clearly discussed across the full episode; reference as needed here):
{story_block}

NOW OUTPUT ONLY THIS SEGMENT.
""".strip()

def _segment_validate(seg_text: str, seg_num: int, seg_words_min: int) -> List[str]:
    issues: List[str] = []
    if not seg_text.strip().startswith(_segment_header(seg_num)):
        issues.append(f"Segment {seg_num} missing required first line '{_segment_header(seg_num)}'.")

    # label validation
    for ln in seg_text.splitlines():
        line = ln.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            continue
        if not SPEAKER_RE.match(line):
            issues.append("Found non-labeled spoken line(s).")
            break

    wc = _word_count(seg_text)
    if wc < seg_words_min:
        issues.append(f"Segment too short ({wc} words). Minimum is {seg_words_min}.")

    # Cold open enforcement: Segment 1 needs real dialogue before [MUSIC]
    if seg_num == 1:
        lines = [l.strip() for l in seg_text.splitlines() if l.strip()]
        try:
            music_idx = next(i for i, l in enumerate(lines) if l.upper() == "[MUSIC]")
        except StopIteration:
            issues.append("Segment 1 missing required [MUSIC] marker.")
            music_idx = None

        if music_idx is not None:
            pre_music_dialogue = [l for l in lines[1:music_idx] if SPEAKER_RE.match(l)]
            if len(pre_music_dialogue) < MIN_COLD_OPEN_LINES:
                issues.append(
                    f"Cold open too short before [MUSIC] ({len(pre_music_dialogue)} lines). Minimum is {MIN_COLD_OPEN_LINES}."
                )

    # Numeric density enforcement (drama/data)
    if _digit_count(seg_text) < MIN_DIGITS_PER_SEGMENT:
        issues.append(
            f"Low numeric density in segment (digits={_digit_count(seg_text)}). Minimum is {MIN_DIGITS_PER_SEGMENT}."
        )

    return issues

def _segment_repair_prompt(seg_num: int, seg_words_min: int, seg_words_target: int, issues: List[str], seg_text: str) -> str:
    return f"""
You are repairing ONLY {_segment_header(seg_num)} for "The AI Edge".

CURRENT ISSUES (fix all):
{chr(10).join([f"- {x}" for x in issues])}

NON-NEGOTIABLE:
- First line MUST be exactly "{_segment_header(seg_num)}"
- Output MUST be dialogue lines only with EXACT labels: ALEX:, JAMIE:, RUFUS:
- Every spoken line MUST start with one of those labels (no unlabeled lines).
- Add MORE back-and-forth to increase length; do NOT compress.
- Keep lines SHORT (1–2 sentences) to increase turn count and chemistry.
- Segment length MUST be at least {seg_words_min} words (target ~{seg_words_target}).

HERE IS THE SEGMENT TO EXPAND/REPAIR (keep good parts, add more lines):
{seg_text}
""".strip()

def _generate_segment(
    seg_num: int,
    seg_words_min: int,
    seg_words_target: int,
    date_str: str,
    stories: List[Dict[str, str]],
    sponsors: List[Dict[str, str]],
) -> str:
    prompt = _segment_prompt(seg_num, seg_words_min, seg_words_target, date_str, stories, sponsors)

    seg_text = ""
    for attempt in range(1, SEGMENT_ATTEMPTS + 1):
        seg_text = generate_text(prompt, temperature=0.75, max_tokens=2600)
        wc = _word_count(seg_text)
        issues = _segment_validate(seg_text, seg_num, seg_words_min)

        _safe_print(f"    ✍️ Segment {seg_num} attempt {attempt}/{SEGMENT_ATTEMPTS} (min {seg_words_min}): {wc} words")

        if not issues:
            return seg_text.strip()

        prompt = _segment_repair_prompt(seg_num, seg_words_min, seg_words_target, issues, seg_text)

    return seg_text.strip()

def _sanitize_dialogue_only(text: str) -> str:
    """
    Ensures every non-marker/non-[MUSIC] line is labeled dialogue.
    Unlabeled lines become continuation of last speaker (if any).
    """
    if not text:
        return ""
    out: List[str] = []
    last_speaker: Optional[str] = None

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("###"):
            out.append(line)
            last_speaker = None
            continue
        if line.upper() == "[MUSIC]":
            out.append("[MUSIC]")
            last_speaker = None
            continue

        m = SPEAKER_RE.match(line)
        if m:
            spk = m.group(1).upper()
            txt = m.group(2).strip()
            if txt:
                out.append(f"{spk}: {txt}")
                last_speaker = spk
            continue

        if last_speaker:
            out.append(f"{last_speaker}: {line}")

    return "\n".join(out).strip()

def _trim_script_to_max_words(script: str, max_words: int) -> str:
    """
    Deterministic trim: remove dialogue lines from SEGMENT 4 first.
    """
    if _word_count(script) <= max_words:
        return script

    parts: Dict[int, List[str]] = {}
    cur = 0
    for ln in script.splitlines():
        m = re.match(r"^###\s*SEGMENT\s*(\d)\b", ln.strip(), flags=re.IGNORECASE)
        if m:
            cur = int(m.group(1))
            parts[cur] = [ln.strip()]
            continue
        if cur:
            parts.setdefault(cur, []).append(ln.strip())

    def rebuild() -> str:
        return "\n".join(["\n".join(parts[i]) for i in sorted(parts.keys()) if i in parts]).strip()

    if 4 in parts:
        lines = parts[4]
        idxs = [i for i, l in enumerate(lines) if SPEAKER_RE.match(l)]
        protected = set(idxs[:10] + idxs[-10:])
        removable = [i for i in idxs if i not in protected]

        mid = len(removable) // 2
        order = removable[mid:] + removable[:mid][::-1]

        for i in order:
            if _word_count(rebuild()) <= max_words:
                break
            lines[i] = ""

        parts[4] = [l for l in lines if l]

    trimmed = rebuild()

    while _word_count(trimmed) > max_words:
        tl = trimmed.splitlines()
        removed = False
        for k in range(len(tl) - 1, 0, -1):
            if SPEAKER_RE.match(tl[k].strip()):
                del tl[k]
                removed = True
                break
        trimmed = "\n".join(tl).strip()
        if not removed or len(tl) < 80:
            break

    return trimmed

def _pad_script_to_min_words(script: str, min_words: int, stories, sponsors, date_str: str) -> str:
    """
    If short, insert an add-on block into SEGMENT 4 (best place to expand) without rewriting everything.
    """
    wc = _word_count(script)
    if wc >= min_words:
        return script

    need = min_words - wc
    add_words = min(900, max(260, need + 160))

    m = re.search(r"^###\s*SEGMENT\s*5\b", script, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return script

    story_block = _story_block(stories)

    prompt = f"""
Write an ADD-ON block to extend SEGMENT 4 of "The AI Edge" ({date_str}).

RULES:
- Output ONLY dialogue lines labeled ALEX:, JAMIE:, RUFUS:
- NO segment markers in your output.
- Add ~{add_words} words (do NOT go under {int(add_words*0.85)}).
- MUST include at least 6 explicit data points (numbers/dates/amounts) from the story block below.
- Keep the show vibe: fast banter, interruptions, dread/greed forecasting.

STORY BLOCK (use the data_points explicitly):
{story_block}
""".strip()

    addon = generate_text(prompt, temperature=0.65, max_tokens=1800)
    addon = _sanitize_dialogue_only(addon)

    insert_at = m.start()
    return (script[:insert_at].rstrip() + "\n" + addon.strip() + "\n\n" + script[insert_at:].lstrip()).strip()

def _data_richness_warning(script: str):
    digits = len(re.findall(r"\d", script or ""))
    if digits < 25:
        _safe_print(f"    ⚠️ DATA-RICHNESS WARNING: low numeric density (digits={digits}). Consider increasing previews/max_per_feed.")

def validate_script(script: str) -> List[str]:
    issues: List[str] = []

    for i in range(1, 6):
        if not re.search(rf"^###\s*SEGMENT\s*{i}\b", script, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(f"Missing segment marker: ### SEGMENT {i}")

    for ln in script.splitlines():
        line = ln.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            continue
        if not SPEAKER_RE.match(line):
            issues.append("Found non-labeled spoken line(s).")
            break

    for name in ("ALEX", "JAMIE", "RUFUS"):
        if not re.search(rf"^{name}\s*:", script, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(f"Speaker missing: {name}")

    min_words, _, max_words = _script_targets()
    wc = _word_count(script)
    if wc < min_words:
        issues.append(f"Script too short ({wc} words). Minimum is {min_words}.")
    if wc > max_words:
        issues.append(f"Script too long ({wc} words). Maximum is {max_words}.")

    turns = sum(1 for line in script.splitlines() if SPEAKER_RE.match(line.strip()))
    min_turns = max(90, wc // 45)
    if turns < min_turns:
        issues.append(f"Too few labeled dialogue lines ({turns}). Minimum is {min_turns} for {wc} words.")

    if re.search(r"```|<html|<body|^Title:|^Podcast:", script, flags=re.IGNORECASE | re.MULTILINE):
        issues.append("Contains non-dialogue formatting blocks.")

    return issues

def generate_episode_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], date_str: str) -> str:
    """
    UPDATED: segmented generation + sanitize + deterministic trim/pad.
    Removes the risky full-script rewrite loop that caused marker loss / massive shortening.
    """
    seg_targets = _segment_word_targets()
    seg_mins = [max(420, int(t * 0.92)) for t in seg_targets]

    _safe_print(" >> ✍️ WRITING FULL EPISODE (SEGMENTED)...")
    segments: List[str] = []
    for i in range(1, 6):
        seg = _generate_segment(
            seg_num=i,
            seg_words_min=seg_mins[i - 1],
            seg_words_target=seg_targets[i - 1],
            date_str=date_str,
            stories=stories,
            sponsors=sponsors,
        )
        seg = _sanitize_dialogue_only(seg)
        segments.append(seg)

    script = "\n\n".join(segments).strip()
    script = _sanitize_dialogue_only(script)

    min_words, _, max_words = _script_targets()

    if _word_count(script) > max_words:
        script = _trim_script_to_max_words(script, max_words=max_words)
    if _word_count(script) < min_words:
        script = _pad_script_to_min_words(script, min_words=min_words, stories=stories, sponsors=sponsors, date_str=date_str)

    script = _sanitize_dialogue_only(script)

    wc = _word_count(script)
    mins = estimate_minutes_from_text(script)
    _safe_print(f"    ✅ Full script check: ~{mins:.1f} min ({wc} words)")
    _data_richness_warning(script)

    issues = validate_script(script)
    if issues:
        raise RuntimeError("Final script validation failed:\n" + "\n".join(issues))
    return script

# ----------------------------
# DIALOGUE PARSING (ROBUST)
# ----------------------------
def iter_dialogue(script: str) -> List[Tuple[str, str]]:
    """
    Parses:
    - ALEX: ...
    - JAMIE: ...
    - RUFUS: ...
    Supports continuation lines by appending them to the current speaker.
    """
    out: List[Tuple[str, str]] = []
    current_speaker: Optional[str] = None
    buf: List[str] = []

    def flush():
        nonlocal current_speaker, buf
        if current_speaker and buf:
            out.append((current_speaker, " ".join(buf).strip()))
        current_speaker = None
        buf = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("###"):
            flush()
            continue

        if line.upper() == "[MUSIC]":
            flush()
            out.append(("MUSIC", "[MUSIC]"))
            continue

        m = SPEAKER_RE.match(line)
        if m:
            flush()
            current_speaker = m.group(1).upper()
            buf = [m.group(2).strip()]
            continue

        if current_speaker:
            buf.append(line)

    flush()
    return out

def merge_dialogue_for_tts(dialogue: List[Tuple[str, str]], max_chars: int = 2400) -> List[Tuple[str, str]]:
    """
    Reduce the number of TTS calls by merging adjacent turns from the same speaker,
    up to max_chars. Preserves MUSIC markers.
    """
    merged: List[Tuple[str, str]] = []
    cur_spk: Optional[str] = None
    cur_txt: List[str] = []

    def flush():
        nonlocal cur_spk, cur_txt
        if cur_spk and cur_txt:
            merged.append((cur_spk, "\n".join(cur_txt).strip()))
        cur_spk = None
        cur_txt = []

    for spk, txt in dialogue:
        if spk == "MUSIC":
            flush()
            merged.append(("MUSIC", "[MUSIC]"))
            continue

        if cur_spk is None:
            cur_spk = spk
            cur_txt = [txt]
            continue

        if spk != cur_spk:
            flush()
            cur_spk = spk
            cur_txt = [txt]
            continue

        candidate = ("\n".join(cur_txt) + "\n" + txt).strip()
        if len(candidate) <= max_chars:
            cur_txt.append(txt)
        else:
            flush()
            cur_spk = spk
            cur_txt = [txt]

    flush()
    return merged

# ----------------------------
# TTS + STITCHING
# ----------------------------
def chunk_text(s: str, max_chars: int = 2800) -> List[str]:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_chars:
        return [s]
    chunks: List[str] = []
    while len(s) > max_chars:
        cut = s.rfind(". ", 0, max_chars)
        if cut < 600:
            cut = max_chars
        chunks.append(s[:cut].strip())
        s = s[cut:].strip()
    if s:
        chunks.append(s)
    return chunks

def tts_to_file(text: str, voice: str, out_path: Path):
    last_err = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            with openai_client.audio.speech.with_streaming_response.create(
                model=OPENAI_TTS_MODEL,
                voice=voice,
                input=text,
            ) as resp:
                resp.stream_to_file(str(out_path))
            return
        except Exception as e:
            last_err = e
            sleep_s = min(10, 1.5 * attempt)
            _safe_print(f"    ⚠️ TTS failed (attempt {attempt}/{TTS_RETRIES}): {e} — retrying in {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"TTS failed after {TTS_RETRIES} retries: {last_err}")

def stitch_with_ffmpeg(file_list: List[Path], out_path: Path):
    """
    Optional. MP3 concat can cause DTS warnings depending on segment encoding.
    Kept as fallback. Default stitching is pydub (below).
    """
    concat_txt = out_path.parent / f"concat_{uuid.uuid4().hex}.txt"
    concat_txt.write_text("\n".join([f"file '{p.as_posix()}'" for p in file_list]), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-af", "aresample=async=1:first_pts=0",
        "-avoid_negative_ts", "make_zero",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)

    try:
        concat_txt.unlink()
    except Exception:
        pass

def stitch_with_pydub(file_list: List[Path], out_path: Path):
    """
    Recommended: decode each segment and export once.
    Avoids FFmpeg non-monotonic DTS issues from MP3 concat.
    """
    combined = AudioSegment.empty()
    for p in file_list:
        combined += AudioSegment.from_file(p)
    combined.export(out_path, format="mp3", bitrate="192k")

def stitch_audio(file_list: List[Path], out_path: Path):
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found in runner (required by pydub/ffmpeg).")

    if STITCH_METHOD == "ffmpeg":
        stitch_with_ffmpeg(file_list, out_path)
    else:
        stitch_with_pydub(file_list, out_path)

# ----------------------------
# MARKETING PIPELINE
# ----------------------------
def run_marketing_pipeline():
    if not RUN_MARKETING_ASSETS:
        _safe_print(" >> 📣 MARKETING: disabled (RUN_MARKETING_ASSETS=false)")
        return

    _safe_print(" >> 📣 MARKETING: generating assets...")
    for script_name in ["marketing_engine.py", "generate_social.py", "animate_social.py"]:
        p = BASE_DIR / script_name
        if p.exists():
            _safe_print(f"    → running {script_name}")
            _run([sys.executable, str(p)], fail_ok=True)

    if PUBLISH_SOCIAL:
        pub = BASE_DIR / "social_publisher.py"
        if pub.exists():
            _safe_print("    → publishing social (PUBLISH_SOCIAL=true)")
            _run([sys.executable, str(pub)], fail_ok=True)

def generate_marketing_pack(stories: List[Dict[str, str]], date_str: str, listen_url: str) -> Dict[str, str]:
    story_lines = "\n".join([f"- {s.get('headline','')} | {s.get('source_url','')}" for s in stories[:5]])

    prompt = f"""
You are a direct-response growth writer for a DAILY AI show called "The AI Edge".
Goal: drive a click TODAY.

Return ONLY valid JSON (no markdown). Schema:
{{
  "hook": "6-10 words, STOP-SCROLL, no date, no quotes, <= 64 chars",
  "card_subhook": "one short teaser line (<= 52 chars)",
  "tweet1": "Tweet 1 text (<= 260 chars). Must work with a video attached. Include a question.",
  "tweet2": "Tweet 2 text (<= 260 chars). Must include this exact link: {listen_url}",
  "yt_title": "YouTube title (<= 90 chars)",
  "yt_description": "YouTube description (<= 1200 chars) including {listen_url}",
  "hashtags": "#AI #TechNews #OpenAI #Nvidia (keep <= 6 tags)"
}}

Today: {date_str}
Top stories:
{story_lines}

Rules:
- No corporate speak.
- Hook must be specific and urgent.
- Avoid repeating the date in hook/title.
""".strip()

    raw = generate_text(prompt, temperature=0.45, max_tokens=900)
    j = _extract_json_object(raw)

    fallback_hook = (stories[0].get("headline") if stories else "AI JUST MOVED — HERE’S WHAT CHANGED")[:64]
    out = {
        "hook": fallback_hook.upper(),
        "card_subhook": "WHAT BREAKS NEXT?",
        "tweet1": f"{fallback_hook}\n\nWhat’s the real consequence here?",
        "tweet2": f"Full episode: {listen_url}\n\n#AI #TechNews",
        "yt_title": f"{fallback_hook} | The AI Edge",
        "yt_description": f"Listen on Spotify: {listen_url}\n\nTop stories:\n"
        + "\n".join([f"- {s.get('headline','')}" for s in stories[:5]]),
        "hashtags": "#AI #TechNews #OpenAI #Nvidia",
    }

    try:
        if j:
            for k in out.keys():
                if isinstance(j.get(k), str) and j[k].strip():
                    out[k] = j[k].strip()

        out["hook"] = out["hook"][:64].upper()
        out["card_subhook"] = out["card_subhook"][:52]
        out["tweet1"] = out["tweet1"][:260]
        out["tweet2"] = out["tweet2"][:260]
        out["yt_title"] = out["yt_title"][:90]
        out["yt_description"] = out["yt_description"][:1200]
        return out
    except Exception:
        return out

# ----------------------------
# RSS FEED WRITER (robust)
# ----------------------------
def update_feed_xml(meta: Dict):
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ATOM_NS = "http://www.w3.org/2005/Atom"

    # Register prefixes ONCE; never manually set xmlns:itunes on root
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("atom", ATOM_NS)

    def rfc2822_from_date(datestr: str) -> str:
        try:
            dt = datetime.datetime.strptime(datestr, "%Y-%m-%d")
            dt = dt.replace(hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc)
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

    def rfc2822_now() -> str:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

    def is_valid_episode_filename(name: str) -> bool:
        return bool(STRICT_EPISODE_FILENAME_RE.match(name or ""))

    def safe_url_join(base: str, filename: str) -> str:
        # Avoid spaces/() issues by encoding the filename portion
        return base.rstrip("/") + "/" + quote(filename)

    def make_item(title: str, description: str, audio_filename: str, pubdate_rfc2822: str, duration_seconds: int = 0) -> ET.Element:
        item = ET.Element("item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "description").text = (description or "")[:8000]

        audio_url = safe_url_join(AUDIO_BASE_URL, audio_filename)

        guid_el = ET.SubElement(item, "guid")
        guid_el.set("isPermaLink", "false")
        guid_el.text = audio_url

        ET.SubElement(item, "pubDate").text = pubdate_rfc2822

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", audio_url)
        enclosure.set("type", "audio/mpeg")

        try:
            length_bytes = int((AUDIO_DIR / audio_filename).stat().st_size)
        except Exception:
            length_bytes = 0
        enclosure.set("length", str(length_bytes))

        if duration_seconds and duration_seconds > 0:
            dur = ET.SubElement(item, f"{{{ITUNES_NS}}}duration")
            dur.text = str(int(duration_seconds))

        ET.SubElement(item, f"{{{ITUNES_NS}}}episodeType").text = "full"
        return item

    # Root WITHOUT manual xmlns attributes
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = LISTEN_URL.rstrip("/") + "/"  # better than GitHub repo for aggregators
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()

    # Atom self link helps many validators
    atom_link = ET.SubElement(channel, f"{{{ATOM_NS}}}link")
    atom_link.set("href", (LISTEN_URL.rstrip("/") + "/feed.xml").replace("/listen/feed.xml", "/feed.xml"))
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = RSS_SETTINGS["author"]
    ET.SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = "no"
    ET.SubElement(channel, f"{{{ITUNES_NS}}}type").text = "episodic"

    cat = ET.SubElement(channel, f"{{{ITUNES_NS}}}category")
    cat.set("text", RSS_SETTINGS["category"])

    img = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    ET.SubElement(owner, f"{{{ITUNES_NS}}}name").text = RSS_SETTINGS["author"]
    ET.SubElement(owner, f"{{{ITUNES_NS}}}email").text = RSS_SETTINGS["email"]

    # Load existing items (and filter out junk)
    existing_episode_items: List[ET.Element] = []
    if FEED_XML_PATH.exists():
        try:
            old_tree = ET.parse(FEED_XML_PATH)
            old_rss = old_tree.getroot()
            old_channel = old_rss.find("channel")
            if old_channel is not None:
                for it in old_channel.findall("item"):
                    enc = it.find("enclosure")
                    if enc is None:
                        continue
                    url = (enc.get("url") or "")
                    # Keep only strict podcast_YYYY-MM-DD.mp3
                    if not re.search(r"podcast_\d{4}-\d{2}-\d{2}\.mp3", url):
                        continue
                    existing_episode_items.append(it)
        except Exception:
            existing_episode_items = []

    audio_file = meta["audio_file"]
    if not is_valid_episode_filename(audio_file):
        raise RuntimeError(f"Refusing to publish invalid episode filename: {audio_file}")

    show_notes = meta.get("show_notes") or ""
    duration_seconds = int(meta.get("duration_seconds") or 0)
    date_str = meta.get("date") or datetime.date.today().isoformat()

    new_item = make_item(
        title=meta["title"],
        description=show_notes,
        audio_filename=audio_file,
        pubdate_rfc2822=rfc2822_from_date(date_str),
        duration_seconds=duration_seconds,
    )

    merged: List[ET.Element] = [new_item]
    seen_urls = set()
    # register the new enclosure url
    new_enc = new_item.find("enclosure")
    if new_enc is not None and new_enc.get("url"):
        seen_urls.add(new_enc.get("url"))

    # Add prior valid items
    for old in existing_episode_items:
        enc = old.find("enclosure")
        if enc is None:
            continue
        url = enc.get("url") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(old)

    # Also add any local files that match strict naming (no spaces/duplicates)
    audio_files = sorted(AUDIO_DIR.glob("podcast_*.mp3"), key=lambda p: p.name, reverse=True)
    for mp3 in audio_files:
        if not is_valid_episode_filename(mp3.name):
            continue
        url = safe_url_join(AUDIO_BASE_URL, mp3.name)
        if url in seen_urls:
            continue
        d = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", mp3.name).group(1)
        merged.append(
            make_item(
                title=f"{RSS_SETTINGS['title']} — {d}",
                description=f"Listen: {LISTEN_URL}",
                audio_filename=mp3.name,
                pubdate_rfc2822=rfc2822_from_date(d),
                duration_seconds=0,
            )
        )
        seen_urls.add(url)

    merged = merged[:KEEP_LAST_EPISODES]
    for it in merged:
        channel.append(it)

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    _safe_print(f"✅ feed.xml updated with {len(merged)} episode items (strict filenames, valid namespaces)")

# ----------------------------
# MAIN PRODUCER
# ----------------------------
def produce_episode():
    today = datetime.date.today().isoformat()

    _safe_print(" >> 📰 GATHERING INTEL (RSS PRIMARY)...")
    intel = fetch_rss_items(max_per_feed=10)
    if not intel:
        _safe_print("    ⚠️ RSS empty. Using test item.")
        intel = [{
            "bucket": "Test",
            "title": "Test: AI model sparks market panic",
            "publisher": "TestWire",
            "published": today,
            "link": "https://example.com",
            "summary": "Simulation. $500M wiped. 24 hours. 3 regulators. 1 leak."
        }]

    sponsors = load_sponsors()
    stories = pick_top_stories(intel, n=5)

    _safe_print(" >> ✍️ WRITING FULL EPISODE (25–30 min, 5 segments)...")
    script = generate_episode_script(stories, sponsors, today)

    est = estimate_minutes_from_text(script)
    _safe_print(f"    Estimated minutes (text): ~{est:.1f}")

    script_path = BASE_DIR / f"script_{today}.txt"
    script_path.write_text(script, encoding="utf-8")

    dialogue = iter_dialogue(script)
    if len(dialogue) < 120:
        raise RuntimeError(
            f"Dialogue parsing produced too few lines ({len(dialogue)}). "
            "Script format likely broken (missing speaker labels)."
        )

    dialogue_merged = merge_dialogue_for_tts(dialogue, max_chars=TTS_MERGE_MAX_CHARS)

    run_tmp = TMP_AUDIO_DIR / today
    if run_tmp.exists():
        shutil.rmtree(run_tmp, ignore_errors=True)
    run_tmp.mkdir(parents=True, exist_ok=True)

    concat_files: List[Path] = []

    # Use WAV silence to avoid MP3 timestamp quirks during stitching
    silence_path = run_tmp / "silence_150ms.wav"
    AudioSegment.silent(duration=150).export(silence_path, format="wav")

    _safe_print(" >> 🎙️ RECORDING (TTS)...")
    seg_idx = 0

    inserted_intro = False

for speaker, text in dialogue_merged:
    if speaker == "MUSIC":
        # FIRST [MUSIC] marker = insert your intro bed there (after the cold open)
        if INTRO_PATH.exists() and not inserted_intro:
            intro = AudioSegment.from_file(INTRO_PATH)[:15000].fade_out(1200)
            intro_path = run_tmp / "intro_trim.mp3"
            intro.export(intro_path, format="mp3", bitrate="192k")
            concat_files.append(intro_path)
            inserted_intro = True
        else:
            concat_files.append(silence_path)
        continue

        voice = VOICE_MAP.get(speaker, "onyx")
        for chunk in chunk_text(text, max_chars=TTS_CHUNK_MAX_CHARS):
            seg_idx += 1
            seg_path = run_tmp / f"{today}_seg_{seg_idx:04d}.mp3"
            tts_to_file(chunk, voice, seg_path)
            concat_files.append(seg_path)
            concat_files.append(silence_path)

    if OUTRO_PATH.exists():
        outro = AudioSegment.from_file(OUTRO_PATH)[:12000].fade_in(800).fade_out(1200)
        outro_path = run_tmp / "outro_trim.mp3"
        outro.export(outro_path, format="mp3", bitrate="192k")
        concat_files.append(outro_path)

    _safe_print(f" >> 🎚️ STITCHING ({STITCH_METHOD})...")
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"
    stitch_audio(concat_files, final_mp3)

    final_audio = AudioSegment.from_mp3(final_mp3)
    duration_seconds = int(len(final_audio) / 1000)
    minutes = duration_seconds / 60.0
    _safe_print(f" ✅ EPISODE COMPLETE: {final_mp3.name} ({minutes:.2f} minutes)")

    if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
        raise RuntimeError(
            f"Episode length out of bounds ({minutes:.2f} min). Must be {MIN_MINUTES}-{MAX_MINUTES}."
        )

    pack = generate_marketing_pack(stories, today, LISTEN_URL)

    card_headline = pack["hook"]
    feed_title = f"{pack['hook']} — {today}"

    show_notes = (
        "Top stories:\n"
        + "\n".join([f"- {s.get('headline','')} ({s.get('source_url','')})" for s in stories])
        + f"\n\nListen: {LISTEN_URL}\n\n"
        + pack["hashtags"]
    )

    viral_caption = "\n".join([
        pack["tweet1"],
        "",
        pack["tweet2"],
        "",
        pack["hashtags"],
    ]).strip()

    (BASE_DIR / "viral_caption.txt").write_text(viral_caption, encoding="utf-8")
    (BASE_DIR / "marketing.txt").write_text(show_notes, encoding="utf-8")

    meta = {
        "date": today,
        "title": feed_title,
        "card_headline": card_headline,
        "listen_url": LISTEN_URL,
        "minutes": round(minutes, 2),
        "audio_file": final_mp3.name,
        "audio_url": AUDIO_BASE_URL + final_mp3.name,
        "stories": stories,
        "marketing_pack": pack,
        "duration_seconds": duration_seconds,
        "show_notes": show_notes,
    }
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    update_feed_xml(meta)
    run_marketing_pipeline()

    if CLEANUP_TEMP:
        shutil.rmtree(run_tmp, ignore_errors=True)

if __name__ == "__main__":
    produce_episode()
