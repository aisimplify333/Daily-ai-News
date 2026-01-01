import os
import json
import re
import time
import hashlib
import datetime
from pathlib import Path
from email.utils import formatdate, parsedate_to_datetime
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from pydub import AudioSegment

# Optional (Gemini). Code will run without Gemini installed.
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

# OpenAI
from openai import OpenAI

# Your project module (email/news ingestion). Optional; main.py will fallback to RSS if it fails.
try:
    import fetch_news
except Exception:
    fetch_news = None


# ============================================================
# 0) CONFIG
# ============================================================

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)

INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

SPONSORS_FILE = BASE_DIR / "sponsors.json"
RSS_FILE = BASE_DIR / "feed.xml"

# GitHub Pages base where MP3s are hosted (must match your repo pages path)
RAW_AUDIO_BASE = os.getenv(
    "RAW_AUDIO_BASE",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
)

# Target length controls (do NOT hard-fail by default; warn and publish)
MIN_MINUTES = float(os.getenv("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "30"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "27"))
ENFORCE_MINUTES = os.getenv("ENFORCE_MINUTES", "0") == "1"  # if 1, will raise when too short

# Story controls
STORIES_TARGET = int(os.getenv("STORIES_TARGET", "7"))  # 5–7 recommended; default 7
STORIES_FETCH_MAX = int(os.getenv("STORIES_FETCH_MAX", "30"))  # how many candidates to pull before selection
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "48"))

# Segment cleanup controls
CLEANUP_TTS_SEGMENTS = os.getenv("CLEANUP_TTS_SEGMENTS", "1") == "1"  # delete *_seg_*.mp3 after final stitch
CLEANUP_OLD_SEGMENT_DAYS = int(os.getenv("CLEANUP_OLD_SEGMENT_DAYS", "3"))  # auto-clean segs older than N days

# Audio pacing controls
GAP_MS = int(os.getenv("GAP_MS", "80"))  # silence between utterances
INTRO_MS = int(os.getenv("INTRO_MS", "15000"))
OUTRO_MS = int(os.getenv("OUTRO_MS", "10000"))

# LLM routing (Gemini primary, OpenAI backup)
PRIMARY_LLM = os.getenv("PRIMARY_LLM", "gemini").lower()  # gemini or openai
OPENAI_SCRIPT_MODEL = os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o-mini")  # cheaper, good enough
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")

# Voices (keep your cast)
CAST = {
    "ALEX": os.getenv("VOICE_ALEX", "onyx"),
    "JAMIE": os.getenv("VOICE_JAMIE", "nova"),
    "RUFUS": os.getenv("VOICE_RUFUS", "fable"),
}

# RSS Settings (Spotify/Apple pickup)
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://aisimplify333.github.io/Daily-ai-News/",
    "description": "Daily AI News, Finance, and Regulation — performed as a humanistic drama between three voices.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
    "language": "en-us",
    "explicit": "no",
}

# Default RSS sources (you can add/remove freely)
DEFAULT_FEEDS = [
    # Mainstream tech + AI
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/tag/ai/latest/rss",
    "https://feeds.arstechnica.com/arstechnica/ai",
    "https://www.technologyreview.com/feed/",
    # Platforms / builders
    "https://openai.com/news/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://blog.google/feed",
    # Aggregators that surface “big impact” quickly
    "https://hnrss.org/newest?q=artificial+intelligence",
    "https://hnrss.org/newest?q=genai",
]

# ============================================================
# 1) ENV HELPERS
# ============================================================

def _env(name: str, required: bool = False, default: str = "") -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def today_str() -> str:
    # Use local runner date
    return datetime.date.today().isoformat()


def safe_print(msg: str):
    print(msg, flush=True)


# ============================================================
# 2) CLIENTS (OpenAI required; Gemini optional)
# ============================================================

client_openai = OpenAI(api_key=_env("OPENAI_API_KEY", required=True))

client_gemini = None
if genai is not None:
    gem_key = os.environ.get("GEMINI_API_KEY")
    if gem_key:
        try:
            client_gemini = genai.Client(api_key=gem_key)
        except Exception:
            client_gemini = None


# ============================================================
# 3) INTEL INGESTION (Email -> RSS -> fallback)
# ============================================================

