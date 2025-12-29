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

# SAFETY CHECK: Handle the folder/file conflict cleanly
if AUDIO_DIR.exists():
    if not AUDIO_DIR.is_dir():
        try:
            os.remove(AUDIO_DIR)
        except: pass
        AUDIO_DIR.mkdir(exist_ok=True)
else:
    AUDIO_DIR.mkdir(exist_ok=True)

# Assets
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"
TRANSITION_SFX = BASE_DIR / "transition.mp3"
SPONSORS_FILE = BASE_DIR / "sponsors.json"

# THE CAST (Updated to catch Sponsors)
CAST = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable",
    # MAPPING SPONSORS TO VOICES SO THEY DON'T GET SKIPPED
    "SPONSOR 1": "onyx",   # Alex reads Ad 1
    "SPONSOR 2": "nova",  # Jamie reads Ad 2
    "SPONSOR 3": "onyx",   # Alex reads Ad 3
    "SPONSOR": "onyx"      # Catch-all
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

# FEEDS
FEED_SOURCES = {
    "ALEX_TECH": ["https://techcrunch.com/feed/", "https://www.theverge.com/rss/index.xml", "https://arstechnica.com/feed/"],
    "JAMIE_ETHICS": ["https://www.humanetech.com/feed", "https://www.eff.org/rss/updates.xml", "https://www.reddit.com/r/ArtificialInteligence/top/.rss"],
    "RUFUS_INTEL": ["http://feeds.feedburner.com/avc", "https://saastr.com/feed/", "https://techcrunch.com/tag/policy/feed/"]
}

# --- 2. INTELLIGENCE GATHERING ---
def deep_search_fallback(persona, query):
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR {persona} ({query})...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} {datetime.date.today()}", max_results=3)
        for r in search_results: results.append(f"BREAKING: {r['title']} - {r['body']}")
    except: pass
    return results

