# -*- coding: utf-8 -*-
"""
The AI Edge — 2026 Rebuild
Drop-in replacement for main.py

Highlights
- Smarter story scoring: importance + credibility + novelty + consequence
- Stronger cast dynamics: Alex / Jamie / Rufus with callback memory and controlled overlap
- Premium audio assembly: cold open stinger, intro bed, transitions, sponsor-safe underbeds
- TheLEDGR native reads built in with weekday rotation
- Safer publish logic: auto-pad near-miss runtimes instead of killing the whole run
- OpenAI TTS upgrade path with expressive instructions and automatic fallback
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

# --------------------------------------------------------------------
# ENV / PATHS
# --------------------------------------------------------------------
load_dotenv()

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
TMP_DIR = BASE_DIR / "_tmp_audio"
AUDIO_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

FEED_XML_PATH = BASE_DIR / "feed.xml"
EPISODE_META_PATH = BASE_DIR / "episode_metadata.json"
MARKETING_PACK_PATH = BASE_DIR / "marketing_pack.json"
VIRAL_CAPTION_PATH = BASE_DIR / "viral_caption.txt"
MEMORY_PATH = BASE_DIR / "show_memory.json"

INTRO_PATH = BASE_DIR / "intro.mp3"
OUTRO_PATH = BASE_DIR / "outro.mp3"
TRANSITION_PATH = BASE_DIR / "transition.mp3"

AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/",
).rstrip("/") + "/"

LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/",
).rstrip("/") + "/"

RSS_SETTINGS: Dict[str, str] = {
    "title": os.getenv("RSS_TITLE", "The AI Edge"),
    "link": os.getenv("RSS_LINK", "https://github.com/aisimplify333/Daily-ai-News"),
    "description": os.getenv(
        "RSS_DESCRIPTION",
        "A premium daily AI show with operator-grade analysis, human stakes, and hard receipts.",
    ),
    "author": os.getenv("RSS_AUTHOR", "AI Simplify Media"),
    "email": os.getenv("RSS_EMAIL", "aisimplify333@gmail.com"),
    "image": os.getenv(
        "RSS_IMAGE",
        "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    ),
    "category": os.getenv("RSS_CATEGORY", "Technology"),
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_JSON_MODEL = os.getenv("OPENAI_JSON_MODEL", OPENAI_CHAT_MODEL)
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")

MIN_MINUTES = float(os.getenv("MIN_MINUTES", "24"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "35"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "28"))
WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "172"))
SHORTFALL_TOLERANCE_SECONDS = int(os.getenv("SHORTFALL_TOLERANCE_SECONDS", "30"))

SEGMENT_ATTEMPTS = int(os.getenv("SEGMENT_ATTEMPTS", "3"))
SCRIPT_MAX_TOKENS = int(os.getenv("SCRIPT_MAX_TOKENS", "2400"))
JSON_MAX_TOKENS = int(os.getenv("JSON_MAX_TOKENS", "1800"))
SAVE_SCRIPT = os.getenv("SAVE_SCRIPT", "true").strip().lower() in {"1", "true", "yes"}
KEEP_LAST_EPISODES = int(os.getenv("KEEP_LAST_EPISODES", "60"))
FORCE_REBUILD = os.getenv("FORCE_REBUILD", "false").strip().lower() in {"1", "true", "yes"}
RUN_MARKETING_ASSETS = os.getenv("RUN_MARKETING_ASSETS", "true").strip().lower() in {"1", "true", "yes"}

VOICE_MAP: Dict[str, str] = {
    "ALEX": os.getenv("VOICE_ALEX", "marin"),
    "JAMIE": os.getenv("VOICE_JAMIE", "coral"),
    "RUFUS": os.getenv("VOICE_RUFUS", "cedar"),
}
VOICE_INSTRUCTIONS: Dict[str, str] = {
    "ALEX": (
        "Sound like a sharp premium host in a Manhattan penthouse studio at night. "
        "Fast, amused, confident, highly conversational. Ask the question the audience "
        "is already thinking. Occasional incredulous laugh energy. Keep it human, not announcer-like."
    ),
    "JAMIE": (
        "Warm, emotionally intelligent, reflective, premium broadcast delivery. "
        "Ground every idea in people, families, operators, workers, patients, creators. "
        "Allow occasional soft laughter or disbelief, but stay elegant and controlled."
    ),
    "RUFUS": (
        "Dry, surgical, worldly, slightly British in rhythm without caricature. "
        "You are often on location somewhere important in the world, painting the scene briefly "
        "before landing the factual edge. Calm authority, understated wit, no melodrama."
    ),
}

# audio tuning
TTS_CHUNK_MAX_CHARS = int(os.getenv("TTS_CHUNK_MAX_CHARS", "2600"))
TTS_RETRIES = int(os.getenv("TTS_RETRIES", "3"))
TRIM_THRESH_DB = float(os.getenv("TRIM_THRESH_DB", "-45.0"))
TRIM_LEADING_MS = int(os.getenv("TRIM_LEADING_MS", "70"))
TRIM_TRAILING_MS = int(os.getenv("TRIM_TRAILING_MS", "150"))
SEGMENT_EXPORT_BITRATE = os.getenv("SEGMENT_EXPORT_BITRATE", "192k")
FINAL_EXPORT_BITRATE = os.getenv("FINAL_EXPORT_BITRATE", "192k")

INTRO_STINGER_MS = int(os.getenv("INTRO_STINGER_MS", "4200"))
INTRO_BED_MS = int(os.getenv("INTRO_BED_MS", "8000"))
OUTRO_MS = int(os.getenv("OUTRO_MS", "14000"))
TRANSITION_MS = int(os.getenv("TRANSITION_MS", "1800"))
SPONSOR_BED_MS = int(os.getenv("SPONSOR_BED_MS", "9000"))

STINGER_TARGET_DBFS = float(os.getenv("STINGER_TARGET_DBFS", "-18.0"))
MUSIC_TARGET_DBFS = float(os.getenv("MUSIC_TARGET_DBFS", "-26.0"))
SPONSOR_BED_TARGET_DBFS = float(os.getenv("SPONSOR_BED_TARGET_DBFS", "-28.0"))
VOICE_TARGET_DBFS = float(os.getenv("VOICE_TARGET_DBFS", "-18.0"))
FINAL_LOUDNESS_DBFS = float(os.getenv("FINAL_LOUDNESS_DBFS", "-16.0"))

MIN_COLD_OPEN_LINES = int(os.getenv("MIN_COLD_OPEN_LINES", "6"))
MIN_DIGITS_PER_SEGMENT = int(os.getenv("MIN_DIGITS_PER_SEGMENT", "10"))
MIN_DIGITS_PER_EPISODE = int(os.getenv("MIN_DIGITS_PER_EPISODE", "70"))
MAX_STORIES = int(os.getenv("MAX_STORIES", "5"))

SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
SEGMENT_RE = re.compile(r"^###\s*SEGMENT\s*(\d)\s*$", re.IGNORECASE)
STRICT_EPISODE_FILENAME_RE = re.compile(r"^podcast_\d{4}-\d{2}-\d{2}\.mp3$")

PUBLISHER_BONUS = {
    "reuters": 14,
    "financial times": 14,
    "the wall street journal": 14,
    "wsj": 14,
    "bloomberg": 14,
    "the information": 12,
    "new york times": 10,
    "ft": 10,
    "semafor": 8,
    "techcrunch": 7,
    "the verge": 7,
    "stat": 9,
    "fierce healthcare": 7,
    "wired": 6,
    "axios": 6,
}

GOOGLE_NEWS_RSS: List[Tuple[str, str]] = [
    (
        "strategy",
        "https://news.google.com/rss/search?q=(AI%20OR%20%22artificial%20intelligence%22%20OR%20OpenAI%20OR%20Anthropic%20OR%20Google%20Gemini%20OR%20Meta%20AI)%20(strategy%20OR%20deployment%20OR%20roadmap%20OR%20enterprise%20OR%20CEO%20OR%20policy)%20when:3d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "tools",
        "https://news.google.com/rss/search?q=(AI%20tools%20OR%20copilot%20OR%20developer%20tools%20OR%20benchmark)%20(pricing%20OR%20launch%20OR%20benchmark%20OR%20testing)%20when:3d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "health",
        "https://news.google.com/rss/search?q=(health%20AI%20OR%20clinical%20AI%20OR%20FDA%20AI%20OR%20medical%20AI)%20(study%20OR%20approval%20OR%20hospital%20OR%20trial)%20when:5d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "agents",
        "https://news.google.com/rss/search?q=(AI%20agent%20OR%20agents)%20(security%20OR%20failure%20OR%20enterprise%20OR%20deployment)%20when:3d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "code",
        "https://news.google.com/rss/search?q=(AI%20coding%20OR%20code%20assistant%20OR%20benchmark)%20(real%20code%20OR%20benchmark%20OR%20production)%20when:3d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "regulation",
        "https://news.google.com/rss/search?q=(AI%20OR%20OpenAI%20OR%20Meta%20AI%20OR%20Anthropic)%20(regulator%20OR%20law%20OR%20ban%20OR%20fine%20OR%20probe%20OR%20safety)%20when:5d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "chips",
        "https://news.google.com/rss/search?q=(Nvidia%20OR%20AMD%20OR%20TSMC%20OR%20ASML%20OR%20%22AI%20chips%22)%20(export%20controls%20OR%20earnings%20OR%20guidance%20OR%20capacity%20OR%20data%20center)%20when:5d&hl=en-US&gl=US&ceid=US:en",
    ),
]

THELEDGR_SPOTS = {
    1: {
        "length": 15,
        "title": "The Question",
        "copy": (
            "Today's episode is presented by TheLEDGR. Here's a question — when was the last time "
            "an AI newsletter told you what NOT to trust? Not what launched. Not what raised money. "
            "What actually fails in production, what the FDA really decided, and which tools are not "
            "worth your money. That's TheLEDGR. Five daily AI briefings. Free. T-H-E-L-E-D-G-R dot I-O."
        ),
    },
    2: {
        "length": 15,
        "title": "Already Knows",
        "copy": (
            "Quick word from our sponsor TheLEDGR. Someone in your industry already knows which AI "
            "coding tools score twenty percent on real code. They already know which enterprise agents "
            "are failing in production. They already read the clinical AI evidence before the committee "
            "meeting. They're reading TheLEDGR. Five free daily briefings. T-H-E-L-E-D-G-R dot I-O."
        ),
    },
    3: {
        "length": 15,
        "title": "Tracked Publicly",
        "copy": (
            "This episode is brought to you by TheLEDGR — the only AI media network that tracks every "
            "prediction on a public ledger. AI strategy, developer tools, health AI, enterprise agents, "
            "code benchmarks — five specialized briefings that tell you what is working, what is failing, "
            "and what to do about it. When they get it wrong, they publish it. T-H-E-L-E-D-G-R dot I-O. It's free."
        ),
    },
    4: {
        "length": 15,
        "title": "Fifteen Seconds of Truth",
        "copy": (
            "Brought to you by TheLEDGR. Five AI briefings every morning. Under five minutes each. "
            "Zero hype tolerated. Every prediction on the record. If your AI newsletter has never saved "
            "you from a bad decision — you need a different newsletter. T-H-E-L-E-D-G-R dot I-O. Free."
        ),
    },
    5: {
        "length": 30,
        "title": "The Prediction Engine",
        "copy": (
            "This portion of the show is brought to you by TheLEDGR. So here is something no other AI "
            "newsletter does. They make specific predictions — with confidence scores and deadlines — "
            "and track every single one publicly. Which FDA decision will go which way. Which enterprise "
            "agents will fail at scale. Which coding benchmarks are inflated. And when they are wrong? "
            "It is right there on the ledger for everyone to see. That kind of accountability is rare in media — period. "
            "Five free daily AI briefings across strategy, tools, health, agents, and code. Subscribe at T-H-E-L-E-D-G-R dot I-O."
        ),
    },
    6: {
        "length": 30,
        "title": "Founded by Frustration",
        "copy": (
            "I want to tell you about TheLEDGR. It started when a founder got laid off, opened his inbox, "
            "and realized every AI newsletter said the same thing. Same press releases. Same hype. "
            "Same tools-of-the-day dead in a month. So he built what he wished existed. Five daily briefings — "
            "each one covering a different side of AI. One for strategy. One that tells you which tools to skip. "
            "One that covers health AI with clinical evidence grades. One that publishes enterprise agent failure "
            "postmortems. And one that tests AI coding tools on real production code. Every prediction tracked. "
            "Zero hype. That's TheLEDGR. T-H-E-L-E-D-G-R dot I-O."
        ),
    },
    7: {
        "length": 30,
        "title": "The Meeting",
        "copy": (
            "Quick message from TheLEDGR. Picture this — you are in a meeting tomorrow and someone across "
            "the table mentions an AI agent security breach you have not heard of. Or a clinical AI study "
            "that changes your roadmap. Or a coding benchmark that proves the tool your team just bought "
            "fails on real code. Or a prediction about your market that is already on the public record. "
            "That is what TheLEDGR covers. Five specialized AI briefings. Every morning. Under five minutes each. "
            "Do not be the last person in the room to know. T-H-E-L-E-D-G-R dot I-O. Free."
        ),
    },
    8: {
        "length": 30,
        "title": "What Makes Them Different",
        "copy": (
            "Let me tell you why TheLEDGR is different from every AI newsletter in your inbox right now. "
            "Their AI strategy briefing tracks predictions publicly — every hit and every miss. Their tools "
            "briefing tells you what to skip, not just what to try — with real pricing. Their health AI briefing "
            "uses clinical evidence grades that a hospital executive would trust. Their enterprise agents briefing "
            "covers deployment failures that other publications will not touch. And their code briefing tests AI coding "
            "tools on actual production codebases — not vendor demos. Five briefings. Each under five minutes. "
            "Each one designed to save you from a bad decision. T-H-E-L-E-D-G-R dot I-O."
        ),
    },
}

THELEDGR_KICKERS = [
    "For the Record. That's TheLEDGR.",
    "Five briefings. Five minutes. Zero hype.",
    "Every prediction tracked. Every miss published. That's the standard.",
    "If your AI newsletter has never told you NOT to buy something — you need TheLEDGR.",
    "T-H-E-L-E-D-G-R dot I-O. Free. No catch. Just signal.",
]

WEEKDAY_ROTATION = {
    0: (1, 6),
    1: (2, 5),
    2: (1, 7),
    3: (3, 8),
    4: (4, 6),
    5: (3, 7),
    6: (2, 8),
}


@dataclass
class StoryItem:
    bucket: str
    title: str
    publisher: str
    published: str
    link: str
    summary: str
    page_text: str = ""
    score: float = 0.0


@dataclass
class StoryBrief:
    bucket: str
    title: str
    publisher: str
    published: str
    link: str
    summary: str
    why_now: str
    human_stakes: str
    market_stakes: str
    policy_stakes: str
    alex_angle: str
    jamie_angle: str
    rufus_angle: str
    listener_question: str
    confidence: str
    data_points: List[str]
    scene: str
    score: float


def _safe_print(msg: str) -> None:
    print(msg, flush=True)


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


def _today_str() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


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
        return " - ".join(parts[:-1]), parts[-1]
    return title.strip(), ""


def _published_iso_from_entry(entry) -> str:
    try:
        tt = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if tt:
            d = dt.datetime(*tt[:6], tzinfo=dt.timezone.utc)
            return d.isoformat()
    except Exception:
        pass
    return (getattr(entry, "published", "") or getattr(entry, "updated", "") or "").strip()[:64]


def _parse_dt(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _digit_count(text: str) -> int:
    return len(re.findall(r"\d", text or ""))


def _extract_json_object(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = raw.strip()
    fences = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    fences = re.sub(r"\s*```$", "", fences).strip()
    for candidate in (raw, fences):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    m = re.search(r"(\{.*\})", fences, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def _recency_score(published: str) -> float:
    parsed = _parse_dt(published)
    if not parsed:
        return 0.0
    age_h = max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 3600)
    if age_h <= 6:
        return 20
    if age_h <= 12:
        return 15
    if age_h <= 24:
        return 10
    if age_h <= 48:
        return 5
    return 1


def _publisher_score(pub: str) -> float:
    blob = (pub or "").lower()
    for key, bonus in PUBLISHER_BONUS.items():
        if key in blob:
            return float(bonus)
    return 2.0 if blob else 0.0


def _numeric_score(text: str) -> float:
    score = 0.0
    score += 2.0 * _digit_count(text)
    if "$" in text or "€" in text or "£" in text:
        score += 10
    if "%" in text:
        score += 8
    for kw, pts in [("billion", 10), ("million", 8), ("fda", 5), ("benchmark", 5), ("security", 5), ("trial", 6), ("earnings", 5), ("guidance", 5)]:
        if kw in text.lower():
            score += pts
    return score


def _consequence_score(text: str) -> float:
    blob = text.lower()
    score = 0.0
    for kw, pts in [
        ("hospital", 8), ("patient", 8), ("enterprise", 7), ("security", 7), ("breach", 8),
        ("regulator", 7), ("lawsuit", 6), ("fda", 7), ("deployment", 6), ("production", 6),
        ("code", 4), ("chips", 5), ("data center", 5), ("market", 5), ("roadmap", 4),
    ]:
        if kw in blob:
            score += pts
    return score


def _item_score(item: StoryItem) -> float:
    body = f"{item.title} {item.summary} {item.page_text}"
    return _recency_score(item.published) + _publisher_score(item.publisher) + _numeric_score(body) + _consequence_score(body)


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def _sentence_chunks(text: str, max_chars: int) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sents = re.split(r"(?<=[.!?])\s+", text)
    out: List[str] = []
    cur = ""
    for s in sents:
        if not s:
            continue
        if len(cur) + len(s) + 1 <= max_chars:
            cur = (cur + " " + s).strip()
        else:
            if cur:
                out.append(cur)
            if len(s) <= max_chars:
                cur = s
            else:
                for i in range(0, len(s), max_chars):
                    out.append(s[i:i + max_chars].strip())
                cur = ""
    if cur:
        out.append(cur)
    return out


def generate_text(prompt: str, system: str, temperature: float = 0.7, max_tokens: int = 1800) -> str:
    resp = openai_client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def generate_json(prompt: str, system: str, required_keys: List[str], max_tokens: int = 1400) -> Dict[str, object]:
    last_raw = ""
    for _ in range(3):
        raw = generate_text(
            prompt=prompt,
            system=system + " Return valid JSON object only. No markdown.",
            temperature=0.2,
            max_tokens=max_tokens,
        )
        last_raw = raw
        obj = _extract_json_object(raw)
        if isinstance(obj, dict) and all(k in obj for k in required_keys):
            return obj
    raise RuntimeError(f"Failed to parse required JSON keys {required_keys}. Raw: {last_raw[:500]}")


def fetch_rss_items(max_per_feed: int = 10) -> List[StoryItem]:
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    items: List[StoryItem] = []
    for bucket, url in GOOGLE_NEWS_RSS:
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
                        StoryItem(
                            bucket=bucket,
                            title=title,
                            publisher=publisher,
                            published=published,
                            link=link,
                            summary=summary,
                        )
                    )
        except Exception as e:
            _safe_print(f"    ⚠️ RSS fetch failed for {bucket}: {e}")

    seen = set()
    deduped: List[StoryItem] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def fetch_page_text(url: str, timeout: int = 15) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "form", "nav"]):
            tag.decompose()
        paras = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "article", "section", "h1", "h2", "h3"])]
        text = re.sub(r"\s+", " ", " ".join(p for p in paras if p)).strip()
        return text[:8000]
    except Exception:
        return ""


def extract_data_points(text: str, summary: str, limit: int = 6) -> List[str]:
    source = " ".join([summary or "", text or ""])
    source = re.sub(r"\s+", " ", source).strip()
    if not source:
        return []
    sents = re.split(r"(?<=[.!?])\s+", source)
    scored: List[Tuple[int, str]] = []
    for s in sents:
        clean = s.strip()
        if len(clean) < 35:
            continue
        score = 0
        digits = _digit_count(clean)
        if digits:
            score += digits * 3
        if any(tok in clean.lower() for tok in ["million", "billion", "%", "fda", "trial", "enterprise", "security", "benchmark", "code", "patients", "revenue", "deadline", "date", "hours"]):
            score += 4
        if score > 0:
            scored.append((score, _truncate(clean, 220)))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    seen = set()
    for _, sent in scored:
        key = sent.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(sent)
        if len(out) >= limit:
            break
    return out


def _infer_scene(bucket: str, title: str, summary: str, publisher: str) -> str:
    blob = f"{bucket} {title} {summary} {publisher}".lower()
    if "europe" in blob or "commission" in blob or "brussels" in blob:
        return "Brussels, outside a regulator's marble corridor"
    if "fda" in blob or "clinical" in blob or "hospital" in blob:
        return "a hospital command center before dawn"
    if "nvidia" in blob or "chips" in blob or "tsmc" in blob or "asml" in blob:
        return "a chip corridor between Taipei and Silicon Valley"
    if "security" in blob or "breach" in blob:
        return "a cyber war room lit by dashboards"
    if "code" in blob or "benchmark" in blob or "developer" in blob:
        return "a late-night engineering floor with test dashboards glowing"
    if "market" in blob or "earnings" in blob or "revenue" in blob:
        return "lower Manhattan with futures still flickering"
    return "a glass-walled room above the city, with the world still moving below"


def build_story_brief(item: StoryItem) -> StoryBrief:
    page_text = fetch_page_text(item.link)
    item.page_text = page_text[:6000]
    item.score = _item_score(item)

    datapoints = extract_data_points(item.page_text, item.summary, limit=6)
    scene_hint = _infer_scene(item.bucket, item.title, item.summary, item.publisher)

    prompt = f"""
