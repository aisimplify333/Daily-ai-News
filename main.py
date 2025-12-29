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

# SAFETY CHECK: Clean start
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
SPONSORS_FILE = BASE_DIR / "sponsors.json"

# THE CAST
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",   # Warm, energetic
    "RUFUS": "fable",  # British, cynical
    "SPONSOR 1": "onyx",
    "SPONSOR 2": "nova",
    "SPONSOR 3": "onyx",
    "SPONSOR": "onyx"
}

# RUFUS LOCATIONS
RUFUS_LOCATIONS = [
    "on the trading floor in London",
    "live from Wall Street",
    "at the regulator's office in Brussels",
    "monitoring the markets in Tokyo",
    "in the server rooms in Silicon Valley",
    "tracking capital flows in Hong Kong"
]

# FEEDS (High Quality)
FEED_SOURCES = {
    "ALEX_TECH": [
        "https://www.theverge.com/rss/index.xml",
        "https://www.cnbc.com/id/19854910/device/rss/rss.html",
        "https://feeds.wired.com/wired/index",
        "https://arstechnica.com/feed/"
    ],
    "JAMIE_ETHICS": [
        "https://www.humanetech.com/feed",
        "https://www.404media.co/rss/", 
        "https://www.reddit.com/r/OpenAI/top/.rss" 
    ],
    "RUFUS_INTEL": [
        "https://techcrunch.com/category/venture/feed/",
        "https://www.bloomberg.com/feeds/sitemap_news.xml",
        "http://feeds.feedburner.com/avc"
    ]
}

# --- 2. INTELLIGENCE GATHERING (SMART FILTERING) ---
def deep_search_fallback(persona, query):
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR {persona} ({query})...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} {datetime.date.today()}", max_results=3)
        for r in search_results: results.append(f"BREAKING: {r['title']} - {r['body']}")
    except: pass
    return results

def is_news_worthy(title):
    """Filters out reviews, deals, and irrelevant junk."""
    junk_words = ["review", "deal", "sale", "best", "monitor", "tv", "headphones", "game", "controller"]
    title_lower = title.lower()
    for word in junk_words:
        if word in title_lower:
            return False
    return True

