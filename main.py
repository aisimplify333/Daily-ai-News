import os
import json
import re
import time
import shutil
import subprocess
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

from openai import OpenAI
import fetch_news

# Optional Gemini (showrunner primary) — safe fallback to OpenAI
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
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing environment variable: {name}")
    return v

client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client_gemini = None
if GEMINI_API_KEY and genai and genai_types:
    # Force stable v1 endpoint, avoids v1beta model mismatch churn
    client_gemini = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=genai_types.HttpOptions(api_version="v1"),
    )

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
TMP_DIR = BASE_DIR / "_tmp_audio"
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"
RSS_FILE = BASE_DIR / "feed.xml"

AUDIO_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

PODCAST_TITLE = os.getenv("PODCAST_TITLE", "The AI Edge")
PODCAST_LINK = os.getenv("PODCAST_LINK", "https://aisimplify333.github.io/Daily-ai-News/episode_audio/")
PODCAST_DESCRIPTION = os.getenv("PODCAST_DESCRIPTION", "Daily AI News, Finance, and Regulation.")
PODCAST_LANGUAGE = os.getenv("PODCAST_LANGUAGE", "en-us")
AUDIO_BASE_URL = os.getenv("AUDIO_BASE_URL", "https://aisimplify333.github.io/Daily-ai-News/episode_audio/")
MAX_RSS_ITEMS = int(os.getenv("MAX_RSS_ITEMS", "60"))

# Quality gate
MIN_EPISODE_MINUTES = float(os.getenv("MIN_EPISODE_MINUTES", "22"))

# Script length enforcement (per act)
MIN_WORDS_PER_ACT = int(os.getenv("MIN_WORDS_PER_ACT", "1500"))
EXPAND_ROUNDS = int(os.getenv("EXPAND_ROUNDS", "3"))

# Stitching settings
GAP_MS = int(os.getenv("SEGMENT_GAP_MS", "150"))
FINAL_BITRATE = os.getenv("FINAL_BITRATE", "192k")

# TTS settings
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1-hd")
OPENAI_SCRIPT_MODEL = os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o")
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "6500"))

# CAST (unchanged)
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable",
}

SPEAKER_RE = re.compile(r"^\s*(ALEX|JAMIE|RUFUS|SPONSOR)\s*:?\s*(.*)\s*$", re.IGNORECASE)

FORMAT_RULES = """
FORMAT RULES (NON-NEGOTIABLE):
- Every spoken line must be exactly ONE line that begins with ALEX: or JAMIE: or RUFUS:
- Stage directions allowed ONLY as [MUSIC] on its own line.
- Do NOT output narration without a speaker tag.
""".strip()

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
# 3) SHOWRUNNER (same dynamics; length enforcement added)
# ============================================================

def word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))

