import os
import json
import random
import re
import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from email.utils import formatdate
from openai import OpenAI
from pydub import AudioSegment

# --- 1. CONFIGURATION ---

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)
ASSETS_DIR = BASE_DIR / "assets"

# VOICES (Platinum Cast)
VOICES = {
    "ALEX": "onyx",   # Anchor
    "JAMIE": "nova",  # Disruptor
    "RUFUS": "fable"  # British Banker (Simulated)
}

# BRANDING
INTRO_TEXT = "Welcome to the AI Edge, your source for Daily News Unfiltered. Introducing Alex, Jamie, and Rufus."

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily News Unfiltered with Alex, Jamie, and Rufus.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.jpg",
    "category": "Technology"
}

# --- 2. FORMAT LOGIC ---

def get_show_settings():
    today = datetime.date.today()
    
    # YEAR END SPECIAL
    if today.month == 12 and today.day >= 26:
        return {
            "type": "Year End Special",
            "tone": "Epic, reflective, cynical yet hopeful.",
            "duration": "45 min",
            # Note: HOOK must be first for the Cold Open logic to work
            "segments": ["HOOK", "Q1_REVIEW", "Q2_REVIEW", "MID_ROLL", "Q3_REVIEW", "Q4_REVIEW", "PREDICTIONS", "OUTRO"]
        }
    
    # WEEKEND DEEP DIVE
    elif today.weekday() >= 5:
        return {
            "type": "Weekend Deep Dive",
            "tone": "Analytical, debate-heavy, slower pace.",
            "duration": "30 min",
            "segments": ["HOOK", "DEEP_DIVE_1", "RUFUS_MONEY", "MID_ROLL", "ROUND_TABLE_DEBATE", "OUTRO"]
        }
    
    # DAILY NEWS
    else:
        return {
            "type": "Daily News Unfiltered",
            "tone": "Fast, aggressive, interruption-heavy.",
            "duration": "20 min",
            "segments": ["HOOK", "TOP_STORY", "RUFUS_FIELD_REPORT", "MID_ROLL", "SECONDARY_STORY", "SPEED_ROUND", "OUTRO"]
        }

def get_rufus_location():
    return random.choice(["London", "The City of London", "Canary Wharf", "Zurich", "Hong Kong"])

# --- 3. THE WRITER (Enhanced Realism) ---

def draft_segment(segment_name, news_context, settings, rufus_loc, sponsor_txt):
    system_prompt = f"""
    You are the Writer for 'The AI Edge'. Write the **{segment_name}** segment.
    
    **CAST:**
    - ALEX (Host): Professional, sets the table. Catchphrase: "Let's get to it."
    - JAMIE (Co-Host): The Disruptor. She hates corporate speak. She interrupts.
    - RUFUS (Analyst): A weary British Banker in {rufus_loc}. He hates hype. Focuses on Profit/Law.
    
    **CONTEXT:**
    - Tone: {settings['tone']}
    - Sponsor (Mid-Roll only): "{sponsor_txt}"
    
    **GOAL:**
    - Accurate news coverage.
    - STRICT FORMAT: ALEX: [Text] / JAMIE: [Text] / RUFUS: [Text]
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Write segment: {segment_name}. Content: {news_context[:2500]}"}
        ]
    )
    return response.choices[0].message.content

def punch_up_script(draft_script):
    """The 95% Realism Booster."""
    system_prompt = """
    You are a Hollywood Script Doctor. Make this sound like REAL humans arguing.
    
    **INSTRUCTIONS:**
    1. **REMOVE INTROS:** If the script says "Welcome to the show" anywhere, DELETE IT. The code handles that.
    2. **ADD INTERRUPTIONS:** Use double dashes (--) to show cutting off.
       (e.g. ALEX: "The data suggests--" JAMIE: "--Oh, spare me the data!")
    3. **RUFUS (BRITISH):** Rewrite RUFUS to sound like a posh Londoner.
       - Use: "Rubbish", "Quite right", "Indeed", "The Exchequer", "Bollocks", "Spot on".
    4. **JAMIE (CYNIC):** Make her sharper. Less polite.
    5. **PRESERVE TAGS:** Keep ALEX:/JAMIE:/RUFUS: format.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": draft_script}
        ],
        temperature=0.9
    )
    return response.choices[0].message.content

# --- 4. PRODUCTION ENGINE ---

def clean_text(text):
    """Scrub stage directions and accidental intros."""
    text = text.replace('**', '').replace('*', '')
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    
    # SAFETY NET: Remove any hallucinated intros from the text
    bad_phrases = ["Welcome to the AI Edge", "Welcome back", "Hello everyone"]
    for phrase in bad_phrases:
        if phrase.lower() in text.lower() and len(text) < 100:
            return "" # Kill the line if it's just a duplicate intro
            
    return text.strip()

def generate_silence(duration_ms):
    """Generates a silent audio segment."""
    return AudioSegment.silent(duration=duration_ms)