Create a concise story brief for a premium daily AI podcast.

TITLE: {item.title}
PUBLISHER: {item.publisher}
BUCKET: {item.bucket}
PUBLISHED: {item.published}
SUMMARY: {item.summary}

PAGE EXCERPT:
{_truncate(item.page_text, 3500)}

DATA POINTS:
{json.dumps(datapoints, ensure_ascii=False)}

Return JSON with keys:
why_now, human_stakes, market_stakes, policy_stakes,
alex_angle, jamie_angle, rufus_angle,
listener_question, confidence, scene
""".strip()

    data = generate_json(
        prompt=prompt,
        system=(
            "You are the showrunner for a premium daily AI news podcast. "
            "Write crisp, concrete, non-hyped briefing language. "
            "Alex angle = sharp listener question. "
            "Jamie angle = human stakes. "
            "Rufus angle = data / incentive / regulatory edge."
        ),
        required_keys=[
            "why_now",
            "human_stakes",
            "market_stakes",
            "policy_stakes",
            "alex_angle",
            "jamie_angle",
            "rufus_angle",
            "listener_question",
            "confidence",
            "scene",
        ],
        max_tokens=JSON_MAX_TOKENS,
    )

    return StoryBrief(
        bucket=item.bucket,
        title=item.title,
        publisher=item.publisher,
        published=item.published,
        link=item.link,
        summary=item.summary,
        why_now=str(data["why_now"]).strip(),
        human_stakes=str(data["human_stakes"]).strip(),
        market_stakes=str(data["market_stakes"]).strip(),
        policy_stakes=str(data["policy_stakes"]).strip(),
        alex_angle=str(data["alex_angle"]).strip(),
        jamie_angle=str(data["jamie_angle"]).strip(),
        rufus_angle=str(data["rufus_angle"]).strip(),
        listener_question=str(data["listener_question"]).strip(),
        confidence=str(data["confidence"]).strip(),
        data_points=datapoints[:6],
        scene=str(data.get("scene") or scene_hint).strip() or scene_hint,
        score=item.score,
    )


def select_story_briefs() -> List[StoryBrief]:
    raw_items = fetch_rss_items(max_per_feed=10)
    if not raw_items:
        raise RuntimeError("No stories returned from RSS feeds.")

    prelim: List[StoryItem] = []
    for item in raw_items:
        item.score = _item_score(item)
        prelim.append(item)

    prelim.sort(key=lambda x: x.score, reverse=True)

    picked: List[StoryBrief] = []
    seen_buckets = set()
    for item in prelim[:20]:
        try:
            brief = build_story_brief(item)
        except Exception as e:
            _safe_print(f"    ⚠️ Story brief failed for '{item.title[:60]}': {e}")
            continue

        if len(picked) < 3 and brief.bucket in seen_buckets:
            continue
        picked.append(brief)
        seen_buckets.add(brief.bucket)
        if len(picked) >= MAX_STORIES:
            break

    if len(picked) < 3:
        raise RuntimeError("Not enough story briefs to assemble a strong show.")

    picked.sort(key=lambda x: x.score, reverse=True)
    return picked[:MAX_STORIES]


def load_show_memory() -> Dict[str, object]:
    if not MEMORY_PATH.exists():
        return {
            "callbacks": [
                "Follow the receipts, not the demo.",
                "If it only works in a keynote, it does not work.",
                "The room gets quieter right before the real number lands.",
            ],
            "running_bits": [
                "Rufus has apparently flown somewhere just to ruin a hype cycle.",
                "Jamie has to remind the room that actual humans exist.",
                "Alex keeps asking the question everyone thought but did not say out loud.",
            ],
            "recent_predictions": [],
        }
    try:
        obj = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save_show_memory(memory: Dict[str, object]) -> None:
    MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def rotate_sponsors_for_today(today: str) -> Dict[str, Dict[str, object]]:
    d = dt.date.fromisoformat(today)
    pre_id, mid_id = WEEKDAY_ROTATION.get(d.weekday(), (1, 6))
    return {
        "pre": {"slot_id": pre_id, **THELEDGR_SPOTS[pre_id]},
        "mid": {"slot_id": mid_id, **THELEDGR_SPOTS[mid_id]},
        "button": {"copy": random.choice(THELEDGR_KICKERS)},
    }


def _story_block(stories: List[StoryBrief]) -> str:
    blocks: List[str] = []
    for i, s in enumerate(stories, start=1):
        dps = "\n".join(f"- {x}" for x in s.data_points[:6]) or "- No explicit figures located."
        blocks.append(
            f"""STORY {i}
