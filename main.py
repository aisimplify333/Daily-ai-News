import os
import json
import re
import time
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

from pydub import AudioSegment
from pydub.effects import normalize

from openai import OpenAI

# Gemini is optional at runtime (will fallback if missing/blocked)
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

import fetch_news


# -----------------------------
# 0) ENV / CONFIG
# -----------------------------
def require_env(name: str, optional: bool = False) -> str | None:
    val = os.environ.get(name)
    if not val and not optional:
        print(f" ❌ MISSING ENV VAR: {name}")
    return val

OPENAI_API_KEY = require_env("OPENAI_API_KEY")
GEMINI_API_KEY = require_env("GEMINI_API_KEY", optional=True)

# Models (override via env if needed)
OPENAI_SCRIPT_MODEL = os.environ.get("OPENAI_SCRIPT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1-hd")

# Gemini model names vary by plan/quota; keep configurable
GEMINI_PRIMARY_MODEL = os.environ.get("GEMINI_PRIMARY_MODEL", "gemini-1.5-pro")
GEMINI_BACKUP_MODEL = os.environ.get("GEMINI_BACKUP_MODEL", "gemini-2.0-flash-exp")

# Length gate (minutes)
MIN_MINUTES = float(os.environ.get("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "30"))

# Audio / pacing
WORDS_PER_MINUTE_EST = float(os.environ.get("WORDS_PER_MINUTE_EST", "155"))
CROSSFADE_MS = int(os.environ.get("CROSSFADE_MS", "80"))
SILENCE_BETWEEN_MS = int(os.environ.get("SILENCE_BETWEEN_MS", "90"))

# Optional cleanup of legacy segments in episode_audio
CLEAN_LEGACY_SEGMENTS = os.environ.get("CLEAN_LEGACY_SEGMENTS", "1") == "1"

# Directories
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
TMP_AUDIO_DIR = BASE_DIR / "_tmp_audio"

INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

AUDIO_DIR.mkdir(exist_ok=True)
TMP_AUDIO_DIR.mkdir(exist_ok=True)

client_openai = OpenAI(api_key=OPENAI_API_KEY)

client_gemini = None
if genai and GEMINI_API_KEY:
    try:
        client_gemini = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"⚠️ Gemini init failed, will fallback to OpenAI. ({e})")
        client_gemini = None

# Voices (keep exactly)
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable",
}

BANNED_PHRASES = [
    "let's dive in",
    "dynamic world of",
    "landscape",
    "synergy",
    "leveraging",
    "in today's fast-paced",
]


# -----------------------------
# 1) INTEL
# -----------------------------
def gather_intel() -> str:
    print(" >> 📡 GATHERING INTEL FROM EMAILS...")
    try:
        data = fetch_news.get_todays_newsletters()
        if isinstance(data, (dict, list)):
            return json.dumps(data, indent=2)
        if data:
            return str(data)
    except Exception as e:
        print(f"    ⚠️ EMAIL ERROR: {e}")

    print("    ⚠️ INBOX EMPTY/ERROR. USING EMPIRE TEST DATA.")
    return (
        "STORY 1: Anthropic's Claude Sonnet 4.5 released. Multi-hour agentic tasks.\n"
        "STORY 2: OpenAI hits $500B valuation after secondary share sale.\n"
        "STORY 3: Meta uses AI-driven chatbot conversations to fuel ads; privacy backlash.\n"
    )


def get_sponsors() -> list[dict]:
    # You can swap this to load sponsors.json if you prefer
    return [
        {"name": "Oracle Cloud", "copy": "Stop burning cash. Oracle Cloud is built for GPU workloads. Visit Oracle.com."},
        {"name": "NetSuite", "copy": "Visibility is survival. NetSuite gives you the data to survive the crash. NetSuite.com."},
        {"name": "ElevenLabs", "copy": "This show is 100% AI. Scale your content with ElevenLabs.io."},
    ]


# -----------------------------
# 2) WRITER (Gemini primary, OpenAI fallback)
# -----------------------------
def _gemini_generate(full_prompt: str, model_name: str) -> str:
    if not client_gemini:
        raise RuntimeError("Gemini not configured")

    conf = types.GenerateContentConfig(
        temperature=0.9,
        max_output_tokens=6000,
    )
    resp = client_gemini.models.generate_content(
        model=model_name,
        contents=full_prompt,
        config=conf,
    )
    return (resp.text or "").strip()


