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

WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "150"))
SEGMENT_ATTEMPTS = int(os.getenv("SEGMENT_ATTEMPTS", "3"))

SCRIPT_MAX_TOKENS = int(os.getenv("SCRIPT_MAX_TOKENS", "2200"))
JSON_MAX_TOKENS = int(os.getenv("JSON_MAX_TOKENS", "1800"))

CLEANUP_TEMP = os.getenv("CLEANUP_TEMP", "true").strip().lower() in ("1", "true", "yes")
KEEP_LAST_EPISODES = int(os.getenv("KEEP_LAST_EPISODES", "60"))

RUN_MARKETING_ASSETS = os.getenv("RUN_MARKETING_ASSETS", "true").strip().lower() in ("1", "true", "yes")
PUBLISH_SOCIAL = os.getenv("PUBLISH_SOCIAL", "false").strip().lower() in ("1", "true", "yes")

SAVE_SCRIPT = os.getenv("SAVE_SCRIPT", "false").strip().lower() in ("1", "true", "yes")

# Idempotency: do not recreate today's episode unless explicitly forced
FORCE_REBUILD = os.getenv("FORCE_REBUILD", "false").strip().lower() in ("1", "true", "yes")

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

# JAMIE speed (default 1.05 per your request)
JAMIE_SPEED = float(os.getenv("JAMIE_SPEED", "1.05"))

# ----------------------------
# QUALITY GATES (98% standard)
# ----------------------------
MIN_COLD_OPEN_LINES = int(os.getenv("MIN_COLD_OPEN_LINES", "6"))
MIN_DIGITS_PER_SEGMENT = int(os.getenv("MIN_DIGITS_PER_SEGMENT", "12"))
MIN_DIGITS_PER_EPISODE = int(os.getenv("MIN_DIGITS_PER_EPISODE", "85"))
MIN_NUMERIC_BULLETS_PER_STORY = int(os.getenv("MIN_NUMERIC_BULLETS_PER_STORY", "2"))

STRICT_EPISODE_FILENAME_RE = re.compile(r"^podcast_\d{4}-\d{2}-\d{2}\.mp3$")

MONEY_RE = re.compile(r"(\$|€|£)\s?\d")
NUMERIC_TOKEN_RE = re.compile(r"(\d+(\.\d+)?%|\$?\d[\d,]*(\.\d+)?|\b\d{4}\b|\bQ[1-4]\b)", re.IGNORECASE)

SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)

# ----------------------------
# FEED + SEO METADATA (catalog-wide)
# ----------------------------
MIN_MP3_BYTES_FEED = int(os.getenv("MIN_MP3_BYTES_FEED", "200000"))
EPISODE_META_MAX_TITLE = int(os.getenv("EPISODE_META_MAX_TITLE", "110"))
EPISODE_META_MAX_DESC = int(os.getenv("EPISODE_META_MAX_DESC", "4500"))

# ----------------------------
# VIRALITY / STORY PICKING
# ----------------------------
VIRAL_KEYWORDS = [
    "leak", "leaked", "whistleblower", "lawsuit", "sues", "ban", "banned", "crackdown", "investigation",
    "antitrust", "fraud", "hack", "breach", "ransomware", "exploit", "backdoor", "spy", "surveillance",
    "layoffs", "fired", "strike", "walkout", "shutdown", "collapse", "panic", "boycott",
    "copycat", "stolen", "copyright", "plagiarism", "deepfake", "election", "misinformation",
    "warning", "urgent", "emergency", "death", "injury", "safety", "weapon", "military",
]
VIRAL_BRANDS = [
    "openai", "anthropic", "nvidia", "microsoft", "google", "deepmind", "meta", "apple",
    "tesla", "amazon", "tiktok", "bytedance", "x", "twitter", "samsung", "intel",
]


def _safe_print(msg: str):
    print(msg, flush=True)


# ----------------------------
# SEO / TAGS HELPERS (98+)
# ----------------------------
TIER1_PUBLISHERS = {
    "reuters", "bloomberg", "wall street journal", "wsj", "financial times", "ft",
    "new york times", "nytimes", "the verge", "techcrunch", "wired", "arstechnica",
    "associated press", "ap", "cnbc"
}


def _clean_keyword(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s\-\&]", "", (s or "")).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def build_episode_keywords(stories: List[Dict[str, str]], max_keywords: int = 14) -> List[str]:
    base = [
        "AI news", "OpenAI", "Anthropic", "Nvidia", "ChatGPT", "Gemini",
        "AI regulation", "AI security", "AI chips", "big tech", "AI jobs"
    ]

    entities: List[str] = []
    for s in stories[:5]:
        ke = s.get("key_entities") if isinstance(s.get("key_entities"), list) else []
        for e in ke:
            e2 = _clean_keyword(str(e))
            if e2 and len(e2) <= 28:
                entities.append(e2)

        pub = (s.get("publisher") or "").strip()
        if pub and pub.lower() in TIER1_PUBLISHERS:
            entities.append(pub)

    out: List[str] = []
    seen = set()
    for x in base + entities:
        k = x.lower().strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
        if len(out) >= max_keywords:
            break
    return out


def build_hashtags_from_keywords(keywords: List[str], max_tags: int = 6) -> str:
    map_to = {
        "ai news": "#AI",
        "openai": "#OpenAI",
        "anthropic": "#Anthropic",
        "nvidia": "#Nvidia",
        "chatgpt": "#ChatGPT",
        "gemini": "#Gemini",
        "ai regulation": "#AIRegulation",
        "ai security": "#AISecurity",
        "ai chips": "#AIChips",
        "ai jobs": "#AIJobs",
        "big tech": "#BigTech",
    }
    tags: List[str] = []
    for k in keywords:
        t = map_to.get(k.lower().strip())
        if t and t not in tags:
            tags.append(t)
        if len(tags) >= max_tags:
            break

    if "#AI" not in tags:
        tags = ["#AI"] + [t for t in tags if t != "#AI"]

    return " ".join(tags[:max_tags])


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
# SIDE-CAR JSON (episode-level metadata persisted next to mp3)
# ----------------------------
def _date_from_episode_filename(name: str) -> Optional[str]:
    m = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", name or "")
    return m.group(1) if m else None


def _sidecar_meta_path_for_date(date_str: str) -> Path:
    return AUDIO_DIR / f"podcast_{date_str}.json"


def _load_sidecar_meta_for_date(date_str: str) -> Dict[str, str]:
    p = _sidecar_meta_path_for_date(date_str)
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        return j if isinstance(j, dict) else {}
    except Exception:
        return {}


