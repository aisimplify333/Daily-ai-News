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
ASSETS_DIR.mkdir(exist_ok=True)

# CAST VOICES
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
    "email": "aisimplifymedia@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.jpg",
    "category": "Technology"
}

# --- 2. FORMAT LOGIC (CAST CONTROL) ---

def get_show_settings():
    today = datetime.date.today()
    
    # YEAR END SPECIAL (45 Mins)
    if today.month == 12 and today.day >= 26:
        return {
            "type": "Year End Special",
            "tone": "Epic, reflective, cynical yet hopeful.",
            "duration": "45 min",
            "segments": [
                {"name": "HOOK", "words": 250, "cast": "ALEX_JAMIE"},
                {"name": "Q1_REVIEW", "words": 800, "cast": "ALEX_JAMIE"},
                {"name": "RUFUS_LAW_MONEY", "words": 800, "cast": "RUFUS_FOCUS"}, # Dedicated Segment
                {"name": "MID_ROLL", "words": 150, "cast": "JAMIE_SOLO"},
                {"name": "Q3_REVIEW", "words": 800, "cast": "ALEX_JAMIE"},
                {"name": "ROUND_TABLE_WRAP", "words": 1000, "cast": "ALL_THREE"}, # Rufus returns
                {"name": "OUTRO_VIRAL", "words": 150, "cast": "ALEX_SOLO"}
            ]
        }
    
    # WEEKEND DEEP DIVE (30 Mins)
    elif today.weekday() >= 5:
        return {
            "type": "Weekend Deep Dive",
            "tone": "Analytical, debate-heavy.",
            "duration": "30 min",
            "segments": [
                {"name": "HOOK", "words": 250, "cast": "ALEX_JAMIE"},
                {"name": "DEEP_DIVE_MAIN", "words": 1200, "cast": "ALEX_JAMIE"},
                {"name": "RUFUS_GLOBAL_MARKETS", "words": 800, "cast": "RUFUS_FOCUS"},
                {"name": "MID_ROLL", "words": 150, "cast": "JAMIE_SOLO"},
                {"name": "ROUND_TABLE_DEBATE", "words": 1000, "cast": "ALL_THREE"},
                {"name": "OUTRO_VIRAL", "words": 150, "cast": "ALEX_SOLO"}
            ]
        }
    
    # DAILY NEWS (20 Mins)
    else:
        return {
            "type": "Daily News Unfiltered",
            "tone": "Fast, aggressive.",
            "duration": "20 min",
            "segments": [
                {"name": "HOOK", "words": 200, "cast": "ALEX_JAMIE"},
                {"name": "TOP_STORY", "words": 800, "cast": "ALEX_JAMIE"},
                {"name": "RUFUS_FIELD_REPORT", "words": 600, "cast": "RUFUS_FOCUS"},
                {"name": "MID_ROLL", "words": 150, "cast": "JAMIE_SOLO"},
                {"name": "SECONDARY_STORY", "words": 600, "cast": "ALEX_JAMIE"},
                {"name": "SPEED_ROUND_WRAP", "words": 500, "cast": "ALL_THREE"},
                {"name": "OUTRO_VIRAL", "words": 150, "cast": "ALEX_SOLO"}
            ]
        }

def get_rufus_location():
    return random.choice(["London", "The City of London", "Canary Wharf", "Zurich", "Hong Kong", "Singapore"])

def load_sponsor():
    try:
        with open("sponsors.json", "r") as f:
            data = json.load(f)
            return random.choice(data.get("sponsors", []))["read_copy"]
    except:
        return "This episode is sponsored by AI Simplify Media."

# --- 3. THE WRITER (CAST ISOLATION) ---