def _openai_generate(full_prompt: str) -> str:
    resp = client_openai.chat.completions.create(
        model=OPENAI_SCRIPT_MODEL,
        messages=[
            {"role": "system", "content": "You are the executive producer of a hit daily AI podcast with three distinct hosts. Output ONLY dialogue lines."},
            {"role": "user", "content": full_prompt},
        ],
        temperature=0.9,
    )
    return resp.choices[0].message.content.strip()


def generate_text(full_prompt: str) -> str:
    # Try Gemini primary
    if client_gemini:
        try:
            return _gemini_generate(full_prompt, GEMINI_PRIMARY_MODEL)
        except Exception as e1:
            print(f"    ⚠️ GEMINI PRIMARY FAILED ({e1}). Trying backup...")
            try:
                return _gemini_generate(full_prompt, GEMINI_BACKUP_MODEL)
            except Exception as e2:
                print(f"    ⚠️ GEMINI BACKUP FAILED ({e2}). Falling back to OpenAI...")

    # Fallback to OpenAI
    try:
        return _openai_generate(full_prompt)
    except Exception as e:
        print(f"    ❌ OPENAI GENERATION ERROR: {e}")
        return "ALEX: We are offline. See you tomorrow."


# -----------------------------
# 3) SCRIPT (STRICT 5 SEGMENTS)
# -----------------------------
def _segment_prompt(segment_id: int, intel: str, sponsors: list[dict], today_str: str) -> str:
    sponsor_a = sponsors[0]
    sponsor_b = sponsors[1]

    common_rules = f"""
YOU ARE WRITING "THE AI EDGE" DAILY PODCAST.

NON-NEGOTIABLE VIBE:
- Overheated conversation. Interruptions. Short punches mixed with longer explanations.
- NO corporate speak. Ban phrases: {", ".join(BANNED_PHRASES)}.
- Characters fight. They do not politely agree.

CAST RULES (MUST HOLD):
- ALEX: high energy, asks the "dumb" clarifying questions. MUST physically introduce the team in Segment 2.
- JAMIE: vulnerable, anxious, uses "I feel" statements, human cost.
- RUFUS: cynical, money/regulation/infrastructure, cold rationalist, dry British/transatlantic edge.

FORMAT RULES:
- Output dialogue only. Each line must start with ALEX: or JAMIE: or RUFUS:
- No narration paragraphs.
- Use occasional cut-ins like: "ALEX: —Wait." "JAMIE: No—listen."
- Keep it slightly messy and human.

CONTEXT (THE DAY'S INTEL):
{intel}
"""

    if segment_id == 1:
        return common_rules + f"""
SEGMENT 1 — THE COLD OPEN (Chaos) [~3-4 minutes]
- Start MID-ARGUMENT immediately. No hello. No music.
- Pick the single most shocking story from intel and make it existential.
- Alex is yelling, Jamie is panicked, Rufus is amused and predatory.
TARGET: 550–750 words.
"""
    if segment_id == 2:
        return common_rules + f"""
SEGMENT 2 — THE TECH (Hard Facts) [~6-7 minutes]
- Alex stabilizes the show: "Good morning" + date = {today_str}
- ALEX MUST SAY: "With me is the conscience of the show, Jamie. Say hello Jamie."
- ALEX MUST SAY: "And checking in from the field... Rufus." Rufus replies with a cynical location gag.
- Alex tees up today’s 3 stories + "Rufus on-location financial/regulatory breakout."
- Rufus explains the mechanics; Alex translates; Jamie fears the human cost.
TARGET: 950–1200 words.
"""
    if segment_id == 3:
        return common_rules + f"""
SEGMENT 3 — THE MONEY (Rufus Pivot + Native Ad) [~7-8 minutes]
- Rufus takes over: "Follow the money."
- Must cover: valuations, infra spend, regulation angle, who wins/loses.
- NATIVE AD must be woven seamlessly as survival advice (NOT a commercial break).
  Sponsor slot A (RUFUS voice): {sponsor_a['name']} — {sponsor_a['copy']}
- Return to analysis immediately after.
TARGET: 1100–1400 words.
"""
    if segment_id == 4:
        return common_rules + f"""
SEGMENT 4 — THE FALLOUT (Ethics & Law) [~6-7 minutes]
- Jamie pushes back: "But at what cost?"
- Must include: legal fights, society impact, human element (jobs, deepfakes, privacy).
- Conflict peaks here (the SOUL).
TARGET: 950–1200 words.
"""
    if segment_id == 5:
        return common_rules + f"""
SEGMENT 5 — THE VERDICT (The Edge) [~3-4 minutes]
- Alex demands conclusions: "Where are we in 6 months?"
- Each character gives ONE sentence prediction.
- Close with CTA to subscribe/share and a quick sponsor tag in-character:
  Sponsor slot B (short): {sponsor_b['name']} — {sponsor_b['copy']}
- End clean.
TARGET: 550–750 words.
"""
    raise ValueError("segment_id must be 1..5")