Title: {s.title}
Publisher: {s.publisher}
Bucket: {s.bucket}
Published: {s.published}
Why now: {s.why_now}
Human stakes: {s.human_stakes}
Market stakes: {s.market_stakes}
Policy stakes: {s.policy_stakes}
Alex angle: {s.alex_angle}
Jamie angle: {s.jamie_angle}
Rufus angle: {s.rufus_angle}
Listener question: {s.listener_question}
Confidence: {s.confidence}
Rufus scene: {s.scene}
Data points:
{dps}
Link: {s.link}"""
        )
    return "\n\n".join(blocks)


def _script_targets() -> Tuple[int, Dict[int, int], int]:
    total_words = int(round(TARGET_MINUTES * WORDS_PER_MINUTE))
    segment_targets = {
        1: int(total_words * 0.16),
        2: int(total_words * 0.22),
        3: int(total_words * 0.20),
        4: int(total_words * 0.24),
        5: int(total_words * 0.18),
    }
    min_total = int(MIN_MINUTES * WORDS_PER_MINUTE)
    max_total = int(MAX_MINUTES * WORDS_PER_MINUTE)
    for k in segment_targets:
        segment_targets[k] = max(340, segment_targets[k])
    return min_total, segment_targets, max_total


def _segment_assignment(seg_num: int) -> str:
    mapping = {
        1: (
            "Cold open starts inside tension or mild disagreement. Alex must ask the question the listener is already asking. "
            "Jamie reacts like a real person. Rufus lands one dry line. Then [MUSIC]. Then a premium welcome and lineup."
        ),
        2: (
            "Only Alex and Jamie. Make this the human and operator deep dive. Include one interruption, one warm laugh or smile beat, "
            "and at least one listener-facing decision prompt."
        ),
        3: (
            "Rufus takes a featured story and goes on location somewhere in the world. He brings a scene, then the facts, then the money, "
            "policy, or incentive edge. Alex can keep him moving. Mid-show TheLEDGR native read belongs here."
        ),
        4: (
            "All three hosts together. Cover the remaining stories with tempo. Include one callback, one clean interruption, one smart joke, "
            "and one direct audience question."
        ),
        5: (
            "Close with a practical takeaway. Alex = operator action. Jamie = human consequence. Rufus = contrarian prediction. "
            "Finish with a short TheLEDGR button and a premium sign-off that makes tomorrow feel necessary."
        ),
    }
    return mapping[seg_num]


def _segment_header(seg_num: int) -> str:
    return f"### SEGMENT {seg_num}"


def _segment_prompt(seg_num: int, date_str: str, stories: List[StoryBrief], sponsors: Dict[str, Dict[str, object]], memory: Dict[str, object], seg_word_target: int) -> str:
    pre = sponsors["pre"]["copy"]
    mid = sponsors["mid"]["copy"]
    button = sponsors["button"]["copy"]
    callbacks = memory.get("callbacks", [])[:3]
    running_bits = memory.get("running_bits", [])[:3]

    special = ""
    if seg_num == 1:
        special = f"""
