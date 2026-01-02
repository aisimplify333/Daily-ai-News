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
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
).rstrip("/") + "/"

LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/"
).rstrip("/") + "/"

PRIMARY_LLM = os.getenv("PRIMARY_LLM", "openai").strip().lower()  # gemini | openai
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")

MIN_MINUTES = float(os.getenv("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "30"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "28"))

# Script sizing: set to 150 because your logs implied ~905 words => ~6.0 minutes
WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "150"))

# How many attempts to regenerate/repair script before failing
SCRIPT_ATTEMPTS = int(os.getenv("SCRIPT_ATTEMPTS", "6"))

# Token ceilings for script generation/repair
SCRIPT_MAX_TOKENS = int(os.getenv("SCRIPT_MAX_TOKENS", "12000"))
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

# Merge adjacent turns for fewer TTS calls
TTS_MERGE_MAX_CHARS = int(os.getenv("TTS_MERGE_MAX_CHARS", "2400"))
TTS_CHUNK_MAX_CHARS = int(os.getenv("TTS_CHUNK_MAX_CHARS", "2800"))
TTS_RETRIES = int(os.getenv("TTS_RETRIES", "3"))

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
# LLM CLIENTS (OpenAI + Gemini)
# ----------------------------
openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
if not openai_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in GitHub Secrets / env.")

openai_client = OpenAI(api_key=openai_key)

gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

# New Gemini SDK (google-genai)
genai_new = None
genai_types = None
gemini_client = None
try:
    from google import genai as genai_new  # from google-genai
    from google.genai import types as genai_types
    if gemini_key:
        gemini_client = genai_new.Client(api_key=gemini_key)
    else:
        # Some environments allow default creds/env discovery
        gemini_client = genai_new.Client()
except Exception:
    genai_new = None
    genai_types = None
    gemini_client = None

# Old Gemini SDK (google-generativeai) - kept for backward compatibility only
genai_old = None
try:
    import google.generativeai as genai_old
    if gemini_key:
        try:
            genai_old.configure(api_key=gemini_key)
        except Exception:
            pass
except Exception:
    genai_old = None

def _gemini_candidate_models() -> List[str]:
    """
    Prefer your current-generation model names first.
    You can override with GEMINI_MODEL env var.
    """
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models = [
        env_model,
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3-flash",
    ]
    return [m for m in models if m]

def generate_text(prompt: str, temperature: float = 0.7, max_tokens: int = 5000) -> str:
    """
    Gemini primary (if enabled + available), OpenAI fallback.
    Fails fast on Gemini 429/404 rather than looping and burning your RPM.
    """
    if PRIMARY_LLM == "gemini" and gemini_key:
        # Try NEW sdk first
        if gemini_client and genai_types:
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
                    _safe_print(f"    ⚠️ Gemini(new) failed on {model_name}: {e}. Falling back to OpenAI...")
                    break

        # Try OLD sdk (legacy)
        if genai_old:
            for model_name in _gemini_candidate_models()[:2]:
                try:
                    model = genai_old.GenerativeModel(model_name)
                    resp = model.generate_content(
                        prompt,
                        generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
                    )
                    txt = getattr(resp, "text", None)
                    if txt and txt.strip():
                        return txt.strip()
                except Exception as e:
                    _safe_print(f"    ⚠️ Gemini(old) failed on {model_name}: {e}. Falling back to OpenAI...")
                    break

    # OpenAI
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
    ("Frontier Models",
     "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20DeepMind)%20(model%20OR%20release%20OR%20launch)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Money",
     "https://news.google.com/rss/search?q=(AI%20funding%20OR%20valuation%20OR%20IPO%20OR%20Nvidia%20OR%20chips)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Regulation",
     "https://news.google.com/rss/search?q=(AI%20regulation%20OR%20EU%20AI%20Act%20OR%20FTC%20OR%20copyright)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Security",
     "https://news.google.com/rss/search?q=(AI%20jailbreak%20OR%20prompt%20injection%20OR%20security%20OR%20leak)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI in Work",
     "https://news.google.com/rss/search?q=(AI%20jobs%20OR%20automation%20OR%20productivity%20OR%20enterprise)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
]

def _strip_html(s: str) -> str:
    if not s:
        return ""
    soup = BeautifulSoup(s, "html.parser")
    txt = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt).strip()

