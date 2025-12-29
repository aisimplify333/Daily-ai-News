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

# THE CAST (Human Realism)
CAST = {
    "ALEX": "onyx",    # The Anchor (Deep, Authoritative)
    "JAMIE": "coral",  # The Co-Host (Bright, Natural)
    "RUFUS": "fable"   # The Ledger (British, Dry)
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

# --- 2. INTELLIGENCE GATHERING ---
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

# --- 3. THE WRITER (LONG FORM EDITION) ---
def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (Aiming for 2500+ Words)...")
    today = datetime.date.today()
    day_name = today.strftime("%A")
    readable_date = today.strftime("%A the %dth of %B")
    weekday_idx = today.weekday() 
    
    cold_open_speaker = random.choice(["ALEX", "JAMIE", "RUFUS"])
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    tech = intel['tech'] if intel['tech'] else ["AI Breakthroughs", "AGI Rumors"]
    ethics = intel['ethics'] if intel['ethics'] else ["Privacy Concerns"]
    ledger = intel['ledger'] if intel['ledger'] else ["Global Regulation"]
    shock_story = random.choice(tech + ledger)

    # SHARED INSTRUCTIONS
    base_instructions = f"""
    You are a HUMAN radio host. NEVER mention you are an AI.
    
    CRITICAL LENGTH INSTRUCTION:
    Your goal is a 20-MINUTE EPISODE. You must write SUBSTANTIAL, DETAILED DIALOGUE.
    DO NOT SUMMARIZE. Write out the full debate, word-for-word.
    Explain concepts in depth. Use examples. Use analogies.
    """

    # --- FORMAT SELECTION ---
    if weekday_idx == 6:
        # C. SUNDAY SHOWDOWN (FORMAT C)
        print(f"    Mode: SUNDAY SHOWDOWN ({day_name})")
        prompt = f"""
        {base_instructions}
        FORMAT: THE SUNDAY SHOWDOWN (Pure Debate).
        
        STRUCTURE:
        [SEGMENT 1: COLD OPEN] (15s)
        - Speaker: {cold_open_speaker}
        - Content: A controversial opinion on: "{shock_story}"
        
        [SEGMENT 2: THE HOOK & ROADMAP]
        - Speaker: ALEX
        - Content: "Welcome to the AI Edge, it's {readable_date}. Today on the Showdown: First, the Main Motion on {tech[0]}. Then, we go live to {rufus_loc} for Rufus's financial take. And finally, the ultimate debate on {ethics[0]}."
        - SPONSOR 1 READ: {sponsors[0]['name']}: "{sponsors[0]['copy']}"
        
        [SEGMENT 3: THE MOTION (LONG FORM)] (800 words minimum)
        - Topic: {tech[0]} vs {ethics[0]}.
        - Alex argues for Progress/Acceleration. Jamie argues for Safety/Pause.
        - Go DEEP. Do not be brief. Argue back and forth multiple times.
        - SPONSOR 2 READ: {sponsors[1]['name']}: "{sponsors[1]['copy']}"
        
        [SEGMENT 4: THE CROSS-EXAMINATION (LONG FORM)] (800 words minimum)
        - Alex throws it to Rufus: "Rufus, you're {rufus_loc}, who is winning this war?"
        - Rufus dissects the argument purely on financial/legal grounds.
        
        [SEGMENT 5: CLOSING STATEMENTS] (300 words)
        - Each gives a final take.
        
        [SEGMENT 6: OUTRO & CTA]
        - Speaker: ALEX
        - Content: "Thanks for listening. If you want the edge, hit that Subscribe button now. Leave us a review, it helps the algorithm."
        - SPONSOR 3 READ: {sponsors[2]['name']}: "{sponsors[2]['copy']}"
        - CTA: "See you Monday."
        
        OUTPUT FORMAT: strictly "SPEAKER: [Dialogue]"
        """

    elif weekday_idx == 5:
        # B. THE WEEKEND WRAP (FORMAT B)
        print(f"    Mode: WEEKEND WRAP ({day_name})")
        prompt = f"""
        {base_instructions}
        FORMAT: THE WEEKEND WRAP.
        
        STRUCTURE:
        [SEGMENT 1: COLD OPEN] (15s)
        - Speaker: {cold_open_speaker}
        - Content: Shocking stat: "{shock_story}"
        
        [SEGMENT 2: THE HOOK & ROADMAP]
        - Speaker: ALEX
        - Content: "Welcome to the Weekend Wrap. Coming up: The Rapid Fire headlines, then a Deep Dive on {ethics[0]}, and we finish with Rufus live from {rufus_loc}."
        - SPONSOR 1 READ: {sponsors[0]['name']}: "{sponsors[0]['copy']}"
        
        [SEGMENT 3: RAPID FIRE WEEK (LONG FORM)] (800 words)
        - Speakers: ALL
        - Discuss 5-7 headlines in detail: {tech[:3]} and {ledger[:3]}.
        - SPONSOR 2 READ: {sponsors[1]['name']}: "{sponsors[1]['copy']}"
        
        [SEGMENT 4: THE DEEP DIVE (LONG FORM)] (800 words)
        - Topic: {ethics[0]}.
        - Alex throws to Rufus: "Rufus, standing by {rufus_loc}, what's the money saying?"
        - Extensive analysis.
        
        [SEGMENT 5: OUTRO & CTA]
        - Speaker: ALEX
        - Content: "Don't forget to Subscribe and rate the show."
        - SPONSOR 3 READ: {sponsors[2]['name']}: "{sponsors[2]['copy']}"
        - CTA: "Sign off."
        
        OUTPUT FORMAT: strictly "SPEAKER: [Dialogue]"
        """
        
    else:
        # A. THE DAILY EDGE (FORMAT A - MONDAY)
        print(f"    Mode: DAILY EDGE ({day_name})")
        prompt = f"""
        {base_instructions}
        FORMAT: THE DAILY EDGE.
        
        STRUCTURE:
        [SEGMENT 1: COLD OPEN] (15s)
        - Speaker: {cold_open_speaker}
        - Content: Shocking data: "{shock_story}"
        
        [SEGMENT 2: THE HOOK & ROADMAP]
        - Speaker: ALEX
        - Content: "Welcome to the AI Edge, your home for the latest news in AI unfiltered. I'm your Host Alex and along side me as always is Jamie."
        - Speaker: JAMIE
        - Content: "Hello nice to be here again Alex." (Or similar warm greeting).
        - Speaker: ALEX
        - Content: "It's {readable_date}. Here's the plan: First, we break down the Hard Hitting News of the day: {tech[0]} and {tech[1]}. Then, we open the Toolbox to look at new {tech[0]}. After that, we head to {rufus_loc} for the Ledger, covering VC trends, following the money and the legal aspects globally."
        - SPONSOR 1 READ: {sponsors[0]['name']}: "{sponsors[0]['copy']}"
        
        [SEGMENT 3: THE HEADLINES (LONG FORM)] (700 words)
        - Speakers: ALEX & JAMIE
        - Topic: Banter on the biggest stories: {tech[:2]}.
        - Dynamic: Energetic, conversational, reacting to the news.
        
        [SEGMENT 4: ALEX'S TOOLBOX (LONG FORM)] (700 words)
        - Speakers: ALEX & JAMIE
        - Topic: Deep dive into a specific tool or model: {tech[0]}. 
        - Go deep on features, pricing, and utility.
        - SPONSOR 2 READ: JAMIE reads for {sponsors[1]['name']}: "{sponsors[1]['copy']}"
        
        [SEGMENT 5: RUFUS'S LEDGER (LONG FORM)] (700 words)
        - Alex Handoff: "Let's go to Rufus, live {rufus_loc}."
        - Speaker: RUFUS (Solo)
        - Topic: VC Money, Lawsuits: {ledger[:2]}.
        - Detailed financial and global legal analysis.
        
        [SEGMENT 6: THE FORUM] (400 words)
        - Speakers: ALL
        - Brief debate on the Ledger topics.
        
        [SEGMENT 7: OUTRO & CTA]
        - Speaker: ALEX
        - Content: "Smash that Subscribe button. We need you to keep this show alive."
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
                
                # --- SPEED ADJUSTMENT (THE FINAL TWEAK) ---
                if speaker == "JAMIE":
                    speed = 1.15
                elif speaker == "ALEX":
                    speed = 1.05
                else: # RUFUS
                    speed = 1.0
                
                try:
                    resp = client.audio.speech.create(
                        model="tts-1-hd", voice=voice, input=text, speed=speed
                    )
                    path = AUDIO_DIR / f"line_{i:03d}_{speaker}.mp3"
                    resp.stream_to_file(path)
                    
                    seg = AudioSegment.from_mp3(path)
                    # Strip silence
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

    # 2. Intro Music (10 SECONDS then fade)
    full_audio += intro[:10000] 
    
    # 3. Body
    body_audio = AudioSegment.empty()
    last_speaker = "UNKNOWN"
    
    for speaker, clip in segments:
        # SFX for Rufus
        if speaker == "RUFUS" and last_speaker != "RUFUS":
            body_audio += sfx
        
        # THE HUMAN BREATH (400ms Pause)
        if body_audio.duration_seconds > 0:
            body_audio += AudioSegment.silent(duration=400) 
            body_audio += clip
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
