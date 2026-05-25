# -*- coding: utf-8 -*-
"""
THE AI EDGE — clean autonomous build (May 2026)

A daily, fully automated 3-host AI-news debate show.
- 3 segments, one story each, ~22 minutes total (room for sponsor reads).
- Alex (driver), Jamie (heartbeat), Rufus (dry British analyst).
- Jamie is voiced by Gemini TTS with per-line emotional direction.
- Alex and Rufus are voiced by OpenAI TTS.
- TheLEDGR sponsor gets a respectful, host-read mention in every segment.
- Self-contained: no growth_engine dependency.

This file replaces the old 6,200-line main.py. Paste it whole as main.py.

REQUIRED ENV (GitHub Secrets):
  OPENAI_API_KEY      - required (script writing + Alex/Rufus voices)
  GEMINI_API_KEY      - required for Jamie's Gemini voice; if missing or the
                        call fails, Jamie automatically falls back to OpenAI.

OPTIONAL ENV (sensible defaults below):
  GEMINI_TTS_VOICE_JAMIE   default "Sulafat"
  AUDIO_BASE_URL / LISTEN_URL / PUBLIC_SUBSCRIBE_URL
  TARGET_MINUTES / MIN_MINUTES / MAX_MINUTES
  FORCE_REBUILD            "true" to regenerate today's episode
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

load_dotenv()

# ===========================================================================
# 1. CONFIG
# ===========================================================================

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
TMP_DIR = BASE_DIR / "_tmp_audio"
AUDIO_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

FEED_XML_PATH = BASE_DIR / "feed.xml"
INTRO_PATH = BASE_DIR / "intro.mp3"
OUTRO_PATH = BASE_DIR / "outro.mp3"
TRANSITION_PATH = BASE_DIR / "transition.mp3"

RSS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "A daily AI debate show. Three hosts, one argument, the story under the headline.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
}

AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/",
).rstrip("/") + "/"
LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/",
).rstrip("/") + "/"
PUBLIC_SUBSCRIBE_URL = os.getenv("PUBLIC_SUBSCRIBE_URL", "https://theledgr.io").strip()

# --- Episode length -------------------------------------------------------
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "22"))
MIN_MINUTES = float(os.getenv("MIN_MINUTES", "19"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "26"))
WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "165"))

FORCE_REBUILD = os.getenv("FORCE_REBUILD", "false").strip().lower() in ("1", "true", "yes")
SAVE_SCRIPT = os.getenv("SAVE_SCRIPT", "true").strip().lower() in ("1", "true", "yes")
KEEP_LAST_EPISODES = int(os.getenv("KEEP_LAST_EPISODES", "60"))

# --- Sponsor --------------------------------------------------------------
SPONSOR_NAME_SPOKEN = "The Ledger"          # how hosts SAY it out loud
SPONSOR_URL_SPOKEN = "T-H-E-L-E-D-G-R dot I-O"
SPONSOR_URL_WRITTEN = "https://theledgr.io"
SPONSOR_PITCH = (
    "decision-grade AI intelligence that helps you cut through the noise and "
    "make sharper calls at work."
)

# --- Models ---------------------------------------------------------------
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
GEMINI_TTS_VOICE_JAMIE = os.getenv("GEMINI_TTS_VOICE_JAMIE", "Sulafat")

# --- OpenAI voices for Alex & Rufus --------------------------------------
OPENAI_VOICE = {"ALEX": os.getenv("VOICE_ALEX", "onyx"),
                "RUFUS": os.getenv("VOICE_RUFUS", "ballad")}

# Static voice-character instructions for the OpenAI hosts.
OPENAI_VOICE_INSTRUCTIONS = {
    "ALEX": ("A confident, high-energy host who runs the room. Curious, amused by "
             "tension, quick and punchy. Sounds entertained by the stakes."),
    "RUFUS": ("A dry British analyst. Elegant, precise, unhurried, faintly amused. "
              "Lands hard facts cleanly with quiet, witty understatement."),
}

# Per-segment voice speeds / gain trims.
VOICE_SPEED = {"ALEX": 1.05, "JAMIE": 1.0, "RUFUS": 1.02}
VOICE_GAIN_DB = {"ALEX": 2.0, "JAMIE": 1.5, "RUFUS": 0.5}

# --- Audio assembly -------------------------------------------------------
INTER_TURN_SILENCE_MS = 130
SEGMENT_GAP_MS = 350
EXPORT_BITRATE = "192k"
MIN_MP3_BYTES_FEED = 200_000

SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)
SEGMENT_RE = re.compile(r"^###\s*SEGMENT\s*(\d+)\b", re.IGNORECASE)

# ===========================================================================
# 2. HOST + SHOW DESIGN  (the creative spec, in one readable place)
# ===========================================================================

HOST_BRIEFS = """
ALEX — the driver. He runs the room. Curious, fast, amused by tension. He asks
the blunt question the listener is already thinking, calls out weak framing,
and instigates the fight. He does not interrupt every beat; when Jamie and
Rufus are cooking he lets them run, then cuts back in hard.

JAMIE — the heartbeat. The most intelligent, most empathetic person in the
room. She is the one tracking the human cost — the patient, the laid-off
worker, the developer, the person whose name is on the approval. She gets
genuinely frustrated when Alex and Rufus get clever or abstract while real
people are at stake. Her empathy is sharp, not soft: it is what makes her cut
through Rufus's detachment. She is right often, and she wins arguments. She is
not a translator or a mascot — she is a person with a point of view.

