import os
import json
import re
import shutil
import time
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

from openai import OpenAI
from google import genai
from google.genai import types
from pydub import AudioSegment, effects

import fetch_news  # must exist in your repo


# =========================
# CONFIG
# =========================

BASE_DIR = Path(__file__).parent
EPISODE_DIR = BASE_DIR / "episode_audio"
TMP_DIR = BASE_DIR / "_tmp_audio"

INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

EPISODE_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# Spotify / RSS (keep these stable)
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://aisimplify333.github.io/Daily-ai-News/episode_audio/",
    "description": "Daily AI News, Finance, and Regulation.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
    "language": "en-us",
}

RAW_AUDIO_BASE = "https://aisimplify333.github.io/Daily-ai-News/episode_audio"

# Voice cast (OpenAI TTS voices)
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable",
}

# Length guardrails
MIN_MINUTES = float(os.environ.get("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "30"))
TARGET_MINUTES = float(os.environ.get("TARGET_MINUTES", "28.5"))

# Controls
KEEP_TMP = os.environ.get("KEEP_TMP_AUDIO", "0") == "1"
STRICT_LENGTH = os.environ.get("STRICT_LENGTH", "1") == "1"

# LLM models
# You can override in Actions secrets/vars if needed
GEMINI_PRIMARY_MODEL = os.environ.get("GEMINI_PRIMARY_MODEL", "gemini-2.0-flash")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash-lite")
OPENAI_SCRIPT_MODEL = os.environ.get("OPENAI_SCRIPT_MODEL", "gpt-4o-mini")

# TTS
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1-hd")
TTS_CHAR_LIMIT = int(os.environ.get("TTS_CHAR_LIMIT", "3500"))

SILENCE_BETWEEN_MS = int(os.environ.get("SILENCE_BETWEEN_MS", "150"))


# =========================
# UTIL
# =========================

def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

def minutes_of(audio: AudioSegment) -> float:
    return len(audio) / 1000.0 / 60.0

def normalize_text(s: str) -> str:
    # remove bracketed stage directions for TTS cleanliness
    s = re.sub(r"[\(\[].*?[\)\]]", "", s)
    s = s.replace('"', "").replace("*", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def chunk_for_tts(text: str, limit: int = TTS_CHAR_LIMIT):
    text = normalize_text(text)
    if len(text) <= limit:
        return [text]

    chunks = []
    while len(text) > limit:
        # try to split on sentence boundary
        split_idx = text.rfind(".", 0, limit)
        if split_idx < 200:
            split_idx = limit
        chunk = text[: split_idx + 1].strip()
        chunks.append(chunk)
        text = text[split_idx + 1 :].strip()

    if text:
        chunks.append(text)
    return chunks


# =========================
# CLIENTS
# =========================

client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))
client_gemini = genai.Client(api_key=require_env("GEMINI_API_KEY"))


# =========================
# CONTENT INTAKE
# =========================

def gather_intel_raw() -> str:
    print(" >> 📡 GATHERING INTEL FROM EMAILS...")
    try:
        data = fetch_news.get_todays_newsletters()
        if isinstance(data, (dict, list)):
            return json.dumps(data, indent=2)
        if data:
            return str(data)
    except Exception as e:
        print(f"    ❌ EMAIL ERROR: {e}")

    print("    ⚠️ INBOX EMPTY/ERROR. USING EMPIRE TEST DATA.")
    return """
STORY: Anthropic upgrades Claude with stronger agentic workflows.
STORY: OpenAI raises at a massive valuation; capital is flooding into model builders.
STORY: Meta expands AI ad targeting; privacy backlash intensifies.
STORY: Regulators signal stricter enforcement around AI disclosures and consumer harms.
STORY: A major enterprise rolls out AI copilots—layoffs + productivity shock ripple through teams.
"""

def load_sponsors():
    sponsors_file = BASE_DIR / "sponsors.json"
    if sponsors_file.exists():
        try:
            data = json.loads(sponsors_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "sponsors" in data:
                return data["sponsors"]
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # safe fallback placeholders
    return [
        {"name": "SPONSOR_1", "copy": "Sponsor slot available."},
        {"name": "SPONSOR_2", "copy": "Sponsor slot available."},
        {"name": "SPONSOR_3", "copy": "Sponsor slot available."},
    ]


# =========================
# LLM (Gemini primary, OpenAI backup)
# =========================

def gemini_generate(prompt: str, temperature: float = 0.9, max_tokens: int = 6000) -> str:
    conf = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens
    )

    # Try primary then fallback
    for model in [GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL]:
        try:
            resp = client_gemini.models.generate_content(
                model=model,
                contents=prompt,
                config=conf
            )
            txt = (resp.text or "").strip()
            if txt:
                return txt
        except Exception as e:
            msg = str(e)
            # Respect retry delay hints if present
            m = re.search(r"retryDelay.*?(\d+)s", msg)
            if m:
                time.sleep(int(m.group(1)) + 1)
            print(f"    ⚠️ GEMINI FAILED on {model}: {e}")

    raise RuntimeError("Gemini generation failed on both primary and fallback models.")

def openai_generate(prompt: str, temperature: float = 0.9, max_tokens: int = 2500) -> str:
    resp = client_openai.chat.completions.create(
        model=OPENAI_SCRIPT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": "You are a premium showrunner and dialogue writer."},
            {"role": "user", "content": prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()

def llm_generate(prompt: str, temperature: float = 0.9, max_tokens: int = 6000) -> str:
    try:
        return gemini_generate(prompt, temperature=temperature, max_tokens=max_tokens)
    except Exception as e:
        print(f"    ⚠️ GEMINI PRIMARY PATH FAILED. FALLING BACK TO OPENAI: {e}")
        # OpenAI fallback (smaller max_tokens to control cost)
        return openai_generate(prompt, temperature=temperature, max_tokens=2500)


# =========================
# STORY SELECTION
# =========================

def extract_top_stories(intel_raw: str, n_deep: int = 5, n_rapid: int = 5):
    """
    Convert messy newsletter dump into:
      - deep stories (n_deep)
      - rapid-fire mentions (n_rapid)
    """
    prompt = f"""
You are the Executive Producer for "The AI Edge".
From the CONTEXT below, extract the most IMPORTANT, high-impact AI stories of the last 24 hours.

Return JSON only with this schema:
{{
  "deep": [
    {{"title": "...", "what_happened": "...", "why_it_matters": "...", "angle": "power|money|human"}},
    ...
  ],
  "rapid": [
    {{"title": "...", "one_liner": "..."}},
    ...
  ]
}}

Rules:
- Make it punchy and specific (no vague corporate language).
- Prioritize stories that trigger DREAD, GREED, or EXCITEMENT.
- Choose {n_deep} deep stories and {n_rapid} rapid stories.
- Ensure at least:
  - 1 money/markets story
  - 1 regulation/policy story
  - 1 human impact story
  - 1 model/product release story

CONTEXT:
{intel_raw}
"""
    raw = llm_generate(prompt, temperature=0.6, max_tokens=2500)

    # defensive JSON parse
    try:
        data = json.loads(raw)
        deep = data.get("deep", [])[:n_deep]
        rapid = data.get("rapid", [])[:n_rapid]
        return deep, rapid
    except Exception:
        # fallback: just treat intel as a single blob
        deep = [{
            "title": "Today in AI: the power shift continues",
            "what_happened": intel_raw[:500],
            "why_it_matters": "The acceleration is destabilizing jobs, markets, and regulation at the same time.",
            "angle": "power"
        }]
        return deep, []


# =========================
# SCRIPT ENGINE (5 segments, your confirmed structure)
# =========================

def build_script(date_str: str, deep_stories, rapid_stories, sponsors):
    # sponsor slots
    s1 = sponsors[0] if len(sponsors) > 0 else {"name": "SPONSOR_1", "copy": "Sponsor slot available."}
    s2 = sponsors[1] if len(sponsors) > 1 else {"name": "SPONSOR_2", "copy": "Sponsor slot available."}
    s3 = sponsors[2] if len(sponsors) > 2 else {"name": "SPONSOR_3", "copy": "Sponsor slot available."}

    stories_compact = json.dumps({"deep": deep_stories, "rapid": rapid_stories}, indent=2)

    prompt = f"""
You are the Showrunner for "The AI Edge" Daily Podcast.

NON-NEGOTIABLE VIBE:
- This is NOT a news read. It must feel overheated, messy, real.
- Interruptions. Tension. Ego. Vulnerability.
- ZERO corporate speak. If anyone says "let's dive in" or "in today's dynamic landscape" you failed.

PERSONAS:
- ALEX (Host): Rogan energy. Fast, curious, blunt. He sets up the show and keeps momentum.
- JAMIE (Co-host): Bartlett empathy. Vulnerable. "I feel..." Human cost, ethics, dread.
- RUFUS (Analyst): Huberman/Levine cynical. Money, incentives, regulation, power. Slightly predatory clarity.

STRUCTURE (5 Segments) — DO NOT CHANGE:
SEGMENT 1 (Cold open chaos + intro + rundown):
- Cold open starts MID-ARGUMENT about Story 1.
- [MUSIC]
- Alex says "Good morning" and states date: {date_str}.
- Alex quickly lists today's TOP 5 stories in a rundown (tight, 30–60 seconds).

SEGMENT 2 (Alex + Jamie studio only):
- Deep dive Story 1 and Story 2.
- Heavy chemistry. Jamie pushes human consequence. Alex pushes clarity and stakes.
- No Rufus in this segment.

SEGMENT 3 (Rufus on location):
- Rufus gives money + regulatory lens on Story 3 + Story 4.
- Alex throws to Rufus "checking in from the field..."
- Jamie can tag ONE empathetic interjection at the end.
- Native sponsor read woven as insider advice (NOT a commercial):
  Sponsor: {s1["name"]} — {s1["copy"]}

SEGMENT 4 (Trio war-room):
- All three together.
- Deep dive Story 5 + "rapid fire" mentions (at least 5).
- Add sponsor #2 seamlessly (Rufus slips it in like advice):
  Sponsor: {s2["name"]} — {s2["copy"]}

SEGMENT 5 (Verdict + close):
- Each gives ONE sharp takeaway ("what to do next").
- Alex CTA: subscribe/share.
- Final sponsor sting by Alex (short, tasteful):
  Sponsor: {s3["name"]} — {s3["copy"]}
- Alex closes: "See you tomorrow."

LENGTH REQUIREMENT:
- Aim for a finished audio runtime of 28–29 minutes.
- Output must be long enough (approximately 4,200–4,800 words).
- Dialogue only (ALEX:, JAMIE:, RUFUS:). Include [MUSIC] marker.

STORIES (do not invent new ones beyond these):
{stories_compact}
"""
    script = llm_generate(prompt, temperature=0.9, max_tokens=7000)
    return script.strip()


# =========================
# PARSE UTTERANCES
# =========================

def iter_utterances(script: str):
    """
    Yields (SPEAKER, TEXT).
    Only ALEX/JAMIE/RUFUS lines become TTS.
    """
    pattern = re.compile(r"^\s*(ALEX|JAMIE|RUFUS)\s*:?\s*(.*)$", re.IGNORECASE)

    current = None
    buf = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.upper() == "[MUSIC]":
            # treat as a stage direction block — caller handles music beds
            if current and buf:
                yield current, " ".join(buf).strip()
            yield "MUSIC", "[MUSIC]"
            current = None
            buf = []
            continue

        m = pattern.match(line)
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


# =========================
# TTS + MIXING
# =========================

def tts_to_file(text: str, voice: str, out_path: Path):
    # Try streaming API first, fall back if needed
    try:
        with client_openai.audio.speech.with_streaming_response.create(
            model=OPENAI_TTS_MODEL,
            voice=voice,
            input=text
        ) as resp:
            resp.stream_to_file(out_path)
        return
    except Exception:
        # fallback to non-streaming
        resp = client_openai.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=voice,
            input=text
        )
        out_path.write_bytes(resp.read() if hasattr(resp, "read") else resp)

def build_audio_from_script(script: str, date_str: str) -> AudioSegment:
    day_tmp = TMP_DIR / date_str
    if day_tmp.exists():
        shutil.rmtree(day_tmp)
    day_tmp.mkdir(parents=True, exist_ok=True)

    audio = AudioSegment.empty()

    # Optional intro bed at top
    if INTRO_MUSIC.exists():
        audio += AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(2000)
        audio += AudioSegment.silent(duration=250)

    seg_idx = 0
    for speaker, text in iter_utterances(script):
        if speaker == "MUSIC":
            # lightweight stinger between acts
            if INTRO_MUSIC.exists():
                audio += AudioSegment.from_mp3(INTRO_MUSIC)[:6000].fade_out(1200)
                audio += AudioSegment.silent(duration=250)
            continue

        if speaker not in CAST:
            continue

        for chunk in chunk_for_tts(text):
            if len(chunk) < 3:
                continue
            out_path = day_tmp / f"seg_{seg_idx:04d}.mp3"
            try:
                tts_to_file(chunk, CAST[speaker], out_path)
                clip = AudioSegment.from_mp3(out_path)
                audio += clip + AudioSegment.silent(duration=SILENCE_BETWEEN_MS)
                seg_idx += 1
            except Exception as e:
                print(f"    ⚠️ TTS ERROR ({speaker}): {e}")

    # Optional outro bed
    if OUTRO_MUSIC.exists():
        audio += AudioSegment.from_mp3(OUTRO_MUSIC)[:10000].fade_in(1500)

    if not KEEP_TMP:
        shutil.rmtree(day_tmp, ignore_errors=True)

    return audio


def speed_fit(audio: AudioSegment, target_minutes: float) -> AudioSegment:
    cur = minutes_of(audio)
    if cur <= 0:
        return audio
    ratio = cur / target_minutes
    # Only apply gentle speedup if needed
    if ratio <= 1.02:
        return audio
    # cap at 1.12 to avoid obvious artifacts
    playback = min(ratio, 1.12)
    return effects.speedup(audio, playback_speed=playback, chunk_size=150, crossfade=25)


def top_up_script(date_str: str, deep_stories, rapid_stories, sponsors, missing_minutes: float) -> str:
    stories_compact = json.dumps({"deep": deep_stories, "rapid": rapid_stories}, indent=2)
    prompt = f"""
You are continuing an episode of "The AI Edge" that is running short.

Write additional dialogue ONLY to extend runtime by ~{missing_minutes:.1f} minutes.
Rules:
- DO NOT repeat intro, date, or rundown.
- Maintain the same vibe and personas (ALEX/JAMIE/RUFUS).
- Add more interruption, conflict, and vivid analogies.
- Stay grounded in THESE stories only:
{stories_compact}

Output dialogue only with speaker tags.
"""
    return llm_generate(prompt, temperature=0.9, max_tokens=2500).strip()


# =========================
# RSS UPDATE (Spotify)
# =========================

def ensure_feed_exists(feed_path: Path):
    if feed_path.exists():
        return

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{RSS_SETTINGS["title"]}</title>
    <link>{RSS_SETTINGS["link"]}</link>
    <description>{RSS_SETTINGS["description"]}</description>
    <language>{RSS_SETTINGS["language"]}</language>
    <itunes:author>{RSS_SETTINGS["author"]}</itunes:author>
    <itunes:summary>{RSS_SETTINGS["description"]}</itunes:summary>
    <itunes:category text="{RSS_SETTINGS["category"]}"/>
  </channel>
</rss>
"""
    feed_path.write_text(rss, encoding="utf-8")


def update_rss_feed(audio_path: Path, show_notes: str):
    feed_path = BASE_DIR / "feed.xml"
    ensure_feed_exists(feed_path)

    tree = ET.parse(feed_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("feed.xml missing <channel>")

    today_str = audio_path.stem.replace("podcast_", "")
    item = ET.Element("item")

    ET.SubElement(item, "title").text = f"The AI Edge — {today_str}"
    ET.SubElement(item, "description").text = show_notes

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", f"{RAW_AUDIO_BASE}/{audio_path.name}")
    enclosure.set("length", str(os.path.getsize(audio_path)))
    enclosure.set("type", "audio/mpeg")

    ET.SubElement(item, "guid").text = f"{RAW_AUDIO_BASE}/{audio_path.name}"
    ET.SubElement(item, "pubDate").text = formatdate(os.path.getmtime(audio_path))

    # Insert newest at top
    channel.insert(0, item)

    tree.write(feed_path, encoding="UTF-8", xml_declaration=True)


# =========================
# SAFE CLEANUP FOR LEGACY SEGMENT ARTIFACTS
# =========================

def cleanup_legacy_segments(episode_dir: Path):
    """
    Deletes ONLY files that look like legacy segment artifacts:
      - *_seg_*.mp3
    Keeps podcast_*.mp3 intact for Spotify.
    """
    for p in episode_dir.glob("*_seg_*.mp3"):
        try:
            p.unlink()
        except Exception:
            pass


# =========================
# MAIN ORCHESTRATION
# =========================

def produce_episode():
    date_str = datetime.date.today().isoformat()

    # Optional cleanup of legacy artifacts
    if os.environ.get("CLEANUP_LEGACY_SEGMENTS", "1") == "1":
        cleanup_legacy_segments(EPISODE_DIR)

    intel_raw = gather_intel_raw()
    sponsors = load_sponsors()

    deep, rapid = extract_top_stories(intel_raw, n_deep=5, n_rapid=5)
    script = build_script(date_str, deep, rapid, sponsors)

    # Save script for auditing
    (BASE_DIR / f"script_{date_str}.txt").write_text(script, encoding="utf-8")

    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")
    audio = build_audio_from_script(script, date_str)

    # Enforce length via top-up loops before final export
    attempts = 0
    while minutes_of(audio) < MIN_MINUTES and attempts < 2:
        missing = MIN_MINUTES - minutes_of(audio) + 1.0  # add buffer
        print(f"    ⚠️ Episode short ({minutes_of(audio):.2f} min). Topping up ~{missing:.1f} min...")
        extra_dialogue = top_up_script(date_str, deep, rapid, sponsors, missing_minutes=missing)
        script += "\n" + extra_dialogue
        audio = build_audio_from_script(script, date_str)
        attempts += 1

    # If too long, gently speed-fit (less damaging than hard cuts)
    if minutes_of(audio) > MAX_MINUTES:
        print(f"    ⚠️ Episode long ({minutes_of(audio):.2f} min). Speed-fitting toward {TARGET_MINUTES:.1f}...")
        audio = speed_fit(audio, TARGET_MINUTES)

    final_minutes = minutes_of(audio)
    print(f" ✅ MIX COMPLETE ({final_minutes:.2f} minutes)")

    if STRICT_LENGTH and not (MIN_MINUTES <= final_minutes <= MAX_MINUTES):
        raise RuntimeError(f"Episode length out of bounds ({final_minutes:.2f} min). Refusing to publish.")

    outfile = EPISODE_DIR / f"podcast_{date_str}.mp3"
    audio.export(outfile, format="mp3", bitrate="192k")
    print(f" ✅ EPISODE EXPORTED: {outfile}")

    # Show notes (SEO-heavy)
    titles = [s.get("title", "") for s in deep][:5]
    rapid_titles = [s.get("title", "") for s in rapid][:5]
    show_notes = (
        f"{date_str} | The AI Edge\n\n"
        f"TOP STORIES:\n- " + "\n- ".join([t for t in titles if t]) + "\n\n"
        f"RAPID FIRE:\n- " + "\n- ".join([t for t in rapid_titles if t]) + "\n\n"
        "#AI #ArtificialIntelligence #Tech #Startups #Regulation #Markets"
    )

    (BASE_DIR / "viral_caption.txt").write_text(show_notes, encoding="utf-8")
    meta = {"title": f"The AI Edge — {date_str}", "date": date_str, "stories": titles, "rapid": rapid_titles}
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    update_rss_feed(outfile, show_notes)


if __name__ == "__main__":
    produce_episode()