SPECIAL:
- The FIRST spoken exchange must already be in motion.
- After the cold open, output a standalone line: [MUSIC]
- Weave the pre-roll TheLEDGR spot naturally after the welcome or first transition using this copy as source material:
{pre}
"""
    elif seg_num == 2:
        special = """
SPECIAL:
- Output ONLY ALEX and JAMIE lines after the segment marker.
- No RUFUS lines in Segment 2.
"""
    elif seg_num == 3:
        special = f"""
SPECIAL:
- Rufus opens with a brief on-location scene, never more than 2 sentences before facts start.
- Weave the mid-roll TheLEDGR read naturally using this copy as source material:
{mid}
- The sponsor should sound native, smart, and premium, not like a stiff ad break.
"""
    elif seg_num == 4:
        special = """
SPECIAL:
- At least one exchange should contain a quick cut-off or overlap cue like wait, hold on, or no, but.
- Keep it polished. Jostling, not chaos.
"""
    elif seg_num == 5:
        special = f"""
SPECIAL:
- End with a short TheLEDGR button or kicker using this source line:
{button}
- Make the final line feel like a quiet Manhattan-at-night sign-off.
"""

    story_block = _story_block(stories)
    prompt = f"""
Write ONLY {_segment_header(seg_num)} for a premium daily podcast called The AI Edge dated {date_str}.