def fetch_rss_items(max_per_feed: int = 10) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    headers = {"User-Agent": "Mozilla/5.0 (AI Edge Bot; +https://github.com/aisimplify333/Daily-ai-News)"}

    for label, url in GOOGLE_NEWS_RSS:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for entry in (feed.entries or [])[:max_per_feed]:
                title = (getattr(entry, "title", "") or "").strip()
                link = (getattr(entry, "link", "") or "").strip()
                summary = _strip_html(getattr(entry, "summary", "") or "")[:450]
                if title and link:
                    items.append({"bucket": label, "title": title, "link": link, "summary": summary})
        except Exception as e:
            _safe_print(f"    ⚠️ RSS fetch failed ({label}): {e}")

    # Dedup by normalized title
    seen = set()
    deduped = []
    for x in items:
        key = re.sub(r"\s+", " ", x["title"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(x)
    return deduped

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

def pick_top_stories(intel_items: List[Dict[str, str]], n: int = 5) -> List[Dict[str, str]]:
    intel_compact = "\n".join(
        [f"- [{x['bucket']}] {x['title']} | {x['summary']} | {x['link']}" for x in intel_items[:80]]
    )

    prompt = f"""
Select the TOP {n} stories for a daily AI show that must feel urgent, emotional, and high-stakes.

Return ONLY valid JSON (no markdown), schema:
{{
  "stories": [
    {{
      "headline": "...",
      "why_shocking": "...",
      "angles": {{
        "alex": "...",
        "jamie": "...",
        "rufus": "..."
      }},
      "source_url": "..."
    }}
  ]
}}

Candidate items:
{intel_compact}
""".strip()

    raw = generate_text(prompt, temperature=0.25, max_tokens=JSON_MAX_TOKENS)

    try:
        j = json.loads(raw)
        stories = j.get("stories", [])
        stories = [s for s in stories if isinstance(s, dict)]
        norm: List[Dict[str, str]] = []
        for s in stories[:n]:
            angles = s.get("angles") if isinstance(s.get("angles"), dict) else {}
            norm.append({
                "headline": (s.get("headline") or "").strip(),
                "why_shocking": (s.get("why_shocking") or "").strip(),
                "angles": {
                    "alex": (angles.get("alex") or "").strip(),
                    "jamie": (angles.get("jamie") or "").strip(),
                    "rufus": (angles.get("rufus") or "").strip(),
                },
                "source_url": (s.get("source_url") or "").strip(),
            })
        if len(norm) < n or any(not x["headline"] for x in norm):
            raise ValueError("Model returned incomplete stories.")
        return norm[:n]
    except Exception:
        return [
            {"headline": x["title"], "why_shocking": x["summary"],
             "angles": {"alex": "", "jamie": "", "rufus": ""}, "source_url": x["link"]}
            for x in intel_items[:n]
        ]

# ----------------------------
# SCRIPTING (SOUL + GUARANTEED LENGTH)
# ----------------------------
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)

def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))

def estimate_minutes_from_text(script: str) -> float:
    words = _word_count(script)
    return words / max(1.0, WORDS_PER_MINUTE)

def _script_targets() -> Tuple[int, int]:
    # Small buffer so real TTS timing still lands inside MIN/MAX
    min_words = int(MIN_MINUTES * WORDS_PER_MINUTE * 1.02)
    max_words = int(MAX_MINUTES * WORDS_PER_MINUTE * 1.10)
    return min_words, max_words

