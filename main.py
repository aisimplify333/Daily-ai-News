import os
import json
import re
import time
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

from openai import OpenAI
from pydub import AudioSegment

import fetch_news

# ----------------------------
# 1) ENVIRONMENT & SETUP
# ----------------------------

def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing environment variable: {name}")
    return val

# OpenAI (always required for voice; also used as showrunner fallback)
client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))

# Optional Gemini (showrunner primary if enabled)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

client_gemini = None
if GEMINI_API_KEY and genai and genai_types:
    # Force stable v1 endpoint to avoid v1beta model mismatch
    client_gemini = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=genai_types.HttpOptions(api_version="v1"),
    )

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

AUDIO_DIR.mkdir(exist_ok=True)

# Podcast metadata (feed)
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "The AI Edge")
PODCAST_LINK = os.getenv("PODCAST_LINK", "https://aisimplify333.github.io/Daily-ai-News/")
AUDIO_BASE_URL = os.getenv("AUDIO_BASE_URL", "https://aisimplify333.github.io/Daily-ai-News/episode_audio/")
PODCAST_DESCRIPTION = os.getenv("PODCAST_DESCRIPTION", "Daily AI News, Finance, and Regulation.")
PODCAST_LANGUAGE = os.getenv("PODCAST_LANGUAGE", "en-us")
PODCAST_AUTHOR = os.getenv("PODCAST_AUTHOR", "AI Simplify Media")
PODCAST_IMAGE = os.getenv("PODCAST_IMAGE", "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png")
ITUNES_CATEGORY = os.getenv("ITUNES_CATEGORY", "Technology")

# Output controls
RSS_FILE = BASE_DIR / "feed.xml"
MAX_RSS_ITEMS = int(os.getenv("MAX_RSS_ITEMS", "60"))

# Episode quality gate
MIN_EPISODE_MINUTES = float(os.getenv("MIN_EPISODE_MINUTES", "18"))

# Voice casting
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable",
}

# TTS model selection
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1-hd")  # or "gpt-4o-mini-tts"

# ----------------------------
# 2) INTEL ENGINE
# ----------------------------

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
        "STORY 1: Anthropic's Claude Sonnet 4.5 released. This model upgrade introduces smarter reasoning, stronger memory tools, "
        "and the ability to run multi-hour tasks without constant resets. It is a significant step forward for agentic AI.\n"
        "STORY 2: OpenAI hits $500 Billion valuation. After a secondary share sale to investors, OpenAI reached this staggering number, "
        "showcasing the company's absolute dominance in the AI market.\n"
        "STORY 3: Meta's AI-driven advertising sparks privacy debates. Meta is using AI-generated chatbot conversations to fuel ads, "
        "highlighting specific ethical implications of AI in advertising.\n"
    )

def get_sponsors():
    return [
        {"name": "Oracle Cloud", "copy": "Stop burning cash. Oracle Cloud is built for GPU workloads. Visit Oracle.com."},
        {"name": "NetSuite", "copy": "Visibility is survival. NetSuite gives you the data to survive the crash. NetSuite.com."},
        {"name": "ElevenLabs", "copy": "This show is 100% AI. Scale your content with ElevenLabs.io."},
    ]

# ----------------------------
# 3) SHOWRUNNER (Gemini primary, OpenAI fallback)
# ----------------------------

FORMAT_RULES = """
FORMAT RULES (NON-NEGOTIABLE):
- Every spoken line must be exactly ONE LINE that begins with ALEX: or JAMIE: or RUFUS:
- No wrapped lines. No paragraphs of dialogue.
- Stage directions allowed ONLY as [MUSIC] on its own line.
- Do NOT output narration without a speaker tag.
"""

SHOW_STYLE = """
THE VIBE:
- This is NOT a news reading. This is a "Succession" style drama about the tech world.
- Fast-paced. Characters should INTERRUPT each other.
- No polite corporate speak. Use real language.

THE CHARACTERS:
- ALEX (Host): "Joe Rogan" proxy. High energy. He must physically introduce the team every time.
- JAMIE (Co-Host): "Steven Bartlett" proxy. Vulnerable. Human cost. Uses "I feel" statements.
- RUFUS (Analyst): "Huberman/Matt Levine" proxy. Cynical. Money-focused. Explains how the scam works.
"""