SHOW AESTHETIC:
Glass-walled penthouse studio in Manhattan after dark, overlooking Central Park.
Expensive, intimate, sharp, calm, intelligent. Not morning zoo radio.

CAST:
- ALEX: host. Fast, amused, sharp. He asks the question the listener already has.
- JAMIE: warm, empathetic, reflective. He brings the world, the people, the cost.
- RUFUS: data, edge, incentives, receipts. Dry wit. Often on location somewhere in the world.

CHEMISTRY RULES:
- Alex interrupts most often, but elegantly.
- Jamie gets the warm reaction laughs and human pushback.
- Rufus talks least but lands the sharpest undercuts.
- Include at least one moment of jostling or amused friction in most segments.
- Humor should feel lived-in, not punchline-y.
- Do not imitate real public figures. Use only the energy/archetype.

NON-NEGOTIABLES:
- FIRST line must be exactly {_segment_header(seg_num)}
- Target length: about {seg_word_target} words
- Mention the publisher when introducing each story
- Use at least 2 explicit data points from the provided data lines for each story discussed
- Do NOT invent facts or numbers
- All spoken lines must begin with ALEX:, JAMIE:, or RUFUS:
- Avoid generic transitions like let's dive in

WHAT THIS SEGMENT MUST DO:
{_segment_assignment(seg_num)}

CALLBACK MATERIAL:
- callbacks: {json.dumps(callbacks, ensure_ascii=False)}
- running bits: {json.dumps(running_bits, ensure_ascii=False)}

{special}

TODAY'S STORIES:
{story_block}

Now output only {_segment_header(seg_num)} and its dialogue.
""".strip()
    return prompt


def _sanitize_dialogue_only(text: str) -> str:
    keep: List[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper() == "[MUSIC]":
            keep.append("[MUSIC]")
            continue
        if SEGMENT_RE.match(stripped):
            keep.append(stripped.upper().replace("SEGMENT", "SEGMENT"))
            continue
        if SPEAKER_RE.match(stripped):
            m = SPEAKER_RE.match(stripped)
            speaker = m.group(1).upper()
            content = m.group(2).strip()
            keep.append(f"{speaker}: {content}")
    return "\n".join(keep).strip()


def _segment_validate(seg_text: str, seg_num: int, min_words: int) -> List[str]:
    issues: List[str] = []
    if not seg_text.strip().startswith(_segment_header(seg_num)):
        issues.append(f"Missing required header {_segment_header(seg_num)}")

    lines = [ln.strip() for ln in seg_text.splitlines() if ln.strip()]
    for ln in lines[1:]:
        if ln.upper() == "[MUSIC]":
            continue
        if not SPEAKER_RE.match(ln):
            issues.append("Found non-dialogue line")
            break

    if seg_num == 2 and re.search(r"^RUFUS\s*:", seg_text, flags=re.IGNORECASE | re.MULTILINE):
        issues.append("Segment 2 must contain only Alex and Jamie")

    if seg_num == 1:
        if "[MUSIC]" not in seg_text:
            issues.append("Segment 1 missing [MUSIC]")
        else:
            idx = lines.index("[MUSIC]") if "[MUSIC]" in lines else -1
            pre_music = [x for x in lines[1:idx] if SPEAKER_RE.match(x)]
            if len(pre_music) < MIN_COLD_OPEN_LINES:
                issues.append("Cold open too short before [MUSIC]")

    wc = _word_count(seg_text)
    if wc < min_words:
        issues.append(f"Segment too short ({wc} words)")
    if _digit_count(seg_text) < MIN_DIGITS_PER_SEGMENT:
        issues.append("Low numeric density")
    return issues


def _segment_repair_prompt(seg_num: int, seg_text: str, issues: List[str], seg_word_target: int) -> str:
    return f"""
Repair this segment so it passes the format and quality checks.

Issues:
{json.dumps(issues, ensure_ascii=False)}

Broken segment:
{seg_text}

Re-write ONLY {_segment_header(seg_num)} and its dialogue.
Target about {seg_word_target} words.
Remember the same cast chemistry, story facts, and premium style.
""".strip()


def write_segment(seg_num: int, date_str: str, stories: List[StoryBrief], sponsors: Dict[str, Dict[str, object]], memory: Dict[str, object], seg_word_target: int) -> str:
    min_words = max(280, int(seg_word_target * 0.76))
    prompt = _segment_prompt(seg_num, date_str, stories, sponsors, memory, seg_word_target)
    seg_text = ""
    issues: List[str] = []
    for attempt in range(1, SEGMENT_ATTEMPTS + 1):
        if attempt == 1:
            raw = generate_text(
                prompt=prompt,
                system=(
                    "You are the elite showrunner and dialogue writer for a premium daily AI podcast. "
                    "Write with chemistry, emotional realism, and hard factual grounding. "
                    "Never use bullet points inside the output."
                ),
                temperature=0.72 if seg_num in (1, 4, 5) else 0.64,
                max_tokens=SCRIPT_MAX_TOKENS,
            )
        else:
            raw = generate_text(
                prompt=_segment_repair_prompt(seg_num, seg_text, issues, seg_word_target),
                system="You repair podcast dialogue to strict format while keeping it natural and premium.",
                temperature=0.35,
                max_tokens=SCRIPT_MAX_TOKENS,
            )
        seg_text = _sanitize_dialogue_only(raw)
        issues = _segment_validate(seg_text, seg_num, min_words)
        if not issues:
            return seg_text
    raise RuntimeError(f"Failed to produce valid segment {seg_num}: {issues}")


def _pad_script_to_min_words(script: str, min_words: int) -> str:
    wc = _word_count(script)
    if wc >= min_words:
        return script
    need = min_words - wc
    prompt = f"""