def _strip_html(text: str) -> str:
    # keep it minimal; you already have BeautifulSoup in fetch_news if needed
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split()).strip()


def _parse_dt(dt_text: str):
    if not dt_text:
        return None
    try:
        return parsedate_to_datetime(dt_text)
    except Exception:
        return None


def fetch_rss_items(feed_urls, lookback_hours=48, per_feed_max=8):
    """
    Pull items from RSS/Atom feeds. Never hard-fails the run.
    Returns list[dict]: {source, title, url, summary, published}
    """
    items = []
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=lookback_hours)

    for feed in feed_urls:
        try:
            req = Request(feed, headers={"User-Agent": "Mozilla/5.0 (DailyAIEdgeBot/1.0)"})
            with urlopen(req, timeout=20) as resp:
                raw = resp.read()
        except (HTTPError, URLError, TimeoutError) as e:
            safe_print(f"    ⚠️ RSS fetch failed: {feed} ({e})")
            continue
        except Exception as e:
            safe_print(f"    ⚠️ RSS fetch failed: {feed} ({e})")
            continue

        try:
            root = ET.fromstring(raw)
        except Exception:
            safe_print(f"    ⚠️ RSS parse failed: {feed} (invalid XML)")
            continue

        # RSS
        channel = root.find("channel")
        if channel is not None:
            src = (channel.findtext("title") or feed).strip()
            for it in channel.findall("item")[:per_feed_max]:
                title = (it.findtext("title") or "").strip()
                url = (it.findtext("link") or "").strip()
                summary = (it.findtext("description") or it.findtext("summary") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                pub_dt = _parse_dt(pub)
                if pub_dt and pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=datetime.timezone.utc)
                if pub_dt and pub_dt < cutoff:
                    continue
                if title:
                    items.append({
                        "source": src,
                        "title": _strip_html(title)[:220],
                        "url": url,
                        "summary": _strip_html(summary)[:800],
                        "published": pub,
                    })
            continue

        # Atom
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        if root.find(f"{ns}entry") is not None:
            src = (root.findtext(f"{ns}title") or feed).strip()
            for ent in root.findall(f"{ns}entry")[:per_feed_max]:
                title = (ent.findtext(f"{ns}title") or "").strip()
                link_el = ent.find(f"{ns}link")
                url = (link_el.attrib.get("href") if link_el is not None else "") or ""
                summary = (ent.findtext(f"{ns}summary") or ent.findtext(f"{ns}content") or "").strip()
                pub = (ent.findtext(f"{ns}updated") or ent.findtext(f"{ns}published") or "").strip()
                # Atom timestamps are often ISO; parsedate_to_datetime may fail; accept as-is
                if title:
                    items.append({
                        "source": src,
                        "title": _strip_html(title)[:220],
                        "url": url,
                        "summary": _strip_html(summary)[:800],
                        "published": pub,
                    })

    # Dedupe by title hash
    seen = set()
    deduped = []
    for it in items:
        h = hashlib.md5(it["title"].lower().encode("utf-8", errors="ignore")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        deduped.append(it)
    return deduped


def gather_intel():
    """
    Returns a *candidate pool* of stories (list[dict]) and a digest string for LLM selection.
    """
    safe_print(" >> 📡 GATHERING INTEL...")

    # 1) Try your existing email workflow (fetch_news.py)
    if fetch_news is not None:
        try:
            safe_print(" >> 📧 TRYING EMAIL INTEL...")
            data = fetch_news.get_todays_newsletters()
            if data and isinstance(data, str) and len(data.strip()) > 50:
                # Convert the email digest into pseudo-items for selection
                return [], data.strip()
        except Exception as e:
            safe_print(f"    ⚠️ EMAIL INTEL FAILED: {e}")

    # 2) RSS workflow (recommended)
    safe_print(" >> 📰 TRYING RSS INTEL...")
    feed_urls = DEFAULT_FEEDS
    items = fetch_rss_items(feed_urls, lookback_hours=LOOKBACK_HOURS, per_feed_max=10)

    # Truncate pool
    items = items[:STORIES_FETCH_MAX]

    if items:
        digest_lines = []
        for it in items:
            digest_lines.append(
                f"SOURCE: {it['source']}\nTITLE: {it['title']}\nSUMMARY: {it['summary']}\nURL: {it['url']}\n---"
            )
        return items, "\n".join(digest_lines)

    # 3) Last resort fallback (keeps pipeline running)
    safe_print("    ⚠️ NO INTEL FOUND. USING FALLBACK STORIES.")
    fallback = """
SOURCE: Internal Fallback
TITLE: AI agents are quietly becoming infinite labor
SUMMARY: Tool-using agents now run multi-step tasks across hours and days, shifting work from humans to persistent software labor.
URL:
---
SOURCE: Internal Fallback
TITLE: Valuations outrun reality as AI becomes a capital war
SUMMARY: Private markets are pricing “AI dominance” like a winner-take-all outcome, with enormous second-order risk.
URL:
---
SOURCE: Internal Fallback
TITLE: Privacy turns into product as conversations become ad inventory
SUMMARY: Chat logs, prompts, and intimate questions are being monetized, creating a new kind of surveillance economy.
URL:
---
"""
    return [], fallback.strip()


# ============================================================
# 4) SPONSORS
# ============================================================

def load_sponsors(n=3):
    """
    sponsors.json expected formats:
      - list of {name, copy, url?}
      - or dict with key "sponsors": [...]
    """
    fallback = [
        {"name": "Oracle Cloud", "copy": "Stop burning cash. Oracle Cloud is built for GPU workloads. Visit Oracle.com."},
        {"name": "NetSuite", "copy": "Visibility is survival. NetSuite gives you the data to survive the crash. NetSuite.com."},
        {"name": "ElevenLabs", "copy": "This show is 100% AI. Scale your content with ElevenLabs.io."},
    ]

    if not SPONSORS_FILE.exists():
        return fallback[:n]

    try:
        obj = json.loads(SPONSORS_FILE.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and "sponsors" in obj:
            sponsors = obj["sponsors"]
        elif isinstance(obj, list):
            sponsors = obj
        else:
            sponsors = []
        sponsors = [s for s in sponsors if isinstance(s, dict) and s.get("name") and s.get("copy")]
        if not sponsors:
            return fallback[:n]
        return sponsors[:n]
    except Exception:
        return fallback[:n]


# ============================================================
# 5) LLM WRAPPERS (Gemini primary, OpenAI backup)
# ============================================================

def _extract_json(text: str):
    """
    Best-effort extraction of the first JSON object in a string.
    """
    if not text:
        return None
    # direct
    try:
        return json.loads(text)
    except Exception:
        pass
    # fenced or embedded
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def gemini_generate(prompt: str, temperature: float = 0.8, max_output_tokens: int = 4096) -> str:
    if client_gemini is None or types is None:
        raise RuntimeError("Gemini client not configured")

    conf = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # Try a small set; accept either "gemini-*" or "models/gemini-*"
    candidates = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    last_err = None
    for model in candidates:
        for mname in (model, f"models/{model}"):
            try:
                resp = client_gemini.models.generate_content(
                    model=mname,
                    contents=prompt,
                    config=conf
                )
                txt = getattr(resp, "text", "") or ""
                if txt.strip():
                    return txt.strip()
            except Exception as e:
                s = str(e)
                last_err = e
                # If quota is literally 0, stop trying Gemini for this run
                if "limit: 0" in s or "RESOURCE_EXHAUSTED" in s:
                    raise RuntimeError(f"Gemini quota exhausted/disabled: {s}")
                # Otherwise try next model/name
                continue
    raise RuntimeError(f"Gemini failed: {last_err}")


def openai_generate(system: str, user: str, temperature: float = 0.8, max_tokens: int = 2500) -> str:
    resp = client_openai.chat.completions.create(
        model=OPENAI_SCRIPT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def llm_generate(system: str, user: str, temperature: float, max_tokens_openai: int, max_tokens_gemini: int):
    """
    Primary LLM with fallback.
    """
    if PRIMARY_LLM == "gemini":
        try:
            prompt = f"SYSTEM:\n{system}\n\nUSER:\n{user}"
            return gemini_generate(prompt, temperature=temperature, max_output_tokens=max_tokens_gemini)
        except Exception as e:
            safe_print(f"    ⚠️ Gemini failed, falling back to OpenAI: {e}")
            return openai_generate(system, user, temperature=temperature, max_tokens=max_tokens_openai)
    else:
        try:
            return openai_generate(system, user, temperature=temperature, max_tokens=max_tokens_openai)
        except Exception as e:
            safe_print(f"    ⚠️ OpenAI failed, falling back to Gemini: {e}")
            prompt = f"SYSTEM:\n{system}\n\nUSER:\n{user}"
            return gemini_generate(prompt, temperature=temperature, max_output_tokens=max_tokens_gemini)


# ============================================================
# 6) EPISODE PLANNING (pick 5–7 stories + SEO + show notes)
# ============================================================

def build_episode_plan(intel_digest: str, sponsors: list):
    """
    Returns dict:
      {
        "episode_hook": "...",
        "episode_title": "...",
        "stories": [{title, source, url, angle, tags}],
        "hashtags": [...],
        "show_notes": "..."
      }
    """
    system = (
        "You are the executive producer and editor for 'The AI Edge' daily podcast. "
        "You select high-impact AI stories and package them for maximum listener retention and SEO. "
        "Return ONLY valid JSON. No markdown."
    )

    user = f"""
DATE: {today_str()}

INTEL DIGEST:
{intel_digest}

TASK:
1) Select exactly {STORIES_TARGET} STORIES with the highest impact today.
   - Mix across: (a) product/model releases, (b) money/valuation/markets, (c) regulation/law/policy, (d) human/ethics/labor, (e) security/misuse.
2) Create a punchy SEO-friendly EPISODE_TITLE (no date in it; we'll add date outside).
3) Create EPISODE_HOOK: one sentence that sounds like we are mid-argument (for cold open).
4) Create HASHTAGS: 12 tags max (no spaces; include #AI #GenAI etc).
5) Create SHOW_NOTES: bullet list of the {STORIES_TARGET} stories + 1-line "why it matters" each, plus sponsor names included at the end.

SPONSORS TODAY (for mentions in show notes):
{json.dumps([s.get("name") for s in sponsors], ensure_ascii=False)}

OUTPUT JSON SCHEMA:
{{
  "episode_title": "string",
  "episode_hook": "string",
  "stories": [
    {{
      "title": "string",
      "source": "string",
      "url": "string",
      "why_it_matters": "string",
      "tags": ["string","string"]
    }}
  ],
  "hashtags": ["#AI", "..."],
  "show_notes": "string"
}}
"""

    raw = llm_generate(system, user, temperature=0.6, max_tokens_openai=2200, max_tokens_gemini=2600)
    plan = _extract_json(raw)
    if not plan or "stories" not in plan:
        safe_print("    ⚠️ Plan JSON parse failed; using minimal fallback plan.")
        plan = {
            "episode_title": "The AI Edge: The Labor Machine Turns On",
            "episode_hook": "Jamie thinks the agents are already out of control; Rufus says that’s the whole point.",
            "stories": [],
            "hashtags": ["#AI", "#GenAI", "#TechNews"],
            "show_notes": raw[:1500] if raw else "",
        }
    return plan


# ============================================================
# 7) SCRIPT WRITING (5 segments; your confirmed structure)
# ============================================================

def write_full_script(plan: dict, sponsors: list):
    """
    Five segments, preserving your dynamics:
      S1: Cold open + welcome + rundown
      S2: Alex + Jamie (studio chemistry)
      S3: Rufus on-location (money/reg) + native ad(s)
      S4: Human impact / ethics escalation (all)
      S5: Verdict / predictions / CTA (Alex close; Jamie button)
    """
    system = (
        "You are the showrunner for 'The AI Edge' Daily Podcast.\n"
        "The vibe is humanistic realism: fast, messy, overheated conversation.\n"
        "Characters are distinct:\n"
        "- ALEX (Host, Rogan-like): high energy, curious, blunt; introduces structure; sets stakes.\n"
        "- JAMIE (Heart, Bartlett-like): vulnerable, empathetic; 'I feel...' and human cost.\n"
        "- RUFUS (Brain/Money, Huberman/Levine-like): cynical, analytical; incentives, regulation, capital.\n\n"
        "Hard rules:\n"
        "1) ZERO corporate speak (ban phrases like 'let's dive in', 'in today's episode', 'dynamic world').\n"
        "2) Interruptions and quick back-and-forth. Short lines. Occasional fragments.\n"
        "3) Standard dialogue ONLY: every spoken line must start with ALEX:, JAMIE:, or RUFUS:.\n"
        "4) Stage directions are allowed ONLY as standalone bracket lines like [MUSIC] or [BEAT].\n"
        "5) Keep it believable: the listener should not suspect it's synthetic.\n"
        "Return ONLY the script text (no commentary)."
    )

    # Build story list for the writer
    stories = plan.get("stories", [])
    story_block = "\n".join(
        [f"{i+1}. {s.get('title','')} ({s.get('source','')}) - {s.get('why_it_matters','')} URL: {s.get('url','')}"
         for i, s in enumerate(stories)]
    )

    sponsor_lines = "\n".join([f"- {s['name']}: {s['copy']}" for s in sponsors])

    user = f"""
DATE: {today_str()}
EPISODE_TITLE: {plan.get('episode_title','The AI Edge')}
COLD_OPEN_HOOK: {plan.get('episode_hook','')}

TODAY'S STORIES (use these; do not invent new ones unless intel is thin):
{story_block}

SPONSORS (RUFUS reads these as insider advice, not as a commercial break):
{sponsor_lines}

STRUCTURE (5 SEGMENTS):
SEGMENT 1 (5–6 min): Cold open mid-argument -> [MUSIC] -> Welcome -> ALEX summarizes all stories in 20–30 seconds (Rogan style) -> set stakes.
SEGMENT 2 (6–7 min): Studio: ALEX + JAMIE only. No Rufus. Deep dive into the most human/behavioral implications of 1–2 stories. High chemistry.
SEGMENT 3 (6–7 min): On-location: ALEX tosses to RUFUS. Rufus covers money + regulation across 2–3 stories. Include TWO native ad reads, woven into analysis.
SEGMENT 4 (5–6 min): Jamie drags it back to human cost. All three. Dread/greed/excitement. Strong metaphors.
SEGMENT 5 (4–5 min): Verdict + predictions + CTA. ALEX closes. JAMIE gets the final human button if it hits her.

TARGET LENGTH: {TARGET_MINUTES} minutes total.
Write enough dialogue to land between {MIN_MINUTES} and {MAX_MINUTES} minutes at ~150 words/minute.

IMPORTANT:
- ALEX must physically introduce the team during the Welcome.
- ALEX must name the stories in the summary rundown (for SEO/listener clarity).
- Do not sound scripted; avoid perfect symmetry.
"""

    script = llm_generate(system, user, temperature=0.85, max_tokens_openai=6000, max_tokens_gemini=6500)

    # Safety: if script is unexpectedly tiny, force a single expansion pass
    wc = len(re.findall(r"\w+", script))
    est_min = wc / 150.0
    if est_min < MIN_MINUTES * 0.7:
        safe_print(f"    ⚠️ Script looks short (est {est_min:.1f} min). Expanding once...")
        user2 = f"""
Your script is too short. Expand SEGMENT 2, 3, and 4 only.
Add ~1800–2200 words total.
Keep continuity. Keep the same vibe and rules.
Return ONLY the full script again, with the same 5 segment headers.
"""
        script2 = llm_generate(system, user2 + "\n\nCURRENT SCRIPT:\n" + script, temperature=0.85,
                              max_tokens_openai=7000, max_tokens_gemini=7500)
        if script2 and len(script2) > len(script):
            script = script2

    return script


# ============================================================
# 8) TTS + STITCHING
# ============================================================

SPEAKER_RE = re.compile(r'^\s*(ALEX|JAMIE|RUFUS)\s*:\s*(.+)\s*$')

def iter_utterances(script: str):
    current = None
    buf = []

    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            # stage direction; flush buffer and skip
            if current and buf:
                yield current, " ".join(buf).strip()
                buf = []
            current = None
            continue

        m = SPEAKER_RE.match(line)
        if m:
            if current and buf:
                yield current, " ".join(buf).strip()
            current = m.group(1).upper()
            buf = [m.group(2).strip()]
        else:
            if current:
                buf.append(line)

    if current and buf:
        yield current, " ".join(buf).strip()


def chunk_text(text: str, limit: int = 3800):
    # Remove bracket content and problematic characters for TTS
    clean = re.sub(r'[\(\[].*?[\)\]]', '', text)
    clean = clean.replace('"', '').replace('*', '').strip()
    if len(clean) <= limit:
        return [clean]

    chunks = []
    t = clean
    while len(t) > limit:
        split_idx = t.rfind('.', 0, limit)
        if split_idx == -1:
            split_idx = limit
        chunks.append(t[:split_idx + 1].strip())
        t = t[split_idx + 1:].strip()
    if t:
        chunks.append(t)
    return chunks


def _seg_paths_for_date(date_iso: str):
    return sorted(AUDIO_DIR.glob(f"{date_iso}_seg_*.mp3"))


def cleanup_old_segments(older_than_days: int):
    if older_than_days <= 0:
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=older_than_days)
    for p in AUDIO_DIR.glob("*_seg_*.mp3"):
        try:
            if datetime.datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
                p.unlink(missing_ok=True)
        except Exception:
            continue


def cleanup_segments_for_date(date_iso: str):
    for p in _seg_paths_for_date(date_iso):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


def tts_build_segments(script: str, date_iso: str):
    """
    Generates TTS segments to episode_audio/{date}_seg_0000.mp3 ... in strict order.
    Returns manifest list of paths in order.
    """
    safe_print(" >> 🎙️  RECORDING (TTS)...")

    # Pre-clean today's segments (prevents accidental stitch of stale segments)
    cleanup_segments_for_date(date_iso)

    seg_idx = 0
    manifest = []

    for speaker, text in iter_utterances(script):
        voice = CAST.get(speaker)
        if not voice:
            continue
        for chunk in chunk_text(text):
            if len(chunk) < 2:
                continue
            outp = AUDIO_DIR / f"{date_iso}_seg_{seg_idx:04d}.mp3"
            try:
                with client_openai.audio.speech.with_streaming_response.create(
                    model=OPENAI_TTS_MODEL,
                    voice=voice,
                    input=chunk
                ) as resp:
                    resp.stream_to_file(outp)
                manifest.append(str(outp))
                seg_idx += 1
            except Exception as e:
                safe_print(f"    ⚠️ TTS error on seg {seg_idx}: {e}")
                # keep going; don't hard-fail

    return manifest


def stitch_episode(manifest_paths: list):
    """
    Stitches segments + intro/outro into one AudioSegment.
    """
    safe_print(" >> 🎚️  STITCHING...")

    clips = []

    if INTRO_MUSIC.exists():
        try:
            clips.append(AudioSegment.from_mp3(INTRO_MUSIC)[:INTRO_MS].fade_out(2000))
        except Exception as e:
            safe_print(f"    ⚠️ Intro load failed: {e}")

    for p in manifest_paths:
        try:
            clips.append(AudioSegment.from_mp3(p))
            clips.append(AudioSegment.silent(duration=GAP_MS))
        except Exception as e:
            safe_print(f"    ⚠️ Segment load failed: {p} ({e})")

    if OUTRO_MUSIC.exists():
        try:
            clips.append(AudioSegment.from_mp3(OUTRO_MUSIC)[:OUTRO_MS].fade_in(2000))
        except Exception as e:
            safe_print(f"    ⚠️ Outro load failed: {e}")

    if not clips:
        return AudioSegment.empty()

    full = clips[0]
    for c in clips[1:]:
        full = full.append(c, crossfade=0)
    return full


def audio_minutes(seg: AudioSegment) -> float:
    return len(seg) / 1000.0 / 60.0


# ============================================================
# 9) RSS (Spotify pickup)
# ============================================================

def ensure_rss_exists():
    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ET.register_namespace("itunes", ITUNES_NS)

    if RSS_FILE.exists():
        return

    rss = ET.Element("rss", {"version": "2.0", f"xmlns:itunes": ITUNES_NS})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "language").text = RSS_SETTINGS["language"]

    # iTunes tags
    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = RSS_SETTINGS["author"]
    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    ET.SubElement(owner, f"{{{ITUNES_NS}}}name").text = RSS_SETTINGS["author"]
    ET.SubElement(owner, f"{{{ITUNES_NS}}}email").text = RSS_SETTINGS["email"]
    ET.SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = RSS_SETTINGS["explicit"]

    img = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", RSS_SETTINGS["image"])

    cat = ET.SubElement(channel, f"{{{ITUNES_NS}}}category")
    cat.set("text", RSS_SETTINGS["category"])

    tree = ET.ElementTree(rss)
    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)


