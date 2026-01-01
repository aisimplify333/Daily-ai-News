import os
import json
import re
import shutil
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

from openai import OpenAI
from pydub import AudioSegment

import fetch_news  # your existing intel source


# =========================
# 0) SETTINGS / CONSTANTS
# =========================

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
TMP_DIR = BASE_DIR / "_tmp_audio"

INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

AUDIO_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# Spotify/iTunes RSS metadata (keep these stable)
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://aisimplify333.github.io/Daily-ai-News/",
    "description": "Daily AI news as a high-stakes conversation: tech, money, policy, and the human fallout.",
    "language": "en-us",
    "author": "AI Simplify Media",
    "email": os.environ.get("PODCAST_EMAIL", "aisimplify333@gmail.com"),
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
    "site_audio_base": "https://aisimplify333.github.io/Daily-ai-News/episode_audio/",
}

# Voices (OpenAI TTS)
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable",
}

# Runtime control
TARGET_MINUTES_MIN = float(os.environ.get("TARGET_MINUTES_MIN", "25"))
TARGET_MINUTES_MAX = float(os.environ.get("TARGET_MINUTES_MAX", "30"))
# Script sizing heuristic: ~150 wpm conversational; 27 min ~ 4050 words.
TARGET_WORDS_MIN = int(os.environ.get("TARGET_WORDS_MIN", "4100"))
TARGET_WORDS_MAX = int(os.environ.get("TARGET_WORDS_MAX", "5200"))

KEEP_SEGMENTS = os.environ.get("KEEP_SEGMENTS", "0") == "1"

# Story volume
CORE_STORIES = int(os.environ.get("CORE_STORIES", "5"))
QUICK_HITS = int(os.environ.get("QUICK_HITS", "3"))  # optional; can be 0


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))


# =========================
# 1) INTEL INGESTION
# =========================

def gather_intel_raw() -> str:
    """
    Pulls today’s newsletter intake. If your IMAP creds fail, fetch_news should raise.
    We fall back to test data to keep the pipeline alive.
    """
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
    return """
    - Anthropic ships a major model upgrade enabling longer autonomous task runs; teams start replacing human ops with always-on agents.
    - OpenAI’s secondary sale resets private-market price expectations and reignites “winner-take-most” platform arguments.
    - Regulators in the EU escalate enforcement around training-data provenance while creators mobilize for stronger licensing.
    - NVIDIA supply constraints shift as new data-center demand spikes, raising energy and cooling costs globally.
    - A viral deepfake incident triggers a corporate crisis and raises fresh questions about verification and liability.
    """


def llm_json(messages, model="gpt-4o-mini", temperature=0.3):
    resp = client_openai.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content


def select_and_structure_stories(raw_text: str, core_n: int, quick_n: int):
    """
    Converts unstructured newsletter blobs into:
      - core_stories: 5 items with title/angle/why_it_matters/keywords
      - quick_hits: short additional headlines
    This is where consistency comes from.
    """
    schema_prompt = f"""
Return STRICT JSON with keys: core_stories, quick_hits.

core_stories: array length {core_n}. Each item:
- title (max 90 chars)
- hook_angle (1 sentence, provocative)
- summary (2-3 sentences, concrete facts)
- why_it_matters (1-2 sentences)
- vertical (one of: Global, Money, Infra, Policy, Human)
- keywords (array of 6-12 SEO keywords)

quick_hits: array length {quick_n}. Each item:
- title (max 90 chars)
- one_liner (max 180 chars)
- keywords (array of 4-8)

Rules:
- No corporate filler. No “landscape”, “synergy”, “let’s dive in”.
- Prefer specific entities: company names, products, regulators, chips, lawsuits.
- If raw_text lacks enough items, synthesize missing ones as plausible composites (clearly written as news-style statements).
"""
    out = llm_json(
        [
            {"role": "system", "content": "You are an executive producer extracting high-signal AI stories for a daily show."},
            {"role": "user", "content": schema_prompt + "\n\nRAW:\n" + raw_text},
        ],
        model=os.environ.get("STORY_MODEL", "gpt-4o-mini"),
        temperature=0.2,
    )

    # Defensive parse
    try:
        data = json.loads(out)
        core = data.get("core_stories", [])[:core_n]
        quick = data.get("quick_hits", [])[:quick_n]
        return core, quick
    except Exception:
        # Fallback: treat raw as single story block
        core = [{
            "title": "AI moves fast. Humans move slow.",
            "hook_angle": "If the agents don’t sleep, neither does the market.",
            "summary": raw_text.strip()[:800],
            "why_it_matters": "The gap between capability and governance is widening daily.",
            "vertical": "Human",
            "keywords": ["AI", "agents", "LLMs", "regulation", "jobs", "chips"]
        }]
        return core, []


