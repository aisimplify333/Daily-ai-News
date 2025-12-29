import os
import json
import random
import datetime
import feedparser
import re
import shutil
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment, effects
from duckduckgo_search import DDGS

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Paths
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

# Clean Start
if AUDIO_DIR.exists():
    if not AUDIO_DIR.is_dir():
        try: os.remove(AUDIO_DIR)
        except: pass
        AUDIO_DIR.mkdir(exist_ok=True)
else:
    AUDIO_DIR.mkdir(exist_ok=True)

# Assets
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"
TRANSITION_SFX = BASE_DIR / "transition.mp3"

# THE CAST
CAST = {
    "ALEX": "onyx",    # The Anchor: 2026 Futurist.
    "JAMIE": "nova",   # The Humanist: Skeptical of the machine age.
    "RUFUS": "fable",  # The Investor: The money behind the curtain.
    "SPONSOR 1": "onyx",
    "SPONSOR 2": "nova",
    "SPONSOR 3": "onyx",
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "from the trading floor in Singapore",
    "analyzing pre-market derivatives in Chicago",
    "tracking sovereign wealth funds in Riyadh",
    "reviewing chip fabrication yields in Taiwan",
    "monitoring energy futures in London"
]

# --- 2. "FUTURE & HARD NEWS" FEEDS ---
FEED_SOURCES = {
    "TITANS": [
        "https://openai.com/blog/rss.xml",
        "https://blogs.microsoft.com/ai/feed/",
        "https://news.google.com/rss/search?q=Nvidia+Blackwell+Architecture&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=TSMC+3nm+Yields&hl=en-US&gl=US&ceid=US:en"
    ],
    "RESEARCH_2026": [
        "https://rss.arxiv.org/rss/cs.AI", # Raw Research Papers
        "https://www.mit.edu/news/rss/topic/artificial-intelligence",
        "https://news.google.com/rss/search?q=Agentic+AI+2026+Trends&hl=en-US&gl=US&ceid=US:en"
    ],
    "INFRASTRUCTURE": [
        "https://www.datacenterdynamics.com/rss/",
        "https://www.semianalysis.com/feed"
    ],
    "MONEY": [
        "https://finance.yahoo.com/news/rssindex",
        "https://news.google.com/rss/search?q=AI+CapEx+Spending+2025&hl=en-US&gl=US&ceid=US:en"
    ]
}

# --- 3. INTELLIGENCE GATHERING ---
def deep_search_fallback(query):
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR DATA: {query}...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} forecast 2026 specs {datetime.date.today()}", max_results=3)
        for r in search_results: results.append(f"DATA POINT: {r['title']} - {r['body']}")
    except: pass
    return results

def is_hard_news(title):
    title_lower = title.lower()
    fluff = ["how to", "guide", "best of", "gift", "deal", "sale", "review", "monitor", "game", "sauron"]
    for word in fluff:
        if word in title_lower: return False
    return True