def produce_episode(news_content, sponsor_msg="Sponsored by AI Simplify Media"):
    print("--- STARTING PLATINUM BUILD ---")
    
    settings = get_show_settings()
    rufus_loc = get_rufus_location()
    
    audio_segments = []     # List of Pydub AudioSegments (not just files)
    full_script_text = ""
    
    # STATE FLAGS (The 95% Correctness Fix)
    has_played_intro = False 
    
    # 1. LOAD ASSETS (Fail gracefully if missing)
    try:
        music_intro = AudioSegment.from_mp3(ASSETS_DIR / "intro.mp3")
    except:
        music_intro = AudioSegment.silent(duration=1000) # Fallback
        
    try:
        music_outro = AudioSegment.from_mp3(ASSETS_DIR / "outro.mp3")
    except:
        music_outro = AudioSegment.silent(duration=1000)

    # 2. GENERATE SEGMENTS
    for segment in settings['segments']:
        print(f" >> Processing: {segment}")
        
        # A. Draft & Punch-Up
        draft = draft_segment(segment, news_content, settings, rufus_loc, sponsor_msg)
        final_script = punch_up_script(draft)
        full_script_text += f"\n{final_script}"
        
        # B. Voice Generation Loop
        lines = final_script.split('\n')
        for line in lines:
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker = match.group(1).upper()
                text = clean_text(match.group(2))
                if not text: continue
                
                # --- AUDIO GENERATION ---
                temp_file = AUDIO_DIR / "temp_speech.mp3"
                client.audio.speech.create(
                    model="tts-1-hd", voice=VOICES[speaker], input=text
                ).stream_to_file(temp_file)
                
                # Convert to Pydub Segment
                speech_segment = AudioSegment.from_mp3(temp_file)
                
                # ADD BREATH (Realism): Add 200ms silence between speakers
                audio_segments.append(speech_segment)
                audio_segments.append(generate_silence(200)) 

        # C. LOGIC: INSERT INTRO (Once Only, After Hook)
        if segment == "HOOK" and not has_played_intro:
            print(" >> Injecting Branding (Unique)...")
            
            # 1. Add Intro Music
            audio_segments.append(music_intro)
            
            # 2. Add Fixed Voice Intro
            intro_voice_path = AUDIO_DIR / "fixed_intro.mp3"
            if not intro_voice_path.exists():
                client.audio.speech.create(
                    model="tts-1-hd", voice=VOICES["ALEX"], input=INTRO_TEXT
                ).stream_to_file(intro_voice_path)
            
            intro_seg = AudioSegment.from_mp3(intro_voice_path)
            audio_segments.append(intro_seg)
            
            # 3. Add Pacing Silence (500ms)
            audio_segments.append(generate_silence(500))
            
            has_played_intro = True

    # 3. ADD OUTRO
    print(" >> Adding Outro...")
    audio_segments.append(music_outro)

    # 4. STITCH & EXPORT
    print(" >> Stitching Master File...")
    final_mix = AudioSegment.empty()
    for seg in audio_segments:
        final_mix += seg
        
    final_filename = f"podcast_{datetime.date.today()}.mp3"
    final_path = AUDIO_DIR / final_filename
    final_mix.export(final_path, format="mp3")
    
    # 5. METADATA & RSS
    print(" >> Updating RSS...")
    meta = generate_metadata(full_script_text) # Uses function defined below
    update_rss_feed(meta, final_filename, os.path.getsize(final_path)) # Uses function defined below
    
    # Save Metadata for debug
    with open("episode_metadata.json", "w") as f:
        json.dump(meta, f, indent=4)

    print(f"DONE. Saved to: {final_path}")

# --- HELPER FUNCTIONS (Metadata & RSS) ---
def generate_metadata(text):
    prompt = 'Generate JSON: {"title": "Clickbait Title", "summary": "2 sentences", "hashtags": "#tag"}'
    response = client.chat.completions.create(
        model="gpt-4o", messages=[{"role":"user","content": f"{prompt}\n{text[:3000]}"}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def update_rss_feed(meta, fname, fsize):
    rss_path = Path("feed.xml")
    # ... (Standard RSS update logic, same as previous, omitted for brevity but assumed present) ...
    # RE-INSERT THE RSS LOGIC FROM PREVIOUS MESSAGE HERE IF YOU NEED THE FULL FILE BLOCK
    # For now, assuming you kept the RSS function from the previous turn. 
    # If not, let me know and I will paste the FULL 200 lines again.
    
    # Simple placeholder to ensure code runs if you paste over old function:
    # (Paste the update_rss_feed function from the previous confirmed code here)
    pass 

if __name__ == "__main__":
    # Load news
    news_file = Path("marketing.txt")
    if news_file.exists():
        with open(news_file, "r") as f: news = f.read()
    else:
        news = "AI News: Tech stocks volatile. Robots advancing. Regulation pending."
    
    produce_episode(news)