# =========================
# 2) SCRIPTING (5 SEGMENTS)
# =========================

def build_show_prompt(date_str: str, core_stories, quick_hits):
    """
    IMPORTANT: We keep your 5-segment Empire framework.
    We do NOT imitate any specific living person; we preserve archetypes.
    """
    stories_block = json.dumps({"core_stories": core_stories, "quick_hits": quick_hits}, indent=2)

    return f"""
You are writing a DAILY 5-SEGMENT episode of "The AI Edge" (high-stakes conversational drama disguised as news).

NON-NEGOTIABLES:
- Must sound like messy, overheated conversation. Interruptions. Pushback. No corporate speak.
- Ban phrases: "let's dive in", "in today's landscape", "synergy", "game-changer" unless used sarcastically.
- Keep it human: short sentences, reactions, disbelief, frustration, dark humor.
- FORMAT: dialogue lines only using exactly ALEX:, JAMIE:, RUFUS:
- Include stage cues on their own lines in square brackets: [COLD OPEN], [MUSIC IN], [MUSIC OUT], [SEGMENT 2], etc.
- Do NOT add narration paragraphs.

CAST ARCHETYPES:
- ALEX = high-energy everyman host. Curious, relentless, keeps momentum. Opens/closes each segment.
- JAMIE = empathetic conscience. Uses “I feel…” and “I don’t know, man…”; spirals into human impact.
- RUFUS = cynical analyst. Clinical. Money, incentives, regulation, moats. Darkly funny.

EPISODE DATE: {date_str}

STORY INPUT (use these facts; don’t invent new unrelated stories):
{stories_block}

STRUCTURE (EXACTLY THIS):
[SEGMENT 1: COLD OPEN]
- Start mid-argument about the SINGLE biggest core story (choose the most shocking).
- All three present. No hello. No intro. Tension instantly.

[MUSIC IN]
- 6–10 seconds worth of words indicating music sting.
[MUSIC OUT]

[SEGMENT 2: THE TECH (STUDIO)]
- ONLY ALEX and JAMIE speaking in this segment.
- Alex does: welcome, date, and a fast rundown of TODAY'S 5 core stories in 20–30 seconds.
- Then they deeply cover 2 tech-forward stories (specs, capabilities, what changed) + 2 quick hits.
- Keep it concrete, no fluff.

[SEGMENT 3: THE MONEY (RUFUS ON LOCATION)]
- Alex throws to Rufus “on location” (invent a different plausible place daily).
- Rufus leads the analysis: valuations, funding, regulation, incentives, second-order effects.
- Native sponsor ad must appear here AS PART OF THE ANALYSIS (not a commercial break).
- Alex can interject briefly 2–3 times, but Rufus dominates.

[SEGMENT 4: THE FALLOUT (ETHICS & LAW)]
- All three back.
- Jamie drives the moral conflict; Rufus pushes back; Alex keeps it moving.
- Cover at least 1 Policy/Human story. Include one vivid metaphor.

[SEGMENT 5: THE VERDICT]
- Alex demands predictions: each gives 1 sentence.
- Alex closes with CTA to subscribe/share.
- Keep it intense and memorable.

RUNTIME TARGET:
- 25–30 minutes of spoken audio.
- That means: approx {TARGET_WORDS_MIN}–{TARGET_WORDS_MAX} words total.
- Do not end early.
"""


def generate_script(date_str: str, core_stories, quick_hits) -> str:
    prompt = build_show_prompt(date_str, core_stories, quick_hits)
    model = os.environ.get("SCRIPT_MODEL", "gpt-4o")

    resp = client_openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are the showrunner of a hit daily tech podcast. Write only the episode script."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
    )
    script = resp.choices[0].message.content.strip()

    # Expand if too short, without changing structure
    words = len(re.findall(r"\b\w+\b", script))
    if words < TARGET_WORDS_MIN:
        script = expand_script_to_target(script, TARGET_WORDS_MIN)

    return script


