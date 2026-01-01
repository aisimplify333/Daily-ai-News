import os
import json
import re
import time
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

# LIBRARIES
from openai import OpenAI
from pydub import AudioSegment
import fetch_news

# Optional Gemini (Showrunner primary) — safely falls back to OpenAI if unavailable/quota-limited
try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None


# ============================================================
# 1) ENVIRONMENT & SETUP
# ============================================================

def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing environment variable: {name}")
    return val

# OpenAI is required (voice, and showrunner fallback)
client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))

# Gemini is optional (showrunner primary)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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
RSS_FILE = BASE_DIR / "feed.xml"

AUDIO_DIR.mkdir(exist_ok=True)

# Podcast metadata
PODCAST_TITLE = os.getenv("PODCAST_TITLE", "The AI Edge")
PODCAST_LINK = os.getenv("PODCAST_LINK", "https://aisimplify333.github.io/Daily-ai-News/episode_audio/")
PODCAST_DESCRIPTION = os.getenv("PODCAST_DESCRIPTION", "Daily AI News, Finance, and Regulation.")
PODCAST_LANGUAGE = os.getenv("PODCAST_LANGUAGE", "en-us")
AUDIO_BASE_URL = os.getenv("AUDIO_BASE_URL", "https://aisimplify333.github.io/Daily-ai-News/episode_audio/")
MAX_RSS_ITEMS = int(os.getenv("MAX_RSS_ITEMS", "60"))

# Quality gate: refuse to publish if episode is too short
MIN_EPISODE_MINUTES = float(os.getenv("MIN_EPISODE_MINUTES", "22"))

# Script length enforcement: per act minimum
# Keep default aligned with your existing intent (~1500 words/act)
MIN_WORDS_PER_ACT = int(os.getenv("MIN_WORDS_PER_ACT", "1500"))
EXPAND_ROUNDS = int(os.getenv("EXPAND_ROUNDS", "3"))

# CAST (The Voices) — unchanged
CAST = {
    "ALEX": "onyx",    # The Host
    "JAMIE": "nova",   # The Heart
    "RUFUS": "fable",  # The Brain
}

# TTS model (leave as-is unless you want to switch)
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1-hd")


# ============================================================
# 2) INTEL ENGINE
# ============================================================

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
    return """
STORY 1: Anthropic's Claude Sonnet 4.5 released. This model upgrade introduces smarter reasoning, stronger memory tools, and the ability to run multi-hour tasks without constant resets. It is a significant step forward for agentic AI.
STORY 2: OpenAI hits $500 Billion valuation. After a secondary share sale to investors, OpenAI reached this staggering number, showcasing the company's absolute dominance in the AI market.
STORY 3: Meta's AI-driven advertising sparks privacy debates. Meta is using AI-generated chatbot conversations to fuel ads, highlighting specific ethical implications of AI in advertising.
""".strip()

def get_sponsors():
    return [
        {"name": "Oracle Cloud", "copy": "Stop burning cash. Oracle Cloud is built for GPU workloads. Visit Oracle.com."},
        {"name": "NetSuite", "copy": "Visibility is survival. NetSuite gives you the data to survive the crash. NetSuite.com."},
        {"name": "ElevenLabs", "copy": "This show is 100% AI. Scale your content with ElevenLabs.io."},
    ]


# ============================================================
# 3) SHOWRUNNER (Dynamics/Structure unchanged; enforcement added)
# ============================================================

# IMPORTANT: This does not change your show dynamics; it only enforces formatting
# so your audio parser cannot silently drop content.
FORMAT_RULES = """
FORMAT RULES (NON-NEGOTIABLE):
- Every spoken line must be exactly ONE line that begins with ALEX: or JAMIE: or RUFUS:
- No wrapped lines. No multi-line paragraphs.
- Stage directions allowed ONLY as [MUSIC] on its own line.
- Do NOT output narration without a speaker tag.
""".strip()