def build_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], date_str: str) -> str:
    sponsor_1 = sponsors[0] if len(sponsors) > 0 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_2 = sponsors[1] if len(sponsors) > 1 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_3 = sponsors[2] if len(sponsors) > 2 else {"name": "Sponsor", "tagline": "", "cta": ""}

    min_words, max_words = _script_targets()

    story_block = "\n".join(
        [f"{i+1}. {s['headline']} — {s.get('why_shocking','')} ({s.get('source_url','')})" for i, s in enumerate(stories)]
    )

    prompt = f"""
You are writing a DAILY podcast episode called "The AI Edge" for {date_str}.
It must feel like a raw, overheated conversation between THREE distinct personalities.
NO corporate speak. They interrupt, argue, laugh, get angry, get quiet, then spike again.

PERSONAS (distinct voice is mandatory):
- ALEX (Host): Rogan energy + frantic curiosity. Drives pace. Calls out BS. Summarizes the lineup fast.
- JAMIE (Co-host): Bartlett vibe. Vulnerable, empathetic, human stakes. Pushes back emotionally.
- RUFUS (Analyst): cynical, money/regulatory edge. Cold, sharp. Sounds like he trades and reads filings.

HARD FORMAT RULES (non-negotiable):
- Output MUST be dialogue lines only using EXACT labels: "ALEX:", "JAMIE:", "RUFUS:"
- Every spoken line MUST start with one of those labels. No multi-paragraph blocks.
- Segment markers are allowed as lines starting with "###" and will NOT be spoken.
- "[MUSIC]" may appear as a standalone line.
- ABSOLUTE LENGTH: {min_words} to {max_words} words total. Do NOT go under {min_words}.
- Aim for {TARGET_MINUTES} minutes in real listening.
- Must cover FIVE stories.
- Must follow this 5-segment structure:

### SEGMENT 1 (Cold open + Welcome + Alex lineup summary)
Start mid-argument (hook). Then [MUSIC]. Then Alex welcomes, states today's 5 stories in rapid-fire summary.

### SEGMENT 2 (Studio: Alex + Jamie only)
High chemistry, fast pacing, human stakes. No Rufus. Make it feel personal and messy.

### SEGMENT 3 (On-location: Rufus money/reg angle)
Alex throws to Rufus. Rufus delivers a "native ad" seamlessly as insider advice.
Native Ad details:
Sponsor: {sponsor_1['name']}
Tagline: {sponsor_1.get('tagline','')}
CTA: {sponsor_1.get('cta','')}

### SEGMENT 4 (All three: dread/greed forecast + lightning round)
Cover remaining stories. Sharp analogies, messy banter, interruptions.
Include woven-in host-read sponsor:
Sponsor: {sponsor_2['name']} | {sponsor_2.get('tagline','')} | {sponsor_2.get('cta','')}

### SEGMENT 5 (Closing)
Alex closes. Jamie lands one empathetic hit. Rufus gives one cynical prophecy.
Final micro sponsor tag as a joke/aside:
Sponsor: {sponsor_3['name']} | {sponsor_3.get('tagline','')} | {sponsor_3.get('cta','')}

TODAY'S STORIES (must be clearly discussed):
{story_block}

STYLE REQUIREMENTS:
- Make the “soul” real: fear, awe, greed, betrayal, humor, sudden silence.
- Use concrete examples, “what this means tomorrow”, and specific stakes (jobs, markets, power, safety).
- Avoid filler openers like “let’s dive in”.
""".strip()

    return generate_text(prompt, temperature=0.75, max_tokens=SCRIPT_MAX_TOKENS)