_gemini_model_cache = None

def pick_gemini_model() -> str | None:
    """
    Picks an available Gemini model at runtime to avoid hardcoding model IDs.
    Returns None if Gemini is not configured/available.
    """
    global _gemini_model_cache
    if _gemini_model_cache:
        return _gemini_model_cache

    if not client_gemini:
        return None

    # Prefer stable models if present
    preferred = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    # Try preferred list
    for m in preferred:
        try:
            client_gemini.models.get(model=m)
            _gemini_model_cache = m
            return m
        except Exception:
            pass

    # Fall back to first listable model
    try:
        for mdl in client_gemini.models.list():
            name = getattr(mdl, "name", None) or getattr(mdl, "model", None)
            if name:
                _gemini_model_cache = name
                return name
    except Exception:
        return None

    return None

def generate_with_gemini(prompt: str, max_output_tokens: int = 6000, temperature: float = 0.9) -> str:
    if not client_gemini or not genai_types:
        raise RuntimeError("Gemini not configured.")

    model_id = pick_gemini_model()
    if not model_id:
        raise RuntimeError("No Gemini model available for this key/project.")

    conf = genai_types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # Limited retries for 429s
    retries = 3
    for attempt in range(retries):
        try:
            resp = client_gemini.models.generate_content(
                model=model_id,
                contents=prompt,
                config=conf,
            )
            text = getattr(resp, "text", "") or ""
            return text.strip()
        except Exception as e:
            msg = str(e)
            # If quota=0 / billing disabled, this will never succeed; fail fast.
            if "limit: 0" in msg or "FreeTier" in msg:
                raise RuntimeError(f"Gemini quota/billing not enabled: {e}")
            # Retry on rate-limits
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                sleep_s = 20
                time.sleep(sleep_s)
                continue
            raise

    raise RuntimeError("Gemini failed after retries.")