def draft_segment(segment_data, news_context, settings, rufus_loc, sponsor_txt):
    seg_name = segment_data["name"]
    cast_mode = segment_data["cast"]
    min_words = segment_data["words"]
    
    # CONSTRUCT CAST PROMPT BASED ON MODE
    if cast_mode == "ALEX_JAMIE":
        cast_prompt = """
        **CAST:** ALEX (Host) and JAMIE (Cynic).
        **RULE:** RUFUS IS NOT HERE. DO NOT WRITE LINES FOR RUFUS.
        """
    elif cast_mode == "RUFUS_FOCUS":
        cast_prompt = f"""
        **CAST:** ALEX (Toss) and RUFUS (Main Speaker).
        **CONTEXT:** Alex throws to Rufus in {rufus_loc}.
        **CONTENT:** Rufus discusses LAW, MONEY, and REGULATION. He uses British syntax.
        """
    elif cast_mode == "ALL_THREE":
        cast_prompt = f"""
        **CAST:** ALEX, JAMIE, and RUFUS.
        **CONTEXT:** Group discussion/Wrap up. Rufus joins from {rufus_loc}.
        """
    elif cast_mode == "ALEX_SOLO": # Outro
        cast_prompt = """
        **CAST:** ALEX Only.
        **GOAL:** Dramatic Sign-off.
        """
    elif cast_mode == "JAMIE_SOLO": # Mid-Roll
        cast_prompt = """
        **CAST:** JAMIE Only.
        **GOAL:** Read Sponsor Ad naturally.
        """

    # OUTRO SPECIFIC INSTRUCTION
    outro_instruction = ""
    if "OUTRO" in seg_name:
        outro_instruction = """
        **CRITICAL INSTRUCTION:** Alex must end with a Call to Action. 
        "Share this podcast. It is critical that your friends understand where the world is moving. Help us grow."
        Make it sound DRAMATIC and URGENT.
        """

    system_prompt = f"""
    You are the Writer for 'The AI Edge'. Write the **{seg_name}** segment.
    **LENGTH:** Write at least **{min_words} words**.
    
    {cast_prompt}
    
    **TONE:** {settings['tone']}
    {outro_instruction}
    **SPONSOR (If applicable):** {sponsor_txt}
    
    **FORMAT:** ALEX: [Text] / JAMIE: [Text] / RUFUS: [Text]
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Write segment: {seg_name}. News Context: {news_context[:3000]}"}
        ]
    )
    return response.choices[0].message.content

def punch_up_script(draft_script):
    """The Realism Engine."""
    system_prompt = """
    You are a Script Doctor.
    1. **RUFUS (IF PRESENT):** British Syntax ("Rubbish", "Indeed", "The Exchequer"). Dry/Formal.
    2. **JAMIE:** Rude interruptions (use "--").
    3. **REMOVE METADATA:** Delete "Welcome to the show" lines.
    4. **KEEP FORMAT:** ALEX:/JAMIE:/RUFUS:
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": draft_script}],
        temperature=0.9
    )
    return response.choices[0].message.content

# --- 4. PRODUCTION ENGINE ---

def clean_text(text):
    text = text.replace('**', '').replace('*', '')
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    bad = ["Welcome to the AI Edge", "Welcome back"]
    for b in bad:
        if b.lower() in text.lower() and len(text) < 100: return ""
    return text.strip()

def generate_silence(duration_ms):
    return AudioSegment.silent(duration=duration_ms)