def validate_script(script: str) -> List[str]:
    issues: List[str] = []

    # Segment markers present
    for i in range(1, 6):
        if not re.search(rf"^###\s*SEGMENT\s*{i}\b", script, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(f"Missing segment marker: ### SEGMENT {i}")

    # Enough labeled dialogue turns
    turns = sum(1 for line in script.splitlines() if SPEAKER_RE.match(line.strip()))
    if turns < 220:
        issues.append(f"Too few labeled dialogue lines ({turns}).")

    # Speakers present
    for name in ("ALEX", "JAMIE", "RUFUS"):
        if not re.search(rf"^{name}\s*:", script, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(f"Speaker missing: {name}")

    # Length targets
    min_words, max_words = _script_targets()
    wc = _word_count(script)
    if wc < min_words:
        issues.append(f"Script too short ({wc} words). Minimum is {min_words}.")
    if wc > max_words:
        issues.append(f"Script too long ({wc} words). Maximum is {max_words}.")

    # Must not contain obvious non-dialogue blocks
    if re.search(r"```|<html|<body|^Title:|^Podcast:", script, flags=re.IGNORECASE | re.MULTILINE):
        issues.append("Contains non-dialogue formatting blocks.")

    return issues

def repair_script(script: str, stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], date_str: str, issues: List[str]) -> str:
    min_words, max_words = _script_targets()
    story_block = "\n".join([f"- {s['headline']} ({s.get('source_url','')})" for s in stories])

    prompt = f"""
You are fixing a podcast script for "The AI Edge" ({date_str}).

CURRENT ISSUES (must fix all):
{chr(10).join([f"- {x}" for x in issues])}

NON-NEGOTIABLE RULES:
- Output MUST be dialogue lines only using EXACT labels: "ALEX:", "JAMIE:", "RUFUS:"
- Every spoken line MUST start with one of those labels.
- You MUST include segment markers exactly: ### SEGMENT 1 ... ### SEGMENT 5
- ABSOLUTE LENGTH: {min_words} to {max_words} words. Do NOT go under {min_words}.
- Do NOT summarize. EXPAND with more back-and-forth, concrete examples, interruptions, and stakes.
- Preserve the show's tone: raw, urgent, emotional, messy, funny at times.

TODAY'S STORIES (must be clearly discussed):
{story_block}

HERE IS THE SCRIPT TO REPAIR (keep the good parts; expand what’s thin):
{script}
""".strip()

    return generate_text(prompt, temperature=0.65, max_tokens=SCRIPT_MAX_TOKENS)

def generate_episode_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], date_str: str) -> str:
    script = build_script(stories, sponsors, date_str)

    for attempt in range(1, SCRIPT_ATTEMPTS + 1):
        wc = _word_count(script)
        mins = estimate_minutes_from_text(script)
        issues = validate_script(script)

        _safe_print(f"    Script attempt #{attempt}: ~{mins:.1f} min ({wc} words)")

        if not issues:
            return script

        _safe_print("    ⚠️ Script issues detected:")
        for x in issues[:8]:
            _safe_print(f"      - {x}")

        script = repair_script(script, stories, sponsors, date_str, issues)

    final_issues = validate_script(script)
    if final_issues:
        raise RuntimeError("Final script validation failed:\n" + "\n".join(final_issues))
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

        # Continuation line
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

    fallback_hook = (stories[0].get("headline") if stories else "AI JUST MOVED — HERE’S WHAT CHANGED")[:64]
    out = {
        "hook": fallback_hook.upper(),
        "card_subhook": "WHAT BREAKS NEXT?",
        "tweet1": f"{fallback_hook}\n\nWhat’s the real consequence here?",
        "tweet2": f"Full episode: {listen_url}\n\n#AI #TechNews",
        "yt_title": f"{fallback_hook} | The AI Edge",
        "yt_description": f"Listen on Spotify: {listen_url}\n\nTop stories:\n" + "\n".join([f"- {s.get('headline','')}" for s in stories[:5]]),
        "hashtags": "#AI #TechNews #OpenAI #Nvidia",
    }

    try:
        j = json.loads(raw)
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
# RSS FEED WRITER (ROBUST)
# ----------------------------
def update_feed_xml(meta: Dict):
    import xml.etree.ElementTree as ET

    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ET.register_namespace("itunes", ITUNES_NS)

    def is_segment_item(item_el: ET.Element) -> bool:
        t = (item_el.findtext("title") or "").strip().lower()
        if t.startswith("seg_") or t.startswith("segment") or t.startswith("clip_"):
            return True
        enc = item_el.find("enclosure")
        if enc is not None:
            url = (enc.get("url") or "").lower()
            if "/seg_" in url or "seg_" in url or "_seg_" in url:
                return True
        return False

    def parse_date_from_filename(filename: str) -> Optional[str]:
        m = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", filename)
        return m.group(1) if m else None

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

    def make_item(title: str, description: str, audio_filename: str, audio_url: str,
                  pubdate_rfc2822: str, duration_seconds: int = 0) -> ET.Element:
        item = ET.Element("item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "description").text = (description or "")[:8000]

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
        return item

    rss = ET.Element("rss", {"version": "2.0", f"xmlns:itunes": ITUNES_NS})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()

    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = RSS_SETTINGS["author"]
    ET.SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = "no"

    cat = ET.SubElement(channel, f"{{{ITUNES_NS}}}category")
    cat.set("text", RSS_SETTINGS["category"])

    img = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    ET.SubElement(owner, f"{{{ITUNES_NS}}}name").text = RSS_SETTINGS["author"]
    ET.SubElement(owner, f"{{{ITUNES_NS}}}email").text = RSS_SETTINGS["email"]

    existing_episode_items: List[ET.Element] = []
    if FEED_XML_PATH.exists():
        try:
            old_tree = ET.parse(FEED_XML_PATH)
            old_rss = old_tree.getroot()
            old_channel = old_rss.find("channel")
            if old_channel is not None:
                for it in old_channel.findall("item"):
                    if is_segment_item(it):
                        continue
                    enc = it.find("enclosure")
                    if enc is None:
                        continue
                    url = (enc.get("url") or "").lower()
                    if "podcast_" not in url:
                        continue
                    existing_episode_items.append(it)
        except Exception:
            existing_episode_items = []

    audio_file = meta["audio_file"]
    audio_url = meta["audio_url"]
    show_notes = meta.get("show_notes") or ""
    duration_seconds = int(meta.get("duration_seconds") or 0)
    date_str = meta.get("date") or datetime.date.today().isoformat()

    new_item = make_item(
        title=meta["title"],
        description=show_notes,
        audio_filename=audio_file,
        audio_url=audio_url,
        pubdate_rfc2822=rfc2822_from_date(date_str),
        duration_seconds=duration_seconds,
    )

    merged: List[ET.Element] = [new_item]
    seen_urls = {audio_url}

    for old in existing_episode_items:
        enc = old.find("enclosure")
        if enc is None:
            continue
        url = enc.get("url") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(old)

    audio_files = sorted(AUDIO_DIR.glob("podcast_*.mp3"), key=lambda p: p.name, reverse=True)
    for mp3 in audio_files:
        url = AUDIO_BASE_URL + mp3.name
        if url in seen_urls:
            continue
        d = parse_date_from_filename(mp3.name) or date_str
        fallback_title = f"{RSS_SETTINGS['title']} — {d}"
        fallback_desc = f"Listen: {LISTEN_URL}"
        merged.append(
            make_item(
                title=fallback_title,
                description=fallback_desc,
                audio_filename=mp3.name,
                audio_url=url,
                pubdate_rfc2822=rfc2822_from_date(d),
                duration_seconds=0,
            )
        )
        seen_urls.add(url)

    merged = merged[:KEEP_LAST_EPISODES]
    for it in merged:
        channel.append(it)

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    _safe_print(f"✅ feed.xml updated with {len(merged)} episode items")

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
            "link": "https://example.com",
            "summary": "Simulation."
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
        raise RuntimeError("Dialogue parsing produced too few lines. Script format likely broken.")

    # Merge turns to reduce TTS calls
    dialogue_merged = merge_dialogue_for_tts(dialogue, max_chars=TTS_MERGE_MAX_CHARS)

    run_tmp = TMP_AUDIO_DIR / today
    if run_tmp.exists():
        shutil.rmtree(run_tmp, ignore_errors=True)
    run_tmp.mkdir(parents=True, exist_ok=True)

    concat_files: List[Path] = []
    silence_path = run_tmp / "silence_150ms.mp3"
    AudioSegment.silent(duration=150).export(silence_path, format="mp3")

    if INTRO_PATH.exists():
        intro = AudioSegment.from_file(INTRO_PATH)[:15000].fade_out(1200)
        intro_path = run_tmp / "intro_trim.mp3"
        intro.export(intro_path, format="mp3", bitrate="192k")
        concat_files.append(intro_path)

    _safe_print(" >> 🎙️ RECORDING (TTS)...")
    seg_idx = 0

    for speaker, text in dialogue_merged:
        if speaker == "MUSIC":
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

    _safe_print(" >> 🎚️ STITCHING (ffmpeg concat)...")
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found in runner.")
    stitch_with_ffmpeg(concat_files, final_mp3)

    final_audio = AudioSegment.from_mp3(final_mp3)
    duration_seconds = int(len(final_audio) / 1000)
    minutes = duration_seconds / 60.0
    _safe_print(f" ✅ EPISODE COMPLETE: {final_mp3.name} ({minutes:.2f} minutes)")

    if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
        raise RuntimeError(
            f"Episode length out of bounds ({minutes:.2f} min). Must be {MIN_MINUTES}-{MAX_MINUTES}."
        )

    # --- Marketing Pack (Hook + Copy) ---
    pack = generate_marketing_pack(stories, today, LISTEN_URL)

    card_headline = pack["hook"]
    feed_title = f"{pack['hook']} — {today}"

    show_notes = (
        "Top stories:\n"
        + "\n".join([f"- {s['headline']} ({s.get('source_url','')})" for s in stories])
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