def _write_sidecar_meta_for_date(date_str: str, title: str, description: str) -> Path:
    p = _sidecar_meta_path_for_date(date_str)
    payload = {"title": (title or "").strip(), "description": (description or "").strip()}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


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
        from google import genai as genai_new
        from google.genai import types as genai_types
        gemini_client = genai_new.Client(api_key=gemini_key)
    except Exception:
        gemini_client = None
        genai_types = None


def _gemini_candidate_models() -> List[str]:
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models = []
    if env_model:
        models.append(env_model)
    models += ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash"]
    seen = set()
    out = []
    for m in models:
        if m and m not in seen:
            out.append(m)
            seen.add(m)
    return out


def _extract_json_object(raw: str) -> Optional[dict]:
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
# NUMERIC UTILITIES
# ----------------------------
def _digit_count(s: str) -> int:
    return len(re.findall(r"\d", s or ""))


def _numeric_score(s: str) -> int:
    if not s:
        return 0
    s2 = s.lower()
    score = 0
    score += 3 * _digit_count(s2)
    if "$" in s2 or "€" in s2 or "£" in s2:
        score += 25
    if "%" in s2:
        score += 15
    for w, pts in [("billion", 18), ("million", 14), ("bn", 14), ("ipo", 10), ("funding", 10), ("valuation", 10)]:
        if w in s2:
            score += pts
    return score


def _virality_score(title: str, summary: str) -> int:
    blob = f"{title or ''} {summary or ''}".lower()
    score = 0
    for kw in VIRAL_KEYWORDS:
        if kw in blob:
            score += 10
    for b in VIRAL_BRANDS:
        if b in blob:
            score += 6
    if "!" in (title or ""):
        score += 6
    if "?" in (title or ""):
        score += 4
    return score


def _parse_published_to_dt(published: str) -> Optional[datetime.datetime]:
    if not published:
        return None
    s = published.strip()
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        dt2 = datetime.datetime.strptime(s[:25], "%a, %d %b %Y %H:%M:%S")
        return dt2.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def _recency_boost(published: str) -> int:
    dt = _parse_published_to_dt(published)
    if not dt:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    if age_hours <= 6:
        return 35
    if age_hours <= 12:
        return 20
    if age_hours <= 24:
        return 10
    if age_hours <= 48:
        return 4
    return 0


def _combined_story_score(item: Dict[str, str]) -> int:
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    published = item.get("published") or ""
    return _numeric_score(title + " " + summary) + _virality_score(title, summary) + _recency_boost(published)