def expand_script_to_target(script: str, target_words: int) -> str:
    """
    Expands within each segment, preserving the 5-segment structure and dynamics.
    """
    expand_prompt = f"""
Expand the following script to AT LEAST {target_words} words.

Rules:
- Preserve the 5 segments and their constraints (Segment 2 only Alex+Jamie, Segment 3 mostly Rufus, etc.).
- Do not change the overall arc or remove anything; only add.
- Add interruptions, vivid metaphors, concrete details, but no corporate speak.

Return the FULL expanded script, same format.
"""
    resp = client_openai.chat.completions.create(
        model=os.environ.get("SCRIPT_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": "You expand scripts while preserving structure and voice constraints."},
            {"role": "user", "content": expand_prompt + "\n\nSCRIPT:\n" + script},
        ],
        temperature=0.9,
    )
    return resp.choices[0].message.content.strip()


# =========================
# 3) TTS + STITCHING
# =========================

def iter_utterances(script: str):
    pattern = re.compile(r'^\s*(ALEX|JAMIE|RUFUS)\s*:\s*(.+)\s*$')
    for line in script.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            yield ("STAGE", line)
            continue
        m = pattern.match(line)
        if m:
            yield (m.group(1), m.group(2))
        else:
            # Ignore malformed lines (keeps pipeline stable)
            continue


def chunk_text(text: str, limit: int = 3200):
    # Keep TTS stable: remove bracketed asides; keep punctuation
    cleaned = re.sub(r'[\(\[].*?[\)\]]', '', text).replace('*', '').strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    if len(cleaned) <= limit:
        return [cleaned] if cleaned else []
    chunks = []
    t = cleaned
    while len(t) > limit:
        split_idx = t.rfind('.', 0, limit)
        if split_idx < 200:
            split_idx = limit
        chunks.append(t[:split_idx + 1].strip())
        t = t[split_idx + 1:].strip()
    if t:
        chunks.append(t)
    return chunks


def tts_to_file(text: str, voice: str, outpath: Path):
    with client_openai.audio.speech.with_streaming_response.create(
        model=os.environ.get("TTS_MODEL", "tts-1-hd"),
        voice=voice,
        input=text
    ) as response:
        response.stream_to_file(outpath)


def produce_audio(date_str: str, script: str) -> Path:
    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")

    day_tmp = TMP_DIR / date_str
    day_tmp.mkdir(parents=True, exist_ok=True)

    clips = []

    # Intro
    if INTRO_MUSIC.exists():
        clips.append(AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(1500))

    seg_index = 0
    for speaker, text in iter_utterances(script):
        if speaker == "STAGE":
            # Optional: add tiny spacing for stage transitions
            if text in ("[MUSIC IN]", "[MUSIC OUT]"):
                clips.append(AudioSegment.silent(duration=250))
            else:
                clips.append(AudioSegment.silent(duration=150))
            continue

        voice = CAST.get(speaker)
        if not voice:
            continue

        for chunk in chunk_text(text):
            if len(chunk) < 2:
                continue
            outpath = day_tmp / f"{date_str}_seg_{seg_index:04d}.mp3"
            try:
                tts_to_file(chunk, voice, outpath)
                clips.append(AudioSegment.from_mp3(outpath))
                # tighter gap for “interruptions” feel
                clips.append(AudioSegment.silent(duration=90))
                seg_index += 1
            except Exception as e:
                print(f"    ⚠️ TTS ERROR ({speaker}): {e}")

    # Outro
    if OUTRO_MUSIC.exists():
        clips.append(AudioSegment.from_mp3(OUTRO_MUSIC)[:12000].fade_in(1200))

    # Stitch
    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    for c in clips:
        full_audio += c

    outfile = AUDIO_DIR / f"podcast_{date_str}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")

    minutes = len(full_audio) / 1000 / 60
    print(f" ✅ EPISODE COMPLETE: {outfile} ({minutes:.2f} minutes)")

    # Cleanup tmp segments unless debugging
    if not KEEP_SEGMENTS:
        shutil.rmtree(day_tmp, ignore_errors=True)

    return outfile


# =========================
# 4) RSS UPDATE (Spotify)
# =========================

def ensure_base_rss(rss_file: Path):
    if rss_file.exists():
        return

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{RSS_SETTINGS['title']}</title>
    <link>{RSS_SETTINGS['link']}</link>
    <language>{RSS_SETTINGS['language']}</language>
    <description>{RSS_SETTINGS['description']}</description>
    <itunes:author>{RSS_SETTINGS['author']}</itunes:author>
    <itunes:owner>
      <itunes:name>{RSS_SETTINGS['author']}</itunes:name>
      <itunes:email>{RSS_SETTINGS['email']}</itunes:email>
    </itunes:owner>
    <itunes:image href="{RSS_SETTINGS['image']}" />
    <itunes:category text="{RSS_SETTINGS['category']}" />
  </channel>
