import os
import json
import random
import datetime
import feedparser
import re
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment, effects
from duckduckgo_search import DDGS

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Paths
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)

# Assets
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"
TRANSITION_SFX = BASE_DIR / "transition.mp3"
SPONSORS_FILE = BASE_DIR / "sponsors.json"

# THE CAST (HD Voices)
CAST = {
    "ALEX": "ash",     # The Pilot (Energetic/Fast)
    "JAMIE": "coral",  # The Skeptic (Deep/Concerned)
    "RUFUS": "fable"   # The Ledger (British/Slow/Cold)
}

# RUFUS LOCATIONS (For that Global Feel)
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
    "ALEX_TECH": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/"
    ],
    "JAMIE_ETHICS": [
        "https://www.humanetech.com/feed",
        "https://www.eff.org/rss/updates.xml",
        "https://www.reddit.com/r/ArtificialInteligence/top/.rss"
    ],
    "RUFUS_INTEL": [
        "http://feeds.feedburner.com/avc", 
        "https://saastr.com/feed/",
        "https://techcrunch.com/tag/policy/feed/"
    ]
}

# --- 2. INTELLIGENCE GATHERING (With Safety Net) ---
def deep_search_fallback(persona, query):
    """Scours the web if feeds are dry."""
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR {persona} ({query})...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} {datetime.date.today()}", max_results=3)
        for r in search_results:
            results.append(f"BREAKING (Web Source): {r['title']} - {r['body']}")
    except Exception as e:
        print(f"   !! SEARCH FAILED: {e}")
    return results