def generate_with_openai(prompt: str, temperature: float = 0.9) -> str:
    # Prefer Responses API if available; fall back to chat.completions if not.
    try:
        resp = client_openai.responses.create(
            model=os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o"),
            instructions="You are the Executive Producer of a hit tech podcast.",
            input=prompt,
            temperature=temperature,
            max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "6000")),
        )
        return (resp.output_text or "").strip()
    except Exception:
        # Compatibility fallback
        resp = client_openai.chat.completions.create(
            model=os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": "You are the Executive Producer of a hit tech podcast."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()

def generate_segment(system_prompt: str, content_context: str) -> str:
    full_prompt = f"{system_prompt}\n\n{FORMAT_RULES}\n\nCONTEXT:\n{content_context}".strip()

    # Try Gemini first (if configured). Fallback to OpenAI always.
    if client_gemini:
        try:
            return generate_with_gemini(full_prompt)
        except Exception as e:
            print(f"    ⚠️ GEMINI FAILED ({e}). FALLING BACK TO OPENAI...")

    try:
        return generate_with_openai(full_prompt)
    except Exception as e:
        print(f"    ❌ OPENAI GENERATION ERROR: {e}")
        return "ALEX: We are offline. See you tomorrow."

def write_full_script(intel: str, sponsors: list[dict]) -> str:
    today = datetime.date.today().strftime("%B %d, %Y")

    act1 = f"""
{SHOW_STYLE}
TASK: Write ACT 1 (Intro + Story 1).
1) COLD OPEN (0:00-0:30): Start MID-ARGUMENT about Story 1. Jamie is panicked about "agents that never sleep", Rufus sees "infinite labor."
2) MUSIC INTRO: Output [MUSIC]
3) THE WELCOME: Alex says "Good morning." States the date as: {today}
   - ALEX MUST SAY: "With me is the conscience of the show, Jamie. Say hello Jamie." (Jamie responds with a mood check)
   - ALEX MUST SAY: "And checking in from the field... Rufus." (Rufus responds with a cynical location/trade)
4) STORY 1 DEEP DIVE: Alex asks what "multi-hour tasks" means. Jamie fears autonomous agents. Rufus explains cost savings by firing humans.

LENGTH: ~1500 words.
""".strip()

    act2 = f"""
{SHOW_STYLE}
TASK: Write ACT 2.
1) TRANSITION: Alex moves to Story 2.
2) THE DEBATE: $500B valuation. Bubble or not? Rufus breaks down valuation mechanics. Jamie asks if one company should own the future.
3) NATIVE AD (IN CHARACTER): Rufus reads this ad naturally as "advice" inside his analysis:
   Sponsor: {sponsors[0]['name']}
   Copy: {sponsors[0]['copy']}

LENGTH: ~1500 words.
""".strip()

    act3 = f"""
{SHOW_STYLE}
TASK: Write ACT 3.
1) STORY 3: Meta reading chatbot logs for ads.
2) JAMIE'S MOMENT: "Our thoughts are now billboards."
3) CTA: Alex: "Subscribe and Share if you want to survive the AI wave."
4) SIGN OFF: Alex: "See you tomorrow."

LENGTH: ~1500 words.
""".strip()

    print(" >> ✍️  WRITING ACT I (THE HOOK & CHEMISTRY)...")
    script_act1 = generate_segment(act1, intel)

    print(" >> ✍️  WRITING ACT II (THE MECHANICS & MONEY)...")
    script_act2 = generate_segment(act2, intel)

    print(" >> ✍️  WRITING ACT III (THE FUTURE & OUTRO)...")
    script_act3 = generate_segment(act3, intel)

    return f"{script_act1}\n{script_act2}\n{script_act3}".strip()

# ----------------------------
# 4) PRODUCTION ENGINE (parse -> TTS -> mix)
# ----------------------------

SPEAKER_RE = re.compile(r"^\s*(ALEX|JAMIE|RUFUS|SPONSOR)\s*:?\s*(.*)\s*$", re.IGNORECASE)

def iter_utterances(script: str):
    current = None
    buf = []

    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = SPEAKER_RE.match(line)
        if m:
            if current and buf:
                yield current, " ".join(buf).strip()
            current = m.group(1).upper()
            if current == "SPONSOR":
                current = "RUFUS"
            buf = [m.group(2).strip()]
        else:
            # continuation of previous speaker
            if current:
                buf.append(line)

    if current and buf:
        yield current, " ".join(buf).strip()

def clean_text(text: str) -> str:
    # Remove bracket/paren stage directions; remove markdown-ish junk
    text = re.sub(r"[\(\[].*?[\)\]]", "", text)
    text = text.replace('"', "").replace("*", "").strip()
    return re.sub(r"\s+", " ", text).strip()

def chunk_for_tts(text: str, limit: int = 3900):
    """
    Keep under 4096-char constraint with margin.
    Splits preferably on sentence boundaries, then hard-splits.
    """
    text = clean_text(text)
    if len(text) <= limit:
        return [text]

    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    cur = ""

    for p in parts:
        if not p:
            continue
        if len(cur) + len(p) + 1 <= limit:
            cur = (cur + " " + p).strip()
        else:
            if cur:
                chunks.append(cur)
            if len(p) <= limit:
                cur = p
            else:
                for i in range(0, len(p), limit):
                    chunks.append(p[i:i+limit])
                cur = ""

    if cur:
        chunks.append(cur)

    return [c for c in chunks if c.strip()]

def synthesize_tts(speaker: str, text: str, out_path: Path):
    with client_openai.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=CAST[speaker],
        input=text,
        response_format="mp3",
    ) as resp:
        resp.stream_to_file(out_path)

# ----------------------------
# 5) RSS FEED
# ----------------------------

def ensure_feed_exists():
    if RSS_FILE.exists():
        return

    # Register namespaces for cleaner output
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

    rss = ET.Element("rss", attrib={
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    })
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = PODCAST_TITLE
    ET.SubElement(channel, "link").text = PODCAST_LINK
    ET.SubElement(channel, "description").text = PODCAST_DESCRIPTION
    ET.SubElement(channel, "language").text = PODCAST_LANGUAGE

    # Basic iTunes metadata (helpful for podcast directories)
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = PODCAST_AUTHOR
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "false"
    img = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
    img.set("href", PODCAST_IMAGE)
    cat = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
    cat.set("text", ITUNES_CATEGORY)

    tree = ET.ElementTree(rss)
    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)

