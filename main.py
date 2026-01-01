import os
import json
import re
import time
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple

import requests
import feedparser
from pydub import AudioSegment

from openai import OpenAI

# Gemini (primary script engine)
from google import genai
from google.genai import types

# Optional email backup
try:
    import fetch_news
except Exception:
    fetch_news = None


# =========================
# 0) SETTINGS
# =========================

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)

INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

RSS_FILE = BASE_DIR / "feed.xml"
SPONSORS_FILE = BASE_DIR / "sponsors.json"

# Voices (keep your mapping)
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable"
}

# Show runtime goal: 25–30 minutes
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "26.5"))
MINUTES_FLOOR = float(os.getenv("MINUTES_FLOOR", "25.0"))
MINUTES_CEILING = float(os.getenv("MINUTES_CEILING", "30.0"))

# Story count
STORY_COUNT = int(os.getenv("STORY_COUNT", "5"))

# TTS safety
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1-hd")
TTS_CHUNK_CHARS = int(os.getenv("TTS_CHUNK_CHARS", "3800"))  # safer than 4000

# Cleanup behavior: delete per-segment mp3s after stitch
CLEANUP_SEGMENTS = os.getenv("CLEANUP_SEGMENTS", "true").lower() in ("1", "true", "yes")

# Script engines
OPENAI_MODEL_BACKUP = os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o")
GEMINI_PRIMARY_MODEL = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.0-flash")
GEMINI_BACKUP_MODEL = os.getenv("GEMINI_MODEL_BACKUP", "gemini-2.0-flash-exp")

# RSS feeds (edit / extend freely)
DEFAULT_FEEDS = [
    # General AI / Big Tech
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/rss",
    "https://www.technologyreview.com/feed/",
    "https://www.artificialintelligence-news.com/feed/",

    # AI research / labs / model releases
    "https://arxiv.org/rss/cs.AI",
    "https://huggingface.co/blog/feed.xml",

    # Business / money / markets
    "https://www.ft.com/technology?format=rss",
    "https://www.economist.com/the-world-this-week/rss.xml",

    # Policy / regulation / security
    "https://www.lawfaremedia.org/rss.xml",
    "https://www.schneier.com/feed/atom/",
]

FEEDS = os.getenv("RSS_FEEDS", "").strip()
FEEDS = [f.strip() for f in FEEDS.split(",") if f.strip()] if FEEDS else DEFAULT_FEEDS


# =========================
# 1) ENV + CLIENTS
# =========================

def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))

# Gemini is optional; if not set, we’ll run OpenAI-only.
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
client_gemini = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None


# =========================
# 2) SPONSORS
# =========================

def load_sponsors() -> List[Dict[str, Any]]:
    if not SPONSORS_FILE.exists():
        # fallback placeholders
        return [
            {"name": "Oracle Cloud", "copy": "Stop burning cash. Oracle Cloud is built for GPU workloads. Visit Oracle.com."},
            {"name": "NetSuite", "copy": "Visibility is survival. NetSuite gives you the data to survive the crash. NetSuite.com."},
            {"name": "ElevenLabs", "copy": "This show is 100% AI. Scale your content with ElevenLabs.io."},
        ]
    try:
        data = json.loads(SPONSORS_FILE.read_text(encoding="utf-8"))
        # Allow either { "sponsors": [...] } or [...]
        if isinstance(data, dict) and "sponsors" in data:
            return data["sponsors"]
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def pick_sponsors(sponsors: List[Dict[str, Any]], n: int = 2) -> List[Dict[str, Any]]:
    # simple deterministic pick: first n active sponsors if present
    if not sponsors:
        return []
    return sponsors[:n]


# =========================
# 3) INTEL (FEED FIRST)
# =========================

def fetch_rss_items(feeds: List[str], limit_per_feed: int = 8) -> List[Dict[str, str]]:
    items = []
    for url in feeds:
        try:
            d = feedparser.parse(url)
            for e in d.entries[:limit_per_feed]:
                title = (getattr(e, "title", "") or "").strip()
                link = (getattr(e, "link", "") or "").strip()
                summary = (getattr(e, "summary", "") or "").strip()
                published = (getattr(e, "published", "") or "").strip()
                if title:
                    items.append({
                        "source": url,
                        "title": title,
                        "link": link,
                        "summary": re.sub(r"\s+", " ", summary)[:400],
                        "published": published
                    })
        except Exception:
            continue
    return items


def intel_from_feeds() -> Optional[Dict[str, Any]]:
    print(" >> 🛰️  GATHERING INTEL FROM RSS FEEDS...")
    items = fetch_rss_items(FEEDS, limit_per_feed=8)
    if not items:
        return None

    # Provide a big pool; the planner model will choose top STORY_COUNT
    return {
        "mode": "rss",
        "items": items
    }