def produce_episode(news_content):
    print("--- STARTING GOLD MASTER PRODUCTION ---")
    settings = get_show_settings()
    rufus_loc = get_rufus_location()
    sponsor_msg = load_sponsor()
    
    print(f"Format: {settings['type']} | Loc: {rufus_loc}")
    
    audio_segments = []
    full_script_text = ""
    has_played_intro = False
    
    # LOAD ASSETS
    try:
        music_intro = AudioSegment.from_mp3(ASSETS_DIR / "intro.mp3")
        music_outro = AudioSegment.from_mp3(ASSETS_DIR / "outro.mp3")
    except:
        music_intro = AudioSegment.silent(duration=1000)
        music_outro = AudioSegment.silent(duration=1000)

    # SEGMENT LOOP
    for segment in settings['segments']:
        print(f" >> Processing {segment['name']} ({segment['cast']})...")
        
        # Draft & Punch-Up
        draft = draft_segment(segment, news_content, settings, rufus_loc, sponsor_msg)
        final_script = punch_up_script(draft)
        full_script_text += f"\n{final_script}"
        
        # Voice Gen
        lines = final_script.split('\n')
        for line in lines:
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker = match.group(1).upper()
                text = clean_text(match.group(2))
                if not text: continue
                
                # Audio Gen
                temp_file = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=VOICES[speaker], input=text).stream_to_file(temp_file)
                seg = AudioSegment.from_mp3(temp_file)
                
                audio_segments.append(seg)
                audio_segments.append(generate_silence(200)) # 0.2s Breath

        # INSERT INTRO (After Hook)
        if segment["name"] == "HOOK" and not has_played_intro:
            print(" >> Injecting Intro Sequence...")
            audio_segments.append(music_intro)
            
            fixed_intro_path = AUDIO_DIR / "fixed_intro.mp3"
            if not fixed_intro_path.exists():
                client.audio.speech.create(model="tts-1-hd", voice=VOICES["ALEX"], input=INTRO_TEXT).stream_to_file(fixed_intro_path)
            
            audio_segments.append(AudioSegment.from_mp3(fixed_intro_path))
            audio_segments.append(generate_silence(500))
            has_played_intro = True

    # OUTRO
    audio_segments.append(music_outro)
    
    # EXPORT
    print(" >> Stitching...")
    final_mix = sum(audio_segments)
    final_name = f"podcast_{datetime.date.today()}.mp3"
    final_path = AUDIO_DIR / final_name
    final_mix.export(final_path, format="mp3")
    
    # METADATA & RSS
    print(" >> Metadata & RSS...")
    meta = generate_metadata(full_script_text)
    update_rss_feed(meta, final_name, os.path.getsize(final_path))
    
    # Save Metadata JSON
    with open("episode_metadata.json", "w") as f:
        json.dump(meta, f, indent=4)
        
    print(f"DONE: {final_path}")

# --- HELPERS ---
def generate_metadata(text):
    prompt = 'Generate JSON: {"title": "Clickbait Title", "summary": "2 sentences", "hashtags": "#tag"}'
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content": f"{prompt}\n{text[:3000]}"}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def update_rss_feed(meta, fname, fsize):
    rss_path = Path("feed.xml")
    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    ET.register_namespace("itunes", ITUNES_NS)
    
    if not rss_path.exists():
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
        ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
        ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
        ET.SubElement(channel, "language").text = "en-us"
        owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}name").text = RSS_SETTINGS["author"]
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = RSS_SETTINGS["email"]
        image = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        image.set("href", RSS_SETTINGS["image"])
        ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category", text=RSS_SETTINGS["category"])
    else:
        tree = ET.parse(rss_path)
        root = tree.getroot()
        channel = root.find("channel")

    item = ET.Element("item")
    ET.SubElement(item, "title").text = meta["title"]
    ET.SubElement(item, "description").text = meta["summary"]
    ET.SubElement(item, "pubDate").text = formatdate(localtime=False, usegmt=True)
    ET.SubElement(item, "guid").text = f"{RSS_SETTINGS['link']}/{fname}"
    
    encl = ET.SubElement(item, "enclosure")
    encl.set("url", f"{RSS_SETTINGS['link']}/{fname}")
    encl.set("length", str(fsize))
    encl.set("type", "audio/mpeg")
    
    channel.append(item)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(rss_path, encoding="UTF-8", xml_declaration=True)

if __name__ == "__main__":
    news_file = Path("marketing.txt")
    if news_file.exists():
        with open(news_file, "r") as f: news = f.read()
    else:
        news = "AI News: Discuss trends."
    
    produce_episode(news)
