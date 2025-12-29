import os
import re
import datetime
import random
import feedparser
from dotenv import load_dotenv

# ✅ API CLIENTS
from google import genai
from google.genai import types
from openai import OpenAI

# ✅ AUDIO ENGINE
from pydub import AudioSegment, effects

load_dotenv()

# --- CONFIGURATION ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not GEMINI_KEY or not OPENAI_KEY:
    print("❌ KEYS MISSING. Please check your .env file.")
    exit()

client_gemini = genai.Client(api_key=GEMINI_KEY)
client_openai = OpenAI(api_key=OPENAI_KEY)

MODEL_ID = "gemini-2.5-flash"

# --- 1. THE CAST & SOURCES ---
VOICE_MAP = {
    "ALEX": "ash",
    "JAMIE": "coral",
    "RUFUS": "fable", # British
    "VOX": "alloy"    # Cold Open
}

# The "Well Rounded" Diet
FEED_SOURCES = {
    "ALEX_TECH": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.producthunt.com/feed",
        "https://news.ycombinator.com/rss"
    ],
    "JAMIE_ETHICS": [
        "https://www.humanetech.com/feed",
        "https://www.eff.org/rss/updates.xml",
        "https://www.reddit.com/r/ArtificialInteligence/top/.rss",
        "https://www.reddit.com/r/Privacy/top/.rss",
        "https://www.vox.com/rss/recode/index.xml",
        "https://mozilla.org/en-US/blog/rss/"
    ],
    "RUFUS_MONEY": [
        "https://search.cnbc.com/rs/search/view.html?partnerId=2000&keywords=tech&sort=date&type=story&pubTime=30&pubFreq=d",
        "http://feeds.feedburner.com/avc", 
        "https://saastr.com/feed/",
        "https://abovethelaw.com/feed/",
        "https://www.reddit.com/r/Economics/top/.rss",
        "https://techmeme.com/feed.xml"
    ]
}

# --- 2. INTELLIGENCE GATHERING ---
def gather_intel():
    print(" >> 📡 SCANNING GLOBAL FEEDS...")
    context = []
    
    # 1. RSS Scan
    for category, urls in FEED_SOURCES.items():
        print(f"    Scanning {category}...")
        for url in urls:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    # Grab top story only to keep it fresh
                    entry = feed.entries[0]
                    clean_summary = re.sub('<[^<]+?>', '', entry.summary)[:200]
                    context.append(f"[{category}] {entry.title}: {clean_summary}")
            except: pass
            
    # 2. Deep Search Fallback (If feeds are thin)
    if len(context) < 10:
        print(" >> ⚠️ DATA THIN. ACTIVATING DEEP SEARCH...")
        try:
            q = f"Top AI news, VC funding, and Tech Ethics scandals for {datetime.date.today()}"
            resp = client_gemini.models.generate_content(
                model=MODEL_ID,
                contents=q,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            context.append(f"SEARCH_DATA: {resp.text}")
        except: pass
        
    return "\n".join(context)

# --- 3. THE WRITER (SORKIN STYLE) ---
def write_script(news_context):
    print(" >> ✍️  WRITING SCRIPT (HEATED)...")
    
    prompt = f"""
    Write a podcast script for 'The AI Edge'.
    
    CAST:
    - ALEX (Host): Energetic, interrupts with excitement.
    - JAMIE (Skeptic): Interrupts with concern.
    - RUFUS (VC): British, Interrupts with data.
    - VOX: Cold open voice.
    
    NEWS CONTEXT:
    {news_context}
    
    INSTRUCTIONS:
    - START with VOX (15s shocking data point).
    - ALEX welcomes + intro.
    - RUFUS takes over with 'The Ledger' (Money).
    - JAMIE cuts him off for 'The Forum' (Debate).
    - STYLE: HEATED. SHORT SENTENCES. They finish each other's sentences.
    - FORMAT: Strictly "NAME: [Line]"
    """
    
    resp = client_gemini.models.generate_content(
        model=MODEL_ID,
        contents=prompt
    )
    return resp.text

# --- 4. THE AUDIO ENGINE (OVERLAPPING) ---
def produce_audio(script_text, output_folder):
    print(" >> 🎙️ CASTING & RECORDING...")
    
    lines = script_text.strip().split('\n')
    segments = []
    
    # 1. Generate Individual Clips
    for i, line in enumerate(lines):
        if ":" in line:
            parts = line.split(":", 1)
            speaker = parts[0].strip().upper()
            text = parts[1].strip()
            text = re.sub(r'\([^)]*\)', '', text) # Remove (laughs)
            
            if speaker in VOICE_MAP and len(text) > 1:
                try:
                    # Generate Audio
                    response = client_openai.audio.speech.create(
                        model="tts-1",
                        voice=VOICE_MAP[speaker],
                        input=text,
                        speed=1.1 # Speed up slightly for urgency
                    )
                    
                    # Save Temp File
                    temp_file = f"{output_folder}/temp_{i:03d}_{speaker}.mp3"
                    with open(temp_file, "wb") as f:
                        f.write(response.content)
                        
                    # Load into Pydub & Strip Silence
                    seg = AudioSegment.from_mp3(temp_file)
                    seg = effects.strip_silence(seg, silence_thresh=-40, padding=10)
                    segments.append(seg)
                    
                    print(f"    [{i:02d}] {speaker}: {text[:30]}...")
                    
                except Exception as e:
                    print(f"    !! Error line {i}: {e}")

    # 2. Stitch with OVERLAP (The "Heated" Logic)
    print(" >> 🎛️ MIXING (OVERLAPPING DIALOGUE)...")
    if segments:
        final_mix = segments[0]
        
        for seg in segments[1:]:
            # Determine overlap duration (randomized for realism)
            # Short overlap (50ms) = Fast banter
            # Long overlap (300ms) = Interruption
            overlap_ms = random.randint(50, 350)
            
            # Safety: Don't overlap more than the clip length
            max_overlap = min(len(final_mix), len(seg)) - 10
            actual_overlap = min(overlap_ms, max_overlap)
            
            if actual_overlap > 0:
                final_mix = final_mix.append(seg, crossfade=actual_overlap)
            else:
                final_mix += seg

        # Export
        today = datetime.date.today()
        outfile = f"AI_Edge_HEATED_{today}.mp3"
        final_mix.export(outfile, format="mp3")
        print(f" ✅ EPISODE READY: {outfile}")
    else:
        print(" !! No audio produced.")

# --- MAIN ---
def main():
    print("--- 🚀 THE AI EDGE: WINDOWS STUDIO (HEATED) ---")
    today = datetime.date.today()
    folder = f"Production_{today}"
    os.makedirs(folder, exist_ok=True)
    
    intel = gather_intel()
    script = write_script(intel)
    
    # Save Script Backup
    with open(f"{folder}/script.txt", "w", encoding="utf-8") as f:
        f.write(script)
        
    produce_audio(script, folder)

if __name__ == "__main__":
    main()