RUFUS — the dry British analyst. Money, liability, regulation, incentives.
Withering, elegant, funny. He undercuts hype with quiet menace. He is the
cleverest read in the room on WHO PAYS — but Jamie is the one who reminds him
who BLEEDS.
"""

# Jamie's emotional arc across the 3 segments. The writer is told her stage.
JAMIE_ARC = {
    1: ("Engaged and warm. She is interested, asks sharp questions, lands one "
        "early human-cost point that Alex and Rufus slightly brush past."),
    2: ("Frustration building. The men keep treating this as a game of "
        "strategy. Jamie pushes back harder, gets visibly impatient, and is "
        "not fully heard. End the segment with her annoyed."),
    3: ("She wins the beat. Jamie stops asking and states it plainly. She "
        "lands a hard, quiet truth about who actually carries the cost, the "
        "room goes still for a moment, and even Rufus concedes she is right."),
}

DEBATE_RULES = """
FORMAT — this is a DEBATE SHOW, not a news digest:
- Output ONLY dialogue lines with EXACT labels: ALEX:, JAMIE:, RUFUS:
- One spoken line per label line. No narration, no markdown, no bullets.
- Real disagreement is required. The hosts argue, interrupt, concede, push.
- Turns are mostly 8-40 words. Let a strong exchange run 3-6 turns before
  Alex cuts back in. Vary the rhythm; never let it feel like a panel.
- No filler openers ("let's dive in", "speaking of", "absolutely").
- No sign-off language until the very end of Segment 3.
- Every segment must contain a real clash and at least one line sharp enough
  that a listener would quote it.
- Use light, dry humor that reveals character or stakes — never goofy.
- Ground claims in the story's real facts; never invent numbers.
"""

# ===========================================================================
# 3. CLIENTS
# ===========================================================================

_openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not _openai_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in GitHub Secrets / env.")
openai_client = OpenAI(api_key=_openai_key)

_gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
gemini_client = None
genai_types = None
if _gemini_key:
    try:
        from google import genai as _genai          # type: ignore
        from google.genai import types as genai_types  # type: ignore
        gemini_client = _genai.Client(api_key=_gemini_key)
    except Exception as e:                            # pragma: no cover
        print(f"  ! Gemini SDK unavailable ({e}). Jamie will use OpenAI.", flush=True)
        gemini_client = None


def log(msg: str) -> None:
    print(msg, flush=True)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

# ===========================================================================
# 4. NEWS INTEL  (self-contained — no growth_engine)
# ===========================================================================

NEWS_FEEDS: List[Tuple[str, str]] = [
    ("topline", "https://news.google.com/rss/search?q=(AI%20OR%20%22artificial%20intelligence%22%20OR%20OpenAI%20OR%20Anthropic%20OR%20Google%20Gemini%20OR%20Nvidia)%20(funding%20OR%20lawsuit%20OR%20ban%20OR%20leak%20OR%20security%20OR%20launch%20OR%20deal%20OR%20earnings)%20when:3d&hl=en-US&gl=US&ceid=US:en"),
    ("agents",  "https://news.google.com/rss/search?q=(AI%20agent%20OR%20agentic%20AI%20OR%20autonomous%20agent)%20(security%20OR%20deployment%20OR%20failure%20OR%20launch%20OR%20enterprise)%20when:4d&hl=en-US&gl=US&ceid=US:en"),
    ("health",  "https://news.google.com/rss/search?q=(AI%20OR%20LLM)%20(healthcare%20OR%20clinical%20OR%20hospital%20OR%20diagnosis%20OR%20FDA)%20when:5d&hl=en-US&gl=US&ceid=US:en"),
    ("code",    "https://news.google.com/rss/search?q=(AI%20coding%20OR%20code%20assistant%20OR%20Copilot%20OR%20Cursor%20OR%20developer)%20(launch%20OR%20benchmark%20OR%20security%20OR%20agent)%20when:4d&hl=en-US&gl=US&ceid=US:en"),
]

VIRAL_WORDS = {
    "leak", "leaked", "lawsuit", "sues", "ban", "banned", "breach", "hack",
    "exploit", "layoffs", "fired", "shutdown", "collapse", "antitrust",
    "investigation", "warning", "fraud", "deepfake", "safety", "crackdown",
}
BIG_BRANDS = {
    "openai", "anthropic", "nvidia", "microsoft", "google", "deepmind",
    "meta", "apple", "tesla", "amazon", "perplexity",
}


def _clean(text: str) -> str:
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _split_title(raw: str) -> Tuple[str, str]:
    parts = [p.strip() for p in (raw or "").split(" - ") if p.strip()]
    if len(parts) >= 2:
        return " - ".join(parts[:-1]).strip(), parts[-1].strip()
    return (raw or "").strip(), ""


def fetch_news() -> List[Dict[str, str]]:
    """Pull recent AI stories from Google News RSS feeds."""
    items: List[Dict[str, str]] = []
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot)"}
    for bucket, url in NEWS_FEEDS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for entry in (feed.entries or [])[:12]:
                title, publisher = _split_title(getattr(entry, "title", "") or "")
                link = (getattr(entry, "link", "") or "").strip()
                summary = _clean(getattr(entry, "summary", "") or "")[:700]
                if not (title and link):
                    continue
                published = ""
                tt = getattr(entry, "published_parsed", None)
                if tt:
                    published = datetime.datetime(*tt[:6]).isoformat()
                items.append({
                    "bucket": bucket, "title": title, "publisher": publisher,
                    "link": link, "summary": summary, "published": published,
                })
        except Exception as e:
            log(f"  ! feed failed ({bucket}): {e}")
    # de-duplicate by title
    seen, deduped = set(), []
    for it in items:
        key = re.sub(r"\s+", " ", it["title"].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(it)
    return deduped


def _story_score(item: Dict[str, str]) -> float:
    blob = f"{item.get('title','')} {item.get('summary','')}".lower()
    score = 0.0
    score += 8.0 * len(re.findall(r"\d", blob[:400]))            # numeric density
    score += sum(14 for w in VIRAL_WORDS if w in blob)           # newsworthiness
    score += sum(10 for b in BIG_BRANDS if b in blob)            # recognizability
    if any(s in blob for s in ("$", "€", "£", "%")):
        score += 20
    # recency
    pub = item.get("published") or ""
    try:
        dt = datetime.datetime.fromisoformat(pub)
        age_h = (datetime.datetime.now() - dt).total_seconds() / 3600.0
        if age_h <= 12:
            score += 40
        elif age_h <= 26:
            score += 22
        elif age_h <= 48:
            score += 8
    except Exception:
        pass
    return score


def pick_top_stories(items: List[Dict[str, str]], n: int = 3) -> List[Dict[str, str]]:
    """Pick the n strongest stories, preferring different buckets for variety."""
    ranked = sorted(items, key=_story_score, reverse=True)
    chosen: List[Dict[str, str]] = []
    used_buckets: set = set()
    for it in ranked:
        if len(chosen) >= n:
            break
        b = it.get("bucket", "")
        if b in used_buckets and len(used_buckets) < n:
            continue
        chosen.append(it)
        used_buckets.add(b)
    # backfill if buckets were too thin
    for it in ranked:
        if len(chosen) >= n:
            break
        if it not in chosen:
            chosen.append(it)
    return chosen[:n]


def enrich_story(item: Dict[str, str]) -> Dict[str, str]:
    """Use the LLM to extract grounded facts. Never invents numbers."""
    prompt = f"""Extract HARD FACTS for a podcast discussion. Use ONLY facts that
