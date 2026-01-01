import os
import re
import json
import time
import uuid
import shutil
import subprocess
import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from pydub import AudioSegment
from openai import OpenAI

# Optional Gemini (safe import)
try:
    import google.generativeai as genai  # older gemini sdk
except Exception:
    genai = None

# ----------------------------
# CONFIG (Spotify/RSS identity)
# ----------------------------
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily AI News Drama: raw, human, high-stakes conversations about the future.",
    "author": "AI Simplify Media",
    "email": "aisimplifynewsfeed@gmail.com",
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
# Must match your Pages structure: https://<user>.github.io/<repo>/episode_audio/<file>
AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
)

PRIMARY_LLM = os.getenv("PRIMARY_LLM", "gemini").strip().lower()  # gemini | openai
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")

MIN_MINUTES = float(os.getenv("MIN_MINUTES", "25"))
MAX_MINUTES = float(os.getenv("MAX_MINUTES", "30"))
TARGET_MINUTES = float(os.getenv("TARGET_MINUTES", "28"))

CLEANUP_TEMP = os.getenv("CLEANUP_TEMP", "true").strip().lower() in ("1", "true", "yes")

# Voices (keep your existing mapping)
VOICE_MAP = {
    "ALEX": os.getenv("VOICE_ALEX", "onyx"),
    "JAMIE": os.getenv("VOICE_JAMIE", "nova"),
    "RUFUS": os.getenv("VOICE_RUFUS", "fable"),
}

# ----------------------------
# LLM CLIENTS
# ----------------------------
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

gemini_key = os.environ.get("GEMINI_API_KEY")
if genai and gemini_key:
    try:
        genai.configure(api_key=gemini_key)
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

def generate_text(prompt: str, temperature: float = 0.9, max_tokens: int = 5000) -> str:
    """
    Gemini primary, OpenAI backup. Never hardcodes a single Gemini model name.
    """
    # 1) Gemini attempt
    if PRIMARY_LLM == "gemini" and genai and gemini_key:
        # Try a short list of common models; if your SDK supports list_models you can expand.
        candidate_models = [
            os.getenv("GEMINI_MODEL", "").strip(),
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
        candidate_models = [m for m in candidate_models if m]

        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(model_name)
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
                _safe_print(f"    ⚠️ Gemini failed on {model_name}: {e}. Trying next...")
                continue

        _safe_print("    ⚠️ Gemini unavailable or quota/model failure. Falling back to OpenAI...")

    # 2) OpenAI fallback
    resp = openai_client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a top-tier podcast writer. Output must follow the requested format exactly."
                )
            },
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content.strip()