def update_rss_feed(audio_path: Path, title: str, description: str):
    ensure_rss_exists()

    tree = ET.parse(RSS_FILE)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS channel not found")

    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = description

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", f"{RAW_AUDIO_BASE}{audio_path.name}")
    enclosure.set("length", str(audio_path.stat().st_size))
    enclosure.set("type", "audio/mpeg")

    ET.SubElement(item, "guid").text = f"{RAW_AUDIO_BASE}{audio_path.name}"
    ET.SubElement(item, "pubDate").text = formatdate(audio_path.stat().st_mtime)

    # Insert item after channel metadata, before first existing item
    children = list(channel)
    first_item_idx = None
    for idx, ch in enumerate(children):
        if ch.tag == "item":
            first_item_idx = idx
            break
    if first_item_idx is None:
        channel.append(item)
    else:
        channel.insert(first_item_idx, item)

    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)


# ============================================================
# 10) PRODUCE EPISODE (END-TO-END)
# ============================================================

def produce_episode():
    # housekeeping
    cleanup_old_segments(CLEANUP_OLD_SEGMENT_DAYS)

    date_iso = today_str()
    sponsors = load_sponsors(n=3)

    items, intel_digest = gather_intel()

    safe_print(" >> 🧠 BUILDING EPISODE PLAN...")
    plan = build_episode_plan(intel_digest, sponsors)

    safe_print(" >> ✍️  WRITING FULL SCRIPT (5 SEGMENTS)...")
    script = write_full_script(plan, sponsors)

    # SEO / metadata artifacts
    episode_title = f"Daily AI Edge: {date_iso} — {plan.get('episode_title','The AI Edge')}"
    show_notes = plan.get("show_notes", "").strip()
    hashtags = plan.get("hashtags", [])
    if hashtags and isinstance(hashtags, list):
        show_notes = (show_notes + "\n\n" + " ".join(hashtags)).strip()

    (BASE_DIR / "viral_caption.txt").write_text(show_notes[:4000], encoding="utf-8")

    meta = {
        "title": episode_title,
        "date": date_iso,
        "hashtags": hashtags,
        "stories": plan.get("stories", []),
    }
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # TTS segments
    manifest = tts_build_segments(script, date_iso)

    if not manifest:
        raise RuntimeError("No TTS segments were generated. Aborting.")

    # Stitch
    full_audio = stitch_episode(manifest)
    minutes = audio_minutes(full_audio)

    outfile = AUDIO_DIR / f"podcast_{date_iso}.mp3"
    safe_print(f" >> 💾 EXPORTING: {outfile.name} ...")
    full_audio.export(outfile, format="mp3", bitrate="192k")

    safe_print(f" ✅ EPISODE COMPLETE: {outfile} ({minutes:.2f} minutes)")

    # Guardrail (optional hard fail)
    if minutes < MIN_MINUTES:
        msg = f"⚠️ WARNING: Episode is short ({minutes:.2f} min). Target {MIN_MINUTES}-{MAX_MINUTES}."
        safe_print(msg)
        if ENFORCE_MINUTES:
            raise RuntimeError(msg)

    # Update RSS so Spotify/clients pick it up
    safe_print(" >> 📡 UPDATING RSS FEED...")
    update_rss_feed(outfile, episode_title, show_notes[:5000])

    # Cleanup segments (do NOT delete podcast_*.mp3)
    if CLEANUP_TTS_SEGMENTS:
        safe_print(" >> 🧹 CLEANING UP TTS SEGMENTS...")
        cleanup_segments_for_date(date_iso)

    return outfile


if __name__ == "__main__":
    produce_episode()