appear in the material below. Do not invent numbers.

Return ONLY valid JSON:
{{
  "why_it_matters": "1-2 sentences on the real stakes",
  "facts": ["2-5 short factual bullets, each grounded in the material"],
  "human_angle": "1 sentence: who is actually affected, and how",
  "the_argument": "1 sentence naming a genuine point of disagreement"
}}

HEADLINE: {item.get('title','')}
PUBLISHER: {item.get('publisher','')}
SUMMARY: {item.get('summary','')}
"""
    raw = chat(prompt, temperature=0.2, max_tokens=600)
    data = _extract_json(raw) or {}
    out = dict(item)
    out["why_it_matters"] = data.get("why_it_matters", "") or item.get("summary", "")[:200]
    out["facts"] = data.get("facts", []) if isinstance(data.get("facts"), list) else []
    out["human_angle"] = data.get("human_angle", "")
    out["the_argument"] = data.get("the_argument", "")
    return out

# ===========================================================================
# 5. LLM HELPER
# ===========================================================================

def chat(prompt: str, temperature: float = 0.7, max_tokens: int = 2000,
         system: Optional[str] = None) -> str:
    """Single OpenAI chat call with retries."""
    system = system or "You write sharp, natural, spoken-word podcast dialogue."
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = openai_client.chat.completions.create(
                model=OPENAI_CHAT_MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"OpenAI chat failed after 3 attempts: {last_err}")


def _extract_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    for candidate in (raw, re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.I).strip()):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

# ===========================================================================
# 6. SCRIPT WRITING  (3 debate segments, sponsor in each)
# ===========================================================================

def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))


def _story_brief(story: Dict[str, str]) -> str:
    facts = "; ".join(str(f) for f in story.get("facts", [])[:5]) or \
            "No hard figures in the snippet — do not invent any."
    return (f"HEADLINE: {story.get('title','')}\n"
            f"PUBLISHER: {story.get('publisher','')}\n"
            f"WHY IT MATTERS: {story.get('why_it_matters','')}\n"
            f"FACTS: {facts}\n"
            f"HUMAN ANGLE: {story.get('human_angle','')}\n"
            f"THE REAL ARGUMENT: {story.get('the_argument','')}")


def _sponsor_instruction(seg_num: int) -> str:
    """A respectful, host-read TheLEDGR mention for every segment."""
    if seg_num == 1:
        return (
            f"SPONSOR — REQUIRED: After the cold open and the [MUSIC] line, ALEX "
            f"delivers a warm, genuine, host-read sponsor spot for {SPONSOR_NAME_SPOKEN} "
            f"({SPONSOR_PITCH}). It should sound like the hosts genuinely value the "
            f"sponsor and are glad to plug it. Alex must say the name as "
            f"'{SPONSOR_NAME_SPOKEN}' and the URL exactly as '{SPONSOR_URL_SPOKEN}'. "
            f"Keep it to 2-3 sentences, native to the conversation, never a flat ad."
        )
    if seg_num == 2:
        return (
            f"SPONSOR — REQUIRED: Somewhere natural mid-segment, RUFUS works in a "
            f"short, dry, genuinely approving mention of {SPONSOR_NAME_SPOKEN} — one "
            f"or two sentences, witty, respectful, tied to the story. He should say "
            f"the name as '{SPONSOR_NAME_SPOKEN}'."
        )
    return (
        f"SPONSOR — REQUIRED: Near the close, JAMIE gives a warm, sincere final "
        f"mention of {SPONSOR_NAME_SPOKEN} and invites listeners to subscribe at "
        f"'{SPONSOR_URL_SPOKEN}'. Two sentences, heartfelt, respectful — the hosts "
        f"clearly value this sponsor."
    )


def _segment_prompt(seg_num: int, story: Dict[str, str], seg_words: int,
                    date_str: str) -> str:
    if seg_num == 1:
        role = ("ACT 1 — open the show. Start mid-argument: a cold open where the "
                "three hosts are already clashing over today's first story — no "
                "intro, no throat-clearing. After 5-7 punchy cold-open lines, put "
                "a single line that is exactly: [MUSIC]. Then Alex welcomes the "
                "listener, delivers the sponsor spot, and frames the show.")
    elif seg_num == 2:
        role = ("ACT 2 — the middle fight. The hardest debate of the episode on "
                "today's second story. This is where the disagreement gets real.")
    else:
        role = ("ACT 3 — the close. The final story, the sharpest clash, and the "
                "resolution. End the whole episode here: the last 2-3 lines land "
                "the show and leave one unresolved question for tomorrow.")

    return f"""You are writing ONE segment of "The AI Edge", a daily AI debate show, for {date_str}.