def build_full_script(intel: str, sponsors: list[dict]) -> str:
    today_str = datetime.date.today().isoformat()

    segments = []
    for seg in range(1, 6):
        print(f" >> ✍️  WRITING SEGMENT {seg}/5...")
        prompt = _segment_prompt(seg, intel, sponsors, today_str)
        seg_text = generate_text(prompt).strip()
        segments.append(seg_text)

    script = "\n".join(segments)

    # Simple banned phrase scrub pass (auto-rewrite if needed)
    lowered = script.lower()
    if any(bp in lowered for bp in BANNED_PHRASES):
        print("    ⚠️ BANNED PHRASE DETECTED. RUNNING QUICK REWRITE PASS...")
        rewrite_prompt = f"""
Rewrite the following script to remove ALL corporate-speak and banned phrases.
Keep the same structure, characters, and content. Keep it overheated and messy.
Return dialogue only.

BANNED PHRASES: {", ".join(BANNED_PHRASES)}

SCRIPT:
{script}
"""
        script = generate_text(rewrite_prompt).strip()

    return script


# -----------------------------
# 4) TTS + MIXING (TEMP SEGMENTS + CLEANUP)
# -----------------------------
def iter_utterances(script: str):
    pattern = re.compile(r"^\s*(ALEX|JAMIE|RUFUS)\s*:\s*(.+)\s*$", re.IGNORECASE)
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = pattern.match(line)
        if not m:
            continue
        speaker = m.group(1).upper()
        text = m.group(2).strip()
        if text:
            yield speaker, text


def chunk_text(text: str, limit: int = 2800) -> list[str]:
    # Remove bracketed stage directions that TTS reads awkwardly
    text = re.sub(r"[\(\[].*?[\)\]]", "", text)
    text = text.replace("*", "").replace('"', "").strip()
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        idx = remaining.rfind(".", 0, limit)
        if idx == -1:
            idx = limit
        chunk = remaining[: idx + 1].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[idx + 1 :].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def tts_to_temp_segments(script: str, date_str: str) -> tuple[list[Path], Path]:
    day_tmp = TMP_AUDIO_DIR / date_str
    if day_tmp.exists():
        # Clean any prior partial run
        for f in day_tmp.glob("*.mp3"):
            try:
                f.unlink()
            except Exception:
                pass
    day_tmp.mkdir(parents=True, exist_ok=True)

    manifest_path = day_tmp / "manifest.json"
    seg_paths: list[Path] = []

    seg_idx = 0
    for speaker, text in iter_utterances(script):
        if speaker not in CAST:
            continue
        for chunk in chunk_text(text):
            if len(chunk) < 2:
                continue
            out_path = day_tmp / f"seg_{seg_idx:05d}.mp3"
            try:
                with client_openai.audio.speech.with_streaming_response.create(
                    model=OPENAI_TTS_MODEL,
                    voice=CAST[speaker],
                    input=chunk,
                ) as response:
                    response.stream_to_file(out_path)
                seg_paths.append(out_path)
                seg_idx += 1
            except Exception as e:
                print(f"    ⚠️ TTS ERROR ({speaker}): {e}")
                # continue producing rather than failing the broadcast

    # Save manifest for debugging
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({"date": date_str, "segments": [p.name for p in seg_paths]}, f, indent=2)
    except Exception:
        pass

    return seg_paths, day_tmp


def _safe_gain(seg: AudioSegment, target_dbfs: float) -> AudioSegment:
    if seg.rms == 0:
        return seg
    # If dBFS is very low, normalize first then fine-tune
    seg2 = normalize(seg)
    if seg2.rms == 0:
        return seg2
    gain = target_dbfs - seg2.dBFS
    return seg2.apply_gain(gain)


