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

# --- 1. CONFIGURATION & SETUP ---

# API CLIENT
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# DIRECTORIES
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True) # Ensure assets folder exists

# THE PLATINUM CAST
# Alex: Onyx (Deep, Professional Anchor)
# Jamie: Nova (High Energy, Prompted to be Cynical/Disruptive)
# Rufus: Fable (Prompted to use British Syntax/Dry Wit)
VOICES = {
    "ALEX": "onyx",
    "JAMIE": "nova",
    "RUFUS": "fable"
}

# HARDCODED BRANDING (The anchor point of the show)
INTRO_TEXT = "Welcome to the AI Edge, your source for Daily News Unfiltered. Introducing Alex, Jamie, and Rufus."

# RSS / SPOTIFY SETTINGS
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily News Unfiltered with Alex, Jamie, and Rufus.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.jpg",
    "category": "Technology"
}

# --- 2. LOGIC: CALENDAR & FORMAT ---

def get_show_settings():
    """Determines show structure based on date."""
    today = datetime.date.today()
    
    # A. YEAR END SPECIAL (45 Mins) - Dec 26-31
    if today.month == 12 and today.day >= 26:
        return {
            "type": "Year End Special",
            "tone": "Epic, reflective, cynical yet hopeful.",
            "duration": "45 min",
            "segments": ["HOOK", "Q1_REVIEW", "Q2_REVIEW", "MID_ROLL", "Q3_REVIEW", "Q4_REVIEW", "PREDICTIONS", "OUTRO"]
        }
    
    # B. WEEKEND DEEP DIVE (30 Mins) - Sat/Sun
    elif today.weekday() >= 5:
        return {
            "type": "Weekend Deep Dive",
            "tone": "Analytical, debate-heavy, slower pace.",
            "duration": "30 min",
            "segments": ["HOOK", "DEEP_DIVE_1", "RUFUS_MONEY", "MID_ROLL", "ROUND_TABLE_DEBATE", "OUTRO"]
        }
    
    # C. DAILY NEWS (20 Mins) - Mon-Fri
    else:
        return {
            "type": "Daily News Unfiltered",
            "tone": "Fast, aggressive, interruption-heavy.",
            "duration": "20 min",
            "segments": ["HOOK", "TOP_STORY", "RUFUS_FIELD_REPORT", "MID_ROLL", "SECONDARY_STORY", "SPEED_ROUND", "OUTRO"]
        }

def get_rufus_location():
    """Rufus is a global correspondent."""
    return random.choice(["London", "The City of London", "Canary Wharf", "Zurich", "Hong Kong", "Singapore"])

# --- 3. THE WRITER (DRAFT + PUNCH-UP) ---

def draft_segment(segment_name, news_context, settings, rufus_loc, sponsor_txt):
    """Step 1: Get the facts right."""
    system_prompt = f"""
    You are the Writer for 'The AI Edge'. Write the **{segment_name}** segment.
    
    **ROLES:**
    - ALEX (Host): Professional, driving the roadmap. Catchphrase: "Let's get to it."
    - JAMIE (Co-Host): The Cynic (Female). She questions hype.
    - RUFUS (Analyst): Reporting from {rufus_loc}. Focus on Money/Law.
    
    **CONTEXT:**
    - Format: {settings['type']}
    - Tone: {settings['tone']}
    - Sponsor Read (if Mid-Roll): "{sponsor_txt}"
    
    **GOAL:**
    - Cover the news accurately.
    - Use format: ALEX: [Text] / JAMIE: [Text] / RUFUS: [Text]
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Write the script for: {segment_name}. News Context: {news_context[:2500]}"}
        ]
    )
    return response.choices[0].message.content

def punch_up_script(draft_script):
    """Step 2: The 'Humanizer'. Adds interruptions and British syntax."""
    system_prompt = """
    You are a Hollywood Script Doctor. Rewrite this to sound like real humans arguing.
    
    **CRITICAL INSTRUCTIONS:**
    1. **REMOVE INTROS:** If the script says "Welcome to the show" anywhere, DELETE IT. The code handles that.
    2. **INTERRUPTIONS:** Use double dashes (--) to cut people off. 
       (e.g., ALEX: "The data shows--" JAMIE: "--Forget the data, look at the reality!")
    3. **JAMIE (The Cynic):** Make her ruder. She should mock corporate speak.
    4. **RUFUS (The Brit):** Rewrite RUFUS's lines using **BRITISH SYNTAX** to simulate an accent.
       - Use: "Rubbish", "Quite right", "Indeed", "The Exchequer", "Cheers", "Mate", "Bollocks", "Spot on".
       - He is DRY and FORMAL.
    5. **PRESERVE FORMAT:** Keep ALEX:/JAMIE:/RUFUS: tags exactly.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": draft_script}
        ],
        temperature=0.9 # High creativity
    )
    return response.choices[0].message.content

# --- 4. PRODUCTION ENGINE (AUDIO & METADATA) ---

def clean_text(text):
    """Scrub stage directions and accidental intros."""
    text = text.replace('**', '').replace('*', '')
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    
    # SAFETY NET: Remove any hallucinated intros from the text so we don't get double intros
    bad_phrases = ["Welcome to the AI Edge", "Welcome back", "Hello everyone"]
    for phrase in bad_phrases:
        if phrase.lower() in text.lower() and len(text) < 100:
            return "" 
            
    return text.strip()