def gather_intel():
    print(" >> 📡 GATHERING GLOBAL INTELLIGENCE...")
    intel = {"tech": [], "ethics": [], "ledger": []}
    
    # Alex (Tech)
    for url in FEED_SOURCES["ALEX_TECH"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: intel["tech"].append(entry.title)
        except: pass
    if len(intel["tech"]) < 2: intel["tech"] += deep_search_fallback("ALEX", "latest AI tools news")

    # Jamie (Ethics)
    for url in FEED_SOURCES["JAMIE_ETHICS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: intel["ethics"].append(entry.title)
        except: pass
    if len(intel["ethics"]) < 2: intel["ethics"] += deep_search_fallback("JAMIE", "AI ethics labor lawsuits")

    # Rufus (Ledger)
    for url in FEED_SOURCES["RUFUS_INTEL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: intel["ledger"].append(entry.title)
        except: pass
    if len(intel["ledger"]) < 2: intel["ledger"] += deep_search_fallback("RUFUS", "VC funding AI regulation antitrust")

    return intel

def get_sponsors():
    defaults = [
        {"name": "The AI Edge Newsletter", "copy": "Join 50k subscribers reading the Edge.", "url": "https://newsletter.aiedge.io"},
        {"name": "TechStart Academy", "copy": "Learn to code in 30 days.", "url": "https://techstart.com/ai"},
        {"name": "CloudScale", "copy": "Deploy AI agents in seconds.", "url": "https://cloudscale.ai"}
    ]
    if SPONSORS_FILE.exists():
        try:
            with open(SPONSORS_FILE, "r") as f:
                loaded = json.load(f)
                return (loaded * 3)[:3] 
        except: pass
    return defaults

# --- 3. THE WRITER (Dynamic Formats) ---
def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT...")
    today = datetime.date.today()
    day_name = today.strftime("%A")
    weekday_idx = today.weekday() # 0=Mon, 6=Sun
    
    # Random Cast Member for Cold Open
    cold_open_speaker = random.choice(["ALEX", "JAMIE", "RUFUS"])
    
    # Flavor for Rufus
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    tech = intel['tech'] if intel['tech'] else ["AI Breakthroughs"]
    ethics = intel['ethics'] if intel['ethics'] else ["Privacy Concerns"]
    ledger = intel['ledger'] if intel['ledger'] else ["Global Regulation"]
    shock_story = random.choice(tech + ledger)

    # --- FORMAT SELECTION ---
    if weekday_idx == 6:
        # C. SUNDAY SHOWDOWN (The Debate)
        print(f"    Mode: SUNDAY SHOWDOWN ({day_name})")
        prompt = f"""
        You are the Executive Producer of 'The AI Edge'. Write the script for {day_name}.
        FORMAT: THE SUNDAY SHOWDOWN (Pure Debate).
        
        TONE: Intense, Argumentative, High IQ. "McLaughlin Group" style.
        
        STRUCTURE:
        [SEGMENT 1: COLD OPEN] (15s)
        - Speaker: {cold_open_speaker}
        - Content: A controversial opinion on: "{shock_story}"
        
        [SEGMENT 2: THE HOOK]
        - Speaker: ALEX
        - Content: "Welcome to the Sunday Showdown. The gloves are off."
        - SPONSOR 1 READ: {sponsors[0]['name']}: "{sponsors[0]['copy']}"
        
        [SEGMENT 3: THE MOTION] (10 mins)
        - Topic: {ethics[0]} vs {tech[0]}.
        - Alex argues for Progress/Acceleration. Jamie argues for Safety/Pause.
        - They go back and forth aggressively.
        - SPONSOR 2 READ: {sponsors[1]['name']}: "{sponsors[1]['copy']}"
        
        [SEGMENT 4: THE CROSS-EXAMINATION] (10 mins)
        - Alex throws it to Rufus: "Rufus, you're {rufus_loc}, who is winning this war?"
        - Rufus dissects the argument purely on financial/legal grounds. He insults both sides.
        
        [SEGMENT 5: CLOSING STATEMENTS] (5 mins)
        - Each gives a 30s final take.
        
        [SEGMENT 6: OUTRO]
        - Speaker: ALEX
        - SPONSOR 3 READ: {sponsors[2]['name']}: "{sponsors[2]['copy']}"
        - CTA: "See you Monday."
        
        OUTPUT FORMAT: strictly "SPEAKER: [Dialogue]"
        """

    elif weekday_idx == 5:
        # B. THE WEEKEND WRAP (Saturday)
        print(f"    Mode: WEEKEND WRAP ({day_name})")
        prompt = f"""
        You are the Executive Producer of 'The AI Edge'. Write the script for {day_name}.
        FORMAT: THE WEEKEND WRAP (Long Form).
        
        TONE: Sorkin-style. Fast, overlapping, "Walk and Talk".
        
        STRUCTURE:
        [SEGMENT 1: COLD OPEN] (15s)
        - Speaker: {cold_open_speaker}
        - Content: Shocking stat: "{shock_story}"
        
        [SEGMENT 2: THE HOOK]
        - Speaker: ALEX
        - Content: "Welcome to the Weekend Wrap."
        - SPONSOR 1 READ: {sponsors[0]['name']}: "{sponsors[0]['copy']}"
        
        [SEGMENT 3: RAPID FIRE WEEK] (10 mins)
        - Speakers: ALL
        - Run through 5-7 headlines: {tech[:3]} and {ledger[:3]}.
        - Fast banter. Overlapping.
        - SPONSOR 2 READ: {sponsors[1]['name']}: "{sponsors[1]['copy']}"
        
        [SEGMENT 4: THE DEEP DIVE] (15 mins)
        - Topic: Pick ONE theme from {ethics[:1]} and go deep.
        - Alex throws to Rufus: "Rufus, standing by {rufus_loc}, what's the money saying?"
        - Rufus gives the global perspective.
        
        [SEGMENT 5: OUTRO]
        - Speaker: ALEX
        - SPONSOR 3 READ: {sponsors[2]['name']}: "{sponsors[2]['copy']}"
        - CTA: "Sign off."
        
        OUTPUT FORMAT: strictly "SPEAKER: [Dialogue]"
        """
        
    else:
        # A. THE DAILY EDGE (Mon-Fri)
        print(f"    Mode: DAILY EDGE ({day_name})")
        prompt = f"""
        You are the Executive Producer of 'The AI Edge'. Write the script for {day_name}.
        FORMAT: THE DAILY EDGE (News & Analysis).
        
        TONE: Heated, Short Sentences, Interruptions.
        
        STRUCTURE:
        [SEGMENT 1: COLD OPEN] (15s)
        - Speaker: {cold_open_speaker}
        - Content: Shocking data: "{shock_story}"
        
        [SEGMENT 2: THE HOOK]
        - Speaker: ALEX
        - Content: "Unfiltered updates."
        - SPONSOR 1 READ: {sponsors[0]['name']}: "{sponsors[0]['copy']}"
        
        [SEGMENT 3: ALEX'S TOOLBOX] (8 mins)
        - Speakers: ALEX & JAMIE
        - Topic: {tech[:2]}. Alex hypes, Jamie critiques.
        - SPONSOR 2 READ: JAMIE reads for {sponsors[1]['name']}: "{sponsors[1]['copy']}"
        
        [SEGMENT 4: RUFUS'S LEDGER] (8 mins)
        - Alex Handoff: "Let's go to Rufus, live {rufus_loc}."
        - Speaker: RUFUS (Solo)
        - Topic: VC Money, Lawsuits: {ledger[:2]}.
        - Tone: Cold, British, Analytical.
        
        [SEGMENT 5: THE FORUM] (3 mins)
        - Speakers: ALL
        - Debate the Ledger topics.
        
        [SEGMENT 6: OUTRO]
        - Speaker: ALEX
        - SPONSOR 3 READ: {sponsors[2]['name']}: "{sponsors[2]['copy']}"
        - CTA: Sign off.
        
        OUTPUT FORMAT: strictly "SPEAKER: [Dialogue]"
        """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )
    return response.choices[0].message.content

# --- 4. SEO & MARKETING ---
def generate_seo_package(script, sponsors):
    print(" >> 🚀 GENERATING SEO METADATA...")
    prompt = f"""
    Based on this script, generate:
    1. A Viral Spotify Title (Max 60 chars). No dates.
    2. Detailed Show Notes.
    3. Hashtags.
    
    SCRIPT: {script[:3000]}
    OUTPUT JSON: {{ "title": "...", "show_notes": "...", "hashtags": "..." }}
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 5. PRODUCTION ENGINE ---
def produce_episode():
    # A. PRE-PRODUCTION
    intel = gather_intel()
    sponsors = get_sponsors()
    script = write_script(intel, sponsors)
    
    # B. MARKETING
    seo_data = generate_seo_package(script, sponsors)
    with open(BASE_DIR / "viral_caption.txt", "w") as f:
        f.write(f"{seo_data['title']}\n\n{seo_data['hashtags']}")
    with open(BASE_DIR / "show_notes.txt", "w") as f:
        f.write(seo_data['show_notes'])

    # C. RECORDING (HD)
    print(" >> 🎙️  RECORDING HD LINES...")
    segments = []
    lines = script.split('\n')
    
    for i, line in enumerate(lines):
        if ": " in line:
            parts = line.split(": ", 1)
            speaker = parts[0].strip().upper()
            text = parts[1].strip()
            text = re.sub(r'\([^)]*\)', '', text)
            
            if speaker in CAST:
                voice = CAST.get(speaker, "alloy")
                # Speed: Alex/Jamie fast (1.15), Rufus slow (1.0)
                speed = 1.15 if speaker in ["ALEX", "JAMIE"] else 1.0
                
                try:
                    resp = client.audio.speech.create(
                        model="tts-1-hd", voice=voice, input=text, speed=speed
                    )
                    path = AUDIO_DIR / f"line_{i:03d}_{speaker}.mp3"
                    resp.stream_to_file(path)
                    
                    seg = AudioSegment.from_mp3(path)
                    # Strip silence for realism
                    seg = effects.strip_silence(seg, silence_thresh=-45, padding=10)
                    segments.append((speaker, seg))
                except Exception as e:
                    print(f"Skipped line {i}: {e}")

    # D. MIXING (The Polish)
    print(" >> 🎚️  MIXING EPISODE...")
    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(1000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(1000)
    sfx = AudioSegment.from_mp3(TRANSITION_SFX) - 6 if TRANSITION_SFX.exists() else AudioSegment.silent(500)

    # 1. Cold Open
    if segments:
        full_audio += segments[0][1]
        segments.pop(0)

    # 2. Intro Music
    full_audio += intro[:4000] # Full volume intro
    
    # 3. Body
    body_audio = AudioSegment.empty()
    last_speaker = "UNKNOWN"
    
    for speaker, clip in segments:
        # SFX for Rufus entrance (Audio branding)
        if speaker == "RUFUS" and last_speaker != "RUFUS":
            body_audio += sfx
        
        # 250ms Overlap for "Sorkin" feel
        if body_audio.duration_seconds > 0:
            body_audio = body_audio.append(clip, crossfade=250)
        else:
            body_audio += clip
        
        last_speaker = speaker

    full_audio += body_audio
    full_audio += outro[:10000].fade_in(1000)

    # E. EXPORT
    today_str = datetime.date.today().isoformat()
    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    # F. METADATA
    meta = {
        "file": str(outfile),
        "title": seo_data['title'],
        "description": seo_data['show_notes'],
        "tags": seo_data['hashtags']
    }
    with open(BASE_DIR / "episode_metadata.json", "w") as f:
        json.dump(meta, f)

    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