# ----------------------------
# NEWS INTEL (RSS primary, email optional backup)
# ----------------------------
GOOGLE_NEWS_RSS = [
    # Big, high-signal queries to feed the archetypes
    ("Frontier Models", "https://news.google.com/rss/search?q=(OpenAI%20OR%20Anthropic%20OR%20DeepMind)%20(model%20OR%20release%20OR%20launch)&hl=en-US&gl=US&ceid=US:en"),
    ("AI Money", "https://news.google.com/rss/search?q=(AI%20funding%20OR%20valuation%20OR%20IPO%20OR%20Nvidia%20OR%20chips)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Regulation", "https://news.google.com/rss/search?q=(AI%20regulation%20OR%20EU%20AI%20Act%20OR%20FTC%20OR%20copyright)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI Security", "https://news.google.com/rss/search?q=(AI%20jailbreak%20OR%20prompt%20injection%20OR%20security%20OR%20leak)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("AI in Work", "https://news.google.com/rss/search?q=(AI%20jobs%20OR%20automation%20OR%20productivity%20OR%20enterprise)%20when:1d&hl=en-US&gl=US&ceid=US:en"),
]

def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fetch_rss_items(max_per_feed: int = 8) -> List[Dict[str, str]]:
    import urllib.request
    import xml.etree.ElementTree as ET

    items: List[Dict[str, str]] = []
    for label, url in GOOGLE_NEWS_RSS:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                xml_data = r.read()
            root = ET.fromstring(xml_data)
            for it in root.findall("./channel/item")[:max_per_feed]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = _strip_html(it.findtext("description") or "")
                if title and link:
                    items.append({
                        "bucket": label,
                        "title": title,
                        "link": link,
                        "summary": desc[:400],
                    })
        except Exception as e:
            _safe_print(f"    ⚠️ RSS fetch failed ({label}): {e}")
            continue

    # De-dupe by title
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
    # placeholders (your file should replace these)
    return [
        {"name": "Sponsor One", "tagline": "Run faster. Think clearer.", "cta": "Link in show notes."},
        {"name": "Sponsor Two", "tagline": "Your edge, automated.", "cta": "Try it free today."},
        {"name": "Sponsor Three", "tagline": "Ship smarter.", "cta": "Join the waitlist."},
    ]

def pick_top_stories(intel_items: List[Dict[str, str]], n: int = 5) -> List[Dict[str, str]]:
    intel_compact = "\n".join(
        [f"- [{x['bucket']}] {x['title']} | {x['summary']} | {x['link']}" for x in intel_items[:40]]
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
"""
    raw = generate_text(prompt, temperature=0.4, max_tokens=1200)

    try:
        j = json.loads(raw)
        stories = j.get("stories", [])
        stories = [s for s in stories if isinstance(s, dict)]
        return stories[:n]
    except Exception:
        # fallback: just take first N
        return [
            {
                "headline": x["title"],
                "why_shocking": x["summary"],
                "angles": {"alex": "", "jamie": "", "rufus": ""},
                "source_url": x["link"],
            }
            for x in intel_items[:n]
        ]

# ----------------------------
# SCRIPT WRITING (5 segments)
# ----------------------------
def build_script(stories: List[Dict[str, str]], sponsors: List[Dict[str, str]], target_minutes: float) -> str:
    date_str = datetime.date.today().isoformat()

    # Sponsor slots
    sponsor_1 = sponsors[0] if len(sponsors) > 0 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_2 = sponsors[1] if len(sponsors) > 1 else {"name": "Sponsor", "tagline": "", "cta": ""}
    sponsor_3 = sponsors[2] if len(sponsors) > 2 else {"name": "Sponsor", "tagline": "", "cta": ""}

    story_block = "\n".join([f"{i+1}. {s['headline']} ({s.get('source_url','')})" for i, s in enumerate(stories)])

    prompt = f"""
You are writing a DAILY podcast episode called "The AI Edge".
It must sound like a raw, overheated conversation between THREE distinct personalities.
NO corporate speak. NO "let's dive in". NO "in today's landscape". They interrupt, argue, and get emotional.

Personas:
- ALEX (Host): Rogan energy + frantic curiosity. Drives pace. Summarizes the lineup after the welcome.
- JAMIE (Co-host): Bartlett vibe. Vulnerable, empathetic, human consequences.
- RUFUS (Analyst): cynical, money/regulatory edge. Cold, sharp. Sounds like he trades and reads filings.

FORMAT REQUIREMENTS (non-negotiable):
- Output MUST be dialogue lines only using EXACT labels: "ALEX:", "JAMIE:", "RUFUS:"
- You may include segment markers as lines starting with "###" (those will NOT be spoken).
- You may include "[MUSIC]" as a standalone line to indicate a music sting.
- Target total length: {target_minutes} minutes (aim 25–30). Roughly 4,400–5,200 words.
- Must cover FIVE stories.
- Must follow this 5-segment structure:

### SEGMENT 1 (Cold open + Welcome + Alex lineup summary)
Start mid-argument (hook). Then [MUSIC]. Then Alex welcomes, states today's 5 stories in rapid summary.

### SEGMENT 2 (Studio: Alex + Jamie only)
High chemistry, fast pacing, human stakes. No Rufus.

### SEGMENT 3 (On-location: Rufus money/reg angle)
Alex throws to Rufus. Rufus delivers the "native ad" seamlessly as insider advice.
Native Ad details (must feel like a tip, not a commercial):
Sponsor: {sponsor_1['name']}
Tagline: {sponsor_1.get('tagline','')}
CTA: {sponsor_1.get('cta','')}

### SEGMENT 4 (All three: dread/greed forecast + lightning round)
Cover remaining stories, sharp analogies, messy banter, interruptions.
Include a short host-read sponsor that is STILL woven-in (not a break):
Sponsor: {sponsor_2['name']} | {sponsor_2.get('tagline','')} | {sponsor_2.get('cta','')}

### SEGMENT 5 (Closing)
Alex closes. Jamie can land one empathetic hit. Rufus gives one cynical prophecy.
Include final micro sponsor tag woven as a joke/aside:
Sponsor: {sponsor_3['name']} | {sponsor_3.get('tagline','')} | {sponsor_3.get('cta','')}

TODAY'S CANDIDATE STORIES:
{story_block}

Write the full episode now.
"""
    return generate_text(prompt, temperature=0.85, max_tokens=6500)

def estimate_minutes_from_text(script: str) -> float:
    words = len(re.findall(r"\b\w+\b", script))
    # conversational wpm: 150–175; choose 165 as middle
    return words / 165.0

# ----------------------------
# TTS + STITCHING
# ----------------------------
SPEAKER_RE = re.compile(r"^(ALEX|JAMIE|RUFUS)\s*:\s*(.+)$", re.IGNORECASE)

def iter_dialogue(script: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("###"):
            continue
        if line.strip().upper() == "[MUSIC]":
            out.append(("MUSIC", "[MUSIC]"))
            continue

        m = SPEAKER_RE.match(line)
        if not m:
            # ignore stage directions
            continue
        speaker = m.group(1).upper()
        text = m.group(2).strip()
        if text:
            out.append((speaker, text))
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
    # OpenAI TTS
    with openai_client.audio.speech.with_streaming_response.create(
        model=OPENAI_TTS_MODEL,
        voice=voice,
        input=text,
    ) as resp:
        resp.stream_to_file(str(out_path))

def stitch_with_ffmpeg(file_list: List[Path], out_path: Path):
    """
    Uses ffmpeg concat (re-encode) so thousands of segments won't crash memory.
    """
    concat_txt = out_path.parent / f"concat_{uuid.uuid4().hex}.txt"
    lines = [f"file '{p.as_posix()}'" for p in file_list]
    concat_txt.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)
    try:
        concat_txt.unlink()
    except Exception:
        pass

def produce_episode():
    today = datetime.date.today().isoformat()
    _safe_print(" >> 📰 GATHERING INTEL (RSS PRIMARY)...")
    intel = fetch_rss_items(max_per_feed=10)

    if not intel:
        _safe_print("    ⚠️ RSS empty. Optional email backup can be wired here (fetch_news.py). Using test items.")
        intel = [
            {"bucket": "Test", "title": "Test: AI model sparks market panic", "link": "https://example.com", "summary": "Simulation."}
        ]

    sponsors = load_sponsors()
    stories = pick_top_stories(intel, n=5)

    _safe_print(" >> ✍️ WRITING FULL EPISODE (5 segments)...")
    script = build_script(stories, sponsors, target_minutes=TARGET_MINUTES)

    est = estimate_minutes_from_text(script)
    _safe_print(f"    Estimated minutes (text): ~{est:.1f}")

    # If text estimate is short, auto-extend segment 4 before segment 5
    if est < MIN_MINUTES:
        missing = max(3.0, MIN_MINUTES - est + 1.5)  # cushion
        _safe_print(f"    ⚠️ Script likely short. Generating ~{missing:.1f} extra minutes for Segment 4...")
        extension_prompt = f"""
Add ~{missing:.1f} minutes of dialogue that belongs INSIDE SEGMENT 4 (before SEGMENT 5 closing).
Must be messy, fast, emotional. Cover implications and analogies. No corporate speak.
Return dialogue only with labels ALEX/JAMIE/RUFUS and include a line '### SEGMENT 4B' at top.
Stories:
{json.dumps(stories, indent=2)}
"""
        extension = generate_text(extension_prompt, temperature=0.85, max_tokens=2500)

        marker = "### SEGMENT 5"
        idx = script.find(marker)
        if idx != -1:
            script = script[:idx] + "\n\n" + extension.strip() + "\n\n" + script[idx:]
        else:
            script += "\n\n" + extension.strip()

    # Save script
    script_path = BASE_DIR / f"script_{today}.txt"
    script_path.write_text(script, encoding="utf-8")

    # Build temp segment folder
    run_tmp = TMP_AUDIO_DIR / today
    if run_tmp.exists():
        shutil.rmtree(run_tmp, ignore_errors=True)
    run_tmp.mkdir(parents=True, exist_ok=True)

    # Prepare intro/outro trimmed (optional)
    concat_files: List[Path] = []
    silence_path = run_tmp / "silence_150ms.mp3"
    AudioSegment.silent(duration=150).export(silence_path, format="mp3")

    if INTRO_PATH.exists():
        intro = AudioSegment.from_file(INTRO_PATH)
        intro = intro[:15000].fade_out(1200)
        intro_path = run_tmp / "intro_trim.mp3"
        intro.export(intro_path, format="mp3", bitrate="192k")
        concat_files.append(intro_path)

    # Generate speech segments
    _safe_print(" >> 🎙️ RECORDING (TTS)...")
    dialogue = iter_dialogue(script)
    seg_idx = 0

    for speaker, text in dialogue:
        if speaker == "MUSIC":
            # just a beat (silence) unless you add a sting file
            concat_files.append(silence_path)
            continue

        voice = VOICE_MAP.get(speaker, "onyx")
        for chunk in chunk_text(text):
            seg_idx += 1
            seg_path = run_tmp / f"{today}_seg_{seg_idx:04d}.mp3"
            tts_to_file(chunk, voice, seg_path)
            concat_files.append(seg_path)
            concat_files.append(silence_path)

    if OUTRO_PATH.exists():
        outro = AudioSegment.from_file(OUTRO_PATH)
        outro = outro[:12000].fade_in(800).fade_out(1200)
        outro_path = run_tmp / "outro_trim.mp3"
        outro.export(outro_path, format="mp3", bitrate="192k")
        concat_files.append(outro_path)

    # Stitch
    _safe_print(" >> 🎚️ STITCHING (ffmpeg concat)...")
    final_mp3 = AUDIO_DIR / f"podcast_{today}.mp3"
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found. MoviePy usually installs it; ensure ffmpeg is available in your runner.")
    stitch_with_ffmpeg(concat_files, final_mp3)

    # Verify duration
    final_audio = AudioSegment.from_mp3(final_mp3)
    minutes = len(final_audio) / 1000 / 60
    _safe_print(f" ✅ EPISODE COMPLETE: {final_mp3} ({minutes:.2f} minutes)")

    if minutes < MIN_MINUTES or minutes > MAX_MINUTES:
        raise RuntimeError(f"Episode length out of bounds ({minutes:.2f} min). Must be {MIN_MINUTES}-{MAX_MINUTES}.")

    # Create SEO/title/hashtags/show notes (kept simple, you can expand)
    top_headline = stories[0]["headline"] if stories else f"AI Edge — {today}"
    hashtags = "#AI #OpenAI #Anthropic #DeepMind #Nvidia #ARegulation #AISafety #TechNews"
    show_notes = "Top stories:\n" + "\n".join([f"- {s['headline']} ({s.get('source_url','')})" for s in stories]) + "\n\n" + hashtags

    (BASE_DIR / "viral_caption.txt").write_text(top_headline, encoding="utf-8")
    (BASE_DIR / "marketing.txt").write_text(show_notes, encoding="utf-8")

    meta = {
        "date": today,
        "title": top_headline,
        "minutes": round(minutes, 2),
        "audio_file": final_mp3.name,
        "audio_url": AUDIO_BASE_URL + final_mp3.name,
        "stories": stories,
    }
    (BASE_DIR / "episode_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Update feed.xml (preserve history)
    update_feed_xml(meta)

    # Cleanup temp artifacts so you never get 300+ segments in episode_audio again
    if CLEANUP_TEMP:
        shutil.rmtree(run_tmp, ignore_errors=True)

def update_feed_xml(meta: Dict):
    import xml.etree.ElementTree as ET

    audio_url = meta["audio_url"]
    audio_file = meta["audio_file"]
    title = meta["title"]
    guid = f"{audio_file}-{meta['date']}"

    # Load existing feed or create new
    if FEED_XML_PATH.exists():
        tree = ET.parse(FEED_XML_PATH)
        rss = tree.getroot()
    else:
        rss = ET.Element("rss", version="2.0")
        rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
        tree = ET.ElementTree(rss)
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
        ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
        ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
        ET.SubElement(channel, "language").text = "en-us"
        ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = RSS_SETTINGS["author"]
        owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = RSS_SETTINGS["email"]
        img = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        img.set("href", RSS_SETTINGS["image"])

    channel = rss.find("channel")
    if channel is None:
        raise RuntimeError("feed.xml missing <channel>.")

    # New item
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "guid").text = guid
    ET.SubElement(item, "pubDate").text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    ET.SubElement(item, "description").text = (BASE_DIR / "marketing.txt").read_text(encoding="utf-8")[:5000]

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", audio_url)
    enclosure.set("type", "audio/mpeg")
    # length is optional; leaving blank is acceptable for many podcast clients
    enclosure.set("length", "0")

    # Prepend item to keep newest first
    existing_items = list(channel.findall("item"))
    for old in existing_items:
        channel.remove(old)
    channel.insert(0, item)
    for old in existing_items:
        channel.append(old)

    tree.write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    produce_episode()