def gather_intel():
    print(" >> 📡 GATHERING GLOBAL INTELLIGENCE...")
    intel = {"tech": [], "ethics": [], "ledger": []}
    # (Simplified feed logic)
    for url in FEED_SOURCES["ALEX_TECH"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: intel["tech"].append(entry.title)
        except: pass
    if len(intel["tech"]) < 2: intel["tech"] += deep_search_fallback("ALEX", "latest AI tools news")

    for url in FEED_SOURCES["JAMIE_ETHICS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: intel["ethics"].append(entry.title)
        except: pass
    if len(intel["ethics"]) < 2: intel["ethics"] += deep_search_fallback("JAMIE", "AI ethics labor lawsuits")

    for url in FEED_SOURCES["RUFUS_INTEL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: intel["ledger"].append(entry.title)
        except: pass
    if len(intel["ledger"]) < 2: intel["ledger"] += deep_search_fallback("RUFUS", "VC funding AI regulation antitrust")
    return intel

def get_sponsors():
    defaults = [
        {"name": "The AI Edge", "copy": "If you want to stay ahead of the curve, join 50,000 others reading The AI Edge newsletter. It's free, it's smart, and it's essential.", "url": "#"}, 
        {"name": "TechStart", "copy": "Stop watching from the sidelines. TechStart Academy can teach you Python in 30 days. Code your future today.", "url": "#"}, 
        {"name": "CloudScale", "copy": "Need to deploy agents fast? CloudScale is the only infrastructure built for the next generation of AI.", "url": "#"}
    ]
    if SPONSORS_FILE.exists():
        try:
            with open(SPONSORS_FILE, "r") as f: return (json.load(f) * 3)[:3]
        except: pass
    return defaults

# --- 3. THE WRITER (ANTI-FLUFF EDITION) ---
def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (Aiming for 3500+ Words for 20 mins)...")
    today = datetime.date.today()
    day_name = today.strftime("%A")
    readable_date = today.strftime("%A the %dth of %B")
    weekday_idx = today.weekday()
    
    cold_open_speaker = random.choice(["ALEX", "JAMIE", "RUFUS"])
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    tech = intel['tech'] if intel['tech'] else ["AI Breakthroughs"]
    ethics = intel['ethics'] if intel['ethics'] else ["Privacy Concerns"]
    ledger = intel['ledger'] if intel['ledger'] else ["Global Regulation"]
    shock_story = random.choice(tech + ledger)

    # *** THE ANTI-FLUFF INSTRUCTION BLOCK ***
    base_instructions = f"""
    You are a HUMAN radio host. NEVER mention you are an AI.
    
    CRITICAL QUALITY RULES:
    1. NO CORPORATE JARGON. Banned words: "ecosystem", "paradigm", "holistic", "leverage", "synergy", "landscape", "robust", "transformative".
    2. USE CONCRETE EXAMPLES. Instead of "This tool improves efficiency," say "This tool saves a coder 4 hours a day by writing the boilerplate."
    3. TELL STORIES. Use "For example...", "Picture this...", "Just yesterday I saw..."
    4. EXTREME VERBOSITY: We need a 25-MINUTE EPISODE. Go deep, but keep it grounded in reality.
    
    FORMAT STRICTLY: "SPEAKER: Dialogue" (No asterisks, no bolding).
    """

    if weekday_idx == 6: # Sunday
        print(f"    Mode: SUNDAY SHOWDOWN ({day_name})")
        prompt = f"""{base_instructions}
        FORMAT: SUNDAY DEBATE.
        [SEGMENT 1: COLD OPEN] (15s) {cold_open_speaker}: "{shock_story}"
        [SEGMENT 2: INTRO] ALEX: "Welcome to the AI Edge, it's {readable_date}. Today: The Showdown." 
        ALEX: "But first, a word from {sponsors[0]['name']}." SPONSOR 1: "{sponsors[0]['copy']}"
        [SEGMENT 3: MOTION] (1000 words) {tech[0]} vs {ethics[0]}. Debate deep. 
        JAMIE: "Support for this segment comes from {sponsors[1]['name']}." SPONSOR 2: "{sponsors[1]['copy']}"
        [SEGMENT 4: CROSS-EXAM] (1000 words) ALEX: "Now, let's go live to Rufus who is standing by {rufus_loc}. Rufus, what is the money saying?" Rufus dissects the argument.
        [SEGMENT 5: CLOSING] (500 words) Final takes.
        [SEGMENT 6: OUTRO] ALEX: "Subscribe." SPONSOR 3: "{sponsors[2]['copy']}"
        """
    elif weekday_idx == 5: # Saturday
        print(f"    Mode: WEEKEND WRAP ({day_name})")
        prompt = f"""{base_instructions}
        FORMAT: WEEKEND WRAP.
        [SEGMENT 1: COLD OPEN] (15s) {cold_open_speaker}: "{shock_story}"
        [SEGMENT 2: INTRO] ALEX: "Welcome to the Weekend Wrap." 
        ALEX: "A quick word from {sponsors[0]['name']}." SPONSOR 1: "{sponsors[0]['copy']}"
        [SEGMENT 3: RAPID FIRE] (1000 words) {tech[:3]}. 
        JAMIE: "Supported by {sponsors[1]['name']}." SPONSOR 2: "{sponsors[1]['copy']}"
        [SEGMENT 4: DEEP DIVE] (1000 words) {ethics[0]}. ALEX: "Let's check the markets. We go now to Rufus, live {rufus_loc}." Rufus analyzes.
        [SEGMENT 5: OUTRO] ALEX: "Subscribe." SPONSOR 3: "{sponsors[2]['copy']}"
        """
    else: # Mon-Fri
        print(f"    Mode: DAILY EDGE ({day_name})")
        prompt = f"""{base_instructions}
        FORMAT: DAILY EDGE.
        [SEGMENT 1: COLD OPEN] (15s) {cold_open_speaker}: "{shock_story}"
        [SEGMENT 2: INTRO] ALEX: "Welcome to the AI Edge, your daily home for AI unfiltered news. I'm Alex, with Jamie." JAMIE: "Hello, thank you for having me Alex." ALEX: "It's {readable_date}. Plan: Headlines, Toolbox on {tech[0]}, then Ledger from {rufus_loc}." 
        ALEX: "But first, a word from {sponsors[0]['name']}." SPONSOR 1: "{sponsors[0]['copy']}"
        [SEGMENT 3: HEADLINES] (1000 words) Banter on {tech[:2]}. Go deep.
        [SEGMENT 4: TOOLBOX] (1000 words) ALEX: "Now, let's open the Toolbox." Deep dive {tech[0]}. 
        JAMIE: "This deep dive is brought to you by {sponsors[1]['name']}." SPONSOR 2: "{sponsors[1]['copy']}"
        [SEGMENT 5: LEDGER] (800 words) ALEX: "Now, let's go live to Rufus who is standing by {rufus_loc}. Rufus, what is the money saying?" Rufus solo {ledger[:2]}.
        [SEGMENT 6: FORUM] (500 words) Debate.
        [SEGMENT 7: OUTRO] ALEX: "Subscribe." SPONSOR 3: "{sponsors[2]['copy']}"
        """

    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": prompt}])
    return response.choices[0].message.content

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
    
    # DEBUG: Save script to check format
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
            # Parse speaker, allowing spaces/numbers for SPONSOR 1
            speaker = re.sub(r'[^A-Z0-9 ]', '', raw_speaker).strip() 
            text = parts[1].strip()
            
            if speaker in CAST and text:
                voice = CAST[speaker]
                # SPEED TUNING
                speed = 1.1 if (speaker == "JAMIE" or speaker == "SPONSOR 2") else (1.05 if "ALEX" in speaker or "SPONSOR" in speaker else 1.0)
                
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
