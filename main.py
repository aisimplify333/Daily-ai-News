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
SPONSORS_FILE = BASE_DIR / "sponsors.json"

# THE CAST
CAST = {
    "ALEX": "onyx",    # Anchor: Deep, Authoritative, Tech-Optimist.
    "JAMIE": "nova",   # Co-Host: Empathetic, Human-First, Skeptic but Warm.
    "RUFUS": "fable",  # Analyst: British, Financial Realist, Dry.
    "SPONSOR 1": "onyx",
    "SPONSOR 2": "nova",
    "SPONSOR 3": "onyx",
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "analyzing chip supply chains in Taiwan",
    "watching the pre-market movers in New York",
    "reviewing data center energy audits in Virginia",
    "tracking insider trading filings in London",
    "monitoring sovereign wealth funds in Dubai"
]

# --- 2. THE "TITAN" FEEDS (Expanded with Groq, Claude, GLM) ---
FEED_SOURCES = {
    # 1. The Titans (US & Global) -> Added Anthropic, Groq, Zhipu
    "TITANS": [
        "https://openai.com/blog/rss.xml",                # OpenAI
        "https://ai.googleblog.com/feeds/posts/default", # Google
        "https://blogs.microsoft.com/ai/feed/",        # Microsoft
        "https://groq.com/feed/",                      # Groq (Inference Speed)
        # USING GOOGLE NEWS RSS BRIDGES FOR HARD-TO-FIND FEEDS:
        "https://news.google.com/rss/search?q=Anthropic+Claude+AI&hl=en-US&gl=US&ceid=US:en", # Anthropic/Claude
        "https://news.google.com/rss/search?q=Zhipu+AI+GLM+Model&hl=en-US&gl=US&ceid=US:en"   # Zhipu/GLM
    ],
    # 2. The Iron (Chips & Infrastructure)
    "INFRASTRUCTURE": [
        "https://www.datacenterdynamics.com/rss/",     # Vertiv/Energy context
        "https://www.semianalysis.com/feed",           # ASML/Broadcom/Nvidia deep dive
        "https://www.anandtech.com/rss/"               # Hardware specifics
    ],
    # 3. The Enterprise & Money
    "ENTERPRISE_FINANCE": [
        "https://finance.yahoo.com/news/rssindex",     # Yahoo Finance
        "https://techcrunch.com/category/enterprise/feed/", # Enterprise AI
        "https://blog.palantir.com/feed"               # Palantir specific
    ],
    # 4. The Trends (Healthcare, Mfg, Emerging Tools)
    "TRENDS_TOOLS": [
        "https://www.unite.ai/feed/",                  # General Trends
        "https://medium.com/feed/tag/artificial-intelligence" # Emerging Tools
    ]
}

# --- 3. INTELLIGENCE GATHERING ---
def deep_search_fallback(query):
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR: {query}...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} news {datetime.date.today()}", max_results=3)
        for r in search_results: results.append(f"WEB SEARCH: {r['title']} - {r['body']}")
    except: pass
    return results

def is_industry_relevant(title):
    """Filters out consumer fluff."""
    title_lower = title.lower()
    banned = ["game", "console", "deal", "sale", "tv", "monitor", "headphone", "gift", "best of"]
    for word in banned:
        if word in title_lower: return False
    return True