</rss>"""
    rss_file.write_text(rss, encoding="utf-8")


def update_rss_feed(audio_path: Path, title: str, show_notes: str):
    rss_file = BASE_DIR / "feed.xml"
    ensure_base_rss(rss_file)

    tree = ET.parse(rss_file)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("feed.xml missing <channel>")

    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = show_notes

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", f"{RSS_SETTINGS['site_audio_base']}{audio_path.name}")
    enclosure.set("length", str(audio_path.stat().st_size))
    enclosure.set("type", "audio/mpeg")

    ET.SubElement(item, "guid").text = f"{RSS_SETTINGS['site_audio_base']}{audio_path.name}"
    ET.SubElement(item, "pubDate").text = formatdate(audio_path.stat().st_mtime)

    # Insert newest first
    channel.insert(0, item)

    tree.write(rss_file, encoding="UTF-8", xml_declaration=True)


# =========================
# 5) SHOW NOTES / SEO
# =========================

def build_show_notes(date_str: str, core_stories, quick_hits):
    titles = [s["title"] for s in core_stories]
    kw = []
    for s in core_stories:
        kw.extend(s.get("keywords", []))
    for q in quick_hits:
        kw.extend(q.get("keywords", []))

    # De-dupe keywords for hashtags/SEO line
    seen = set()
    kws = []
    for k in kw:
        k2 = re.sub(r'[^A-Za-z0-9_]+', '', k.strip().replace(" ", ""))
        if not k2:
            continue
        k2 = k2[:28]
        if k2.lower() in seen:
            continue
        seen.add(k2.lower())
        kws.append(k2)
        if len(kws) >= 18:
            break

    notes = []
    notes.append(f"{date_str} | The AI Edge")
    notes.append("")
    notes.append("TOP STORIES:")
    for i, t in enumerate(titles, 1):
        notes.append(f"{i}. {t}")

    if quick_hits:
        notes.append("")
        notes.append("QUICK HITS:")
        for q in quick_hits:
            notes.append(f"- {q['title']}")

    notes.append("")
    notes.append("TAGS:")
    notes.append(" ".join([f"#{k}" for k in kws]))

    notes.append("")
    notes.append("Note: This episode is produced using synthetic voices and automated scripting.")
    return "\n".join(notes)


def build_episode_title(date_str: str, core_stories):
    # SEO-friendly: date + top story
    top = core_stories[0]["title"] if core_stories else "AI moves fast"
    top = top[:80]
    return f"The AI Edge — {date_str} — {top}"


# =========================
# 6) MAIN
# =========================

def produce_episode():
    date_str = datetime.date.today().isoformat()

    raw = gather_intel_raw()
    core_stories, quick_hits = select_and_structure_stories(raw, CORE_STORIES, QUICK_HITS)

    # Script
    print(" >> ✍️  WRITING (5-SEGMENT EMPIRE)...")
    script = generate_script(date_str, core_stories, quick_hits)

    # Save script + metadata
    (BASE_DIR / f"script_{date_str}.txt").write_text(script, encoding="utf-8")

    episode_title = build_episode_title(date_str, core_stories)
    show_notes = build_show_notes(date_str, core_stories, quick_hits)

    (BASE_DIR / "viral_caption.txt").write_text(show_notes, encoding="utf-8")
    meta = {
        "title": episode_title,
        "date": date_str,
        "core_stories": core_stories,
        "quick_hits": quick_hits,
    }
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Audio
    audio_path = produce_audio(date_str, script)

    # Runtime guardrail: warn (don’t crash the whole run unless you want it)
    audio = AudioSegment.from_mp3(audio_path)
    minutes = len(audio) / 1000 / 60
    if minutes < TARGET_MINUTES_MIN or minutes > TARGET_MINUTES_MAX:
        print(f"    ⚠️ WARNING: Runtime {minutes:.2f} min (target {TARGET_MINUTES_MIN}-{TARGET_MINUTES_MAX}).")

    # RSS
    update_rss_feed(audio_path, episode_title, show_notes)


if __name__ == "__main__":
    produce_episode()