This is SEGMENT {seg_num} of 3. Write ONLY this segment.

{HOST_BRIEFS}

JAMIE'S ARC — SEGMENT {seg_num}: {JAMIE_ARC[seg_num]}

{DEBATE_RULES}

WHAT THIS SEGMENT IS:
{role}

{_sponsor_instruction(seg_num)}

LENGTH: about {seg_words} words. Write a real, full debate — not a summary.

TODAY'S STORY FOR THIS SEGMENT:
{_story_brief(story)}

OUTPUT FORMAT:
- First line MUST be exactly: ### SEGMENT {seg_num}
- Then dialogue lines only: "ALEX: ...", "JAMIE: ...", "RUFUS: ..."
- Segment 1 only: include one standalone [MUSIC] line after the cold open.
- No other text.

Write the segment now."""


def _sanitize(text: str) -> str:
    """Keep only valid labelled dialogue lines, segment markers, [MUSIC]."""
    out: List[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if SEGMENT_RE.match(line):
            out.append(line)
            continue
        if line.upper() == "[MUSIC]":
            out.append("[MUSIC]")
            continue
        m = SPEAKER_RE.match(line)
        if m:
            out.append(f"{m.group(1).upper()}: {m.group(2).strip()}")
    return "\n".join(out).strip()


def write_episode(stories: List[Dict[str, str]], date_str: str) -> str:
    """Write all 3 segments and return the full script."""
    seg_words = int((TARGET_MINUTES * WORDS_PER_MINUTE) / 3)
    segments: List[str] = []
    for i, story in enumerate(stories[:3], start=1):
        log(f"  writing segment {i}/3 ...")
        raw = chat(_segment_prompt(i, story, seg_words, date_str),
                   temperature=0.8, max_tokens=2600)
        seg = _sanitize(raw)
        if not seg.startswith(f"### SEGMENT {i}"):
            seg = f"### SEGMENT {i}\n{seg}"
        segments.append(seg)
    return "\n\n".join(segments).strip()

# ===========================================================================
# 7. JAMIE — PER-LINE EMOTIONAL DIRECTION  (mood-aware Gemini routing)
# ===========================================================================

# Jamie's fixed Audio Profile — sent with every line so Sulafat stays in
# character. (Gemini TTS "advanced prompting": Audio Profile + Director's Notes.)
JAMIE_PROFILE = (
    "Jamie is a co-host on a sharp daily AI debate show. She is the most "
    "intelligent and most empathetic person in the room: warm, fast, "
    "articulate, emotionally present. She tracks the human cost of every "
    "story and is not afraid to push back on her co-hosts."
)

# Nine debate moods. Each maps to a Director's Note (how she delivers the
# line) and an optional inline audio tag the Gemini docs support directly.
JAMIE_MOODS: Dict[str, Tuple[str, str]] = {
    # mood:        (director's note,                                   inline tag)
    "warm":        ("Warm, open, genuinely engaged.",                  ""),
    "curious":     ("Bright, sharp curiosity; leaning in.",            "[curious] "),
    "pointed":     ("A pointed, challenging edge; pressing the point.", ""),
    "impatient":   ("Rising impatience, like she is not being heard.", ""),
    "frustrated":  ("Real, controlled frustration held just in check.", "[frustrated] "),
    "incredulous": ("Incredulous disbelief, almost laughing at how wrong it is.", ""),
    "firm":        ("Quiet, firm, absolute conviction. She is done asking.", "[serious] "),
    "concerned":   ("Genuine concern for the people affected; softer.", ""),
    "wry":         ("A dry, wry half-smile in the voice.",             ""),
}


def infer_jamie_mood(line: str, seg_num: int) -> str:
    """Pick a delivery mood for one of Jamie's lines from its text + arc stage."""
    low = line.lower()

    # explicit emotional cues in the text win first
    if any(k in low for k in ("ridiculous", "seriously?", "you cannot", "that's absurd",
                              "are you hearing", "come on")):
        return "incredulous"
    if any(k in low for k in ("no.", "listen to me", "i'm telling you", "stop",
                              "that is the point", "that's the whole point")):
        return "firm"
    if any(k in low for k in ("patient", "people", "family", "worker", "human",
                              "someone", "kids", "nurse", "loses their job")):
        return "concerned"
    if low.endswith("?"):
        return "pointed" if seg_num >= 2 else "curious"
    if any(k in low for k in ("but ", "actually", "that's not", "you're missing",
                              "hold on")):
        return "impatient" if seg_num >= 2 else "pointed"

    # otherwise, fall back to the arc stage
    if seg_num == 1:
        return "warm"
    if seg_num == 2:
        return "frustrated"
    return "firm"