def intel_from_email_backup() -> Optional[Dict[str, Any]]:
    if not fetch_news:
        return None
    print(" >> 📡 FALLBACK: GATHERING INTEL FROM EMAIL...")
    try:
        data = fetch_news.get_todays_newsletters()
        if data:
            return {"mode": "email", "raw": data}
    except Exception as e:
        print(f"    ⚠️ EMAIL BACKUP FAILED: {e}")
    return None


def fallback_test_intel() -> Dict[str, Any]:
    return {
        "mode": "test",
        "raw": """
STORY 1: Anthropic’s Claude Sonnet upgrade triggers “infinite labor” fears.
STORY 2: OpenAI valuation / capital concentration accelerates.
STORY 3: Meta personalization + ads + private chats raises ethical alarms.
STORY 4: Major regulator proposes new model safety reporting requirements.
STORY 5: AI security incident shows prompt injection moving from theory to practice.
""".strip()
    }


def gather_intel() -> Dict[str, Any]:
    # Primary: feeds
    intel = intel_from_feeds()
    if intel:
        return intel

    # Backup: email newsletters
    intel = intel_from_email_backup()
    if intel:
        return intel

    # Last resort
    print("    ⚠️ NO FEEDS/EMAIL. USING TEST INTEL.")
    return fallback_test_intel()


# =========================
# 4) SCRIPT ENGINE (Gemini primary, OpenAI backup)
# =========================

def _gemini_generate(text: str, temperature: float = 0.9, max_tokens: int = 6000) -> str:
    if not client_gemini:
        raise RuntimeError("Gemini not configured (missing GEMINI_API_KEY).")

    conf = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens
    )

    # Try primary then backup
    for model in [GEMINI_PRIMARY_MODEL, GEMINI_BACKUP_MODEL]:
        try:
            r = client_gemini.models.generate_content(model=model, contents=text, config=conf)
            out = (r.text or "").strip()
            if out:
                return out
        except Exception as e:
            print(f"    ⚠️ GEMINI MODEL FAILED ({model}): {e}")
            continue

    raise RuntimeError("Gemini generation failed (all models).")


def _openai_generate(text: str, temperature: float = 0.9) -> str:
    r = client_openai.chat.completions.create(
        model=OPENAI_MODEL_BACKUP,
        messages=[
            {"role": "system", "content": "You are the Executive Producer of a hit tech podcast."},
            {"role": "user", "content": text}
        ],
        temperature=temperature
    )
    return (r.choices[0].message.content or "").strip()


def generate_text(full_prompt: str) -> str:
    """
    Gemini primary. OpenAI backup.
    """
    if client_gemini:
        try:
            return _gemini_generate(full_prompt)
        except Exception as e:
            print(f"    ⚠️ Gemini failed. Using OpenAI backup. Reason: {e}")

    try:
        return _openai_generate(full_prompt)
    except Exception as e:
        print(f"    ❌ OpenAI backup failed: {e}")
        return "ALEX: We are offline. See you tomorrow."


def build_story_pool(intel: Dict[str, Any]) -> str:
    """
    Convert intel into a planner-friendly text blob.
    """
    if intel.get("mode") == "rss":
        lines = []
        for it in intel.get("items", [])[:80]:
            lines.append(
                f"- TITLE: {it.get('title','')}\n  SUMMARY: {it.get('summary','')}\n  LINK: {it.get('link','')}\n  PUBLISHED: {it.get('published','')}\n"
            )
        return "\n".join(lines).strip()

    if intel.get("mode") == "email":
        return str(intel.get("raw", ""))[:12000]

    return str(intel.get("raw", ""))[:6000]


