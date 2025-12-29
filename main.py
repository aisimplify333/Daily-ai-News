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
    "ALEX": "onyx",    # The Anchor. Punchy. Headlines.
    "JAMIE": "nova",   # The Analyst. Adds context/humanity.
    "RUFUS": "fable",  # The Money. Fast, cynical.
    "SPONSOR 1": "onyx",
    "SPONSOR 2": "nova",
    "SPONSOR 3": "onyx",
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "on the trading floor in Tokyo",
    "tracking pre-market movers in London",
    "analyzing energy grid spikes in Texas",
    "reviewing chip shipments in Taiwan",
    "monitoring sovereign wealth funds in Dubai"
]

# --- 2. HARD NEWS FEEDS ---
FEED_SOURCES = {
    "TITANS": [
        "https://openai.com/blog/rss.xml",
        "https://blogs.microsoft.com/ai/feed/",
        "https://news.google.com/rss/search?q=Nvidia+Stock+Price&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=OpenAI+Release&hl=en-US&gl=US&ceid=US:en"
    ],
    "INFRASTRUCTURE": [
        "https://www.datacenterdynamics.com/rss/",
        "https://www.semianalysis.com/feed",
        "https://news.google.com/rss/search?q=TSMC+Production+Yields&hl=en-US&gl=US&ceid=US:en"
    ],
    "MONEY": [
        "https://finance.yahoo.com/news/rssindex",
        "https://news.google.com/rss/search?q=AI+VC+Funding+Rounds&hl=en-US&gl=US&ceid=US:en"
    ],
    "GLOBAL": [
        "https://restofworld.org/feed/",
        "https://news.google.com/rss/search?q=China+AI+Regulation&hl=en-US&gl=US&ceid=US:en"
    ]
}

# --- 3. INTELLIGENCE GATHERING ---
def deep_search_fallback(query):
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR DATA: {query}...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} 2025 news", max_results=3)
        for r in search_results: results.append(f"STORY: {r['title']} - {r['body']}")
    except: pass
    return results

def is_hard_news(title):
    title_lower = title.lower()
    fluff = ["how to", "guide", "best of", "gift", "deal", "review", "monitor", "game", "sauron"]
    for word in fluff:
        if word in title_lower: return False
    return True