def _jamie_tts_prompt(line: str, seg_num: int) -> str:
    """Build a Gemini-TTS prompt for one of Jamie's lines.

    Uses the structure the Gemini docs recommend: a clear preamble that tells
    the model to SYNTHESIZE SPEECH, an Audio Profile + Director's Note, and an
    explicitly labelled transcript. This prevents the documented failure mode
    where vague prompts make the model read the direction aloud.
    """
    mood = infer_jamie_mood(line, seg_num)
    note, tag = JAMIE_MOODS.get(mood, JAMIE_MOODS["warm"])
    spoken = f"{tag}{line}".strip()
    return (
        "Read the transcript below aloud as a natural spoken-word performance. "
        "Do not read the profile or notes — only speak the TRANSCRIPT line.\n\n"
        f"# AUDIO PROFILE\n{JAMIE_PROFILE}\n\n"
        f"# DIRECTOR'S NOTE\nDelivery for this line: {note}\n\n"
        f"# TRANSCRIPT\n{spoken}"
    )

# ===========================================================================
# 8. TEXT-TO-SPEECH
# ===========================================================================

def _speech_friendly(text: str) -> str:
    """Make acronyms and figures speak cleanly."""
    s = re.sub(r"\s+", " ", text or "").strip()
    s = s.replace("TheLEDGR", SPONSOR_NAME_SPOKEN)
    for abbr, spoken in (("AI", "A.I."), ("API", "A.P.I."), ("GPU", "G.P.U."),
                         ("LLM", "L.L.M."), ("CEO", "C.E.O."), ("EHR", "E.H.R.")):
        s = re.sub(rf"\b{abbr}\b", spoken, s)
    s = re.sub(r"\b(\d+)%", lambda m: f"{m.group(1)} percent", s)
    return s