def gather_intel():
    print(" >> 📡 GATHERING TITAN INTEL (Groq, Claude, GLM, & The Bigs)...")
    intel = {"titans": [], "infra": [], "money": [], "trends": []}
    
    # 1. Titans (Prioritize Claude/Groq/GLM if found)
    for url in FEED_SOURCES["TITANS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title):
                    intel["titans"].append(entry.title)
                    if len(intel["titans"]) >= 3: break
        except: pass
    if len(intel["titans"]) < 1: intel["titans"] += deep_search_fallback("Anthropic Claude 3.5 Groq LPU Zhipu GLM-4")

    # 2. Infrastructure
    for url in FEED_SOURCES["INFRASTRUCTURE"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title):
                    intel["infra"].append(entry.title)
                    if len(intel["infra"]) >= 2: break
        except: pass

    # 3. Enterprise & Finance
    for url in FEED_SOURCES["ENTERPRISE_FINANCE"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title) and "AI" in entry.title:
                    intel["money"].append(entry.title)
                    if len(intel["money"]) >= 2: break
        except: pass

    # 4. Trends/Tools
    for url in FEED_SOURCES["TRENDS_TOOLS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title):
                    intel["trends"].append(entry.title)
                    if len(intel["trends"]) >= 2: break
        except: pass
    
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

# --- 4. THE WRITER (EMPATHETIC JAMIE ENGINE) ---
def generate_segment(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.75, # Slight bump for "Chemistry" banter
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content

def clean_text_for_audio(text):
    """Scrub text to prevent TTS stutters."""
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text) 
    text = text.replace('"', '').replace("'", "")
    text = text.replace("AI", "A.I.")
    return text.strip()

def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (Chemistry Mode: Alex & Empathetic Jamie)...")
    today = datetime.date.today()
    readable_date = today.strftime("%A the %dth of %B")
    
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    # Story Selection
    titan_story = intel['titans'][0] if intel['titans'] else "The Model Wars: Claude vs GPT"
    infra_story = intel['infra'][0] if intel['infra'] else "Groq's Speed Record"
    money_story = intel['money'][0] if intel['money'] else "The Capital Flows"
    
    base_instructions = """
    You are writing a BROADCAST QUALITY PODCAST SCRIPT.
    
    CHARACTERS:
    - ALEX (Host): The "Brain". Tech-optimist, obsessed with specs, speed, and business. Voices the "Hard Reality".
    - JAMIE (Co-Host): The "Heart". Empathetic Skeptic. She worries about the *human cost*. She champions artists, workers, and ethics. She isn't mean; she's thoughtful.
    - RUFUS (Analyst): The "Wallet". British, cynical, follows the cash.
    
    CHEMISTRY RULES:
    1. THEY ARE FRIENDS. They banter. Alex respects Jamie's caution; Jamie respects Alex's vision.
    2. JAMIE'S CATCHPHRASE: "But what about the people, Alex?"
    3. ALEX'S DEFENSE: "The progress is inevitable, Jamie."
    
    FORMAT RULES:
    1. NO STAGE DIRECTIONS (No *laughs*, No [intro]).
    2. SPEAK IN FULL, NATURAL SENTENCES.
    3. MENTION: Groq, Anthropic (Claude), Zhipu (GLM), or Nvidia.
    """

    full_script = ""

    # --- PART 1: THE TITANS (Alex & Jamie) ---
    print(f"    ...Part 1: The Titans ({titan_story})")
    prompt_1 = f"""
    {base_instructions}
    Write PART 1 (Approx 800 words).
    
    STRUCTURE:
    [COLD OPEN] ALEX: A shocking stat about {titan_story}.
    [INTRO] ALEX: "Welcome to the AI Edge. I'm Alex." JAMIE: "And I'm Jamie, trying to find the humanity in the machine."
    [AD 1] ALEX: "First, {sponsors[0]['name']}." SPONSOR 1: "{sponsors[0]['copy']}"
    [SEGMENT] ALEX: Discuss {titan_story}. 
    - Mention Anthropic's Claude, Zhipu's GLM, or Groq's speed.
    - JAMIE: "It's fast, Alex, but is it good? And what happens to the writers/coders who can't compete with this speed?"
    - ALEX: "It frees them to do higher level work."
    - JAMIE: "Or it frees them from a paycheck. Let's be real."
    """
    full_script += generate_segment(prompt_1) + "\n"

    # --- PART 2: THE IRON & SECTORS (Alex & Jamie) ---
    print(f"    ...Part 2: Infrastructure ({infra_story})")
    prompt_2 = f"""
    {base_instructions}
    Write PART 2 (Approx 1000 words).
    
    STRUCTURE:
    [SEGMENT] ALEX: "Software is nothing without the Iron."
    - Discuss {infra_story}. (Nvidia, Vertiv, ASML).
    - ALEX: "The energy demand is massive. Data centers are the new oil fields."
    - JAMIE: "And the environment? We're burning forests to build chatbots? That keeps me up at night."
    - ALEX: "Nuclear is coming, Jamie."
    - JAMIE: "That's a whole other podcast, Alex."
    [AD 2] JAMIE: "Supported by {sponsors[1]['name']}." SPONSOR 2: "{sponsors[1]['copy']}"
    """
    full_script += generate_segment(prompt_2) + "\n"

    # --- PART 3: THE MONEY (Rufus) ---
    print(f"    ...Part 3: The Money ({money_story})")
    prompt_3 = f"""
    {base_instructions}
    Write PART 3 (Approx 800 words).
    
    STRUCTURE:
    [SEGMENT] ALEX: "Let's check the ledger. Rufus, are you there {rufus_loc}?"
    - RUFUS: "I am indeed." Analyze {money_story}.
    - Focus on Palantir, Salesforce, or VC funding.
    - RUFUS: "While you two argue about feelings, I'm watching the profit margins."
    [OUTRO] ALEX: "Subscribe." SPONSOR 3: "{sponsors[2]['copy']}"
    """
    full_script += generate_segment(prompt_3)

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
            
            # CRITICAL FIX: CLEAN TEXT
            text = clean_text_for_audio(text)
            
            if speaker in CAST and text:
                voice = CAST[speaker]
                speed = 1.0 # STABILITY LOCK
                
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

    print(" >> 🎚️  MIXING EPISODE...")
    if not segments: return

    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(1000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(1000)
    sfx = AudioSegment.from_mp3(TRANSITION_SFX) - 6 if TRANSITION_SFX.exists() else AudioSegment.silent(500)

    if segments:
        full_audio += segments[0][1]
        segments.pop(0)

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