# Your existing vibe/character dynamics — unchanged
SHOW_STYLE = """
THE VIBE:
- This is NOT a news reading. This is a "Succession" style drama about the tech world.
- Fast-paced. Characters should INTERRUPT each other.
- NO polite corporate speak. Use real language.

THE CHARACTERS:
- ALEX (Host): The "Joe Rogan" proxy. He asks the "dumb" questions the listener is thinking. High energy.
  *MANDATORY:* He must physically introduce the team every time.
- JAMIE (Co-Host): The "Steven Bartlett" proxy. Deeply vulnerable. She worries about the HUMAN cost. Uses "I feel" statements.
- RUFUS (Analyst): The "Huberman/Matt Levine" proxy. Cynical. He cares about MONEY. He explains *how* the scam works.
""".strip()

def word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))

_gemini_model_cache = None

def pick_gemini_model() -> str | None:
    """
    Pick an available Gemini model at runtime. Avoids hardcoded model churn.
    Returns None if Gemini isn't configured or models can't be listed.
    """
    global _gemini_model_cache
    if _gemini_model_cache:
        return _gemini_model_cache
    if not client_gemini:
        return None

    preferred = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    for m in preferred:
        try:
            client_gemini.models.get(model=m)
            _gemini_model_cache = m
            return m
        except Exception:
            pass

    try:
        for mdl in client_gemini.models.list():
            name = getattr(mdl, "name", None) or getattr(mdl, "model", None)
            if name:
                _gemini_model_cache = name
                return name
    except Exception:
        return None

    return None

def generate_with_gemini(prompt: str, temperature: float = 0.9, max_output_tokens: int = 6000) -> str:
    if not client_gemini or not genai_types:
        raise RuntimeError("Gemini not configured.")
    model_id = pick_gemini_model()
    if not model_id:
        raise RuntimeError("No Gemini model available for this key/project.")

    conf = genai_types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # retry lightly on 429s; fail fast if quota is 0/billing disabled
    for attempt in range(3):
        try:
            resp = client_gemini.models.generate_content(
                model=model_id,
                contents=prompt,
                config=conf,
            )
            txt = getattr(resp, "text", "") or ""
            return txt.strip()
        except Exception as e:
            msg = str(e)
            if "limit: 0" in msg or "FreeTier" in msg:
                raise RuntimeError(f"Gemini quota/billing not enabled: {e}")
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                time.sleep(20)
                continue
            raise
    raise RuntimeError("Gemini failed after retries.")

def generate_with_openai(prompt: str, temperature: float = 0.9) -> str:
    # Prefer Responses API; fall back to chat.completions for compatibility
    try:
        resp = client_openai.responses.create(
            model=os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o"),
            instructions="You are the Executive Producer of a hit tech podcast.",
            input=prompt,
            temperature=temperature,
            max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "6500")),
        )
        return (resp.output_text or "").strip()
    except Exception:
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

    # Primary: Gemini (if available). Fallback: OpenAI.
    if client_gemini:
        try:
            return generate_with_gemini(full_prompt, temperature=0.9, max_output_tokens=6500)
        except Exception as e:
            print(f"    ⚠️ GEMINI FAILED ({e}). FALLING BACK TO OPENAI...")

    try:
        return generate_with_openai(full_prompt, temperature=0.9)
    except Exception as e:
        print(f"    ❌ OPENAI GENERATION ERROR: {e}")
        return "ALEX: We are offline. See you tomorrow."