def _pcm_to_mp3(pcm_bytes: bytes, out_path: Path,
                sample_rate: int = 24000) -> None:
    """Gemini returns raw 16-bit mono PCM; wrap as WAV then export MP3."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    AudioSegment.from_wav(buf).export(out_path, format="mp3", bitrate=EXPORT_BITRATE)


def tts_openai(text: str, speaker: str, out_path: Path) -> None:
    """Voice Alex or Rufus with OpenAI TTS."""
    spoken = _speech_friendly(text)
    voice = OPENAI_VOICE.get(speaker, "onyx")
    instructions = OPENAI_VOICE_INSTRUCTIONS.get(speaker, "")
    last_err = None
    for attempt in range(1, 4):
        try:
            with openai_client.audio.speech.with_streaming_response.create(
                model=OPENAI_TTS_MODEL,
                voice=voice,
                input=spoken,
                instructions=instructions,
            ) as resp:
                resp.stream_to_file(str(out_path))
            return
        except Exception as e:
            last_err = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"OpenAI TTS failed for {speaker}: {last_err}")


def tts_gemini_jamie(text: str, seg_num: int, out_path: Path) -> bool:
    """Voice Jamie with Gemini TTS + per-line emotional direction.

    Returns True on success, False if Gemini is unavailable or every attempt
    fails (caller then falls back to OpenAI so the episode still ships).

    The Gemini 3.1 TTS docs note the model occasionally returns text tokens
    instead of audio and 500s, so we retry up to 5 times and also verify the
    response part actually contains audio data before accepting it.
    """
    if gemini_client is None or genai_types is None:
        return False
    prompt = _jamie_tts_prompt(_speech_friendly(text), seg_num)
    for attempt in range(1, 6):
        try:
            resp = gemini_client.models.generate_content(
                model=GEMINI_TTS_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=genai_types.SpeechConfig(
                        voice_config=genai_types.VoiceConfig(
                            prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                                voice_name=GEMINI_TTS_VOICE_JAMIE,
                            )
                        )
                    ),
                ),
            )
            part = resp.candidates[0].content.parts[0]
            inline = getattr(part, "inline_data", None)
            pcm = getattr(inline, "data", None) if inline else None
            if not pcm:
                raise RuntimeError("Gemini returned text instead of audio")
            _pcm_to_mp3(pcm, out_path)
            return True
        except Exception as e:
            log(f"  ! Gemini TTS attempt {attempt}/5 failed: {e}")
            time.sleep(1.5 * attempt)
    return False


def render_line(speaker: str, text: str, seg_num: int, out_path: Path) -> None:
    """Render one spoken line to MP3, routing Jamie to Gemini."""
    if speaker == "JAMIE":
        if tts_gemini_jamie(text, seg_num, out_path):
            return
        log("  ! Jamie falling back to OpenAI for this line.")
        # fall back: voice Jamie on OpenAI 'shimmer' so the show still ships
        spoken = _speech_friendly(text)
        for attempt in range(1, 4):
            try:
                with openai_client.audio.speech.with_streaming_response.create(
                    model=OPENAI_TTS_MODEL, voice="shimmer", input=spoken,
                    instructions=("An intelligent, warm, emotionally present "
                                  "co-host reacting in real time."),
                ) as resp:
                    resp.stream_to_file(str(out_path))
                return
            except Exception:
                time.sleep(1.5 * attempt)
        raise RuntimeError("Jamie TTS failed on both Gemini and OpenAI.")
    else:
        tts_openai(text, speaker, out_path)

# ===========================================================================
# 9. AUDIO ASSEMBLY
# ===========================================================================

def _trim_silence(seg: AudioSegment, thresh_db: float = -45.0,
                  max_ms: int = 120) -> AudioSegment:
    if len(seg) < 60:
        return seg

    def lead(a: AudioSegment) -> int:
        ms = 0
        while ms < len(a) and a[ms:ms + 10].dBFS < thresh_db:
            ms += 10
        return min(ms, max_ms)

    start, end = lead(seg), lead(seg.reverse())
    return seg[start:len(seg) - end] if len(seg) > start + end + 20 else seg


def _post_process(path: Path) -> None:
    try:
        clip = _trim_silence(AudioSegment.from_file(path))
        clip = clip + AudioSegment.silent(duration=80)
        clip.export(path, format="mp3", bitrate=EXPORT_BITRATE)
    except Exception as e:
        log(f"  ! post-process failed for {path.name}: {e}")


def _master(in_path: Path, out_path: Path) -> None:
    """Loudness-normalize the final mix to broadcast level."""
    cmd = ["ffmpeg", "-y", "-i", str(in_path), "-af",
           "acompressor=threshold=-18dB:ratio=3:attack=10:release=120:makeup=4,"
           "loudnorm=I=-16:TP=-1.5:LRA=11",
           "-c:a", "libmp3lame", "-b:a", EXPORT_BITRATE, str(out_path)]
    subprocess.run(cmd, check=True)


def parse_dialogue(script: str) -> List[Tuple[int, str, str]]:
    """Return (segment_number, speaker, text) tuples. 'MUSIC' is a speaker."""
    out: List[Tuple[int, str, str]] = []
    seg = 1
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        ms = SEGMENT_RE.match(line)
        if ms:
            seg = int(ms.group(1))
            continue
        if line.upper() == "[MUSIC]":
            out.append((seg, "MUSIC", "[MUSIC]"))
            continue
        m = SPEAKER_RE.match(line)
        if m:
            out.append((seg, m.group(1).upper(), m.group(2).strip()))
    return out


def build_audio(script: str, date_str: str) -> Path:
    """Render every line, stitch with music + transitions, master."""
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg is required. Install it on the runner.")

    run_tmp = TMP_DIR / date_str
    if run_tmp.exists():
        shutil.rmtree(run_tmp, ignore_errors=True)
    run_tmp.mkdir(parents=True, exist_ok=True)

    turn_gap = AudioSegment.silent(duration=INTER_TURN_SILENCE_MS)
    seg_gap = AudioSegment.silent(duration=SEGMENT_GAP_MS)

    dialogue = parse_dialogue(script)

    # SAFETY GATE: never build (and never publish) an empty or near-empty
    # episode. If the script collapsed for any reason, stop here so a blank
    # MP3 cannot reach the live feed.
    spoken = [d for d in dialogue if d[1] != "MUSIC"]
    MIN_SPOKEN_LINES = 30
    if len(spoken) < MIN_SPOKEN_LINES:
        raise RuntimeError(
            f"Script produced only {len(spoken)} spoken lines "
            f"(minimum {MIN_SPOKEN_LINES}). Refusing to build a thin episode. "
            f"Inspect the saved script_*.txt — today's feed is left untouched."
        )

    pieces: List[AudioSegment] = []
    last_seg = 1
    idx = 0

    # optional intro music
    if INTRO_PATH.exists():
        pieces.append(AudioSegment.from_file(INTRO_PATH))
        pieces.append(seg_gap)

    log(f"  rendering {len(dialogue)} dialogue lines ...")
    for seg_num, speaker, text in dialogue:
        # segment transition music
        if seg_num != last_seg:
            if TRANSITION_PATH.exists():
                pieces.append(seg_gap)
                pieces.append(AudioSegment.from_file(TRANSITION_PATH))
            pieces.append(seg_gap)
            last_seg = seg_num

        if speaker == "MUSIC":
            if INTRO_PATH.exists():
                pieces.append(AudioSegment.from_file(INTRO_PATH))
            pieces.append(seg_gap)
            continue

        idx += 1
        line_path = run_tmp / f"{date_str}_{idx:04d}_{speaker.lower()}.mp3"
        render_line(speaker, text, seg_num, line_path)
        _post_process(line_path)

        clip = AudioSegment.from_file(line_path)
        # per-host speed
        speed = VOICE_SPEED.get(speaker, 1.0)
        if abs(speed - 1.0) > 1e-6:
            sped = run_tmp / f"{date_str}_{idx:04d}_spd.mp3"
            subprocess.run(["ffmpeg", "-y", "-i", str(line_path), "-filter:a",
                            f"atempo={speed:.4f}", "-c:a", "libmp3lame",
                            "-b:a", EXPORT_BITRATE, str(sped)], check=True)
            clip = AudioSegment.from_file(sped)
        # per-host gain trim
        gain = VOICE_GAIN_DB.get(speaker, 0.0)
        if abs(gain) > 0.01:
            clip = clip.apply_gain(gain)

        pieces.append(clip)
        pieces.append(turn_gap)

    # optional outro music
    if OUTRO_PATH.exists():
        pieces.append(seg_gap)
        pieces.append(AudioSegment.from_file(OUTRO_PATH))

    log("  stitching ...")
    combined = AudioSegment.empty()
    for p in pieces:
        combined += p
    rough = run_tmp / f"{date_str}_rough.mp3"
    combined.export(rough, format="mp3", bitrate=EXPORT_BITRATE)

    log("  mastering ...")
    final_mp3 = AUDIO_DIR / f"podcast_{date_str}.mp3"
    _master(rough, final_mp3)

    shutil.rmtree(run_tmp, ignore_errors=True)
    return final_mp3

# ===========================================================================
# 10. RSS FEED WRITER
# ===========================================================================

def _sidecar_path(date_str: str) -> Path:
    return AUDIO_DIR / f"podcast_{date_str}.json"


def write_sidecar(date_str: str, title: str, description: str) -> None:
    _sidecar_path(date_str).write_text(
        json.dumps({"title": title, "description": description},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def _load_sidecar(date_str: str) -> Dict[str, str]:
    p = _sidecar_path(date_str)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def update_feed(latest_meta: Dict) -> None:
    """Rebuild feed.xml from every valid episode mp3 on disk."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ATOM = "http://www.w3.org/2005/Atom"
    ET.register_namespace("itunes", ITUNES)
    ET.register_namespace("atom", ATOM)

    def rfc2822(date_str: str) -> str:
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(
                hour=12, tzinfo=datetime.timezone.utc)
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = RSS["title"]
    ET.SubElement(ch, "description").text = RSS["description"]
    ET.SubElement(ch, "link").text = LISTEN_URL
    ET.SubElement(ch, "language").text = "en-us"
    ET.SubElement(ch, "lastBuildDate").text = rfc2822(
        datetime.date.today().isoformat())
    atom = ET.SubElement(ch, f"{{{ATOM}}}link")
    atom.set("href", LISTEN_URL.rstrip("/") + "/feed.xml")
    atom.set("rel", "self")
    atom.set("type", "application/rss+xml")
    ET.SubElement(ch, f"{{{ITUNES}}}author").text = RSS["author"]
    ET.SubElement(ch, f"{{{ITUNES}}}explicit").text = "no"
    ET.SubElement(ch, f"{{{ITUNES}}}type").text = "episodic"
    ET.SubElement(ch, f"{{{ITUNES}}}category").set("text", RSS["category"])
    ET.SubElement(ch, f"{{{ITUNES}}}image").set("href", RSS["image"])
    owner = ET.SubElement(ch, f"{{{ITUNES}}}owner")
    ET.SubElement(owner, f"{{{ITUNES}}}name").text = RSS["author"]
    ET.SubElement(owner, f"{{{ITUNES}}}email").text = RSS["email"]

    mp3s = sorted(AUDIO_DIR.glob("podcast_*.mp3"),
                  key=lambda p: p.name, reverse=True)
    added = 0
    for mp3 in mp3s:
        if added >= KEEP_LAST_EPISODES:
            break
        m = re.match(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", mp3.name)
        if not m:
            continue
        try:
            size = mp3.stat().st_size
        except Exception:
            continue
        if size < MIN_MP3_BYTES_FEED:
            continue
        date_str = m.group(1)
        sidecar = _load_sidecar(date_str)
        title = sidecar.get("title") or f"{RSS['title']} — {date_str}"
        desc = sidecar.get("description") or f"Listen: {LISTEN_URL}"
        dur = 0
        if latest_meta.get("audio_file") == mp3.name:
            title = latest_meta.get("title", title)
            desc = latest_meta.get("show_notes", desc)
            dur = int(latest_meta.get("duration_seconds", 0))

        url = AUDIO_BASE_URL + quote(mp3.name)
        item = ET.SubElement(ch, "item")
        ET.SubElement(item, "title").text = title[:120]
        ET.SubElement(item, "description").text = desc[:6000]
        ET.SubElement(item, f"{{{ITUNES}}}summary").text = desc[:6000]
        g = ET.SubElement(item, "guid")
        g.set("isPermaLink", "false")
        g.text = url
        ET.SubElement(item, "pubDate").text = rfc2822(date_str)
        enc = ET.SubElement(item, "enclosure")
        enc.set("url", url)
        enc.set("type", "audio/mpeg")
        enc.set("length", str(size))
        if dur > 0:
            ET.SubElement(item, f"{{{ITUNES}}}duration").text = str(dur)
        ET.SubElement(item, f"{{{ITUNES}}}image").set("href", RSS["image"])
        ET.SubElement(item, f"{{{ITUNES}}}episodeType").text = "full"
        added += 1

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8",
                              xml_declaration=True)
    log(f"  feed.xml rebuilt — {added} episodes")