def select_top_stories(intel: Dict[str, Any], n: int) -> List[Dict[str, str]]:
    """
    Use model to pick the top N stories with angles for each character.
    Returns list of {headline, why_it_hits, link(optional)}.
    """
    pool = build_story_pool(intel)

    prompt = f"""
You are the lead producer for "The AI Edge" podcast.

Goal: pick the TOP {n} stories for today that will create DREAD, GREED, or EXCITEMENT.

Rules:
- Avoid boring "product updates" unless the implication is massive.
- Must cover multiple angles: human impact, money/power, regulation/risk, and "future shock."
- Output MUST be JSON array only.

Each item schema:
{{
  "headline": "...",
  "why_it_hits": "1-2 sentences explaining why listeners will care",
  "link": "optional url if available"
}}

Here is the raw story pool:
{pool}
""".strip()

    raw = generate_text(prompt)

    # extract JSON safely
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        arr = json.loads(m.group(0) if m else raw)
        if isinstance(arr, list) and arr:
            out = []
            for x in arr[:n]:
                out.append({
                    "headline": str(x.get("headline", "")).strip(),
                    "why_it_hits": str(x.get("why_it_hits", "")).strip(),
                    "link": str(x.get("link", "")).strip()
                })
            # drop empties
            out = [o for o in out if o["headline"]]
            return out[:n]
    except Exception:
        pass

    # fallback: take first N rss titles
    if intel.get("mode") == "rss":
        items = intel.get("items", [])[:n]
        return [{"headline": it["title"], "why_it_hits": it.get("summary","")[:140], "link": it.get("link","")} for it in items]

    return [{"headline": "AI shockwave continues", "why_it_hits": "High-impact changes across labor, capital, and regulation.", "link": ""}]


def write_full_script(selected_stories: List[Dict[str, str]], sponsors: List[Dict[str, Any]]) -> str:
    """
    5-segment structure. Preserve your character dynamics.
    """
    today_str = datetime.date.today().isoformat()

    stories_text = "\n".join([f"{i+1}. {s['headline']} — {s['why_it_hits']}" for i, s in enumerate(selected_stories)])

    sponsor_a = sponsors[0] if sponsors else {"name": "Sponsor", "copy": "Sponsor copy missing."}
    sponsor_b = sponsors[1] if len(sponsors) > 1 else sponsor_a

    # One prompt that instructs exact structure and bans corporate speak.
    prompt = f"""
You are the Showrunner for 'The AI Edge' Daily Podcast.

NON-NEGOTIABLE VIBE:
- "Succession" energy. Fast. Interruptions. Slightly messy.
- ZERO corporate speak. If you say "let's dive in" or "in today's rapidly evolving world" you failed.
- The listener MUST NOT suspect it is synthetic.

CHARACTERS (consistent every day):
- ALEX (Host, Rogan-style): high energy, curious, blunt, asks "dumb" listener questions.
- JAMIE (Co-host, Bartlett-style): vulnerable, human cost, "I feel..." statements, empathy.
- RUFUS (Analyst, Huberman/Matt Levine style): cynical, money/power/regulation, explains how the scam works.

TODAY'S DATE: {today_str}

TODAY'S TOP STORIES (use all of them):
{stories_text}

STRUCTURE: 5 SEGMENTS. Use these exact headers in the script:
[SEGMENT 1]
[SEGMENT 2]
[SEGMENT 3]
[SEGMENT 4]
[SEGMENT 5]

SEGMENT RULES:
[SEGMENT 1] (Trio)
- Cold open STARTS mid-argument about Story #1.
- Then [MUSIC]
- Then Alex: "Good morning" + date
- Alex physically introduces Jamie and Rufus every time (mandatory).
- Alex gives a Rogan-style SUMMARY of the stories for today in 30–45 seconds, teasing stakes.
- Then deep dive Story #1.

[SEGMENT 2] (Alex + Jamie only)
- Rufus is NOT present.
- Chemistry scene: human impact / creators / families / workers angle using Stories #2 and #3 as fuel.
- Must feel like two people in the studio.

[SEGMENT 3] (Rufus on location; Alex bridges)
- Alex tosses to Rufus "from the field."
- Rufus covers money + regulation angles across today’s stories.
- Must include NATIVE AD read woven into Rufus analysis as insider advice:
  Sponsor: {sponsor_a['name']} — {sponsor_a['copy']}
  It must not sound like a commercial break.

[SEGMENT 4] (Trio)
- Escalate to "future shock" synthesis. Use Story #4/#5 strongly.
- Interruptions, tension, greed/dread.

[SEGMENT 5] (Close)
- Alex closes and repeats the strongest thesis in 1 sentence.
- CTA: subscribe/share.
- Jamie may add one empathetic tag ONLY if it hits her vibe.

FORMAT:
- Dialogue lines like: ALEX: ... JAMIE: ... RUFUS: ...
- No narrator text except [MUSIC]
- No bullet points in the spoken dialogue.

TARGET LENGTH:
- Aim for 25–30 minutes of spoken audio.
""".strip()

    return generate_text(prompt)


# =========================
# 5) TTS + STITCHING
# =========================

def iter_utterances(script: str):
    """
    Reads lines like "ALEX: ..." and collects continuations.
    """
    pattern = re.compile(r'^\s*(ALEX|JAMIE|RUFUS)\s*:?\s*(.*)', re.IGNORECASE)
    current = None
    buf = []

    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue

        # ignore segment headers and [MUSIC]
        if line.startswith("[SEGMENT") or line == "[MUSIC]":
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