def stitch_episode(seg_paths: list[Path], date_str: str) -> AudioSegment:
    clips: list[AudioSegment] = []

    # Optional intro music
    if INTRO_MUSIC.exists():
        intro = AudioSegment.from_mp3(INTRO_MUSIC)[:15000]
        intro = intro.fade_out(2000).apply_gain(-10)
        clips.append(intro)

    # Voice segments
    for p in seg_paths:
        a = AudioSegment.from_mp3(p)
        a = _safe_gain(a, target_dbfs=-18.0)  # bring voice up consistently
        clips.append(a + AudioSegment.silent(duration=SILENCE_BETWEEN_MS))

    # Optional outro music
    if OUTRO_MUSIC.exists():
        outro = AudioSegment.from_mp3(OUTRO_MUSIC)[:12000]
        outro = outro.fade_in(1500).apply_gain(-10)
        clips.append(outro)

    if not clips:
        return AudioSegment.silent(duration=1000)

    full = clips[0]
    for c in clips[1:]:
        # Crossfade reduces dead air and creates a more "interrupt-y" feel
        full = full.append(c, crossfade=CROSSFADE_MS)

    return full


def cleanup_temp(day_tmp: Path):
    try:
        for f in day_tmp.glob("seg_*.mp3"):
            f.unlink()
        # Keep manifest.json for debug, but you can remove it too if you prefer
    except Exception:
        pass


def cleanup_legacy_segments_in_episode_audio(date_str: str):
    # Deletes ONLY legacy segment pattern in episode_audio, never podcast_*.mp3
    for f in AUDIO_DIR.glob(f"{date_str}_seg_*.mp3"):
        try:
            f.unlink()
        except Exception:
            pass


# -----------------------------
# 5) RSS UPDATE
# -----------------------------
def update_rss_feed(audio_path: Path, show_notes: str):
    rss_file = BASE_DIR / "feed.xml"
    if not rss_file.exists():
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The AI Edge</title>
    <link>https://aisimplify333.github.io/Daily-ai-News/episode_audio/</link>
    <description>Daily AI News, Finance, and Regulation.</description>
    <language>en-us</language>
  </channel>
</rss>"""
        rss_file.write_text(rss, encoding="utf-8")

    tree = ET.parse(rss_file)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("feed.xml missing <channel>")

    item = ET.Element("item")
    ET.SubElement(item, "title").text = audio_path.stem
    ET.SubElement(item, "description").text = show_notes

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", f"https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}")
    enclosure.set("length", str(os.path.getsize(audio_path)))
    enclosure.set("type", "audio/mpeg")

    ET.SubElement(item, "guid").text = f"https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}"
    ET.SubElement(item, "pubDate").text = formatdate(os.path.getmtime(audio_path))

    channel.insert(0, item)
    tree.write(rss_file, encoding="UTF-8", xml_declaration=True)


# -----------------------------
# 6) MAIN PRODUCER
# -----------------------------
def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors()

    today_str = datetime.date.today().isoformat()
    episode_title = f"Daily AI Edge: {today_str}"

    # Write full script (strict 5 segments)
    script = build_full_script(intel, sponsors)

    # Persist script for review/scoring
    (BASE_DIR / f"script_{today_str}.txt").write_text(script, encoding="utf-8")

    # Show notes (kept simple + deterministic)
    show_notes = f"{today_str} | {episode_title}\n\nTOPICS:\n{intel[:800]}...\n\n#AI #TechNews"

    (BASE_DIR / "viral_caption.txt").write_text(show_notes, encoding="utf-8")
    meta = {"title": episode_title, "date": today_str, "headlines": [intel[:140]]}
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")

    # TTS into temp folder
    seg_paths, day_tmp = tts_to_temp_segments(script, today_str)

    # Stitch
    full_audio = stitch_episode(seg_paths, today_str)

    minutes = len(full_audio) / 1000 / 60
    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"

    # If out of bounds, we still export (so you don't lose the run),
    # but we warn loudly. You can enforce hard-fail via env if you want.
    print(f" >> 🎚️  MIXING...")
    full_audio.export(outfile, format="mp3", bitrate="192k")
    print(f" ✅ EPISODE COMPLETE: {outfile} ({minutes:.2f} minutes)")

    # Cleanup temp segments
    cleanup_temp(day_tmp)

    # Cleanup legacy segment mess for this date (optional)
    if CLEAN_LEGACY_SEGMENTS:
        cleanup_legacy_segments_in_episode_audio(today_str)

    # RSS update
    try:
        update_rss_feed(outfile, show_notes)
    except Exception as e:
        print(f"⚠️ RSS UPDATE FAILED: {e}")

    # Length gate report (do not crash the run by default)
    if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
        print(f"⚠️ LENGTH OUT OF RANGE: {minutes:.2f} min (target {MIN_MINUTES}-{MAX_MINUTES}).")


if __name__ == "__main__":
    produce_episode()