def enforce_min_words(act_name: str, act_text: str, intel: str, min_words: int, max_rounds: int = 3) -> str:
    """
    Enforce length without changing show structure/dynamics:
    we only ask the model to CONTINUE exactly where it left off.
    """
    w = word_count(act_text)
    if w >= min_words:
        print(f"    ✅ {act_name} length ok: {w} words")
        return act_text

    print(f"    ⚠️ {act_name} too short: {w} words. Expanding to >= {min_words}...")

    for i in range(1, max_rounds + 1):
        need = max(250, min_words - w)
        tail = act_text[-6000:]  # keep prompt lean

        expand_prompt = f"""
CONTINUE {act_name}.

You must add at least {need} MORE WORDS of NEW DIALOGUE.
DO NOT repeat any lines already written.
DO NOT restart the act.
Continue exactly where it left off, maintaining the SAME dynamics and structure.

{FORMAT_RULES}

EXISTING {act_name} (tail for context):
{tail}
""".strip()

        addition = generate_segment(expand_prompt, intel)
        act_text = (act_text + "\n" + addition).strip()
        w = word_count(act_text)
        print(f"    📈 {act_name} expansion round {i}: {w} words total")

        if w >= min_words:
            print(f"    ✅ {act_name} reached target: {w} words")
            break

    return act_text

def write_full_script(intel: str, sponsors: list[dict]) -> str:
    print(" >> ✍️  WRITING ACT I (THE HOOK & CHEMISTRY)...")
    prompt_act1 = f"""
You are the Showrunner for '{PODCAST_TITLE}' Daily Podcast.

{SHOW_STYLE}

TASK: Write ACT 1 (Intro + Story 1).
1. COLD OPEN (0:00-0:30): Start MID-ARGUMENT about Story 1 (Claude 4.5). Jamie is panicked about "Agents that never sleep", Rufus sees "Infinite Labor." High tension.
2. MUSIC INTRO: Write [MUSIC].
3. THE WELCOME: Alex says "Good morning." States the Date.
   - ALEX MUST SAY: "With me is the conscience of the show, Jamie. Say hello Jamie." (Jamie responds with a mood check).
   - ALEX MUST SAY: "And checking in from the field... Rufus." (Rufus responds with a cynical location/trade).
4. STORY 1 DEEP DIVE: Claude Sonnet 4.5. Alex asks what "Multi-hour tasks" means. Jamie fears autonomous agents. Rufus explains the cost savings of firing humans.

LENGTH: 1500 words (approx 8-10 mins).
""".strip()

    script_act1 = generate_segment(prompt_act1, intel)
    script_act1 = enforce_min_words("ACT 1", script_act1, intel, MIN_WORDS_PER_ACT, EXPAND_ROUNDS)

    print(" >> ✍️  WRITING ACT II (THE MECHANICS & MONEY)...")
    prompt_act2 = f"""
Write ACT 2 of '{PODCAST_TITLE}'.

{SHOW_STYLE}

TASK: Cover Story 2 ($500B Valuation) and the Native Ad.
1. TRANSITION: Alex moves to Story 2 (OpenAI's Money).
2. THE DEBATE: $500 Billion. Is it a bubble? Rufus breaks down the valuation metrics. Jamie asks if one company should own the future.
3. NATIVE AD (THE RUFUS MOMENT): Rufus interrupts to read this ad IN CHARACTER: {sponsors[0]['name']} - {sponsors[0]['copy']}.
   *CRITICAL:* He must weave it into his analysis as advice. "Look, if you want to survive this valuation war..."

LENGTH: 1500 words (approx 8-10 mins).
""".strip()

    script_act2 = generate_segment(prompt_act2, intel)
    script_act2 = enforce_min_words("ACT 2", script_act2, intel, MIN_WORDS_PER_ACT, EXPAND_ROUNDS)

    print(" >> ✍️  WRITING ACT III (THE FUTURE & OUTRO)...")
    prompt_act3 = f"""
Write ACT 3 of '{PODCAST_TITLE}'.

{SHOW_STYLE}

TASK: Cover Story 3 (Meta Privacy) and the Sign-Off.
1. STORY 3: Meta reading chatbot logs for ads.
2. JAMIE'S MOMENT: Jamie gets vulnerable. "Our thoughts are now billboards."
3. THE CTA: Alex asks listeners to "Subscribe and Share if you want to survive the AI wave."
4. SIGN OFF: Alex says "See you tomorrow."

LENGTH: 1500 words (approx 8-10 mins).
""".strip()

    script_act3 = generate_segment(prompt_act3, intel)
    script_act3 = enforce_min_words("ACT 3", script_act3, intel, MIN_WORDS_PER_ACT, EXPAND_ROUNDS)

    full = f"{script_act1}\n{script_act2}\n{script_act3}".strip()
    total_words = word_count(full)
    print(f" >> 🧾 SCRIPT STATS: {total_words} words total")

    # Save script for scrutiny/debug
    today_str = datetime.date.today().isoformat()
    (BASE_DIR / f"script_{today_str}.txt").write_text(full, encoding="utf-8")

    return full