# ===========================================================================
# 11. EPISODE PACKAGING  (curiosity-gap title engine + show notes)
# ===========================================================================

TITLES_LOG_PATH = BASE_DIR / "titles_log.jsonl"

# The three title mechanisms. Each opens a loop the listener needs closed.
TITLE_MECHANISMS = {
    "withheld_number": (
        "THE WITHHELD NUMBER — lead with a specific, real figure from the "
        "story but withhold the part that explains it, so the listener has "
        "to open the episode to resolve it. "
        "Example shape: 'The 1% Problem Inside a 99% AI Diagnosis.'"
    ),
    "reframe": (
        "THE REFRAME — state that the obvious read of the story is wrong and "
        "name the real story instead. "
        "Example shape: 'OpenAI Didn't Launch a Phone. It Launched a "
        "Permission Layer.'"
    ),
    "stakes_question": (
        "THE STAKES QUESTION — pose an unresolved, high-stakes consequence "
        "as a question the listener cannot answer without listening. "
        "Example shape: 'AI Got the Diagnosis Right. So Who Gets Sued?'"
    ),
}


def _title_curiosity_score(title: str) -> float:
    """Heuristic: does this title open a loop? Higher = more tap-worthy."""
    if not title:
        return 0.0
    low = title.lower()
    score = 0.0
    # a specific number creates a concrete, unresolved hook
    if re.search(r"\d", title):
        score += 25
    if re.search(r"\d+\s?%", title):
        score += 10
    # an unresolved question
    if title.strip().endswith("?"):
        score += 20
    # contrast / reframe language ("not ... but", "didn't ... it")
    if re.search(r"\b(not|didn'?t|isn'?t|wasn'?t)\b", low) and \
       re.search(r"\b(but|it|the real|actually)\b", low):
        score += 22
    # who/why/what stakes words
    if re.search(r"\b(who|why|what|when)\b", low):
        score += 12
    # consequence / stakes vocabulary
    if any(w in low for w in ("sued", "blamed", "pays", "exposed", "breaks",
                              "loses", "wins", "caught", "costs", "risk")):
        score += 14
    # penalize a flat, pre-resolved announcement headline
    if any(w in low for w in ("launches", "announces", "unveils", "introduces",
                              "releases", "update")):
        score -= 20
    # length sweet spot: 35-75 chars taps best on a phone
    n = len(title)
    if 35 <= n <= 75:
        score += 12
    elif n > 95:
        score -= 12
    return score