def gather_intel():
    print(" >> 📡 GATHERING GLOBAL INTELLIGENCE (Filtering Junk)...")
    intel = {"tech": [], "ethics": [], "ledger": []}
    
    # Alex (Tech Giants - Filtered)
    for url in FEED_SOURCES["ALEX_TECH"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_news_worthy(entry.title):
                    intel["tech"].append(entry.title)
                    if len(intel["tech"]) >= 2: break
            if len(intel["tech"]) >= 2: break
        except: pass
    if len(intel["tech"]) < 2: intel["tech"] += deep_search_fallback("ALEX", "OpenAI Google Apple leaks")

    # Jamie (Ethics)
    for url in FEED_SOURCES["JAMIE_ETHICS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]: 
                if is_news_worthy(entry.title): intel["ethics"].append(entry.title)
        except: pass
    if len(intel["ethics"]) < 2: intel["ethics"] += deep_search_fallback("JAMIE", "AI lawsuits data privacy scandal")

    # Rufus (Money)
    for url in FEED_SOURCES["RUFUS_INTEL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]: 
                if is_news_worthy(entry.title): intel["ledger"].append(entry.title)
        except: pass
    if len(intel["ledger"]) < 2: intel["ledger"] += deep_search_fallback("RUFUS", "VC funding IPO market crash")
    
    return intel

def get_sponsors():
    defaults = [
        {"name": "The AI Edge", "copy": "Join the newsletter.", "url": "#"}, 
        {"name": "TechStart", "copy": "Learn code.", "url": "#"}, 
        {"name": "CloudScale", "copy": "Deploy AI.", "url": "#"}
    ]
    if SPONSORS_FILE.exists():
        try:
            with open(SPONSORS_FILE, "r") as f: return (json.load(f) * 3)[:3]
        except: pass
    return defaults

# --- 3. THE WRITER (CONTEXT AWARE ASSEMBLY LINE) ---
def generate_segment(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content

def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (Context-Aware)...")
    today = datetime.date.today()
    readable_date = today.strftime("%A the %dth of %B")
    
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    tech = intel['tech'] if intel['tech'] else ["AI Breakthroughs"]
    ledger = intel['ledger'] if intel['ledger'] else ["Global Regulation"]
    
    # Identify the MAIN STORY for consistency
    main_story = tech[0]

    base_instructions = """
    You are writing a segment for a PROFESSIONAL RADIO SHOW.
    RULES:
    1. NO CORPORATE JARGON.
    2. USE CONCRETE EXAMPLES.
    3. FORMAT STRICTLY: "SPEAKER: Dialogue"
    """

    full_script = ""

    # --- PART 1: INTRO & HEADLINES ---
    print(f"    ...Generating Part 1 (Main Story: {main_story})")
    prompt_1 = f"""
    {base_instructions}
    Write PART 1 (5 Minutes of dialogue).
    
    STRUCTURE:
    [COLD OPEN] ALEX: A shocking fact about {main_story}.
    [INTRO] ALEX: "Welcome to the AI Edge. I'm Alex, with Jamie." JAMIE: Greetings. ALEX: "It's {readable_date}. Plan: Headlines, Deep Dive on {main_story}, then Rufus." 
    [AD 1] ALEX: "First, a word from {sponsors[0]['name']}." SPONSOR 1: "{sponsors[0]['copy']}"
    [HEADLINES] ALEX & JAMIE: 
    - Discuss {main_story} in depth.
    - Jamie asks 3 specific questions about the ethics/danger.
    - Alex defends the tech.
    - Discuss {tech[1]} briefly.
    """
    full_script += generate_segment(prompt_1) + "\n"

    # --- PART 2: THE DEEP DIVE ---
    print("    ...Generating Part 2 (The Deep Dive)")
    prompt_2 = f"""
    {base_instructions}
    Write PART 2 (8 Minutes of dialogue).
    CONTEXT: Continuing the discussion on {main_story}.
    
    STRUCTURE:
    [TOOLBOX SEGMENT] ALEX: "Now, let's open the Toolbox." 
    - Detailed breakdown of a tool related to {main_story}.
    - Discuss pricing, features, and specific use cases (e.g. "It saves coders 5 hours").
    - Jamie pushes back on the cost or complexity.
    - Alex gives a rebuttal.
    - JAMIE: "Supported by {sponsors[1]['name']}." SPONSOR 2: "{sponsors[1]['copy']}"
    """
    full_script += generate_segment(prompt_2) + "\n"

    # --- PART 3: RUFUS & OUTRO ---
    print("    ...Generating Part 3 (Rufus & Outro)")
    prompt_3 = f"""
    {base_instructions}
    Write PART 3 (5 Minutes of dialogue).
    CONTEXT: Moving from Tech to Money.
    
    STRUCTURE:
    [LEDGER SEGMENT] ALEX: "Now, let's go live to Rufus who is standing by {rufus_loc}. Rufus, what is the money saying about {main_story} and {ledger[0]}?"
    - RUFUS (British, Cynical): Analyze the financial impact of {main_story}. Then discuss {ledger[0]}.
    - Rufus insults the naivety of Silicon Valley.
    [FORUM] Short debate between all three.
    [OUTRO] ALEX: "Subscribe." SPONSOR 3: "{sponsors[2]['copy']}"
    """
    full_script += generate_segment(prompt_3)

    return full_script

# --- 4. SEO ---
def generate_seo_package(script, sponsors):
    print(" >> 🚀 GENERATING SEO METADATA...")
    prompt = f"""Generate JSON: {{ "title": "Viral Title", "show_notes": "Notes", "hashtags": "#Tags" }} for script: {script[:2000]}"""
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": prompt}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

# --- 5. PRODUCTION ---
def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors()
    script = write_script(intel, sponsors)
    
    # DEBUG: Save script
    with open(BASE_DIR / "debug_script.txt", "w") as f: f.write(script)
    print(f"    ℹ️ Script generated ({len(script)} chars). Saved to debug_script.txt")

    seo_data = generate_seo_package(script, sponsors)
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(f"{seo_data['title']}\n\n{seo_data['hashtags']}")
    with open(BASE_DIR / "show_notes.txt", "w") as f: f.write(seo_data['show_notes'])

    print(" >> 🎙️  RECORDING HD LINES...")
    segments = []
    lines = script.split('\n')
    
    for i, line in enumerate(lines):
        if ":" in line:
            parts = line.split(":", 1)
            raw_speaker = parts[0].strip().upper()
            speaker = re.sub(r'[^A-Z0-9 ]', '', raw_speaker).strip() 
            text = parts[1].strip()
            
            if speaker in CAST and text:
                voice = CAST[speaker]
                # SPEED TUNING
                speed = 1.0 if (speaker == "JAMIE" or speaker == "SPONSOR 2") else (1.05 if "ALEX" in speaker or "SPONSOR" in speaker else 1.0)
                
                try:
                    resp = client.audio.speech.create(model="tts-1-hd", voice=voice, input=text, speed=speed)
                    path = AUDIO_DIR / f"line_{i:03d}_{speaker}.mp3"
                    resp.stream_to_file(path)
                    seg = AudioSegment.from_mp3(path)
                    seg = effects.strip_silence(seg, silence_thresh=-45, padding=10)
                    segments.append((speaker, seg))
                    print(f"    ✔ Recorded: {speaker} ({len(text)} chars)")
                except Exception as e:
                    print(f"    ❌ FAILED line {i}: {e}")
            else:
                if len(text) > 5: print(f"    ⚠️ Skipped (Unknown Speaker '{speaker}'): {line[:30]}...")

    print(" >> 🎚️  MIXING EPISODE...")
    if not segments:
        print(" ❌ CRITICAL: No audio segments recorded. Check debug_script.txt.")
        return

    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(1000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(1000)
    sfx = AudioSegment.from_mp3(TRANSITION_SFX) - 6 if TRANSITION_SFX.exists() else AudioSegment.silent(500)

    if segments:
        full_audio += segments[0][1] # Cold open
        segments.pop(0)

    # Intro Fade Logic
    full_audio += intro[:10000].fade_out(3000)
    full_audio += AudioSegment.silent(duration=1000)

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