# ============================================================
# 4) PRODUCTION ENGINE
# ============================================================

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
            if current:
                buf.append(line)
    if current and buf:
        yield current, " ".join(buf).strip()

def clean_text(text: str) -> str:
    text = re.sub(r"[\(\[].*?[\)\]]", "", text)
    text = text.replace('"', "").replace("*", "").strip()
    return re.sub(r"\s+", " ", text).strip()

def chunk_for_tts(text: str, limit: int = 3900):
    """
    Keep under 4096-char constraint with margin.
    Splits on sentence boundaries, then hard-splits if needed.
    """
    text = clean_text(text)
    if len(text) <= limit:
        return [text]

    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""

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


# ============================================================
# 5) RSS FEED (safe insertion + dedupe + keep last N)
# ============================================================

def ensure_feed_exists():
    if RSS_FILE.exists():
        return
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

    tree = ET.ElementTree(rss)
    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)

def update_rss_feed(audio_path: Path, show_notes: str, title: str):
    ensure_feed_exists()

    tree = ET.parse(RSS_FILE)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS feed missing <channel> element.")

    enclosure_url = f"{AUDIO_BASE_URL}{audio_path.name}"
    guid_val = enclosure_url

    # Deduplicate
    for item in channel.findall("item"):
        guid = item.findtext("guid", default="")
        enc = item.find("enclosure")
        enc_url = enc.get("url") if enc is not None else ""
        if guid == guid_val or enc_url == enclosure_url:
            print(" >> 📡 RSS: Episode already exists in feed; skipping.")
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

    # Insert after channel metadata (before first existing item)
    items = channel.findall("item")
    if items:
        idx = list(channel).index(items[0])
        channel.insert(idx, item)
    else:
        channel.append(item)

    # Trim
    items = channel.findall("item")
    if len(items) > MAX_RSS_ITEMS:
        for old in items[MAX_RSS_ITEMS:]:
            channel.remove(old)

    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)


# ============================================================
# 6) PRODUCE EPISODE
# ============================================================

def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors()

    full_script = write_full_script(intel, sponsors)

    today_str = datetime.date.today().isoformat()
    episode_title = f"{PODCAST_TITLE}: {today_str}"
    show_notes = f"{today_str} | {episode_title}\n\nTOPICS:\n{intel[:700]}...\n\n#AI #TechNews"

    (BASE_DIR / "viral_caption.txt").write_text(show_notes, encoding="utf-8")
    meta = {"title": episode_title, "date": today_str, "headlines": [intel[:120]]}
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")
    audio_clips = []

    if INTRO_MUSIC.exists():
        audio_clips.append(AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(2000))

    seg_idx = 0
    for speaker, text in iter_utterances(full_script):
        if speaker not in CAST:
            continue
        for chunk in chunk_for_tts(text):
            if len(chunk) < 3:
                continue
            out_seg = AUDIO_DIR / f"{today_str}_seg_{seg_idx:04d}.mp3"
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

    # Hard quality gate (prevents publishing short episodes)
    if minutes < MIN_EPISODE_MINUTES:
        raise RuntimeError(f"Episode too short ({minutes:.2f} min). Refusing to publish.")

    update_rss_feed(outfile, show_notes, episode_title)

if __name__ == "__main__":
    produce_episode()