def gather_intel():
    print(" >> 📡 GATHERING 2026 INTEL...")
    intel = {"titans": [], "future": [], "infra": [], "money": []}
    
    # 1. Titans
    for url in FEED_SOURCES["TITANS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    intel["titans"].append(entry.title)
                    if len(intel["titans"]) >= 2: break
        except: pass
    if len(intel["titans"]) < 1: intel["titans"] += deep_search_fallback("Nvidia Blackwell B200 Specs")

    # 2. Future (Research/2026)
    for url in FEED_SOURCES["RESEARCH_2026"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    intel["future"].append(entry.title)
                    if len(intel["future"]) >= 2: break
        except: pass
    if len(intel["future"]) < 1: intel["future"] += deep_search_fallback("Agentic AI Agents 2026 Prediction")

    # 3. Infrastructure
    for url in FEED_SOURCES["INFRASTRUCTURE"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    intel["infra"].append(entry.title)
                    if len(intel["infra"]) >= 2: break
        except: pass

    # 4. Money
    for url in FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title and is_hard_news(entry.title):
                    intel["money"].append(entry.title)
                    if len(intel["money"]) >= 2: break
        except: pass
    
    return intel

def get_sponsors():
    return [
        {"name": "ElevenLabs", "copy": "The standard for AI voice. If you need to scale your content globally, you need ElevenLabs. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Stop drowning in tabs. Notion AI organizes your business, writes your docs, and cleans your workflow. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. The daily newsletter that breaks down Wall Street without the jargon. Sign up at MorningBrew.com."}
    ]

# --- 4. THE WRITER (PARAGRAPH PROTOCOL) ---
def generate_segment_with_retry(system_prompt, retries=2):
    for attempt in range(retries):
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.75,
            messages=[{"role": "system", "content": system_prompt}]
        )
        content = response.choices[0].message.content.strip()
        if content[-1] in ['.', '!', '?', '"']:
            return content
        else:
            print("    ⚠️ Cut-off detected. Retrying...")
    return content + "."

def clean_text_for_audio(text):
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text) 
    text = text.replace('"', '').replace("'", "")
    text = text.replace("...", ".") 
    text = text.replace("AI", "A.I.")
    text = text.replace("listening to AI", "listening to the future")
    return text.strip()

def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (Target: 22 Mins / 5 Segments)...")
    today = datetime.date.today()
    readable_date = today.strftime("%A the %dth of %B")
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    titan_story = intel['titans'][0] if intel['titans'] else "Nvidia's Dominance"
    future_story = intel['future'][0] if intel['future'] else "The Rise of Agents"
    infra_story = intel['infra'][0] if intel['infra'] else "The Energy Crisis"
    money_story = intel['money'][0] if intel['money'] else "VC Capital Deployment"
    
    base_instructions = """
    You are writing a BROADCAST NEWS PODCAST (NPR/Bloomberg Style).
    
    CHARACTERS:
    - ALEX (Host): Serious, Fast, Obsessed with HARD DATA (Specs, Dates, Dollars).
    - JAMIE (Co-Host): Skeptical but Smart. Asks: "What does this mean for 2026?"
    - RUFUS (Analyst): Cynical. Only cares about Profit.
    
    RULES:
    1. WRITE LENGTH: Use exactly 12 PARAGRAPHS per segment. DO NOT BE BRIEF.
    2. USE DATA: Invent plausible but specific data if needed (e.g. "4.5 Gigawatts", "$300 Billion CapEx").
    3. NO META: Never say "I am an AI".
    """

    full_script = ""

    # --- SEGMENT 1: THE HEADLINES (TITANS) ---
    print(f"    ...Part 1: The Titans ({titan_story})")
    prompt_1 = f"""
    {base_instructions}
    Write PART 1 (12 Paragraphs).
    [COLD OPEN] ALEX: A shocking statistic about {titan_story}.
    [INTRO] ALEX: "This is the AI Edge. I'm Alex." JAMIE: "I'm Jamie." ALEX: "It's {readable_date}. Today: {titan_story}, The 2026 Outlook, and The Money."
    [AD] ALEX: Read {sponsors[0]['name']} copy.
    [NEWS] ALEX: Deep dive into {titan_story}. 
    - Quote specific specs (e.g. "72-core Grace CPU").
    - JAMIE: "Alex, this is impressive, but is it overkill?"
    - ALEX: "Not for what's coming in 2026."
    """
    full_script += generate_segment_with_retry(prompt_1) + "\n"

    # --- SEGMENT 2: INFRASTRUCTURE ---
    print(f"    ...Part 2: The Iron ({infra_story})")
    prompt_2 = f"""
    {base_instructions}
    Write PART 2 (12 Paragraphs).
    [SEGMENT] ALEX: "Let's talk Iron. The physical constraints."
    - Discuss {infra_story}. 
    - Focus on ENERGY (Nuclear, Gas) and CHIPS (CoWoS packaging).
    - JAMIE: "We are building a machine god that eats electricity."
    - ALEX: "And we are running out of copper."
    [AD] JAMIE: Read {sponsors[1]['name']} copy.
    """
    full_script += generate_segment_with_retry(prompt_2) + "\n"

    # --- SEGMENT 3: THE FUTURIST (2026 PREDICTIONS) ---
    print(f"    ...Part 3: 2026 Prediction ({future_story})")
    prompt_3 = f"""
    {base_instructions}
    Write PART 3 (12 Paragraphs).
    [SEGMENT] ALEX: "Let's look forward. 2026. The Year of the Agent."
    - Discuss {future_story}.
    - Explain "Agentic AI" (AI that *does* things, not just talks).
    - ALEX: "By 2026, you won't book a flight. Your agent will negotiate with the airline's agent."
    - JAMIE: "That sounds terrifyingly efficient. What happens to the service economy?"
    """
    full_script += generate_segment_with_retry(prompt_3) + "\n"

    # --- SEGMENT 4: THE LEDGER (RUFUS) ---
    print(f"    ...Part 4: The Money ({money_story})")
    prompt_4 = f"""
    {base_instructions}
    Write PART 4 (12 Paragraphs).
    [SEGMENT] ALEX: "Let's go to Rufus, live {rufus_loc}."
    - RUFUS: "Cheers." Analyze {money_story}.
    - Focus on "CapEx" (Capital Expenditure). Are they spending too much?
    - RUFUS: "The market is pricing in perfection. If 2026 delays, this crashes."
    [OUTRO] ALEX: "Subscribe." SPONSOR 3: Copy.
    """
    full_script += generate_segment_with_retry(prompt_4)

    return full_script

# --- 5. PRODUCTION ---
def generate_seo_package(script, sponsors):
    print(" >> 🚀 GENERATING SEO METADATA...")
    prompt = f"""Generate JSON: {{ "title": "Viral Title", "show_notes": "Notes", "hashtags": "#Tags" }} for script: {script[:2000]}"""
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": prompt}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors() 
    script = write_script(intel, sponsors)
    
    with open(BASE_DIR / "debug_script.txt", "w") as f: f.write(script)
    seo_data = generate_seo_package(script, sponsors)
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(f"{seo_data['title']}\n\n{seo_data['hashtags']}")
    
    print(" >> 🎙️  RECORDING HD LINES...")
    segments = []
    lines = script.split('\n')
    
    for i, line in enumerate(lines):
        if ":" in line:
            parts = line.split(":", 1)
            raw_speaker = parts[0].strip().upper()
            speaker = re.sub(r'[^A-Z0-9 ]', '', raw_speaker).strip() 
            text = parts[1].strip()
            text = clean_text_for_audio(text)
            
            if speaker in CAST and text:
                voice = CAST[speaker]
                try:
                    resp = client.audio.speech.create(model="tts-1-hd", voice=voice, input=text, speed=1.0)
                    path = AUDIO_DIR / f"line_{i:03d}_{speaker}.mp3"
                    resp.stream_to_file(path)
                    seg = AudioSegment.from_mp3(path)
                    seg = effects.strip_silence(seg, silence_thresh=-50, padding=50) 
                    segments.append((speaker, seg))
                    print(f"    ✔ Recorded: {speaker} ({len(text)} chars)")
                except Exception as e:
                    print(f"    ❌ FAILED line {i}: {e}")

    print(" >> 🎚️  MIXING EPISODE...")
    if not segments: return

    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(1000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(1000)
    sfx = AudioSegment.from_mp3(TRANSITION_SFX) - 6 if TRANSITION_SFX.exists() else AudioSegment.silent(500)

    # 1. COLD OPEN FIRST (NO MUSIC)
    if segments:
        cold_open = segments[0][1]
        full_audio += cold_open
        segments.pop(0)

    # 2. THEN INTRO MUSIC (FADE IN/OUT)
    if INTRO_MUSIC.exists():
        # Play 8 seconds of music, fade out over 2s
        music_bed = intro[:8000].fade_out(2000)
        full_audio += music_bed

    # 3. REST OF THE SHOW
    last_speaker = "UNKNOWN"
    for speaker, clip in segments:
        if speaker == "RUFUS" and last_speaker != "RUFUS": full_audio += sfx
        if body_audio := full_audio: body_audio += AudioSegment.silent(duration=400)
        full_audio += clip
        last_speaker = speaker

    full_audio += outro[:10000].fade_in(1000)
    
    outfile = AUDIO_DIR / f"podcast_{datetime.date.today()}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    meta = {"file": str(outfile), "title": seo_data['title'], "description": seo_data['show_notes'], "tags": seo_data['hashtags']}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)
    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