def generate_with_openai(prompt: str, temperature: float = 0.9) -> str:
    # Prefer Responses API
    try:
        resp = client_openai.responses.create(
            model=OPENAI_SCRIPT_MODEL,
            instructions="You are the Executive Producer of a hit tech podcast.",
            input=prompt,
            temperature=temperature,
            max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
        )
        return (resp.output_text or "").strip()
    except Exception:
        resp = client_openai.chat.completions.create(
            model=OPENAI_SCRIPT_MODEL,
            messages=[
                {"role": "system", "content": "You are the Executive Producer of a hit tech podcast."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()

_gemini_model_cache = None

def pick_gemini_model() -> str | None:
    global _gemini_model_cache
    if _gemini_model_cache:
        return _gemini_model_cache
    if not client_gemini:
        return None

    # Try some common, then list fallback
    preferred = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
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

def generate_with_gemini(prompt: str, temperature: float = 0.9, max_output_tokens: int = 6500) -> str:
    if not client_gemini or not genai_types:
        raise RuntimeError("Gemini not configured.")
    model_id = pick_gemini_model()
    if not model_id:
        raise RuntimeError("No Gemini model available for this key/project.")

    conf = genai_types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # Light retries on transient 429
    for _ in range(3):
        try:
            resp = client_gemini.models.generate_content(
                model=model_id,
                contents=prompt,
                config=conf,
            )
            return (getattr(resp, "text", "") or "").strip()
        except Exception as e:
            msg = str(e)
            if "limit: 0" in msg or "FreeTier" in msg:
                raise RuntimeError(f"Gemini quota/billing not enabled: {e}")
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                time.sleep(20)
                continue
            raise
    raise RuntimeError("Gemini failed after retries.")

def generate_segment(system_prompt: str, content_context: str) -> str:
    full_prompt = f"{system_prompt}\n\n{FORMAT_RULES}\n\nCONTEXT:\n{content_context}".strip()

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
    w = word_count(act_text)
    if w >= min_words:
        print(f"    ✅ {act_name} length ok: {w} words")
        return act_text

    print(f"    ⚠️ {act_name} too short: {w} words. Expanding to >= {min_words}...")

    for i in range(1, max_rounds + 1):
        need = max(250, min_words - w)
        tail = act_text[-6000:]

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
            break

    print(f"    ✅ {act_name} final: {w} words")
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
    act1 = generate_segment(prompt_act1, intel)
    act1 = enforce_min_words("ACT 1", act1, intel, MIN_WORDS_PER_ACT, EXPAND_ROUNDS)

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
    act2 = generate_segment(prompt_act2, intel)
    act2 = enforce_min_words("ACT 2", act2, intel, MIN_WORDS_PER_ACT, EXPAND_ROUNDS)

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
    act3 = generate_segment(prompt_act3, intel)
    act3 = enforce_min_words("ACT 3", act3, intel, MIN_WORDS_PER_ACT, EXPAND_ROUNDS)

    full = f"{act1}\n{act2}\n{act3}".strip()
    today_str = datetime.date.today().isoformat()
    (BASE_DIR / f"script_{today_str}.txt").write_text(full, encoding="utf-8")

    print(f" >> 🧾 SCRIPT STATS: {word_count(full)} words total")
    return full


# ============================================================
# 4) SCRIPT PARSING + TTS CHUNKING (same content, fewer segments)
# ============================================================

def clean_text(text: str) -> str:
    text = re.sub(r"[\(\[].*?[\)\]]", "", text)
    text = text.replace('"', "").replace("*", "").strip()
    return re.sub(r"\s+", " ", text).strip()

def iter_utterances(script: str):
    current = None
    buf = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "[MUSIC]":
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
            # If the model emits a non-tag line, attach it to current speaker (prevents silent drops)
            if current:
                buf.append(line)
    if current and buf:
        yield current, " ".join(buf).strip()

def iter_speaker_blocks(script: str, max_chars: int = 3200):
    """
    Collapse consecutive utterances by the same speaker into larger blocks
    (does NOT change order/dynamics; just reduces TTS calls/segments).
    """
    cur_speaker = None
    cur_text = ""

    for speaker, text in iter_utterances(script):
        if speaker not in CAST:
            continue
        text = clean_text(text)
        if not text:
            continue

        if cur_speaker is None:
            cur_speaker, cur_text = speaker, text
            continue

        if speaker == cur_speaker and (len(cur_text) + 1 + len(text)) <= max_chars:
            cur_text = f"{cur_text} {text}".strip()
        else:
            yield cur_speaker, cur_text
            cur_speaker, cur_text = speaker, text

    if cur_speaker and cur_text:
        yield cur_speaker, cur_text

def chunk_for_tts(text: str, limit: int = 3900):
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


# ============================================================
# 5) FFMPEG STITCHING (reliable, no huge in-memory concat)
# ============================================================

def require_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. MoviePy typically installs it; ensure it exists.")
    return ffmpeg, ffprobe

def run_proc(cmd: list[str], desc: str):
    print(f" >> 🎛️  {desc}...")
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"{desc} failed.\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")

def make_silence_mp3(path: Path, duration_ms: int):
    ffmpeg, _ = require_ffmpeg()
    dur = max(0.01, duration_ms / 1000.0)
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{dur}",
        "-c:a", "libmp3lame",
        "-b:a", FINAL_BITRATE,
        str(path),
    ]
    run_proc(cmd, f"Generating {duration_ms}ms silence")

def render_music_clip(src: Path, out: Path, seconds: int, fade: str):
    """
    fade: 'in' or 'out' or 'none'
    """
    ffmpeg, _ = require_ffmpeg()
    af = None
    if fade == "out":
        # fade out last 2 seconds
        st = max(0, seconds - 2)
        af = f"afade=t=out:st={st}:d=2"
    elif fade == "in":
        af = "afade=t=in:st=0:d=2"

    cmd = [ffmpeg, "-y", "-i", str(src), "-t", str(seconds)]
    if af:
        cmd += ["-af", af]
    cmd += ["-c:a", "libmp3lame", "-b:a", FINAL_BITRATE, str(out)]
    run_proc(cmd, f"Rendering music clip ({src.name})")

def stitch_audio_ffmpeg(ordered_mp3s: list[Path], outfile: Path):
    ffmpeg, _ = require_ffmpeg()
    if not ordered_mp3s:
        raise RuntimeError("No audio segments to stitch.")

    list_file = TMP_DIR / "concat_list.txt"
    with list_file.open("w", encoding="utf-8") as f:
        for p in ordered_mp3s:
            # paths are safe in Actions (no quotes/spaces), but keep quotes anyway
            f.write(f"file '{p.as_posix()}'\n")

    cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c:a", "libmp3lame",
        "-b:a", FINAL_BITRATE,
        str(outfile),
    ]
    run_proc(cmd, "Stitching episode with ffmpeg")