def gather_intel():
    print(" >> 📡 GATHERING THE RUNDOWN...")
    intel = {"headlines": [], "deep_dive": [], "money": []}
    
    # 1. Get 5 Top Headlines (Titans + Global)
    all_stories = []
    for url in FEED_SOURCES["TITANS"] + FEED_SOURCES["GLOBAL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    all_stories.append(entry.title)
        except: pass
    
    if len(all_stories) < 5:
        all_stories += deep_search_fallback("Top AI News Stories Today")
    
    # Shuffle and pick 5 unique
    intel["headlines"] = list(set(all_stories))[:5]

    # 2. Deep Dive (Infra)
    for url in FEED_SOURCES["INFRASTRUCTURE"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    intel["deep_dive"].append(entry.title)
        except: pass
    if not intel["deep_dive"]: intel["deep_dive"] += deep_search_fallback("AI Data Center Power Crisis")

    # 3. Money
    for url in FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title:
                    intel["money"].append(entry.title)
        except: pass
    
    return intel

def get_sponsors():
    return [
        {"name": "ElevenLabs", "copy": "The standard for AI voice. If you need to scale your content globally, you need ElevenLabs. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Stop drowning in tabs. Notion AI organizes your business, writes your docs, and cleans your workflow. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. The daily newsletter that breaks down Wall Street without the jargon. Sign up at MorningBrew.com."}
    ]

# --- 4. THE WRITER (SEGMENTED) ---
def generate_segment(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.7,
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content.strip()

def clean_text_for_audio(text):
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text) 
    text = text.replace('"', '').replace("'", "")
    text = text.replace("...", ".") 
    text = text.replace("AI", "A.I.")
    return text.strip()

def write_script(intel, sponsors, rufus_loc):
    print(" >> ✍️  WRITING SCRIPT (Strict News Format)...")
    today = datetime.date.today()
    readable_date = today.strftime("%A, %B %d")
    
    # Unpack Intel
    headlines_text = "\n".join([f"- {h}" for h in intel['headlines']])
    deep_story = intel['deep_dive'][0] if intel['deep_dive'] else "Global Compute Shortage"
    money_story = intel['money'][0] if intel['money'] else "Tech Stocks Rally"

    script_parts = []

    # --- PART 1: THE COLD OPEN & RUNDOWN ---
    print("    ...Writing The Rundown (Top 5)")
    prompt_1 = f"""
    You are Alex, a hard-hitting news anchor.
    DATE: {readable_date}.
    
    TASK 1: Write a COLD OPEN (1 sentence, shocking stat about {intel['headlines'][0]}).
    TASK 2: Write the INTRO & RUNDOWN.
    - Say: "I'm Alex, and this is the AI Edge. Here are the top 5 stories shaping our world."
    - List these 5 stories exactly: {headlines_text}
    - Keep it punchy. "Story 1: [Detail]. Story 2: [Detail]."
    - End with: "But first, a word from {sponsors[0]['name']}."
    AD COPY: "{sponsors[0]['copy']}"
    """
    script_parts.append(generate_segment(prompt_1))

    # --- PART 2: THE DEEP DIVE ---
    print(f"    ...Writing Deep Dive ({deep_story})")
    prompt_2 = f"""
    Characters: ALEX (Host) & JAMIE (Analyst).
    TOPIC: {deep_story}.
    
    INSTRUCTIONS:
    - Alex presents the hard facts (Specs, Megawatts, Costs).
    - Jamie analyzes the impact (Human cost, 2026 predictions).
    - MENTION SPECIFIC COMPANIES (Nvidia, TSMC, Microsoft).
    - Length: 10 Paragraphs of dialogue.
    - End with JAMIE reading ad for {sponsors[1]['name']}: "{sponsors[1]['copy']}"
    """
    script_parts.append(generate_segment(prompt_2))

    # --- PART 3: THE TRANSITION (HARDCODED IN PYTHON, BUT WE NEED TEXT FOR AUDIO) ---
    # We will insert the text directly into the loop, but we need the script text for SEO.
    script_parts.append(f"ALEX: And now, let's check the markets. We go live to Rufus, who is standing by {rufus_loc}. Rufus, what is the smart money doing?")

    # --- PART 4: THE MONEY (RUFUS) ---
    print(f"    ...Writing The Money ({money_story})")
    prompt_4 = f"""
    Character: RUFUS (Cynical Investor, British).
    LOCATION: {rufus_loc}.
    TOPIC: {money_story}.
    
    INSTRUCTIONS:
    - Start with: "Thank you, Alex."
    - Analyze the financial news. Be ruthless.
    - Mention Stock Tickers (NVDA, MSFT).
    - Predict the next crash or boom.
    - Length: 8 Paragraphs.
    - End with: "Back to you."
    - OUTRO: ALEX signs off. AD for {sponsors[2]['name']}: "{sponsors[2]['copy']}"
    """
    script_parts.append(generate_segment(prompt_4))

    return "\n".join(script_parts)

# --- 5. PRODUCTION ---
def produce_episode():
    # Setup
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    intel = gather_intel()
    sponsors = get_sponsors()
    
    # Write
    full_script = write_script(intel, sponsors, rufus_loc)
    
    # Save text
    with open(BASE_DIR / "debug_script.txt", "w") as f: f.write(full_script)
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(f"AI Edge: {intel['headlines'][0]}\n\n#AI #TechNews")

    print(" >> 🎙️  RECORDING HD LINES...")
    segments = []
    
    # Split by newlines to process line-by-line
    lines = full_script.split('\n')
    
    for i, line in enumerate(lines):
        if ":" in line:
            parts = line.split(":", 1)
            raw_speaker = parts[0].strip().upper()
            text = parts[1].strip()
            text = clean_text_for_audio(text)
            
            # Map Speaker to Voice
            speaker = "ALEX"
            if "JAMIE" in raw_speaker: speaker = "JAMIE"
            elif "RUFUS" in raw_speaker: speaker = "RUFUS"
            elif "SPONSOR" in raw_speaker: speaker = "ALEX" # Fallback
            
            if text:
                voice = CAST.get(speaker, "onyx")
                try:
                    # Generate Audio
                    resp = client.audio.speech.create(model="tts-1-hd", voice=voice, input=text, speed=1.0)
                    path = AUDIO_DIR / f"line_{i:03d}_{speaker}.mp3"
                    resp.stream_to_file(path)
                    
                    # Silence Trimming
                    seg = AudioSegment.from_mp3(path)
                    seg = effects.strip_silence(seg, silence_thresh=-50, padding=50)
                    segments.append((speaker, seg))
                    print(f"    ✔ {speaker}: {text[:30]}...")
                except Exception as e:
                    print(f"    ❌ Error line {i}: {e}")

    print(" >> 🎚️  MIXING EPISODE...")
    full_audio = AudioSegment.empty()
    intro_music = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(5000)
    outro_music = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(5000)
    sfx = AudioSegment.from_mp3(TRANSITION_SFX) - 3 if TRANSITION_SFX.exists() else AudioSegment.silent(1000)

    # 1. COLD OPEN (First line only)
    if segments:
        full_audio += segments[0][1]
        segments.pop(0)

    # 2. INTRO MUSIC DROP
    # Fade music in, play for 6s, fade out under speech
    full_audio += intro_music[:6000].fade_out(2000)

    # 3. MAIN SHOW LOOP
    last_speaker = "UNKNOWN"
    for speaker, clip in segments:
        # Insert SFX before Rufus
        if speaker == "RUFUS" and last_speaker != "RUFUS":
            full_audio += sfx
        
        # Natural Pause
        if len(full_audio) > 0: full_audio += AudioSegment.silent(duration=350)
        
        full_audio += clip
        last_speaker = speaker

    # 4. OUTRO
    full_audio += outro_music[:10000].fade_in(2000)
    
    outfile = AUDIO_DIR / f"podcast_{datetime.date.today()}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    # Metadata for Spotify
    meta = {"file": str(outfile), "title": f"The AI Edge: {intel['headlines'][0]}", "description": full_script[:500], "tags": "#AI #News"}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)
    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