def _extract_numeric_sentences(text: str, max_items: int = 6) -> List[str]:
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
# NEWS INTEL (RSS)
# ----------------------------
GOOGLE_NEWS_RSS = [
    ("Numbers & Markets",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Nvidia%20OR%20DeepMind%20OR%20Microsoft)%20(billion%20OR%20million%20OR%20%25%20OR%20%24%20OR%20IPO%20OR%20funding%20OR%20revenue%20OR%20valuation)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Market Shock (AI-specific drivers)",
     "https://news.google.com/rss/search?q=(AI%20OR%20%22generative%20AI%22%20OR%20LLM%20OR%20%22AI%20chips%22%20OR%20GPU%20OR%20%22data%20center%22)%20(Nvidia%20OR%20Microsoft%20OR%20Alphabet%20OR%20Meta%20OR%20AMD%20OR%20TSMC)%20(shares%20OR%20stock%20OR%20plunge%20OR%20surge%20OR%20earnings%20OR%20guidance%20OR%20%22market%20cap%22)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Money",
     "https://news.google.com/rss/search?q=(AI%20funding%20OR%20valuation%20OR%20IPO%20OR%20Nvidia%20OR%20chips)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Frontier Models",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20DeepMind)%20(model%20OR%20release%20OR%20launch%20OR%20benchmark)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Viral AI Breakers (Catch-all)",
     "https://news.google.com/rss/search?q=(AI%20OR%20%22artificial%20intelligence%22%20OR%20ChatGPT%20OR%20OpenAI%20OR%20Anthropic%20OR%20Google%20Gemini%20OR%20xAI%20OR%20Grok%20OR%20Meta%20AI%20OR%20Nvidia)%20(leak%20OR%20%22data%20breach%22%20OR%20hack%20OR%20lawsuit%20OR%20ban%20OR%20scandal%20OR%20%22class%20action%22%20OR%20whistleblower%20OR%20%22internal%20memo%22)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Leaks, Hacks, Breaches (Hard Security)",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Microsoft%20OR%20Google%20OR%20Meta%20OR%20Nvidia)%20(%22data%20breach%22%20OR%20breach%20OR%20hack%20OR%20leak%20OR%20ransomware%20OR%20%22prompt%20injection%22%20OR%20jailbreak%20OR%20%22model%20weights%22)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Outages / Reliability Incidents (Instantly Viral)",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20ChatGPT%20OR%20Azure%20OR%20%22Google%20Cloud%22%20OR%20AWS)%20(outage%20OR%20downtime%20OR%20incident%20OR%20degraded%20OR%20%22service%20disruption%22)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Deepfakes, Scams, Election Chaos",
     "https://news.google.com/rss/search?q=(AI%20OR%20deepfake%20OR%20%22voice%20clone%22%20OR%20%22AI%20scam%22%20OR%20impersonation%20OR%20fraud)%20(CEO%20OR%20bank%20OR%20election%20OR%20robocall%20OR%20%22identity%20theft%22)%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Copyright, IP Wars, Artist Revolt",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20Stability%20OR%20Midjourney%20OR%20Runway)%20(copyright%20OR%20lawsuit%20OR%20%22training%20data%22%20OR%20licensing%20OR%20%22class%20action%22%20OR%20%22rights%20holders%22)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
    ("Regulators + Bans + Enforcement",
     "https://news.google.com/rss/search?q=(FTC%20OR%20DOJ%20OR%20%22European%20Commission%22%20OR%20ICO%20OR%20EDPB%20OR%20CNIL)%20(AI%20OR%20OpenAI%20OR%20Anthropic%20OR%20Meta%20AI)%20(investigation%20OR%20enforcement%20OR%20fine%20OR%20ban%20OR%20order)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
    ("Chip War + Export Controls + Geopolitics",
     "https://news.google.com/rss/search?q=(Nvidia%20OR%20H100%20OR%20H200%20OR%20%22AI%20chips%22%20OR%20TSMC%20OR%20ASML%20OR%20AMD)%20(export%20controls%20OR%20sanctions%20OR%20China%20OR%20%22national%20security%22%20OR%20%22supply%20chain%22)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
    ("OpenAI / Anthropic / xAI Drama (Leadership + Conflict)",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20xAI%20OR%20Grok)%20(board%20OR%20CEO%20OR%20Altman%20OR%20resigns%20OR%20whistleblower%20OR%20%22internal%20memo%22%20OR%20%22employee%20walkout%22)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
    ("Robots + Autonomy Incidents (Physical Risk)",
     "https://news.google.com/rss/search?q=(AI%20OR%20%22artificial%20intelligence%22%20OR%20%22generative%20AI%22%20OR%20LLM%20OR%20ChatGPT%20OR%20OpenAI%20OR%20Anthropic%20OR%20Gemini)%20(robot%20OR%20humanoid%20OR%20drone%20OR%20autonomous)%20(accident%20OR%20injury%20OR%20crash%20OR%20recall%20OR%20malfunction)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
    ("AI in Work (Jobs + Layoffs + Enterprise)",
     "https://news.google.com/rss/search?q=(AI%20jobs%20OR%20automation%20OR%20productivity%20OR%20enterprise%20OR%20layoffs)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
    ("AI in Schools + Cheating Crackdowns",
     "https://news.google.com/rss/search?q=(ChatGPT%20OR%20AI)%20(schools%20OR%20students%20OR%20cheating%20OR%20plagiarism%20OR%20ban%20OR%20policy)%20when:7d&hl=en-US&gl=US&ceid=US:en"),
]


def _strip_html(s: str) -> str:
    if not s:
        return ""
    soup = BeautifulSoup(s, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt).strip()


def _split_headline_publisher(title: str) -> Tuple[str, str]:
    if not title:
        return "", ""
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return " - ".join(parts[:-1]).strip(), parts[-1].strip()
    return title.strip(), ""


def _published_iso_from_entry(entry) -> str:
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


@lru_cache(maxsize=128)
def _resolve_final_url(url: str) -> str:
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
    if not url:
        return ""
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    try:
        final_url = _resolve_final_url(url)
        r = requests.get(final_url, headers=headers, timeout=18)
        r.raise_for_status()

        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return ""

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

        for h in base.find_all(["h1", "h2", "h3"]):
            txt = h.get_text(" ", strip=True)
            if txt and 20 <= len(txt) <= 180:
                chunks.append(txt)
            if len(chunks) >= 10:
                break

        paras = []
        for p in base.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if txt and len(txt) > 40:
                paras.append(txt)
            if len(paras) >= 10:
                break
        chunks.extend(paras)

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


def enrich_stories_with_data(stories: List[Dict[str, str]]) -> List[Dict[str, str]]:
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
    if not intel_items:
        return []

    ranked = sorted(intel_items, key=_combined_story_score, reverse=True)
    candidates = ranked[:50]

    picked: List[Dict[str, str]] = []
    bucket_counts: Dict[str, int] = {}
    for x in candidates:
        b = (x.get("bucket") or "").strip()
        if bucket_counts.get(b, 0) >= 2:
            continue
        picked.append(x)
        bucket_counts[b] = bucket_counts.get(b, 0) + 1
        if len(picked) >= max(n * 3, 12):
            break

    if len(picked) < n:
        picked = candidates[:max(n * 3, 12)]

    intel_compact = "\n".join(
        [
            f"- [{x.get('bucket','')}] {x.get('title','')} | {x.get('publisher','')} | {x.get('published','')} | {x.get('summary','')} | {x.get('link','')}"
            for x in picked
        ]
    )

    prompt = f"""
Select the TOP {n} stories for a daily AI show that must feel urgent, emotional, and high-stakes.
Preference: scandal/security/regulation/market shock when credible.

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

    if len(stories) < n:
        stories = []
        for x in candidates[:n]:
            stories.append(
                {
                    "headline": x.get("title", ""),
                    "why_shocking": x.get("summary", ""),
                    "data_points": _extract_numeric_sentences((x.get("summary", "") or ""), max_items=4) or ["Needs enrichment"],
                    "angles": {"alex": "", "jamie": "", "rufus": ""},
                    "source_url": x.get("link", ""),
                    "publisher": x.get("publisher", ""),
                    "published": x.get("published", ""),
                    "rss_summary": x.get("summary", ""),
                }
            )

    for st in stories:
        match = next((x for x in intel_items if (x.get("link") or "").strip() == st["source_url"]), None)
        if match:
            st["rss_summary"] = (match.get("summary") or "").strip()
            st["publisher"] = st["publisher"] or (match.get("publisher") or "").strip()
            st["published"] = st["published"] or (match.get("published") or "").strip()
        else:
            st["rss_summary"] = st.get("rss_summary", "") or ""

    enriched = enrich_stories_with_data(stories[:n])

    def numeric_bullets(dp: List[str]) -> int:
        return sum(1 for b in (dp or []) if NUMERIC_TOKEN_RE.search(b or ""))

    weak = [s for s in enriched if numeric_bullets(s.get("data_points") or []) < MIN_NUMERIC_BULLETS_PER_STORY]
    if weak:
        fallback = []
        for x in candidates:
            fb = {
                "headline": x.get("title", ""),
                "why_shocking": x.get("summary", ""),
                "data_points": _extract_numeric_sentences((x.get("summary", "") or ""), max_items=6) or ["Needs enrichment"],
                "angles": {"alex": "", "jamie": "", "rufus": ""},
                "source_url": x.get("link", ""),
                "publisher": x.get("publisher", ""),
                "published": x.get("published", ""),
                "rss_summary": x.get("summary", ""),
            }
            fallback.append(fb)
            if len(fallback) >= n:
                break
        enriched = enrich_stories_with_data(fallback[:n])

    return enriched[:n]


# ----------------------------
# SCRIPTING (SOUL + GUARANTEED LENGTH + DATA RICHNESS)
# ----------------------------
def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))


def estimate_minutes_from_text(script: str) -> float:
    return _word_count(script) / max(1.0, WORDS_PER_MINUTE)


def _script_targets() -> Tuple[int, int, int]:
    min_words = int(MIN_MINUTES * WORDS_PER_MINUTE * 1.02)
    target_words = int(TARGET_MINUTES * WORDS_PER_MINUTE * 1.00)
    max_words = int(MAX_MINUTES * WORDS_PER_MINUTE * 1.10)
    return min_words, target_words, max_words


def _segment_word_targets() -> List[int]:
    min_words, _, max_words = _script_targets()
    seg = [650, 1200, 900, 1400, 650]  # total ~4800

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
            "Studio segment: ONLY Alex + Jamie (no Rufus at all). High chemistry, fast pacing. "
            "Deep dive Story 1 + Story 2 with human stakes and emotional pushback.\n"
            f"(1) {s1['headline']}\n"
            f"(2) {s2['headline']}"
        )
    if seg_num == 3:
        return (
            "On-location: Alex throws to Rufus, then Rufus dominates with money/reg angle. "
            "Primary focus Story 3 with filings/trading/regulatory edge.\n"
            f"(3) {s3['headline']}"
        )
    if seg_num == 4:
        return (
            "All three together: dread/greed forecast + lightning round. "
            "Cover Story 4 + Story 5, and callback earlier claims. Interruptions and analogies.\n"
            f"(4) {s4['headline']}\n"
            f"(5) {s5['headline']}"
        )
    return (
        "Closing: Alex closes hard, Jamie lands one empathetic gut-punch, "
        "Rufus delivers one cynical prophecy. Keep it tight and memorable."
    )


def _sanitize_segment_speakers(
    seg_text: str,
    allowed: Optional[set] = None,
    disallowed: Optional[set] = None
) -> str:
    """
    Defensive post-processing:
    - If `allowed` is set, removes any speaker lines NOT in allowed.
    - If `disallowed` is set, removes any speaker lines IN disallowed.
    Keeps segment marker and [MUSIC].
    """
    if not seg_text:
        return ""

    allowed_set = {a.upper() for a in (allowed or set())}
    disallowed_set = {d.upper() for d in (disallowed or set())}

    out: List[str] = []
    for raw in seg_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            out.append("[MUSIC]" if line.upper() == "[MUSIC]" else line)
            continue

        m = SPEAKER_RE.match(line)
        if not m:
            continue

        spk = m.group(1).upper()
        txt = m.group(2).strip()

        if allowed_set and spk not in allowed_set:
            continue
        if disallowed_set and spk in disallowed_set:
            continue
        if txt:
            out.append(f"{spk}: {txt}")

    return "\n".join(out).strip()


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
- For every story you discuss in THIS segment, you MUST speak at least 2 explicit data points
  (numbers/dates/amounts) from the provided "Data points" lines in TODAY'S STORIES.
- Mention the publisher at least once when introducing a story.
- Do NOT invent numbers. If a story has "No explicit figures in snippet", say that plainly and focus on consequences.

WHAT THIS SEGMENT MUST DO:
{assignment}

SPECIAL INSTRUCTIONS FOR THIS SEGMENT:
{extra}

TODAY'S STORIES:
{story_block}

NOW OUTPUT ONLY THIS SEGMENT.
""".strip()


def _segment_validate(seg_text: str, seg_num: int, seg_words_min: int) -> List[str]:
    issues: List[str] = []
    if not seg_text.strip().startswith(_segment_header(seg_num)):
        issues.append(f"Segment {seg_num} missing required first line '{_segment_header(seg_num)}'.")

    for ln in seg_text.splitlines():
        line = ln.strip()
        if not line:
            continue
        if line.startswith("###") or line.upper() == "[MUSIC]":
            continue
        if not SPEAKER_RE.match(line):
            issues.append("Found non-labeled spoken line(s).")
            break

    if seg_num == 2:
        if re.search(r"^RUFUS\s*:", seg_text, flags=re.IGNORECASE | re.MULTILINE):
            issues.append("SEGMENT 2 contains RUFUS lines; it must be ONLY ALEX + JAMIE.")

    wc = _word_count(seg_text)
    if wc < seg_words_min:
        issues.append(f"Segment too short ({wc} words). Minimum is {seg_words_min}.")

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

    if _digit_count(seg_text) < MIN_DIGITS_PER_SEGMENT:
        issues.append(
            f"Low numeric density in segment (digits={_digit_count(seg_text)}). Minimum is {MIN_DIGITS_PER_SEGMENT}."
        )

    return issues


def _segment_repair_prompt(
    seg_num: int,
    seg_words_min: int,
    seg_words_target: int,
    issues: List[str],
    seg_text: str
) -> str:
    seg_specific = ""
    if seg_num == 2:
        seg_specific = (
            "- SEGMENT 2 MUST contain ONLY ALEX and JAMIE lines.\n"
            "- Delete ANY RUFUS lines and do NOT reintroduce RUFUS.\n"
        )

    return f"""
You are repairing ONLY {_segment_header(seg_num)} for "The AI Edge".

CURRENT ISSUES (fix all):
{chr(10).join([f"- {x}" for x in issues])}

NON-NEGOTIABLE:
- First line MUST be exactly "{_segment_header(seg_num)}"
- Output MUST be dialogue lines only with EXACT labels: ALEX:, JAMIE:, RUFUS:
- Every spoken line MUST start with one of those labels.
{seg_specific}- Add MORE back-and-forth; do NOT compress.
- Keep lines SHORT (1–2 sentences) to increase turn count.
- Segment length MUST be at least {seg_words_min} words (target ~{seg_words_target}).

HERE IS THE SEGMENT TO EXPAND/REPAIR:
{seg_text}
""".strip()


def _sanitize_dialogue_only(text: str, allowed_speakers: Optional[set] = None) -> str:
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

            if allowed_speakers is not None and spk not in allowed_speakers:
                last_speaker = None
                continue

            if txt:
                out.append(f"{spk}: {txt}")
                last_speaker = spk
            else:
                last_speaker = None
            continue

        if last_speaker:
            if allowed_speakers is not None and last_speaker not in allowed_speakers:
                continue
            out.append(f"{last_speaker}: {line}")

    return "\n".join(out).strip()


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

        if seg_num == 2:
            seg_text = _sanitize_segment_speakers(seg_text, allowed={"ALEX", "JAMIE"})
            if not seg_text.strip().startswith(_segment_header(seg_num)):
                seg_text = f"{_segment_header(seg_num)}\n{seg_text}".strip()

        wc = _word_count(seg_text)
        issues = _segment_validate(seg_text, seg_num, seg_words_min)
        _safe_print(f"    ✍️ Segment {seg_num} attempt {attempt}/{SEGMENT_ATTEMPTS} (min {seg_words_min}): {wc} words")

        if not issues:
            return seg_text.strip()

        prompt = _segment_repair_prompt(seg_num, seg_words_min, seg_words_target, issues, seg_text)

    return seg_text.strip()


def _trim_script_to_max_words(script: str, max_words: int) -> str:
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
- NO segment markers.
- Add ~{add_words} words (do NOT go under {int(add_words*0.85)}).
- MUST include at least 6 explicit data points from the story block below.
- Keep fast banter, interruptions, dread/greed forecasting.

STORY BLOCK:
{story_block}
""".strip()

    addon = generate_text(prompt, temperature=0.65, max_tokens=1800)
    addon = _sanitize_dialogue_only(addon)

    insert_at = m.start()
    return (script[:insert_at].rstrip() + "\n" + addon.strip() + "\n\n" + script[insert_at:].lstrip()).strip()


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

    seg2_block = re.search(
        r"^###\s*SEGMENT\s*2\b(.*?)(^###\s*SEGMENT\s*3\b|\Z)",
        script,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    if seg2_block and re.search(r"^RUFUS\s*:", seg2_block.group(1), flags=re.IGNORECASE | re.MULTILINE):
        issues.append("SEGMENT 2 contains RUFUS lines; it must be ONLY ALEX + JAMIE.")

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


def enforce_episode_numeric_density(script: str, stories: List[Dict[str, str]], date_str: str) -> str:
    if _digit_count(script) >= MIN_DIGITS_PER_EPISODE:
        return script

    deficit = MIN_DIGITS_PER_EPISODE - _digit_count(script)
    add_words = min(900, max(320, deficit * 6))
    story_block = _story_block(stories)

    prompt = f"""
Write a DATA-DUMP add-on for SEGMENT 4 of "The AI Edge" ({date_str}).

NON-NEGOTIABLE:
- Output ONLY dialogue lines labeled ALEX:, JAMIE:, RUFUS:
- Use story DATA POINTS verbatim (numbers/dates/amounts must appear).
- Add ~{add_words} words.
- MUST include at least 12 distinct numeric tokens overall.
- Keep it intense: consequences + "what this means tomorrow".

STORY BLOCK:
{story_block}
""".strip()

    addon = generate_text(prompt, temperature=0.55, max_tokens=1800)
    addon = _sanitize_dialogue_only(addon)

    m = re.search(r"^###\s*SEGMENT\s*5\b", script, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        script2 = (script.rstrip() + "\n" + addon.strip()).strip()
    else:
        script2 = (script[:m.start()].rstrip() + "\n" + addon.strip() + "\n\n" + script[m.start():].lstrip()).strip()

    min_words, _, max_words = _script_targets()
    if _word_count(script2) > max_words:
        script2 = _trim_script_to_max_words(script2, max_words=max_words)

    script2 = _sanitize_dialogue_only(script2)
    return script2


def generate_episode_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], date_str: str) -> str:
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
        seg = _sanitize_dialogue_only(seg, allowed_speakers={"ALEX", "JAMIE"} if i == 2 else None)
        segments.append(seg)

    script = "\n\n".join(segments).strip()
    script = _sanitize_dialogue_only(script)

    min_words, _, max_words = _script_targets()

    if _word_count(script) > max_words:
        script = _trim_script_to_max_words(script, max_words=max_words)
    if _word_count(script) < min_words:
        script = _pad_script_to_min_words(script, min_words=min_words, stories=stories, sponsors=sponsors, date_str=date_str)

    script = _sanitize_dialogue_only(script)

    issues = validate_script(script)
    if issues:
        raise RuntimeError("Final script validation failed:\n" + "\n".join(issues))

    return script


# ----------------------------
# DIALOGUE PARSING (ROBUST)
# ----------------------------
def iter_dialogue(script: str) -> List[Tuple[str, str]]:
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


def apply_speed_ffmpeg(in_path: Path, out_path: Path, speed: float):
    if abs(speed - 1.0) < 1e-6:
        shutil.copyfile(in_path, out_path)
        return
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found; required for JAMIE speed adjustment.")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-filter:a", f"atempo={speed:.4f}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)


def stitch_with_ffmpeg(file_list: List[Path], out_path: Path):
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
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found in runner (required by pydub decode).")
    combined = AudioSegment.empty()
    for p in file_list:
        combined += AudioSegment.from_file(p)
    combined.export(out_path, format="mp3", bitrate="192k")


def stitch_audio(file_list: List[Path], out_path: Path):
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


def _hashtags_from_stories(stories: List[Dict[str, str]], max_tags: int = 6) -> str:
    tags: List[str] = ["#AI", "#TechNews"]
    ent: List[str] = []
    for s in stories[:5]:
        ke = s.get("key_entities")
        if isinstance(ke, list):
            ent.extend([str(x).strip() for x in ke if str(x).strip()])
    for s in stories[:5]:
        ent.extend(re.findall(r"\b[A-Z][A-Za-z0-9]+\b", (s.get("headline") or "")))

    cleaned: List[str] = []
    for e in ent:
        e2 = re.sub(r"[^A-Za-z0-9]", "", e)
        if not e2 or len(e2) < 3:
            continue
        low = e2.lower()
        if low in ("openai", "nvidia", "anthropic", "microsoft", "google", "deepmind", "meta", "apple"):
            cleaned.append("#" + e2[0].upper() + e2[1:])
        elif low in ("eu", "ftc", "sec", "doj"):
            cleaned.append("#" + e2.upper())
        else:
            cleaned.append("#" + e2)

    priority = [
        "#OpenAI", "#Nvidia", "#Anthropic", "#Microsoft", "#Google", "#DeepMind", "#Meta", "#Apple",
        "#Cybersecurity", "#AIRegulation", "#AIGovernance", "#TechLayoffs"
    ]
    out: List[str] = []
    for p in priority:
        if p in cleaned and p not in out:
            out.append(p)
    for t in cleaned:
        if t not in out and t not in tags:
            out.append(t)

    final = tags + out
    seen = set()
    uniq = []
    for t in final:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    return " ".join(uniq[:max_tags])


def generate_marketing_pack(stories: List[Dict[str, str]], date_str: str, listen_url: str) -> Dict[str, str]:
    story_lines = "\n".join([f"- {s.get('headline','')} | {s.get('source_url','')}" for s in stories[:5]])

    prompt = f"""
You are a direct-response growth writer for a DAILY AI show called "The AI Edge".
Goal: drive a click TODAY using the most viral, high-stakes framing that remains grounded.

Return ONLY valid JSON (no markdown). Schema:
{{
  "hook": "6-10 words, STOP-SCROLL, no date, no quotes, <= 64 chars",
  "card_subhook": "one short teaser line (<= 52 chars)",
  "tweet1": "Tweet 1 text (<= 260 chars). Must work with a video attached. Include a question.",
  "tweet2": "Tweet 2 text (<= 260 chars). Must include this exact link: {listen_url}",
  "yt_title": "YouTube title (<= 90 chars)",
  "yt_description": "YouTube description (<= 1200 chars) including {listen_url}",
  "ig_caption": "Instagram caption (<= 500 chars) including {listen_url}",
  "tiktok_caption": "TikTok caption (<= 220 chars) including {listen_url}",
  "hashtags": "Space-separated hashtags. Keep <= 6 total tags. Must include #AI and #TechNews"
}}

Today: {date_str}
Top stories:
{story_lines}

Rules:
- No corporate speak.
- Hook must be specific and urgent.
- Make it feel like consequences are imminent.
- Avoid repeating the date in hook/title.
""".strip()

    raw = generate_text(prompt, temperature=0.45, max_tokens=1100)
    j = _extract_json_object(raw)

    fallback_hook = (stories[0].get("headline") if stories else "AI JUST MOVED — HERE’S WHAT CHANGED")[:64]
    fallback_tags = _hashtags_from_stories(stories, max_tags=6)

    out = {
        "hook": fallback_hook.upper(),
        "card_subhook": "WHAT BREAKS NEXT?",
        "tweet1": f"{fallback_hook}\n\nWhat’s the real consequence here?",
        "tweet2": f"Full episode: {listen_url}\n\n{fallback_tags}",
        "yt_title": f"{fallback_hook} | The AI Edge",
        "yt_description": f"Listen: {listen_url}\n\nTop stories:\n" + "\n".join([f"- {s.get('headline','')}" for s in stories[:5]]),
        "ig_caption": f"{fallback_hook}\n\nListen: {listen_url}\n\n{fallback_tags}",
        "tiktok_caption": f"{fallback_hook} {listen_url} {fallback_tags}",
        "hashtags": fallback_tags,
    }

    try:
        if j:
            for k in list(out.keys()):
                if isinstance(j.get(k), str) and j[k].strip():
                    out[k] = j[k].strip()

        out["hook"] = out["hook"][:64].upper()
        out["card_subhook"] = out["card_subhook"][:52]
        out["tweet1"] = out["tweet1"][:260]
        out["tweet2"] = out["tweet2"][:260]
        out["yt_title"] = out["yt_title"][:90]
        out["yt_description"] = out["yt_description"][:1200]
        out["ig_caption"] = out["ig_caption"][:500]
        out["tiktok_caption"] = out["tiktok_caption"][:220]

        tags = out.get("hashtags", "")
        tags_list = [t.strip() for t in tags.split() if t.strip().startswith("#")]
        if "#AI" not in tags_list:
            tags_list = ["#AI"] + tags_list
        if "#TechNews" not in tags_list:
            tags_list = ["#TechNews"] + tags_list

        seen = set()
        uniq = []
        for t in tags_list:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        out["hashtags"] = " ".join(uniq[:6])

        return out
    except Exception:
        return out


# ----------------------------
# EPISODE SEO META
# ----------------------------
def _generate_episode_seo_meta(
    date_str: str,
    stories: List[Dict[str, str]],
    listen_url: str,
    script_text: str,
    marketing_pack: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    story_block = _story_block(stories)
    hook = (marketing_pack or {}).get("hook", "").strip()

    keywords = build_episode_keywords(stories, max_keywords=14)
    hashtags = build_hashtags_from_keywords(keywords, max_tags=6)

    top_headline = (stories[0].get("headline") if stories else "AI BREAKING UPDATE").strip()
    top_pub = (stories[0].get("publisher") if stories else "").strip()
    mnum = NUMERIC_TOKEN_RE.search(story_block)
    num_token = mnum.group(0) if mnum else date_str

    prompt = f"""
You are writing Spotify/Apple SEO metadata for a daily AI podcast episode.

Return ONLY valid JSON (no markdown):
{{
  "title": "VIRAL + SEARCHABLE episode title <= {EPISODE_META_MAX_TITLE} chars. Must include 1 clear keyword (OpenAI/Nvidia/Anthropic/ChatGPT/Gemini) AND at least one number/$/%/date token from story block if available. Do NOT start with just the date.",
  "subtitle": "Short subtitle <= 120 chars. Must feel urgent and human-impact.",
  "description": "Show notes <= {EPISODE_META_MAX_DESC} chars with sections EXACTLY:
TODAY’S LINEUP
KEY NUMBERS
WHY IT MATTERS
SOURCES
LISTEN
TAGS
HASHTAGS
Rules: use story data_points verbatim wherever possible; do NOT invent numbers."
}}

Episode date: {date_str}
Listen URL: {listen_url}
Hook (optional): {hook}

Preferred TAGS/KEYWORDS (use in TAGS section):
{", ".join(keywords)}

TODAY'S STORIES:
{story_block}

SCRIPT (context only; do not paste long chunks):
{script_text[:1600]}
""".strip()

    raw = generate_text(prompt, temperature=0.25, max_tokens=1400)
    j = _extract_json_object(raw) or {}

    title = (j.get("title") or "").strip()
    subtitle = (j.get("subtitle") or "").strip()
    desc = (j.get("description") or "").strip()

    def ok_title(t: str) -> bool:
        if not t or len(t) > EPISODE_META_MAX_TITLE:
            return False
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.strip()):
            return False
        if not (NUMERIC_TOKEN_RE.search(t) or re.search(r"\d", t)):
            return False
        core = ["openai", "nvidia", "anthropic", "chatgpt", "gemini", "xai", "grok", "meta"]
        if not any(c in t.lower() for c in core):
            return False
        return True

    def ok_desc(d: str) -> bool:
        if not d or len(d) > EPISODE_META_MAX_DESC:
            return False
        must = ["TODAY", "KEY NUMBERS", "WHY IT MATTERS", "SOURCES", "LISTEN", "TAGS", "HASHTAGS"]
        if sum(1 for m in must if m.lower() in d.lower()) < 6:
            return False
        return _digit_count(d) >= 35

    if not ok_title(title):
        core_kw = "OpenAI" if "openai" in story_block.lower() else ("Nvidia" if "nvidia" in story_block.lower() else "AI")
        pub_bit = f" ({top_pub})" if top_pub else ""
        title = f"{core_kw} shock: {num_token} — {top_headline[:70]}{pub_bit}"
        title = title[:EPISODE_META_MAX_TITLE].strip()

    if not subtitle:
        subtitle = (hook or "5 stories. Real consequences. What breaks next.").strip()[:120]

    if not ok_desc(desc):
        lines = []
        lines.append((hook or title).strip())
        lines.append("")
        lines.append("TODAY’S LINEUP")
        for s in stories[:5]:
            pub = (s.get("publisher") or "").strip()
            head = (s.get("headline") or "").strip()
            lines.append(f"- {head}" + (f" ({pub})" if pub else ""))

        lines.append("")
        lines.append("KEY NUMBERS")
        for i, s in enumerate(stories[:5], start=1):
            lines.append(f"{i}) {(s.get('headline') or '').strip()}")
            dp = s.get("data_points") if isinstance(s.get("data_points"), list) else []
            dp = [str(x).strip() for x in dp if str(x).strip()] or ["No explicit figures in snippet."]
            for b in dp[:6]:
                lines.append(f"   • {b}")

        lines.append("")
        lines.append("WHY IT MATTERS")
        for s in stories[:5]:
            why = (s.get("why_shocking") or "").strip()
            if why:
                lines.append(f"- {why[:220]}")

        lines.append("")
        lines.append("SOURCES")
        for s in stories[:5]:
            url = (s.get("source_url") or "").strip()
            if url:
                lines.append(f"- {url}")

        lines.append("")
        lines.append("LISTEN")
        lines.append(listen_url)

        lines.append("")
        lines.append("TAGS")
        lines.append(", ".join(keywords))

        lines.append("")
        lines.append("HASHTAGS")
        lines.append(hashtags)

        desc = "\n".join(lines).strip()[:EPISODE_META_MAX_DESC]

    return {
        "title": title,
        "subtitle": subtitle,
        "description": desc,
        "keywords": keywords,
        "hashtags": hashtags,
    }


# ----------------------------
# RSS FEED WRITER (catalog-wide truth)
# ----------------------------
def update_feed_xml(meta: Dict):
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ATOM_NS = "http://www.w3.org/2005/Atom"

    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("atom", ATOM_NS)

    def rfc2822_from_date(datestr: str) -> str:
        try:
            dtx = datetime.datetime.strptime(datestr, "%Y-%m-%d")
            dtx = dtx.replace(hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc)
        except Exception:
            dtx = datetime.datetime.now(datetime.timezone.utc)
        return dtx.strftime("%a, %d %b %Y %H:%M:%S -0000")

    def rfc2822_now() -> str:
        dtx = datetime.datetime.now(datetime.timezone.utc)
        return dtx.strftime("%a, %d %b %Y %H:%M:%S -0000")

    def safe_url_join(base: str, filename: str) -> str:
        return base.rstrip("/") + "/" + quote(filename)

    def is_valid_episode_filename(name: str) -> bool:
        return bool(STRICT_EPISODE_FILENAME_RE.match(name or ""))

    def file_ok_for_feed(p: Path) -> bool:
        try:
            return p.exists() and p.stat().st_size >= MIN_MP3_BYTES_FEED
        except Exception:
            return False

    def make_item(
        title: str,
        description: str,
        audio_filename: str,
        pubdate_rfc2822: str,
        duration_seconds: int = 0,
        subtitle: str = "",
        keywords_csv: str = "",
    ) -> ET.Element:
        item = ET.Element("item")
        ET.SubElement(item, "title").text = (title or "")[:EPISODE_META_MAX_TITLE]
        ET.SubElement(item, "description").text = (description or "")[:8000]
        ET.SubElement(item, f"{{{ITUNES_NS}}}summary").text = (description or "")[:8000]

        if subtitle:
            ET.SubElement(item, f"{{{ITUNES_NS}}}subtitle").text = subtitle[:255]
        if keywords_csv:
            ET.SubElement(item, f"{{{ITUNES_NS}}}keywords").text = keywords_csv[:255]

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

        ep_img = ET.SubElement(item, f"{{{ITUNES_NS}}}image")
        ep_img.set("href", RSS_SETTINGS["image"])

        ET.SubElement(item, f"{{{ITUNES_NS}}}episodeType").text = "full"
        return item

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = LISTEN_URL.rstrip("/") + "/"
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()

    atom_link = ET.SubElement(channel, f"{{{ATOM_NS}}}link")
    feed_href = (LISTEN_URL.rstrip("/") + "/feed.xml").replace("/listen/feed.xml", "/feed.xml")
    atom_link.set("href", feed_href)
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

    mp3s = sorted(AUDIO_DIR.glob("podcast_*.mp3"), key=lambda p: p.name, reverse=True)

    items_added = 0
    for mp3 in mp3s:
        if items_added >= KEEP_LAST_EPISODES:
            break
        if not is_valid_episode_filename(mp3.name):
            continue
        if not file_ok_for_feed(mp3):
            continue

        date_str = _date_from_episode_filename(mp3.name) or datetime.date.today().isoformat()
        sidecar = _load_sidecar_meta_for_date(date_str)

        title = (sidecar.get("title") or f"{RSS_SETTINGS['title']} — {date_str}").strip()
        desc = (sidecar.get("description") or f"Listen: {LISTEN_URL}").strip()

        if meta.get("audio_file") == mp3.name:
            title = (meta.get("title") or title).strip()
            desc = (meta.get("show_notes") or desc).strip()
            dur = int(meta.get("duration_seconds") or 0)
            subtitle = (meta.get("subtitle") or "").strip()
            keywords_csv = (meta.get("keywords_csv") or "").strip()
        else:
            dur = 0
            subtitle = ""
            keywords_csv = ""

        channel.append(
            make_item(
                title=title,
                description=desc,
                audio_filename=mp3.name,
                pubdate_rfc2822=rfc2822_from_date(date_str),
                duration_seconds=dur,
                subtitle=subtitle,
                keywords_csv=keywords_csv,
            )
        )
        items_added += 1

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    _safe_print(
        f"✅ feed.xml rebuilt from local episodes: {items_added} items (skipped broken files < {MIN_MP3_BYTES_FEED} bytes)"
    )


# ----------------------------
# MAIN PRODUCER
# ----------------------------
def _maybe_append_date(title: str, date_str: str) -> str:
    """
    Ensures date suffix is present and title length <= EPISODE_META_MAX_TITLE.
    Preserves the date suffix by truncating the base title if needed.
    """
    t = (title or "").strip()
    if not t:
        return f"{RSS_SETTINGS['title']} — {date_str}"[:EPISODE_META_MAX_TITLE]

    if date_str in t:
        return t[:EPISODE_META_MAX_TITLE].strip()

    suffix = f" — {date_str}"
    max_base = EPISODE_META_MAX_TITLE - len(suffix)
    if max_base < 10:
        return (t[:EPISODE_META_MAX_TITLE]).strip()

    base = t
    if len(base) > max_base:
        base = base[:max_base].rstrip(" -—:|")
    return (base + suffix)[:EPISODE_META_MAX_TITLE].strip()


def _file_ok_for_feed(p: Path) -> bool:
    try:
        return p.exists() and p.stat().st_size >= MIN_MP3_BYTES_FEED
    except Exception:
        return False


def produce_episode():
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg is required for stitching and JAMIE speed adjustment. Install it on runner/host.")

    today = datetime.date.today().isoformat()
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"

    # Idempotency guard
    if final_mp3.exists() and _file_ok_for_feed(final_mp3) and not FORCE_REBUILD:
        _safe_print(f"🛑 Today's episode already exists ({final_mp3.name}). Set FORCE_REBUILD=true to regenerate.")

        try:
            final_audio = AudioSegment.from_mp3(final_mp3)
            duration_seconds = int(len(final_audio) / 1000)
        except Exception:
            duration_seconds = 0

        sidecar = _load_sidecar_meta_for_date(today)
        meta = {
            "date": today,
            "title": sidecar.get("title") or f"{RSS_SETTINGS['title']} — {today}",
            "subtitle": "",
            "keywords_csv": "",
            "listen_url": LISTEN_URL,
            "minutes": round(duration_seconds / 60.0, 2) if duration_seconds else 0,
            "audio_file": final_mp3.name,
            "audio_url": AUDIO_BASE_URL + final_mp3.name,
            "stories": [],
            "marketing_pack": {},
            "duration_seconds": duration_seconds,
            "show_notes": sidecar.get("description") or f"LISTEN: {LISTEN_URL}",
        }
        update_feed_xml(meta)
        return

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
    script = enforce_episode_numeric_density(script, stories, today)
    script = _sanitize_dialogue_only(script)

    issues = validate_script(script)
    if issues:
        raise RuntimeError("Script validation failed after numeric-density enforcement:\n" + "\n".join(issues))

    est = estimate_minutes_from_text(script)
    _safe_print(f"    Estimated minutes (text): ~{est:.1f}")

    if SAVE_SCRIPT:
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

    if STITCH_METHOD == "ffmpeg":
        silence_path = run_tmp / "silence_150ms.mp3"
        AudioSegment.silent(duration=150).export(silence_path, format="mp3", bitrate="192k")
    else:
        silence_path = run_tmp / "silence_150ms.wav"
        AudioSegment.silent(duration=150).export(silence_path, format="wav")

    _safe_print(" >> 🎙️ RECORDING (TTS)...")
    seg_idx = 0
    inserted_intro = False

    for speaker, text in dialogue_merged:
        if speaker == "MUSIC":
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
            raw_seg_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_raw.mp3"
            tts_to_file(chunk, voice, raw_seg_path)

            if speaker == "JAMIE" and abs(JAMIE_SPEED - 1.0) > 1e-6:
                sped_path = run_tmp / f"{today}_seg_{seg_idx:04d}_{speaker.lower()}_spd.mp3"
                apply_speed_ffmpeg(raw_seg_path, sped_path, JAMIE_SPEED)
                concat_files.append(sped_path)
            else:
                concat_files.append(raw_seg_path)

            concat_files.append(silence_path)

    if OUTRO_PATH.exists():
        outro = AudioSegment.from_file(OUTRO_PATH)[:12000].fade_in(800).fade_out(1200)
        outro_path = run_tmp / "outro_trim.mp3"
        outro.export(outro_path, format="mp3", bitrate="192k")
        concat_files.append(outro_path)

    _safe_print(f" >> 🎚️ STITCHING ({STITCH_METHOD})...")
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
    seo = _generate_episode_seo_meta(
        date_str=today,
        stories=stories,
        listen_url=LISTEN_URL,
        script_text=script,
        marketing_pack=pack,
    )

    feed_title = _maybe_append_date(seo["title"], today)
    subtitle = (seo.get("subtitle") or "").strip()[:255]
    keywords_csv = ", ".join(seo.get("keywords") or [])[:255]
    show_notes = (seo.get("description") or "").strip()

    _write_sidecar_meta_for_date(today, title=feed_title, description=show_notes)

    viral_caption = "\n".join([
        (pack.get("tweet1", "") or "").strip(),
        "",
        (pack.get("tweet2", "") or "").strip(),
        "",
        (pack.get("hashtags", "") or "").strip(),
    ]).strip()

    (BASE_DIR / "viral_caption.txt").write_text(viral_caption, encoding="utf-8")
    (BASE_DIR / "marketing.txt").write_text(show_notes, encoding="utf-8")
    (BASE_DIR / "marketing_pack.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")

    platform_pack = {
        "date": today,
        "listen_url": LISTEN_URL,
        "hook": pack.get("hook", ""),
        "yt_title": pack.get("yt_title", ""),
        "yt_description": pack.get("yt_description", ""),
        "ig_caption": pack.get("ig_caption", ""),
        "tiktok_caption": pack.get("tiktok_caption", ""),
        "hashtags": pack.get("hashtags", ""),
    }
    (BASE_DIR / "platform_pack.json").write_text(json.dumps(platform_pack, indent=2, ensure_ascii=False), encoding="utf-8")

    meta = {
        "date": today,
        "title": feed_title,
        "subtitle": subtitle,
        "keywords_csv": keywords_csv,
        "listen_url": LISTEN_URL,
        "minutes": round(minutes, 2),
        "audio_file": final_mp3.name,
        "audio_url": AUDIO_BASE_URL + final_mp3.name,
        "stories": stories,
        "marketing_pack": pack,
        "duration_seconds": duration_seconds,
        "show_notes": show_notes,
    }
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    update_feed_xml(meta)

    run_marketing_pipeline()

    if CLEANUP_TEMP:
        shutil.rmtree(run_tmp, ignore_errors=True)


# ----------------------------
# ENTRYPOINT
# ----------------------------
if __name__ == "__main__":
    produce_episode()
