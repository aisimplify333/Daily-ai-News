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

from pydub import AudioSegment
from openai import OpenAI

# Optional Gemini SDKs:
# - google.generativeai is deprecated but may already be installed in your repo.
# - google.genai is the newer SDK; only used if installed (optional).
try:
    import google.genai as genai_new  # type: ignore
except Exception:
    genai_new = None

try:
    import google.generativeai as genai_old  # type: ignore
except Exception:
    genai_old = None


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

# Where Spotify reads the audio from (GitHub Pages)
AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
).rstrip("/") + "/"

LISTEN_URL = os.getenv(
    "LISTEN_URL",
    "https://aisimplify333.github.io/Daily-ai-News/listen/"
).rstrip("/") + "/"

# Split LLM routing so Gemini RPM limits don't kill the run.
PRIMARY_LLM_SCRIPT = os.getenv("PRIMARY_LLM_SCRIPT", "openai").strip().lower()  # gemini | openai
PRIMARY_LLM_MISC = os.getenv("PRIMARY_LLM_MISC", "openai").strip().lower()      # gemini | openai

OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")

MIN_MINUTES = float(os.getenv("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "30"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "28"))

# For planning word count; TTS often runs faster than human read, so be conservative.
WORDS_PER_MINUTE = float(os.getenv("WORDS_PER_MINUTE", "155"))

# Output controls
SCRIPT_SEGMENT_MAX_TOKENS = int(os.getenv("SCRIPT_SEGMENT_MAX_TOKENS", "2800"))
SEGMENT_RETRIES = int(os.getenv("SEGMENT_RETRIES", "3"))
GLOBAL_REPAIR_RETRIES = int(os.getenv("GLOBAL_REPAIR_RETRIES", "2"))

CLEANUP_TEMP = os.getenv("CLEANUP_TEMP", "true").strip().lower() in ("1", "true", "yes")
KEEP_LAST_EPISODES = int(os.getenv("KEEP_LAST_EPISODES", "60"))

RUN_MARKETING_ASSETS = os.getenv("RUN_MARKETING_ASSETS", "true").strip().lower() in ("1", "true", "yes")
PUBLISH_SOCIAL = os.getenv("PUBLISH_SOCIAL", "false").strip().lower() in ("1", "true", "yes")

# If audio lands slightly outside bounds, allow a small pad/trim instead of hard fail.
AUDIO_PAD_MAX_SECONDS = int(os.getenv("AUDIO_PAD_MAX_SECONDS", "120"))
AUDIO_TRIM_MAX_SECONDS = int(os.getenv("AUDIO_TRIM_MAX_SECONDS", "60"))

VOICE_MAP = {
    "ALEX": os.getenv("VOICE_ALEX", "onyx"),
    "JAMIE": os.getenv("VOICE_JAMIE", "nova"),
    "RUFUS": os.getenv("VOICE_RUFUS", "fable"),
}

# ----------------------------
# CLIENTS
# ----------------------------
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

# new SDK client (optional)
genai_new_client = None
if genai_new and gemini_key:
    try:
        genai_new_client = genai_new.Client(api_key=gemini_key)
    except Exception:
        genai_new_client = None

# old SDK configure (optional)
if genai_old and gemini_key:
    try:
        genai_old.configure(api_key=gemini_key)
    except Exception:
        pass


def _safe_print(msg: str):
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


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def estimate_minutes_from_text(script: str) -> float:
    return _count_words(script) / max(1.0, WORDS_PER_MINUTE)


def generate_text(
    prompt: str,
    *,
    llm: str,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    system: str = "You are a top-tier writer. Follow the requested format exactly."
) -> str:
    """
    llm: "openai" or "gemini"
    """
    llm = (llm or "openai").strip().lower()

    if llm == "gemini" and gemini_key:
        # Prefer YOUR current models (per your screenshot)
        candidates = [
            os.getenv("GEMINI_MODEL", "").strip(),
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-3-flash",
        ]
        candidates = [m for m in candidates if m]

        # Backoff for 429/rate limits
        for model_name in candidates:
            for attempt in range(1, 4):
                try:
                    if genai_new_client:
                        # New SDK path (if installed)
                        resp = genai_new_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config={
                                "temperature": temperature,
                                "max_output_tokens": max_tokens,
                            },
                        )
                        txt = getattr(resp, "text", None)
                        if txt and str(txt).strip():
                            return str(txt).strip()

                    if genai_old:
                        # Old SDK path
                        model = genai_old.GenerativeModel(model_name)
                        resp = model.generate_content(
                            prompt,
                            generation_config={
                                "temperature": temperature,
                                "max_output_tokens": max_tokens,
                            },
                        )
                        txt = getattr(resp, "text", None)
                        if txt and txt.strip():
                            return txt.strip()

                except Exception as e:
                    wait = min(12, 2 * attempt)
                    _safe_print(f"    ⚠️ Gemini failed ({model_name}) attempt {attempt}/3: {e} — waiting {wait}s")
                    time.sleep(wait)

        _safe_print("    ⚠️ Gemini unavailable. Falling back to OpenAI...")

    # OpenAI with small retry
    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            resp = openai_client.chat.completions.create(
                model=OPENAI_CHAT_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            wait = min(10, 2 * attempt)
            _safe_print(f"    ⚠️ OpenAI failed attempt {attempt}/3: {e} — waiting {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"generate_text failed after retries: {last_err}")


# ----------------------------
# NEWS INTEL (RSS primary)
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
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_rss_items(max_per_feed: int = 10) -> List[Dict[str, str]]:
    import urllib.request
    import xml.etree.ElementTree as ET

    items: List[Dict[str, str]] = []
    for label, url in GOOGLE_NEWS_RSS:
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                xml_data = r.read()
            root = ET.fromstring(xml_data)
            for it in root.findall("./channel/item")[:max_per_feed]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = _strip_html(it.findtext("description") or "")
                if title and link:
                    items.append({"bucket": label, "title": title, "link": link, "summary": desc[:450]})
        except Exception as e:
            _safe_print(f"    ⚠️ RSS fetch failed ({label}): {e}")

    seen = set()
    deduped = []
    for x in items:
        key = x["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(x)

    return deduped


def load_sponsors() -> List[Dict[str, str]]:
    if SPONSORS_PATH.exists():
        try:
            data = json.loads(SPONSORS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "sponsors" in data:
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

    raw = generate_text(
        prompt,
        llm=PRIMARY_LLM_MISC,
        temperature=0.35,
        max_tokens=1400,
        system="You are an editor for a high-stakes daily show. Return only valid JSON."
    )

    try:
        j = json.loads(raw)
        stories = j.get("stories", [])
        stories = [s for s in stories if isinstance(s, dict)]
        norm = []
        for s in stories[:n]:
            norm.append({
                "headline": (s.get("headline") or "").strip(),
                "why_shocking": (s.get("why_shocking") or "").strip(),
                "angles": s.get("angles") if isinstance(s.get("angles"), dict) else {"alex": "", "jamie": "", "rufus": ""},
                "source_url": (s.get("source_url") or "").strip(),
            })
        if any(not x["headline"] for x in norm):
            raise ValueError("Empty headline returned.")
        return norm
    except Exception:
        return [
            {"headline": x["title"], "why_shocking": x["summary"], "angles": {"alex": "", "jamie": "", "rufus": ""}, "source_url": x["link"]}
            for x in intel_items[:n]
        ]


# ----------------------------
# SCRIPT BUILDING (SEGMENTED + HARD WORD TARGETS)
# ----------------------------
def _show_bible() -> str:
    return """
SHOW SOUL (non-negotiable):
- This is NOT a calm news recap. It’s an overheard argument with stakes.
- Interruptions, callbacks, sharp emotion, no corporate filler.
- Alex: pace + urgency + framing. Jamie: human consequence + empathy. Rufus: money/reg + cynical incentives.
- Avoid phrases: "let’s dive in", "in today’s landscape", "moving forward", "synergy", "AI is transforming".
- They speak like real people. They disagree. They crack under it.
""".strip()


def _segment_targets(total_words: int) -> Dict[int, int]:
    # Ratios tuned to hit 25–30 minutes with the “meat” in Seg 2 and Seg 4.
    ratios = {1: 0.14, 2: 0.24, 3: 0.18, 4: 0.30, 5: 0.14}
    targets = {k: int(total_words * v) for k, v in ratios.items()}
    # Ensure minimums
    targets[1] = max(targets[1], 450)
    targets[2] = max(targets[2], 1100)
    targets[3] = max(targets[3], 800)
    targets[4] = max(targets[4], 1400)
    targets[5] = max(targets[5], 450)
    return targets


def _stories_block(stories: List[Dict[str, str]]) -> str:
    out = []
    for i, s in enumerate(stories, start=1):
        out.append(f"[STORY {i}] {s['headline']} | {s.get('source_url','')}")
        if s.get("why_shocking"):
            out.append(f"  - why_shocking: {s['why_shocking']}")
    return "\n".join(out)


def _sponsor_block(s: Dict[str, str]) -> str:
    return f"Sponsor: {s.get('name','')}\nTagline: {s.get('tagline','')}\nCTA: {s.get('cta','')}"


def generate_segment(
    seg_num: int,
    *,
    target_words: int,
    stories: List[Dict[str, str]],
    sponsors: List[Dict[str, str]],
    continuity: str
) -> str:
    sponsor_1 = sponsors[0] if len(sponsors) > 0 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_2 = sponsors[1] if len(sponsors) > 1 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_3 = sponsors[2] if len(sponsors) > 2 else {"name": "Sponsor", "tagline": "", "cta": ""}

    # Assign story emphasis per segment (but they can callback across segments)
    # Seg1: hook + lineup of all 5
    # Seg2: Story 1 & 2 deep, Alex+Jamie only
    # Seg3: Story 3 deep w/ Rufus and sponsor_1
    # Seg4: Stories 4 & 5 + lightning callbacks + sponsor_2
    # Seg5: close + sponsor_3 tag
    seg_focus = {
        1: "You must mention all 5 stories in Alex’s rapid lineup summary.",
        2: "Focus mainly on STORY 1 and STORY 2. Alex+Jamie only (NO Rufus).",
        3: "Focus mainly on STORY 3. Alex throws to Rufus. Include native ad seamlessly.",
        4: "Focus mainly on STORY 4 and STORY 5. All three. Lightning round callbacks to earlier stories.",
        5: "Closing beat: Jamie hits human consequence. Rufus cynical prophecy. Alex closes. Micro sponsor aside.",
    }[seg_num]

    seg_rules = {
        1: """
Segment 1 requirements:
- Start mid-argument (first line is dialogue, no intro).
- Include a standalone line: [MUSIC]
- After [MUSIC], Alex welcomes + gives a rapid 5-story lineup (fast, urgent).
""".strip(),
        2: """
Segment 2 requirements:
- ALEX and JAMIE ONLY.
- Fast chemistry. Human stakes. At least 2 emotional punches from Jamie.
""".strip(),
        3: f"""
Segment 3 requirements:
- Alex throws to Rufus like "we're going live with Rufus" vibe.
- Rufus delivers insider money/reg angle.
- Must include the native sponsor as seamless "insider tip" (not a cheesy ad).
Native ad details:
{_sponsor_block(sponsor_1)}
""".strip(),
        4: f"""
Segment 4 requirements:
- All three present.
- Cover remaining stories with dread/greed forecast + lightning round.
- Must include host-read sponsor woven in naturally (not a break).
Sponsor details:
{_sponsor_block(sponsor_2)}
""".strip(),
        5: f"""
Segment 5 requirements:
- Closing. Alex wraps. Jamie lands one empathetic hit. Rufus cynical prophecy.
- Final micro sponsor tag as a joke/aside:
{_sponsor_block(sponsor_3)}
""".strip(),
    }[seg_num]

    prompt = f"""
{_show_bible()}

FORMAT (hard):
- Output dialogue lines ONLY.
- Every spoken line MUST start with EXACT labels: ALEX:, JAMIE:, RUFUS:
- You may include [MUSIC] as a standalone line (only in Segment 1).
- Do NOT write stage directions. Do NOT write paragraphs. No markdown.
- Do NOT include "###" here; main.py will wrap with segment headers.

SEGMENT {seg_num} WORD COUNT (hard):
- Target at least {target_words} words in this segment alone.
- If you feel done early, keep writing more dialogue until you hit the word target.

FOCUS:
{seg_focus}

SEGMENT RULES:
{seg_rules}

TODAY’S STORIES (reference):
{_stories_block(stories)}

CONTINUITY SO FAR (what already happened; keep it consistent):
{continuity if continuity else "(none yet)"}

Now write Segment {seg_num}.
""".strip()

    return generate_text(
        prompt,
        llm=PRIMARY_LLM_SCRIPT,
        temperature=0.85 if seg_num in (2, 4) else 0.75,
        max_tokens=SCRIPT_SEGMENT_MAX_TOKENS,
        system="You are a top-tier podcast writer. Output must be strictly formatted dialogue lines only.",
    )


def normalize_script(script: str) -> str:
    """
    Converts common drift formats into strict ALEX:/JAMIE:/RUFUS: lines.
    Also removes empty/garbage lines while preserving [MUSIC].
    """
    lines = []
    for raw in (script or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        # Keep [MUSIC]
        if line.upper() == "[MUSIC]":
            lines.append("[MUSIC]")
            continue

        # Normalize speaker prefixes:
        # Examples: "ALEX — blah", "ALEX - blah", "ALEX (Host): blah", "ALEX: blah"
        m = re.match(r"^(ALEX|JAMIE|RUFUS)\s*(?:\([^)]+\))?\s*[:\-—]\s*(.+)$", line, re.IGNORECASE)
        if m:
            spk = m.group(1).upper()
            txt = m.group(2).strip().strip('"').strip()
            if txt:
                lines.append(f"{spk}: {txt}")
            continue

        # If line doesn't match, discard (prevents paragraphs breaking TTS loop).
        # If you prefer to keep them, you can attach to last speaker, but that risks weird voice.
        continue

    return "\n".join(lines).strip()


def validate_full_script(script: str) -> Tuple[bool, str]:
    if not script or len(script) < 2000:
        return False, "Script too short/empty."
    if "[MUSIC]" not in script:
        return False, "Missing [MUSIC]."
    if not re.search(r"^ALEX:", script, re.MULTILINE):
        return False, "Missing ALEX lines."
    if not re.search(r"^JAMIE:", script, re.MULTILINE):
        return False, "Missing JAMIE lines."
    if not re.search(r"^RUFUS:", script, re.MULTILINE):
        return False, "Missing RUFUS lines."
    return True, "OK"


def build_full_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]]) -> str:
    total_target_words = int(TARGET_MINUTES * WORDS_PER_MINUTE)
    min_words = int(MIN_MINUTES * WORDS_PER_MINUTE)
    max_words = int(MAX_MINUTES * WORDS_PER_MINUTE)

    targets = _segment_targets(total_target_words)

    continuity = ""
    segments: Dict[int, str] = {}

    for seg_num in [1, 2, 3, 4, 5]:
        best = ""
        best_words = 0

        for attempt in range(1, SEGMENT_RETRIES + 1):
            _safe_print(f"    ✍️ Segment {seg_num} attempt {attempt}/{SEGMENT_RETRIES} (target {targets[seg_num]} words)")
            seg = generate_segment(
                seg_num,
                target_words=targets[seg_num],
                stories=stories,
                sponsors=sponsors,
                continuity=continuity,
            )
            seg = normalize_script(seg)
            w = _count_words(seg)

            if w > best_words:
                best = seg
                best_words = w

            if w >= targets[seg_num]:
                break
            _safe_print(f"    ⚠️ Segment {seg_num} short ({w} words). Retrying with stronger length pressure...")

        segments[seg_num] = best

        # continuity summary for the next segment (short, not bloated)
        continuity = (continuity + "\n" + f"- Segment {seg_num} key beats: "
                      f"{(' '.join(best.split()[:60]) + ' ...') if best else '(missing)'}").strip()

    # Wrap with explicit segment headers
    full = "\n".join([
        "### SEGMENT 1",
        segments.get(1, ""),
        "### SEGMENT 2",
        segments.get(2, ""),
        "### SEGMENT 3",
        segments.get(3, ""),
        "### SEGMENT 4",
        segments.get(4, ""),
        "### SEGMENT 5",
        segments.get(5, ""),
    ]).strip()

    # Normalize again (in case headers introduced noise)
    # Keep headers in full script (they get skipped by iter_dialogue)
    # But ensure the content under headers is normalized
    # (We normalize only dialogue lines; headers remain.)
    cleaned_lines = []
    for raw in full.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("###"):
            cleaned_lines.append(line)
            continue
        if line == "[MUSIC]":
            cleaned_lines.append(line)
            continue
        m = re.match(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            cleaned_lines.append(f"{m.group(1).upper()}: {m.group(2).strip()}")
            continue
        # drop non-dialogue noise
        continue
    full = "\n".join(cleaned_lines).strip()

    ok, reason = validate_full_script(full)
    if not ok:
        _safe_print(f"    ⚠️ Full script validation failed: {reason}. Attempting global repair...")

        for attempt in range(1, GLOBAL_REPAIR_RETRIES + 1):
            repair_prompt = f"""
Repair this full script to comply with format WITHOUT shortening it.

Hard rules:
- Keep ALL segment headers exactly: ### SEGMENT 1 ... ### SEGMENT 5
- Keep [MUSIC] as a standalone line in Segment 1
- All spoken lines must start with EXACT labels: ALEX:, JAMIE:, RUFUS:
- Output must be dialogue lines only (plus the ### headers and [MUSIC]).
- Do NOT add prose paragraphs.

You must also ensure the total word count is at least {min_words} words (ideally ~{total_target_words}, max ~{max_words}).

SCRIPT:
{full}
""".strip()
            full = generate_text(
                repair_prompt,
                llm=PRIMARY_LLM_SCRIPT,
                temperature=0.35,
                max_tokens=SCRIPT_SEGMENT_MAX_TOKENS * 2,
                system="You are a strict format enforcer. Output must be compliant and long enough.",
            )
            # re-clean
            tmp = []
            for raw in full.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("###") or line == "[MUSIC]":
                    tmp.append(line)
                    continue
                m = re.match(r"^(ALEX|JAMIE|RUFUS)\s*(?:\([^)]+\))?\s*[:\-—]\s*(.+)$", line, re.IGNORECASE)
                if m:
                    tmp.append(f"{m.group(1).upper()}: {m.group(2).strip()}")
            full = "\n".join(tmp).strip()

            ok, reason = validate_full_script(full)
            if ok:
                break

    # Final length sanity (do not fail here; TTS duration is the ultimate measure)
    words = _count_words(full)
    est = estimate_minutes_from_text(full)
    _safe_print(f"    ✅ Script complete: {words} words (~{est:.1f} min est @ {WORDS_PER_MINUTE} wpm)")
    if words < min_words:
        _safe_print(f"    ⚠️ Script still under minimum word target ({words} < {min_words}). "
                    f"It may produce a short episode. Consider raising SCRIPT_SEGMENT_MAX_TOKENS or lowering WORDS_PER_MINUTE.")

    return full


# ----------------------------
# TTS + STITCHING
# ----------------------------
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)


def iter_dialogue(script: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for raw_line in (script or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("###"):
            continue
        if line.upper() == "[MUSIC]":
            out.append(("MUSIC", "[MUSIC]"))
            continue
        m = SPEAKER_RE.match(line)
        if not m:
            continue
        out.append((m.group(1).upper(), m.group(2).strip()))
    return out


def chunk_text(s: str, max_chars: int = 2800) -> List[str]:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_chars:
        return [s]
    chunks = []
    while len(s) > max_chars:
        cut = s.rfind(". ", 0, max_chars)
        if cut < 500:
            cut = max_chars
        chunks.append(s[:cut].strip())
        s = s[cut:].strip()
    if s:
        chunks.append(s)
    return chunks


def tts_to_file(text: str, voice: str, out_path: Path):
    with openai_client.audio.speech.with_streaming_response.create(
        model=OPENAI_TTS_MODEL,
        voice=voice,
        input=text,
    ) as resp:
        resp.stream_to_file(str(out_path))


def stitch_with_ffmpeg(file_list: List[Path], out_path: Path):
    concat_txt = out_path.parent / f"concat_{uuid.uuid4().hex}.txt"
    concat_txt.write_text("\n".join([f"file '{p.as_posix()}'" for p in file_list]), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-af", "aresample=async=1:first_pts=0",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)

    try:
        concat_txt.unlink()
    except Exception:
        pass


def _pad_or_trim_audio_to_bounds(mp3_path: Path) -> Tuple[int, float]:
    audio = AudioSegment.from_mp3(mp3_path)
    duration_seconds = int(len(audio) / 1000)
    minutes = duration_seconds / 60.0

    if minutes < MIN_MINUTES:
        need = int((MIN_MINUTES * 60) - duration_seconds)
        if 0 < need <= AUDIO_PAD_MAX_SECONDS:
            _safe_print(f"    ⚠️ Audio under min by {need}s — padding with silence")
            audio = audio + AudioSegment.silent(duration=need * 1000)
            audio.export(mp3_path, format="mp3", bitrate="192k")
            audio = AudioSegment.from_mp3(mp3_path)
            duration_seconds = int(len(audio) / 1000)
            minutes = duration_seconds / 60.0

    if minutes > MAX_MINUTES:
        over = int(duration_seconds - (MAX_MINUTES * 60))
        if 0 < over <= AUDIO_TRIM_MAX_SECONDS:
            _safe_print(f"    ⚠️ Audio over max by {over}s — trimming tail")
            keep_ms = int(MAX_MINUTES * 60 * 1000)
            audio = audio[:keep_ms].fade_out(900)
            audio.export(mp3_path, format="mp3", bitrate="192k")
            audio = AudioSegment.from_mp3(mp3_path)
            duration_seconds = int(len(audio) / 1000)
            minutes = duration_seconds / 60.0

    return duration_seconds, minutes


# ----------------------------
# MARKETING
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

    raw = generate_text(
        prompt,
        llm=PRIMARY_LLM_MISC,
        temperature=0.6,
        max_tokens=900,
        system="You are an elite direct-response copywriter. Return only valid JSON."
    )

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
# RSS FEED WRITER (robust)
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

    def make_item(
        title: str,
        description: str,
        audio_filename: str,
        audio_url: str,
        pubdate_rfc2822: str,
        duration_seconds: int = 0,
    ) -> ET.Element:
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
        merged.append(
            make_item(
                title=f"{RSS_SETTINGS['title']} — {d}",
                description=f"Listen: {LISTEN_URL}",
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

    _safe_print(" >> ✍️ WRITING FULL EPISODE (SEGMENTED)...")
    script = build_full_script(stories, sponsors)

    est = estimate_minutes_from_text(script)
    _safe_print(f"    Estimated minutes (text): ~{est:.1f}")

    script_path = BASE_DIR / f"script_{today}.txt"
    script_path.write_text(script, encoding="utf-8")

    # Build TTS workspace
    run_tmp = TMP_AUDIO_DIR / today
    if run_tmp.exists():
        shutil.rmtree(run_tmp, ignore_errors=True)
    run_tmp.mkdir(parents=True, exist_ok=True)

    concat_files: List[Path] = []

    # silence spacer
    silence_path = run_tmp / "silence_150ms.mp3"
    AudioSegment.silent(duration=150).export(silence_path, format="mp3")

    # intro
    if INTRO_PATH.exists():
        intro = AudioSegment.from_file(INTRO_PATH)[:15000].fade_out(1200)
        intro_path = run_tmp / "intro_trim.mp3"
        intro.export(intro_path, format="mp3", bitrate="192k")
        concat_files.append(intro_path)

    _safe_print(" >> 🎙️ RECORDING (TTS)...")
    dialogue = iter_dialogue(script)
    if len(dialogue) < 80:
        # Write debug file and hard fail; this should not happen with normalizer + segmented generation.
        (BASE_DIR / f"debug_bad_script_{today}.txt").write_text(script, encoding="utf-8")
        raise RuntimeError(f"Dialogue parsing produced too few lines ({len(dialogue)}). Debug script saved.")

    seg_idx = 0
    for speaker, text in dialogue:
        if speaker == "MUSIC":
            concat_files.append(silence_path)
            continue

        voice = VOICE_MAP.get(speaker, "onyx")
        for chunk in chunk_text(text):
            seg_idx += 1
            seg_path = run_tmp / f"{today}_seg_{seg_idx:04d}.mp3"
            tts_to_file(chunk, voice, seg_path)
            concat_files.append(seg_path)
            concat_files.append(silence_path)

    # outro
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

    duration_seconds, minutes = _pad_or_trim_audio_to_bounds(final_mp3)
    _safe_print(f" ✅ EPISODE COMPLETE: {final_mp3.name} ({minutes:.2f} minutes)")

    if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
        raise RuntimeError(
            f"Episode length out of bounds ({minutes:.2f} min). Must be {MIN_MINUTES}-{MAX_MINUTES}."
        )

    # Marketing pack
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
