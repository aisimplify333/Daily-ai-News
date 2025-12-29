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
    "ALEX": "onyx",    # Authoritative, Deep
    "JAMIE": "nova",   # Warm, Energetic
    "RUFUS": "fable",  # British, Cynical
    "SPONSOR 1": "onyx",
    "SPONSOR 2": "nova",
    "SPONSOR 3": "onyx",
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "analyzing term sheets in Sand Hill Road",
    "monitoring the antitrust hearing in Brussels",
    "watching the Asian markets open in Singapore",
    "reviewing IPO filings in New York",
    "tracking sovereign wealth funds in the Middle East"
]

# --- 2. THE "INDUSTRY HARDLINE" FEEDS ---
FEED_SOURCES = {
    "MODELS_AND_PRODUCT": [
        "https://venturebeat.com/category/ai/feed/",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://openai.com/blog/rss.xml",
        "https://huggingface.co/blog/feed.xml"
    ],
    "INFRASTRUCTURE_AND_CORP": [
        "https://www.datacenterdynamics.com/rss/", # Energy/Building
        "https://www.semianalysis.com/feed", # Chips/Supply Chain
        "https://www.bloomberg.com/feeds/sitemap_news.xml" # Corporate
    ],
    "MONEY_LEGAL_GLOBAL": [
        "https://techcrunch.com/category/venture/feed/", # Pure VC Money
        "https://www.theverge.com/rss/policy/index.xml", # Legal/Regulation
        "https://restofworld.org/feed/", # Global (Non-US) Tech
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
    """Filters out consumer fluff to ensure 'Insider' status."""
    title_lower = title.lower()
    banned = ["monitor", "tv", "deal", "sale", "headphone", "review", "best of", "game", "console", "gift", "laptop"]
    for word in banned:
        if word in title_lower: return False
    return True

def gather_intel():
    print(" >> 📡 GATHERING FULL SPECTRUM INTEL (Money, Law, Tech)...")
    intel = {"models": [], "infra": [], "money_law": []}
    
    # 1. Models (Alex)
    for url in FEED_SOURCES["MODELS_AND_PRODUCT"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title):
                    intel["models"].append(entry.title)
                    if len(intel["models"]) >= 2: break
            if len(intel["models"]) >= 2: break
        except: pass
    if len(intel["models"]) < 2: intel["models"] += deep_search_fallback("New AI Model Release LLM parameters")

    # 2. Infrastructure (Alex/Jamie)
    for url in FEED_SOURCES["INFRASTRUCTURE_AND_CORP"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title):
                    intel["infra"].append(entry.title)
                    if len(intel["infra"]) >= 2: break
            if len(intel["infra"]) >= 2: break
        except: pass
    if len(intel["infra"]) < 2: intel["infra"] += deep_search_fallback("AI Data Center Energy Consumption GPU Shortage")

    # 3. Money, Law & Global (Rufus)
    for url in FEED_SOURCES["MONEY_LEGAL_GLOBAL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_industry_relevant(entry.title):
                    intel["money_law"].append(entry.title)
                    if len(intel["money_law"]) >= 3: break
        except: pass
    if len(intel["money_law"]) < 2: intel["money_law"] += deep_search_fallback("AI Venture Capital funding Antitrust Lawsuit EU AI Act")
    
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

# --- 4. THE WRITER (CONTEXT-AWARE ASSEMBLY LINE) ---
def generate_segment(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content

def clean_text_for_audio(text):
    """
    Sanitizes text to prevent TTS stuttering.
    Removes: *asterisks*, [brackets], (parentheses), and excessive punctuation.
    """
    text = re.sub(r'\*.*?\*', '', text) # Remove *actions*
    text = re.sub(r'\[.*?\]', '', text) # Remove [stage directions]
    text = re.sub(r'\(.*?\)', '', text) # Remove (notes)
    text = text.replace('*', '').replace('#', '').replace('_', '') # Clean markup
    return text.strip()

def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (Full Spectrum)...")
    today = datetime.date.today()
    readable_date = today.strftime("%A the %dth of %B")
    
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    # TOPIC SELECTION
    model_story = intel['models'][0] if intel['models'] else "OpenAI's Next Move"
    infra_story = intel['infra'][0] if intel['infra'] else "The Energy Crisis"
    money_story = intel['money_law'][0] if intel['money_law'] else "VC Funding Trends"
    legal_story = intel['money_law'][1] if len(intel['money_law']) > 1 else "Global Regulation"

    base_instructions = """
    You are writing a segment for 'THE AI EDGE', a podcast for INDUSTRY INSIDERS.
    AUDIENCE: Engineers, VCs, Founders.
    TONE: Serious, fast-paced, high-IQ. No fluff.
    CRITICAL RULE: DO NOT use phrases like "I think" or "Uh". Speak in complete, confident sentences.
    FORMAT STRICTLY: "SPEAKER: Dialogue"
    """

    full_script = ""

    # --- PART 1: INTRO & MODELS (Alex & Jamie) ---
    print(f"    ...Part 1: The Tech ({model_story})")
    prompt_1 = f"""
    {base_instructions}
    Write PART 1 (Approx 800 words).
    
    STRUCTURE:
    [COLD OPEN] ALEX: A hard number about {model_story} (e.g. parameter count, speed, price).
    [INTRO] ALEX: "Welcome to the AI Edge. I'm Alex, with Jamie." JAMIE: "Ready." ALEX: "It's {readable_date}. Today: {model_story}, the infrastructure bottleneck with {infra_story}, and finally the money trail." 
    [AD 1] ALEX: "First, {sponsors[0]['name']}." SPONSOR 1: "{sponsors[0]['copy']}"
    [HEADLINES] ALEX & JAMIE: 
    - Dissect {model_story}. 
    - Jamie asks: "Does this change the deployment strategy for enterprise?"
    - Alex answers with technical depth.
    """
    full_script += generate_segment(prompt_1) + "\n"

    # --- PART 2: INFRASTRUCTURE & ENERGY (Alex & Jamie) ---
    print(f"    ...Part 2: The Build ({infra_story})")
    prompt_2 = f"""
    {base_instructions}
    Write PART 2 (Approx 1000 words).
    CONTEXT: Moving from software to the physical constraints.
    
    STRUCTURE:
    [DEEP DIVE] ALEX: "But models need power. Let's talk infrastructure." 
    - Discuss {infra_story}. Focus on Energy, Data Centers, or GPU supply.
    - Mention specific companies (Nvidia, Microsoft, Energy providers).
    - Jamie pushes back: "Is this sustainable?"
    - Alex argues the bull case for massive scale.
    [AD 2] JAMIE: "Supported by {sponsors[1]['name']}." SPONSOR 2: "{sponsors[1]['copy']}"
    """
    full_script += generate_segment(prompt_2) + "\n"

    # --- PART 3: THE LEDGER (VC & LAW) (Rufus) ---
    print(f"    ...Part 3: The Money & Law ({money_story}, {legal_story})")
    prompt_3 = f"""
    {base_instructions}
    Write PART 3 (Approx 1000 words).
    CONTEXT: Financial and Legal analysis.
    
    STRUCTURE:
    [LEDGER SEGMENT] ALEX: "Let's go to Rufus, {rufus_loc}. Rufus, what's the deal flow looking like?"
    - RUFUS (British, Cynical, Insider): 
      1. Analyze the Venture Capital angle on {money_story}. Who is funding this? At what valuation? Is the burn rate sustainable?
      2. Pivot to the Legal/Global angle: {legal_story}. Discuss Antitrust, Regulation, or Geopolitics (China/EU).
    - Rufus concludes: "The lawyers are the only ones winning."
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
    
    # Save script for review
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
            
            # CLEAN TEXT TO PREVENT STUTTER
            text = clean_text_for_audio(text)
            
            if speaker in CAST and text:
                voice = CAST[speaker]
                # SPEED TUNING - LOCKED TO 1.0 FOR STABILITY
                speed = 1.0 
                
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