def clean_text(t: str) -> str:
    # remove bracketed stage directions and stray formatting
    t = re.sub(r'[\(\[].*?[\)\]]', '', t)
    t = t.replace('"', '').replace('*', '')
    t = re.sub(r"\s+", " ", t).strip()
    return t


def chunk_text(text: str, limit: int = TTS_CHUNK_CHARS) -> List[str]:
    text = clean_text(text)
    if len(text) <= limit:
        return [text] if text else []
    chunks = []
    remaining = text
    while len(remaining) > limit:
        # split at sentence boundary if possible
        cut = remaining.rfind('.', 0, limit)
        if cut < 200:
            cut = limit
        chunks.append(remaining[:cut+1].strip())
        remaining = remaining[cut+1:].strip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if len(c) > 2]


def tts_to_segments(script: str, today_str: str) -> List[Path]:
    """
    Generate segment mp3s with deterministic names and return paths.
    """
    seg_paths = []
    seg_idx = 0

    for speaker, text in iter_utterances(script):
        if speaker not in CAST:
            continue
        for chunk in chunk_text(text):
            out = AUDIO_DIR / f"{today_str}_seg_{seg_idx:04d}.mp3"
            try:
                with client_openai.audio.speech.with_streaming_response.create(
                    model=TTS_MODEL,
                    voice=CAST[speaker],
                    input=chunk
                ) as resp:
                    resp.stream_to_file(out)
                seg_paths.append(out)
                seg_idx += 1
            except Exception as e:
                print(f"    ⚠️ TTS ERROR ({speaker}): {e}")

    return seg_paths


def stitch_episode(seg_paths: List[Path], today_str: str) -> Path:
    """
    Stitch segments in order with small gaps + intro/outro if present.
    """
    audio = AudioSegment.empty()

    if INTRO_MUSIC.exists():
        audio += AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(2000)
        audio += AudioSegment.silent(duration=200)

    # Ensure sorted by seg index
    seg_paths_sorted = sorted(seg_paths, key=lambda p: p.name)

    for p in seg_paths_sorted:
        try:
            clip = AudioSegment.from_mp3(p)
            audio += clip
            audio += AudioSegment.silent(duration=150)
        except Exception:
            continue

    if OUTRO_MUSIC.exists():
        audio += AudioSegment.silent(duration=200)
        audio += AudioSegment.from_mp3(OUTRO_MUSIC)[:10000].fade_in(2000)

    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"
    audio.export(outfile, format="mp3", bitrate="192k")
    return outfile


def audio_minutes(path: Path) -> float:
    a = AudioSegment.from_mp3(path)
    return len(a) / 1000.0 / 60.0


def cleanup_segment_files(today_str: str, keep_latest_n: int = 0):
    """
    Deletes today's segment files after stitching, unless configured otherwise.
    """
    if not CLEANUP_SEGMENTS:
        return

    segs = sorted(AUDIO_DIR.glob(f"{today_str}_seg_*.mp3"))
    if keep_latest_n > 0 and len(segs) > keep_latest_n:
        segs_to_delete = segs[:-keep_latest_n]
    else:
        segs_to_delete = segs

    for p in segs_to_delete:
        try:
            p.unlink()
        except Exception:
            pass


# =========================
# 6) RSS UPDATE (Spotify stability)
# =========================

def ensure_feed_base():
    if RSS_FILE.exists():
        return
    base = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The AI Edge</title>
    <link>https://aisimplify333.github.io/Daily-ai-News/episode_audio/</link>
    <description>Daily AI News, Finance, and Regulation.</description>
    <language>en-us</language>
  </channel>
</rss>"""
    RSS_FILE.write_text(base, encoding="utf-8")


def update_rss_feed(audio_path: Path, title: str, show_notes: str):
    ensure_feed_base()
    tree = ET.parse(RSS_FILE)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("feed.xml is missing <channel> node")

    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = show_notes

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", f"https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}")
    enclosure.set("length", str(os.path.getsize(audio_path)))
    enclosure.set("type", "audio/mpeg")

    ET.SubElement(item, "guid").text = f"https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}"
    ET.SubElement(item, "pubDate").text = formatdate(os.path.getmtime(audio_path))

    # Insert newest at top
    channel.insert(0, item)

    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)


# =========================
# 7) MAIN ORCHESTRATION
# =========================

def build_show_notes(selected_stories: List[Dict[str, str]], today_str: str) -> Tuple[str, str, str]:
    """
    Returns (episode_title, show_notes, viral_caption)
    """
    # SEO: include 2–3 strongest nouns in title without spam
    top = selected_stories[0]["headline"] if selected_stories else "AI Shock"
    title = f"The AI Edge — {today_str} — {top[:70]}"

    topics = "\n".join([f"- {s['headline']}" for s in selected_stories])
    links = "\n".join([f"- {s['link']}" for s in selected_stories if s.get("link")])

    hashtags = "#AI #ArtificialIntelligence #TechNews #Business #Regulation"

    show_notes = f"""{today_str}