def make_episode_meta(stories: List[Dict[str, str]],
                      date_str: str) -> Tuple[str, str]:
    """Generate 3 curiosity-gap titles, pick the strongest, log all 3.

    Returns (title, show_notes). The two runner-up titles and their scores
    are appended to titles_log.jsonl so that, over weeks, you can review
    which MECHANISM your audience actually opens — an A/B record without
    needing any ad spend.
    """
    lead = stories[0] if stories else {}
    facts = "; ".join(str(f) for f in lead.get("facts", [])[:4])

    prompt = f"""You are titling an episode of "The AI Edge", a daily AI debate show.
Write THREE competing episode titles, one for each mechanism below. A great
title opens a curiosity loop the listener must tap to close. Be specific and
concrete; use a real figure from the story when one exists. Never write a flat
announcement headline. No date, no show name, each title <= 80 characters.

MECHANISM 1 — {TITLE_MECHANISMS['withheld_number']}
MECHANISM 2 — {TITLE_MECHANISMS['reframe']}
MECHANISM 3 — {TITLE_MECHANISMS['stakes_question']}

LEAD STORY: {lead.get('title','')}
WHY IT MATTERS: {lead.get('why_it_matters','')}
FACTS: {facts or 'no hard figures available — do not invent any'}
THE ARGUMENT: {lead.get('the_argument','')}

Return ONLY valid JSON:
{{"withheld_number": "title text",
  "reframe": "title text",
  "stakes_question": "title text",
  "blurb": "2 sentences: what the debate is about and what's at stake"}}"""

    data = _extract_json(chat(prompt, temperature=0.8, max_tokens=400)) or {}

    # collect candidates, score each on curiosity-gap signals
    candidates: List[Tuple[str, str, float]] = []
    for mech in ("withheld_number", "reframe", "stakes_question"):
        t = (data.get(mech) or "").strip().strip('"').strip()
        if t:
            candidates.append((mech, t[:100], _title_curiosity_score(t)))

    if candidates:
        candidates.sort(key=lambda x: x[2], reverse=True)
        winner_mech, title, winner_score = candidates[0]
    else:
        winner_mech, title, winner_score = ("fallback",
                                            f"The AI Edge — {date_str}", 0.0)

    # log all candidates so the show can learn which mechanism wins over time
    try:
        with open(TITLES_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "date": date_str,
                "chosen_mechanism": winner_mech,
                "chosen_title": title,
                "candidates": [{"mechanism": m, "title": t, "score": s}
                               for m, t, s in candidates],
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"  ! could not write titles_log: {e}")
    log(f"  title [{winner_mech}, score {winner_score:.0f}]: {title}")

    bullets = "\n".join(f"• {s.get('title','')}" for s in stories[:3])
    blurb = (data.get("blurb", "") or "").strip()
    notes = (
        f"{blurb}\n\n"
        f"In this episode Alex, Jamie, and Rufus debate:\n{bullets}\n\n"
        f"This episode is brought to you by {SPONSOR_NAME_SPOKEN} — "
        f"{SPONSOR_PITCH}\nSubscribe: {SPONSOR_URL_WRITTEN}"
    )
    return title, notes

# ===========================================================================
# 12. PRODUCER  (entry point)
# ===========================================================================

def produce_episode() -> None:
    today = datetime.date.today().isoformat()
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"

    if final_mp3.exists() and final_mp3.stat().st_size >= MIN_MP3_BYTES_FEED \
            and not FORCE_REBUILD:
        log(f"Episode already exists ({final_mp3.name}). "
            f"Set FORCE_REBUILD=true to regenerate.")
        try:
            dur = int(len(AudioSegment.from_mp3(final_mp3)) / 1000)
        except Exception:
            dur = 0
        sc = _load_sidecar(today)
        update_feed({"audio_file": final_mp3.name,
                     "title": sc.get("title", f"{RSS['title']} — {today}"),
                     "show_notes": sc.get("description", ""),
                     "duration_seconds": dur})
        return

    log("THE AI EDGE — building today's episode")
    log("1. gathering news ...")
    news = fetch_news()
    if not news:
        raise RuntimeError("No news fetched — cannot build an episode.")

    log("2. selecting 3 stories ...")
    stories = pick_top_stories(news, n=3)
    if len(stories) < 3:
        raise RuntimeError(f"Only {len(stories)} stories survived selection.")
    log("   stories: " + " | ".join(s["title"][:50] for s in stories))

    log("3. enriching stories with grounded facts ...")
    stories = [enrich_story(s) for s in stories]

    log("4. writing the debate ...")
    script = write_episode(stories, today)
    if SAVE_SCRIPT:
        (BASE_DIR / f"script_{today}.txt").write_text(script, encoding="utf-8")
        log(f"   saved script_{today}.txt")

    log("5. recording + assembling audio ...")
    final_mp3 = build_audio(script, today)

    final_audio = AudioSegment.from_mp3(final_mp3)
    minutes = len(final_audio) / 60000.0
    dur_seconds = int(len(final_audio) / 1000)
    log(f"   episode length: {minutes:.1f} min")
    if minutes < MIN_MINUTES:
        log(f"   ! warning: shorter than target ({MIN_MINUTES} min)")
    elif minutes > MAX_MINUTES:
        log(f"   ! warning: longer than target ({MAX_MINUTES} min)")

    log("6. packaging + feed ...")
    title, notes = make_episode_meta(stories, today)
    write_sidecar(today, title, notes)
    update_feed({"audio_file": final_mp3.name, "title": title,
                 "show_notes": notes, "duration_seconds": dur_seconds})

    log(f"DONE — {final_mp3.name} ({minutes:.1f} min)")


if __name__ == "__main__":
    produce_episode()