def update_rss_feed(audio_path: Path, show_notes: str, title: str):
    ensure_feed_exists()

    tree = ET.parse(RSS_FILE)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS feed missing channel element.")

    enclosure_url = f"{AUDIO_BASE_URL}{audio_path.name}"
    guid_val = enclosure_url

    # Deduplicate (by guid or enclosure url)
    for item in channel.findall("item"):
        guid = item.findtext("guid", default="")
        enc = item.find("enclosure")
        enc_url = enc.get("url") if enc is not None else ""
        if guid == guid_val or enc_url == enclosure_url:
            # already present; skip inserting
            print(" >> 📡 RSS: Episode already in feed, skipping insert.")
            return

    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = show_notes

    enc = ET.SubElement(item, "enclosure")
    enc.set("url", enclosure_url)
    enc.set("length", str(os.path.getsize(audio_path)))
    enc.set("type", "audio/mpeg")

    ET.SubElement(item, "guid").text = guid_val
    ET.SubElement(item, "pubDate").text = formatdate(os.path.getmtime(audio_path))

    # Insert item after channel metadata (before first existing item)
    items = channel.findall("item")
    if items:
        idx = list(channel).index(items[0])
        channel.insert(idx, item)
    else:
        channel.append(item)

    # Trim feed to MAX_RSS_ITEMS
    items = channel.findall("item")
    if len(items) > MAX_RSS_ITEMS:
        for old in items[MAX_RSS_ITEMS:]:
            channel.remove(old)

    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)

# ----------------------------
# 6) MAIN EPISODE PRODUCTION
# ----------------------------

def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors()

    full_script = write_full_script(intel, sponsors)

    # Quality gate: refuse to publish clearly failed scripts
    if "we are offline" in full_script.lower() or len(full_script) < 8000:
        raise RuntimeError("Showrunner failed or script too short. Refusing to publish episode.")

    today_str = datetime.date.today().isoformat()
    episode_title = f"{PODCAST_TITLE}: {today_str}"

    show_notes = (
        f"{today_str} | {episode_title}\n\n"
        f"TOPICS:\n{intel[:700]}...\n\n"
        "#AI #TechNews"
    )

    (BASE_DIR / "viral_caption.txt").write_text(show_notes, encoding="utf-8")
    meta = {"title": episode_title, "date": today_str, "headlines": [intel[:120]]}
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")
    audio_clips = []

    if INTRO_MUSIC.exists():
        audio_clips.append(AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(2000))

    seg_idx = 0
    run_id = today_str

    for speaker, text in iter_utterances(full_script):
        if speaker not in CAST:
            continue

        for chunk in chunk_for_tts(text):
            if len(chunk) < 3:
                continue

            out_seg = AUDIO_DIR / f"{run_id}_seg_{seg_idx:04d}.mp3"
            try:
                synthesize_tts(speaker, chunk, out_seg)
                audio_clips.append(AudioSegment.from_mp3(out_seg))
                seg_idx += 1
            except Exception as e:
                print(f"    ⚠️ TTS ERROR: {e}")

    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    for clip in audio_clips:
        full_audio += clip + AudioSegment.silent(duration=150)

    if OUTRO_MUSIC.exists():
        full_audio += AudioSegment.from_mp3(OUTRO_MUSIC)[:10000].fade_in(2000)

    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")

    minutes = (len(full_audio) / 1000.0) / 60.0
    print(f" ✅ EPISODE COMPLETE: {outfile} ({minutes:.2f} minutes)")

    # Final quality gate
    if minutes < MIN_EPISODE_MINUTES:
        raise RuntimeError(f"Episode too short ({minutes:.2f} min). Refusing to publish.")

    update_rss_feed(outfile, show_notes, episode_title)

if __name__ == "__main__":
    produce_episode()