TOP STORIES:
{topics}

LINKS:
{links if links else "- (links unavailable)"}

{hashtags}
""".strip()

    viral_caption = f"""{today_str} | {title}

TOP STORIES:
{topics}

{hashtags}
""".strip()

    return title, show_notes, viral_caption


def expand_script_if_needed(script: str, selected_stories: List[Dict[str, str]]) -> str:
    """
    If the audio comes out too short, we expand the script by adding depth,
    WITHOUT changing the segment structure or character dynamics.
    """
    prompt = f"""
You are the showrunner. Expand the script to hit 25–30 minutes.

Non-negotiables:
- Keep EXACT same 5 segment headers: [SEGMENT 1]...[SEGMENT 5]
- Keep the same character dynamics and tone.
- Add more interruptions, analogies, and depth. No corporate speak.
- Add only dialogue. Preserve [MUSIC] where it exists.

Here are today's stories (keep them consistent):
{json.dumps(selected_stories, indent=2)}

Here is the current script to expand:
{script}
""".strip()

    return generate_text(prompt)


def produce_episode():
    today_str = datetime.date.today().isoformat()

    sponsors = load_sponsors()
    picked_sponsors = pick_sponsors(sponsors, n=2)

    intel = gather_intel()
    selected_stories = select_top_stories(intel, STORY_COUNT)

    # 1) Script
    print(" >> ✍️  WRITING FULL SCRIPT (5 SEGMENTS)...")
    script = write_full_script(selected_stories, picked_sponsors)

    # 2) TTS segments + Stitch
    print(" >> 🎙️  RECORDING (TTS)...")
    seg_paths = tts_to_segments(script, today_str)

    if not seg_paths:
        raise RuntimeError("No TTS segments were generated; cannot stitch episode.")

    print(" >> 🎚️  STITCHING FULL EPISODE...")
    episode_path = stitch_episode(seg_paths, today_str)
    minutes = audio_minutes(episode_path)
    print(f" ✅ EPISODE COMPLETE: {episode_path} ({minutes:.2f} minutes)")

    # If too short, expand once and re-render (keeps structure, just adds depth)
    if minutes < MINUTES_FLOOR:
        print(f"    ⚠️ Episode too short ({minutes:.2f} min). Expanding script and regenerating once...")
        script2 = expand_script_if_needed(script, selected_stories)

        # generate a fresh set of segments for the same day, but avoid collisions by clearing old segs first
        # (we keep the final podcast mp3)
        cleanup_segment_files(today_str)

        seg_paths2 = tts_to_segments(script2, today_str)
        episode_path2 = stitch_episode(seg_paths2, today_str)
        minutes2 = audio_minutes(episode_path2)
        print(f" ✅ EPISODE REBUILT: {episode_path2} ({minutes2:.2f} minutes)")

        # Replace for downstream use
        script = script2
        episode_path = episode_path2
        minutes = minutes2

    # Hard guardrail: if still too short, do NOT fail the run by throwing;
    # we publish anyway to keep daily cadence, but log a red flag.
    if minutes < MINUTES_FLOOR:
        print(f"    ❌ RED FLAG: Episode still short ({minutes:.2f} min). Publishing to maintain cadence.")
    elif minutes > MINUTES_CEILING:
        print(f"    ⚠️ Episode long ({minutes:.2f} min). Consider reducing depth next run.")
    else:
        print(f"    ✅ Runtime within target window ({minutes:.2f} min).")

    # 3) Notes + metadata
    title, show_notes, viral_caption = build_show_notes(selected_stories, today_str)
    (BASE_DIR / "viral_caption.txt").write_text(viral_caption, encoding="utf-8")
    (BASE_DIR / "episode_metadata.json").write_text(
        json.dumps({"title": title, "date": today_str, "stories": selected_stories}, indent=2),
        encoding="utf-8"
    )

    # 4) RSS update for Spotify
    print(" >> 📡 UPDATING RSS FEED...")
    update_rss_feed(episode_path, title, show_notes)

    # 5) Cleanup segment clutter
    cleanup_segment_files(today_str)

    return episode_path


if __name__ == "__main__":
    produce_episode()