def get_duration_minutes(path: Path) -> float:
    _, ffprobe = require_ffmpeg()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed.\nSTDERR:\n{p.stderr}")
    sec = float((p.stdout or "").strip() or "0")
    return sec / 60.0


# ============================================================
# 6) RSS FEED
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
    ET.ElementTree(rss).write(RSS_FILE, encoding="UTF-8", xml_declaration=True)

def update_rss_feed(audio_path: Path, show_notes: str, title: str):
    ensure_feed_exists()
    tree = ET.parse(RSS_FILE)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS feed missing <channel>")

    enclosure_url = f"{AUDIO_BASE_URL}{audio_path.name}"
    guid_val = enclosure_url

    # Dedup
    for item in channel.findall("item"):
        guid = item.findtext("guid", default="")
        enc = item.find("enclosure")
        enc_url = enc.get("url") if enc is not None else ""
        if guid == guid_val or enc_url == enclosure_url:
            print(" >> 📡 RSS: Episode already exists; skipping RSS update.")
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

    items = channel.findall("item")
    if items:
        idx = list(channel).index(items[0])
        channel.insert(idx, item)
    else:
        channel.append(item)

    items = channel.findall("item")
    if len(items) > MAX_RSS_ITEMS:
        for old in items[MAX_RSS_ITEMS:]:
            channel.remove(old)

    tree.write(RSS_FILE, encoding="UTF-8", xml_declaration=True)


# ============================================================
# 7) PRODUCE EPISODE
# ============================================================

def synthesize_tts(speaker: str, text: str, out_path: Path):
    with client_openai.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=CAST[speaker],
        input=text,
        response_format="mp3",
    ) as resp:
        resp.stream_to_file(out_path)

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

    # Generate TTS segments (fewer segments thanks to speaker block compaction)
    seg_paths: list[Path] = []
    seg_idx = 0

    for speaker, block in iter_speaker_blocks(full_script, max_chars=3200):
        for chunk in chunk_for_tts(block, limit=3900):
            if len(chunk) < 3:
                continue
            out_seg = AUDIO_DIR / f"{today_str}_seg_{seg_idx:04d}.mp3"
            synthesize_tts(speaker, chunk, out_seg)
            seg_paths.append(out_seg)
            seg_idx += 1

    if not seg_paths:
        raise RuntimeError("No TTS segments produced. Check script format or model output.")

    print(f" >> ✅ TTS COMPLETE: {len(seg_paths)} segments generated")

    # Build ordered list for stitching: intro -> (seg + silence) -> outro
    silence_mp3 = TMP_DIR / f"silence_{GAP_MS}ms.mp3"
    if not silence_mp3.exists():
        make_silence_mp3(silence_mp3, GAP_MS)

    ordered: list[Path] = []

    intro_clip = TMP_DIR / "intro_clip.mp3"
    if INTRO_MUSIC.exists():
        render_music_clip(INTRO_MUSIC, intro_clip, seconds=15, fade="out")
        ordered.append(intro_clip)
        ordered.append(silence_mp3)

    for i, seg in enumerate(seg_paths):
        ordered.append(seg)
        # add silence between spoken segments
        if i != len(seg_paths) - 1:
            ordered.append(silence_mp3)

    outro_clip = TMP_DIR / "outro_clip.mp3"
    if OUTRO_MUSIC.exists():
        ordered.append(silence_mp3)
        render_music_clip(OUTRO_MUSIC, outro_clip, seconds=10, fade="in")
        ordered.append(outro_clip)

    # Stitch with ffmpeg (reliable)
    print(" >> 🎚️  STITCHING (ffmpeg concat)...")
    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"
    stitch_audio_ffmpeg(ordered, outfile)

    minutes = get_duration_minutes(outfile)
    print(f" ✅ EPISODE COMPLETE: {outfile} ({minutes:.2f} minutes)")

    if minutes < MIN_EPISODE_MINUTES:
        raise RuntimeError(f"Episode too short ({minutes:.2f} min). Refusing to publish.")

    update_rss_feed(outfile, show_notes, episode_title)


if __name__ == "__main__":
    produce_episode()