def generate_silence(duration_ms):
    """Generates a silent audio segment."""
    return AudioSegment.silent(duration=duration_ms)

def generate_metadata(full_script_text):
    """Generates Title, Summary, Tags for Spotify."""
    prompt = """
    Generate JSON metadata for this podcast episode.
    - "title": Clickbait style, max 60 chars. (e.g., "Nvidia Crashes? + OpenAI's Secret")
    - "summary": 3 sentences, punchy.
    - "hashtags": #Tag1 #Tag2
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": full_script_text[:4000]}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def update_rss_feed(metadata, filename, file_size):
    """Updates feed.xml with Spotify Keys."""
    rss_path = Path("feed.xml")
    
    # Namespaces
    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ET.register_namespace("itunes", ITUNES_NS)
    
    if not rss_path.exists():
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
        ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
        ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
        ET.SubElement(channel, "language").text = "en-us"
        
        # Spotify/iTunes Owner Tags
        owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}name").text = RSS_SETTINGS["author"]
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = RSS_SETTINGS["email"]
        
        image = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        image.set("href", RSS_SETTINGS["image"])
        
        ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category", text=RSS_SETTINGS["category"])
        ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "no"
    else:
        tree = ET.parse(rss_path)
        root = tree.getroot()
        channel = root.find("channel")

    # Create New Item
    item = ET.Element("item")
    ET.SubElement(item, "title").text = metadata["title"]
    ET.SubElement(item, "description").text = metadata["summary"]
    ET.SubElement(item, "pubDate").text = formatdate(localtime=False, usegmt=True)
    ET.SubElement(item, "guid").text = f"{RSS_SETTINGS['link']}/{filename}"
    
    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", f"{RSS_SETTINGS['link']}/{filename}")
    enclosure.set("length", str(file_size))
    enclosure.set("type", "audio/mpeg")
    
    ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration").text = "20:00" # Approximate placeholder

    # Append to channel
    channel.append(item) 
    
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(rss_path, encoding="UTF-8", xml_declaration=True)
    print(" >> RSS Feed Updated.")

# --- 5. MAIN EXECUTION ---

def produce_episode(news_content, sponsor_msg="Sponsored by AI Simplify Media"):
    print("--- STARTING PLATINUM PRODUCTION ---")
    
    # 1. SETUP
    settings = get_show_settings()
    rufus_loc = get_rufus_location()
    print(f"Format: {settings['type']} ({settings['duration']}) | Loc: {rufus_loc}")
    
    audio_segments = []     
    full_script_text = ""
    
    # STATE FLAGS (Prevents Double Intro)
    has_played_intro = False 
    
    # LOAD ASSETS (Graceful Fallback)
    try:
        music_intro = AudioSegment.from_mp3(ASSETS_DIR / "intro.mp3")
    except:
        music_intro = AudioSegment.silent(duration=1000) 
        
    try:
        music_outro = AudioSegment.from_mp3(ASSETS_DIR / "outro.mp3")
    except:
        music_outro = AudioSegment.silent(duration=1000)

    # 2. GENERATE SEGMENTS
    for segment in settings['segments']:
        print(f" >> Processing Segment: {segment}")
        
        # A. Draft & Punch-Up
        draft = draft_segment(segment, news_content, settings, rufus_loc, sponsor_msg)
        final_script = punch_up_script(draft)
        full_script_text += f"\n{final_script}"
        
        # B. Voice Gen Loop
        lines = final_script.split('\n')
        for line in lines:
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker = match.group(1).upper()
                text = clean_text(match.group(2))
                if not text: continue
                
                # Generate Audio File
                temp_file = AUDIO_DIR / "temp_speech.mp3"
                client.audio.speech.create(
                    model="tts-1-hd", voice=VOICES[speaker], input=text
                ).stream_to_file(temp_file)
                
                # Convert to AudioSegment
                speech_segment = AudioSegment.from_mp3(temp_file)
                
                # ADD REALISM: 200ms silence between speakers
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

    # 4. METADATA
    print(" >> Generating Metadata...")
    meta = generate_metadata(full_script_text)
    with open("episode_metadata.json", "w") as f:
        json.dump(meta, f, indent=4)

    # 5. STITCH & EXPORT
    print(" >> Stitching Master File...")
    final_mix = AudioSegment.empty()
    for seg in audio_segments:
        final_mix += seg
        
    final_filename = f"podcast_{datetime.date.today()}.mp3"
    final_path = AUDIO_DIR / final_filename
    final_mix.export(final_path, format="mp3")
    
    # 6. RSS UPDATE
    print(" >> Updating RSS Feed...")
    file_size = os.path.getsize(final_path)
    update_rss_feed(meta, final_filename, file_size)

    print(f"\nDONE! Episode Ready: {final_path}")
    print(f"Title: {meta['title']}")

# --- RUN ---
if __name__ == "__main__":
    # Reads 'marketing.txt' as the news source.
    news_file = Path("marketing.txt")
    if news_file.exists():
        with open(news_file, "r") as f:
            news = f.read()
    else:
        news = "Discuss the latest trends in Artificial Intelligence and Robotics."
    
    # Fail-safe if file is empty
    if len(news) < 10:
         news = "Discuss the latest trends in Artificial Intelligence and Robotics."

    produce_episode(news)