Add about {max(220, min(600, need + 120))} words to SEGMENT 4 of this script.
Keep all format rules.
Add listener-facing value, concrete data, and natural chemistry.

Current script:
{script}
"""
    addon = generate_text(
        prompt=prompt,
        system="You extend podcast scripts while preserving exact format and speaker labels.",
        temperature=0.55,
        max_tokens=1400,
    )
    addon = _sanitize_dialogue_only(addon)
    m = re.search(r"^###\s*SEGMENT\s*5\b", script, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return script
    body_lines = [ln for ln in addon.splitlines() if not SEGMENT_RE.match(ln.strip())]
    return (script[:m.start()].rstrip() + "\n" + "\n".join(body_lines).strip() + "\n\n" + script[m.start():].lstrip()).strip()


def _trim_script_to_max_words(script: str, max_words: int) -> str:
    if _word_count(script) <= max_words:
        return script
    lines = script.splitlines()
    while _word_count("\n".join(lines)) > max_words and len(lines) > 20:
        for idx in range(len(lines) - 1, -1, -1):
            if SPEAKER_RE.match(lines[idx].strip()):
                del lines[idx]
                break
        else:
            break
    return "\n".join(lines).strip()


def validate_script(script: str) -> List[str]:
    issues: List[str] = []
    for i in range(1, 6):
        if not re.search(rf"^###\s*SEGMENT\s*{i}\b", script, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(f"Missing segment {i}")
    for ln in script.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.upper() == "[MUSIC]":
            continue
        if SEGMENT_RE.match(stripped):
            continue
        if not SPEAKER_RE.match(stripped):
            issues.append("Found non-dialogue content")
            break
    seg2 = re.search(r"^###\s*SEGMENT\s*2\b(.*?)(^###\s*SEGMENT\s*3\b|\Z)", script, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if seg2 and re.search(r"^RUFUS\s*:", seg2.group(1), flags=re.MULTILINE | re.IGNORECASE):
        issues.append("Rufus appears in Segment 2")
    if _digit_count(script) < MIN_DIGITS_PER_EPISODE:
        issues.append("Episode numeric density too low")
    min_total, _, max_total = _script_targets()
    wc = _word_count(script)
    if wc < min_total:
        issues.append(f"Episode too short in words ({wc})")
    if wc > max_total:
        issues.append(f"Episode too long in words ({wc})")
    return issues


def compose_script(stories: List[StoryBrief], sponsors: Dict[str, Dict[str, object]], today: str, memory: Dict[str, object]) -> str:
    min_total, seg_targets, max_total = _script_targets()
    parts: List[str] = []
    for seg_num in range(1, 6):
        _safe_print(f" >> 🚀 WRITING SEGMENT {seg_num}...")
        part = write_segment(seg_num, today, stories, sponsors, memory, seg_targets[seg_num])
        parts.append(part)

    script = "\n\n".join(parts).strip()
    if _word_count(script) < min_total:
        script = _pad_script_to_min_words(script, min_total)
    if _word_count(script) > max_total:
        script = _trim_script_to_max_words(script, max_total)

    issues = validate_script(script)
    if issues:
        raise RuntimeError(f"Final script failed validation: {issues}")
    return script


def _lead_silence_ms(seg: AudioSegment, thresh_db: float) -> int:
    pos = 0
    step = 10
    while pos < len(seg):
        if seg[pos: pos + step].dBFS > thresh_db:
            return pos
        pos += step
    return pos


def trim_silence(seg: AudioSegment) -> AudioSegment:
    if len(seg) < 50:
        return seg
    lead = min(_lead_silence_ms(seg, TRIM_THRESH_DB), TRIM_LEADING_MS)
    trail = min(_lead_silence_ms(seg.reverse(), TRIM_THRESH_DB), TRIM_TRAILING_MS)
    if len(seg) <= lead + trail + 20:
        return seg
    return seg[lead: len(seg) - trail]


def match_level(seg: AudioSegment, target_dbfs: float) -> AudioSegment:
    if seg.dBFS == float("-inf"):
        return seg
    return seg.apply_gain(target_dbfs - seg.dBFS)


def _pad_to_length(seg: AudioSegment, length_ms: int) -> AudioSegment:
    if len(seg) >= length_ms:
        return seg[:length_ms]
    return seg + AudioSegment.silent(duration=length_ms - len(seg))


def duck_music_under_voice(voice: AudioSegment, music: AudioSegment, duck_db: float = 12.0, threshold_dbfs: float = -34.0, window_ms: int = 40) -> AudioSegment:
    voice = voice if voice.channels == 2 else voice.set_channels(2)
    music = _pad_to_length(music if music.channels == 2 else music.set_channels(2), len(voice))
    out = AudioSegment.empty()
    for i in range(0, len(voice), window_ms):
        v = voice[i:i+window_ms]
        m = music[i:i+window_ms]
        if v.dBFS != float("-inf") and v.dBFS > threshold_dbfs:
            m = m.apply_gain(-duck_db)
        out += m
    return out.overlay(voice)


def _ffmpeg_atempo(in_path: Path, out_path: Path, speed: float) -> None:
    if not _has_ffmpeg():
        shutil.copyfile(in_path, out_path)
        return
    speed = max(0.5, min(2.0, speed))
    _run([
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-filter:a", f"atempo={speed}",
        str(out_path),
    ])


def _voice_speed(speaker: str) -> float:
    return {
        "ALEX": float(os.getenv("SPEED_ALEX", "1.02")),
        "JAMIE": float(os.getenv("SPEED_JAMIE", "1.00")),
        "RUFUS": float(os.getenv("SPEED_RUFUS", "0.98")),
    }.get(speaker.upper(), 1.0)


def tts_to_file(text: str, speaker: str, out_path: Path) -> None:
    voice = VOICE_MAP[speaker]
    instructions = VOICE_INSTRUCTIONS[speaker]
    chunks = _sentence_chunks(text, TTS_CHUNK_MAX_CHARS)
    if not chunks:
        raise RuntimeError("Empty TTS text")

    rendered: List[AudioSegment] = []
    for idx, chunk in enumerate(chunks, start=1):
        part_mp3 = TMP_DIR / f"{speaker.lower()}_{uuid.uuid4().hex}_{idx}.mp3"
        last_err = None
        for attempt in range(1, TTS_RETRIES + 1):
            try:
                with openai_client.audio.speech.with_streaming_response.create(
                    model=OPENAI_TTS_MODEL,
                    voice=voice,
                    input=chunk,
                    instructions=instructions,
                ) as response:
                    response.stream_to_file(part_mp3)
                break
            except TypeError:
                try:
                    with openai_client.audio.speech.with_streaming_response.create(
                        model=OPENAI_TTS_MODEL,
                        voice=voice,
                        input=chunk,
                    ) as response:
                        response.stream_to_file(part_mp3)
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.2 * attempt)
            except Exception as e:
                last_err = e
                time.sleep(1.2 * attempt)
        else:
            raise RuntimeError(f"TTS failed for {speaker}: {last_err}")

        audio = AudioSegment.from_file(part_mp3)
        audio = trim_silence(audio)
        audio = match_level(audio, VOICE_TARGET_DBFS)
        rendered.append(audio)

    merged = AudioSegment.silent(duration=0)
    for idx, seg in enumerate(rendered):
        merged += seg
        if idx < len(rendered) - 1:
            merged += AudioSegment.silent(duration=160)

    temp_export = TMP_DIR / f"{speaker.lower()}_{uuid.uuid4().hex}_merged.mp3"
    merged.export(temp_export, format="mp3", bitrate=SEGMENT_EXPORT_BITRATE)

    speed = _voice_speed(speaker)
    if abs(speed - 1.0) > 0.01:
        _ffmpeg_atempo(temp_export, out_path, speed)
    else:
        shutil.copyfile(temp_export, out_path)


def script_to_utterances(script: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        mseg = SEGMENT_RE.match(stripped)
        if mseg:
            out.append(("META", f"SEGMENT_{int(mseg.group(1))}"))
            continue
        if stripped.upper() == "[MUSIC]":
            out.append(("MUSIC", "[MUSIC]"))
            continue
        m = SPEAKER_RE.match(stripped)
        if m:
            out.append((m.group(1).upper(), m.group(2).strip()))
    return out


def load_music_slice(path: Path, ms: int, target_dbfs: float) -> Optional[AudioSegment]:
    if not path.exists():
        return None
    seg = AudioSegment.from_file(path)
    if ms > 0:
        seg = seg[:ms]
    return match_level(seg, target_dbfs)


def master_final_audio_ffmpeg(in_path: Path, out_path: Path) -> None:
    _run([
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-af",
        "acompressor=threshold=-18dB:ratio=3:attack=8:release=120:makeup=3,loudnorm=I=-16:TP=-1.5:LRA=9",
        "-c:a", "libmp3lame",
        "-b:a", FINAL_EXPORT_BITRATE,
        str(out_path),
    ])


def assemble_episode(script: str, today: str, run_tmp: Path) -> Path:
    utterances = script_to_utterances(script)
    intro_stinger = load_music_slice(INTRO_PATH, INTRO_STINGER_MS, STINGER_TARGET_DBFS)
    intro_bed = load_music_slice(INTRO_PATH, INTRO_BED_MS, MUSIC_TARGET_DBFS)
    transition = load_music_slice(TRANSITION_PATH, TRANSITION_MS, MUSIC_TARGET_DBFS)
    sponsor_bed = load_music_slice(TRANSITION_PATH if TRANSITION_PATH.exists() else INTRO_PATH, SPONSOR_BED_MS, SPONSOR_BED_TARGET_DBFS)
    outro = load_music_slice(OUTRO_PATH, OUTRO_MS, MUSIC_TARGET_DBFS)

    final = AudioSegment.silent(duration=0)
    first_spoken_after_music = False
    current_segment = 0

    for idx, (speaker, text) in enumerate(utterances):
        if speaker == "META":
            seg_num = int(text.split("_")[-1])
            if seg_num > 1 and transition is not None:
                final += transition.fade_in(120).fade_out(300)
                final += AudioSegment.silent(duration=160)
            current_segment = seg_num
            continue

        if speaker == "MUSIC":
            if intro_stinger is not None:
                final += intro_stinger.fade_in(100).fade_out(700)
                final += AudioSegment.silent(duration=120)
                first_spoken_after_music = True
            continue

        out_path = run_tmp / f"{idx:04d}_{speaker.lower()}.mp3"
        tts_to_file(text, speaker, out_path)
        voice_seg = AudioSegment.from_file(out_path)
        voice_seg = match_level(trim_silence(voice_seg), VOICE_TARGET_DBFS)

        lowered_text = text.lower()
        use_sponsor_bed = (
            "theledgr" in lowered_text or
            (speaker == "RUFUS" and current_segment == 3 and sponsor_bed is not None and idx < len(utterances) - 1)
        )

        if first_spoken_after_music and intro_bed is not None:
            final += duck_music_under_voice(voice_seg, intro_bed)
            first_spoken_after_music = False
        elif use_sponsor_bed and sponsor_bed is not None:
            final += duck_music_under_voice(voice_seg, sponsor_bed)
        else:
            final += voice_seg

        final += AudioSegment.silent(duration=140)

    if outro is not None:
        final += AudioSegment.silent(duration=220)
        final += outro.fade_in(800).fade_out(1200)

    temp_mix = run_tmp / f"podcast_{today}_premaster.mp3"
    final.export(temp_mix, format="mp3", bitrate=FINAL_EXPORT_BITRATE)

    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"
    if _has_ffmpeg():
        mastered = run_tmp / f"podcast_{today}_mastered.mp3"
        master_final_audio_ffmpeg(temp_mix, mastered)
        shutil.copyfile(mastered, final_mp3)
    else:
        final_audio = AudioSegment.from_file(temp_mix)
        final_audio = match_level(final_audio, FINAL_LOUDNESS_DBFS)
        final_audio.export(final_mp3, format="mp3", bitrate=FINAL_EXPORT_BITRATE)
    return final_mp3


def generate_marketing_pack(stories: List[StoryBrief], date_str: str, listen_url: str) -> Dict[str, str]:
    compact = [
        {
            "title": s.title,
            "publisher": s.publisher,
            "why_now": s.why_now,
            "human_stakes": s.human_stakes,
            "market_stakes": s.market_stakes,
            "listener_question": s.listener_question,
        }
        for s in stories
    ]
    prompt = f"""
Create a marketing pack for a premium AI podcast episode.

DATE: {date_str}
LISTEN_URL: {listen_url}
STORIES: {json.dumps(compact, ensure_ascii=False)}

Return JSON with keys:
yt_title, yt_description, tweet1, tweet2, hashtags
""".strip()

    return generate_json(
        prompt=prompt,
        system=(
            "You write premium, high-CTR but credible marketing copy for a daily AI show. "
            "Avoid clickbait sludge. Make it sharp, current, and sponsor-safe."
        ),
        required_keys=["yt_title", "yt_description", "tweet1", "tweet2", "hashtags"],
        max_tokens=900,
    )


def _sidecar_meta_path_for_date(date_str: str) -> Path:
    return AUDIO_DIR / f"podcast_{date_str}.json"


def _write_sidecar_meta_for_date(date_str: str, title: str, description: str) -> None:
    _sidecar_meta_path_for_date(date_str).write_text(
        json.dumps({"title": title.strip(), "description": description.strip()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_feed_xml(meta: Dict[str, object]) -> None:
    existing_items: List[Dict[str, str]] = []
    if FEED_XML_PATH.exists():
        try:
            parsed = feedparser.parse(FEED_XML_PATH.read_text(encoding="utf-8"))
            for entry in parsed.entries[: KEEP_LAST_EPISODES - 1]:
                existing_items.append(
                    {
                        "title": getattr(entry, "title", ""),
                        "description": getattr(entry, "summary", ""),
                        "link": getattr(entry, "link", ""),
                        "guid": getattr(entry, "id", getattr(entry, "guid", getattr(entry, "link", ""))),
                        "pubDate": getattr(entry, "published", ""),
                        "enclosure_url": getattr(entry, "enclosures", [{}])[0].get("href", "") if getattr(entry, "enclosures", None) else "",
                        "enclosure_length": str(getattr(entry, "enclosures", [{}])[0].get("length", "")) if getattr(entry, "enclosures", None) else "",
                        "enclosure_type": getattr(entry, "enclosures", [{}])[0].get("type", "audio/mpeg") if getattr(entry, "enclosures", None) else "audio/mpeg",
                    }
                )
        except Exception as e:
            _safe_print(f"    ⚠️ Could not parse existing feed.xml: {e}")

    new_item = {
        "title": str(meta["title"]),
        "description": str(meta["show_notes"]),
        "link": str(meta["audio_url"]),
        "guid": str(meta["audio_url"]),
        "pubDate": dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "enclosure_url": str(meta["audio_url"]),
        "enclosure_length": str((AUDIO_DIR / str(meta["audio_file"])).stat().st_size),
        "enclosure_type": "audio/mpeg",
    }

    remaining = [x for x in existing_items if x.get("guid") != new_item["guid"]]
    items = [new_item] + remaining[: KEEP_LAST_EPISODES - 1]

    rss = ET.Element("rss", attrib={"version": "2.0", "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"})
    channel = ET.SubElement(rss, "channel")
    for tag, value in [
        ("title", RSS_SETTINGS["title"]),
        ("link", RSS_SETTINGS["link"]),
        ("description", RSS_SETTINGS["description"]),
        ("language", "en-us"),
        ("itunes:author", RSS_SETTINGS["author"]),
        ("itunes:summary", RSS_SETTINGS["description"]),
        ("itunes:explicit", "no"),
        ("itunes:category", RSS_SETTINGS["category"]),
    ]:
        child = ET.SubElement(channel, tag)
        child.text = value

    image = ET.SubElement(channel, "itunes:image")
    image.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, "itunes:owner")
    owner_name = ET.SubElement(owner, "itunes:name")
    owner_name.text = RSS_SETTINGS["author"]
    owner_email = ET.SubElement(owner, "itunes:email")
    owner_email.text = RSS_SETTINGS["email"]

    for item in items:
        itm = ET.SubElement(channel, "item")
        for tag in ["title", "description", "link", "guid", "pubDate"]:
            child = ET.SubElement(itm, tag)
            child.text = item.get(tag, "")
        enclosure = ET.SubElement(itm, "enclosure")
        enclosure.set("url", item.get("enclosure_url", ""))
        enclosure.set("length", item.get("enclosure_length", "0"))
        enclosure.set("type", item.get("enclosure_type", "audio/mpeg"))

    ET.indent(rss)
    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)


def run_marketing_pipeline() -> None:
    return


def _require_assets() -> None:
    if not INTRO_PATH.exists():
        _safe_print("    ⚠️ intro.mp3 missing; continuing without intro.")
    if not OUTRO_PATH.exists():
        _safe_print("    ⚠️ outro.mp3 missing; continuing without outro.")
    if not TRANSITION_PATH.exists():
        _safe_print("    ⚠️ transition.mp3 missing; sponsor/transition beds will be minimal.")


def produce_episode() -> None:
    today = _today_str()
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"

    if final_mp3.exists() and not FORCE_REBUILD:
        _safe_print(f" >> ✅ Episode already exists: {final_mp3.name} (set FORCE_REBUILD=true to rebuild)")
        return

    _require_assets()
    run_tmp = TMP_DIR / f"run_{today}_{uuid.uuid4().hex[:8]}"
    run_tmp.mkdir(parents=True, exist_ok=True)

    memory = load_show_memory()
    sponsors = rotate_sponsors_for_today(today)

    _safe_print(" >> 🚀 STARTING: 1. Story Intelligence...")
    stories = select_story_briefs()
    _safe_print(f" >> ✅ COMPLETE: 1. Story Intelligence ({len(stories)} stories)")

    _safe_print(" >> 🚀 STARTING: 2. Writing Script...")
    script = compose_script(stories, sponsors, today, memory)
    if SAVE_SCRIPT:
        (BASE_DIR / f"script_{today}.txt").write_text(script, encoding="utf-8")
    _safe_print(" >> ✅ COMPLETE: 2. Writing Script")

    _safe_print(" >> 🚀 STARTING: 3. Studio Recording...")
    final_mp3 = assemble_episode(script, today, run_tmp)
    final_audio = AudioSegment.from_file(final_mp3)
    duration_seconds = int(len(final_audio) / 1000)
    minutes = duration_seconds / 60.0
    _safe_print(f" ✅ EPISODE COMPLETE: {final_mp3.name} ({minutes:.2f} minutes)")

    if minutes < MIN_MINUTES:
        shortfall_seconds = int(round((MIN_MINUTES - minutes) * 60))
        if shortfall_seconds <= SHORTFALL_TOLERANCE_SECONDS:
            _safe_print(f" ⚠️ Episode short by {shortfall_seconds}s. Auto-padding to {MIN_MINUTES:.2f} minutes.")
            final_audio = final_audio + AudioSegment.silent(duration=shortfall_seconds * 1000)
            final_audio.export(final_mp3, format="mp3", bitrate=FINAL_EXPORT_BITRATE)
            final_audio = AudioSegment.from_file(final_mp3)
            duration_seconds = int(len(final_audio) / 1000)
            minutes = duration_seconds / 60.0
            _safe_print(f" ✅ EPISODE PADDED: {final_mp3.name} ({minutes:.2f} minutes)")
        else:
            raise RuntimeError(f"Episode length out of bounds ({minutes:.2f} min). Must be {MIN_MINUTES}-{MAX_MINUTES}.")
    elif minutes > MAX_MINUTES:
        raise RuntimeError(f"Episode length out of bounds ({minutes:.2f} min). Must be {MIN_MINUTES}-{MAX_MINUTES}.")

    _safe_print(" >> ✅ COMPLETE: 3. Studio Recording")

    _safe_print(" >> 🚀 STARTING: 4. Publishing Assets...")
    pack = generate_marketing_pack(stories, today, LISTEN_URL)
    feed_title = pack.get("yt_title", RSS_SETTINGS["title"]).strip()
    show_notes = pack.get("yt_description", f"LISTEN: {LISTEN_URL}").strip()
    _write_sidecar_meta_for_date(today, title=feed_title, description=show_notes)

    viral_caption = "\n".join([
        pack.get("tweet1", "").strip(),
        "",
        pack.get("tweet2", "").strip(),
        "",
        pack.get("hashtags", "").strip(),
    ]).strip()
    VIRAL_CAPTION_PATH.write_text(viral_caption, encoding="utf-8")
    MARKETING_PACK_PATH.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")

    meta = {
        "date": today,
        "title": feed_title,
        "listen_url": LISTEN_URL,
        "minutes": round(minutes, 2),
        "duration_seconds": duration_seconds,
        "audio_file": final_mp3.name,
        "audio_url": AUDIO_BASE_URL + final_mp3.name,
        "stories": [asdict(s) for s in stories],
        "marketing_pack": pack,
        "show_notes": show_notes,
    }
    EPISODE_META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    update_feed_xml(meta)
    if RUN_MARKETING_ASSETS:
        run_marketing_pipeline()
    _safe_print(" >> ✅ COMPLETE: 4. Publishing Assets")

    memory.setdefault("callbacks", [])
    cb = memory["callbacks"]
    if isinstance(cb, list):
        cb.insert(0, random.choice([
            "Follow the receipts, not the keynote.",
            "If the model only works in a demo, it does not work yet.",
            "The real number always arrives after the applause.",
            "Do not confuse narrative velocity with product truth.",
        ]))
        del cb[8:]
    save_show_memory(memory)

    shutil.rmtree(run_tmp, ignore_errors=True)


if __name__ == "__main__":
    produce_episode()
