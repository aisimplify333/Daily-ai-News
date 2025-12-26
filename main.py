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
    "RUFUS": "fable"  # Correspondent
}

# BRANDING
INTRO_TEXT = "Welcome to the AI Edge. Unpacking the systems shaping our future. Introducing Alex, Jamie, and Rufus."

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Deep dives into AI, Technology, and the Future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.jpg",
    "category": "Technology"
}

# --- 2. FORMAT LOGIC (DEBUG MODE: LOW WORD COUNTS) ---

def get_show_settings():
    today = datetime.date.today()
    
    # DEBUG SETTINGS: All word counts set to ~75-100 to save money while testing structure.
    # Once structure is perfect, increase these to 1200+
    
    return {
        "type": "Daily News (Debug Mode)",
        "tone": "Hard-hitting, analytical, fast-paced.",
        "duration": "Test Run",
        "segments": [
            # 1. THE HOOK: Must be a Hot Clip. No Intro.
            {"name": "HOOK", "words": 75, "cast": "ALEX_JAMIE", "transition": False},
            
            # 2. MAIN STORY: Alex & Jamie
            {"name": "TOP_STORY_MECHANISMS", "words": 150, "cast": "ALEX_JAMIE", "transition": False},
            
            # 3. RUFUS: Remote Report (Transition Sting plays before this)
            {"name": "RUFUS_MARKETS_LAW", "words": 100, "cast": "RUFUS_FOCUS", "transition": True},
            
            # 4. MID ROLL: Jamie Solo (Transition Sting plays before this)
            {"name": "MID_ROLL", "words": 50, "cast": "JAMIE_SOLO", "transition": True},
            
            # 5. WRAP UP: All Three
            {"name": "SPEED_ROUND_WRAP", "words": 100, "cast": "ALL_THREE", "transition": True},
            
            # 6. OUTRO: Viral CTA
            {"name": "OUTRO_VIRAL", "words": 50, "cast": "ALEX_SOLO", "transition": False}
        ]
    }

def get_rufus_location():
    return random.choice(["London", "Canary Wharf", "Zurich", "Hong Kong"])

def load_sponsor():
    sponsor_path = BASE_DIR / "sponsors.json"
    try:
        if not sponsor_path.exists(): return "Sponsored by AI Simplify Media."
        with open(sponsor_path, "r") as f:
            data = json.load(f)
        if "sponsors" in data and data["sponsors"]:
            return random.choice(data["sponsors"])["read_copy"]
    except:
        return "Sponsored by AI Simplify Media."
    return "Sponsored by AI Simplify Media."

def check_assets():
    """Verifies music files exist before spending money."""
    required = ["intro.mp3", "outro.mp3", "transition.mp3"]
    print("--- ASSET CHECK ---")
    all_good = True
    for f in required:
        path = ASSETS_DIR / f
        if path.exists():
            print(f" [OK] Found {f}")
        else:
            print(f" [MISSING] {f} - Will use silence fallback.")
            all_good = False
    return all_good

# --- 3. THE WRITER (HOT CLIP LOGIC) ---

def draft_segment(segment_data, news_context, settings, rufus_loc, sponsor_txt):
    seg_name = segment_data["name"]
    cast_mode = segment_data["cast"]
    min_words = segment_data["words"]
    
    # --- SPECIAL LOGIC: THE HOT CLIP HOOK ---
    if seg_name == "HOOK":
        system_prompt = f"""
        You are the Producer. Write the **COLD OPEN HOOK**.
        
        **CRITICAL INSTRUCTION:** - This must sound like a **HOT CLIP** pulled from the middle of a heated debate.
        - **DO NOT** introduce the show. **DO NOT** say "Hello" or "Welcome."
        - Start **MID-ARGUMENT**. High energy. Shocking statement.
        - Example: 
          ALEX: "...but the data proves it's safe!" 
          JAMIE: "--The data is faked, Alex! You can't just ignore the bodies!"
        
        **CONTEXT:** Use the most shocking part of this news: {news_context[:500]}
        **FORMAT:** ALEX: [Text] / JAMIE: [Text]
        """
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}])
        return response.choices[0].message.content

    # --- STANDARD LOGIC FOR REST OF SHOW ---
    
    if cast_mode == "ALEX_JAMIE":
        cast_prompt = "**CAST:** ALEX and JAMIE. (NO RUFUS)."
    elif cast_mode == "RUFUS_FOCUS":
        cast_prompt = f"**CAST:** ALEX (Toss) and RUFUS (Main). Alex throws to Rufus in {rufus_loc}."
    elif cast_mode == "ALL_THREE":
        cast_prompt = f"**CAST:** ALEX, JAMIE, RUFUS. Group discussion."
    elif cast_mode == "ALEX_SOLO":
        cast_prompt = "**CAST:** ALEX Only."
    elif cast_mode == "JAMIE_SOLO":
        cast_prompt = "**CAST:** JAMIE Only."

    outro_instr = ""
    if "OUTRO" in seg_name:
        outro_instr = "ALEX: Dramatic Call to Action. Tell them to share this podcast to save humanity."

    system_prompt = f"""
    Write the **{seg_name}** segment.
    **LENGTH:** Keep it tight (~{min_words} words).
    {cast_prompt}
    **TONE:** {settings['tone']}
    {outro_instr}
    **SPONSOR:** {sponsor_txt}
    **FORMAT:** ALEX: [Text] / JAMIE: [Text] / RUFUS: [Text]
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Write segment: {seg_name}. Context: {news_context[:2000]}"}
        ]
    )
    return response.choices[0].message.content

def punch_up_script(draft_script):
    system_prompt = """
    Script Doctor. 
    1. **RUFUS:** British Syntax ("Rubbish", "Indeed").
    2. **JAMIE:** Interruptions ("--").
    3. **REMOVE:** Any "Welcome to the show" lines.
    """
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": draft_script}], temperature=0.9)
    return response.choices[0].message.content

# --- 4. PRODUCTION ENGINE ---

def clean_text(text):
    """The Welcome Assassin."""
    text = text.replace('**', '').replace('*', '')
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    
    # KILL LIST
    bad_phrases = ["Welcome to the AI Edge", "Welcome back", "Techtonic Shifts", "Hello listeners", "Hi everyone", "Welcome to the show"]
    for phrase in bad_phrases:
        if phrase.lower() in text.lower() and len(text) < 100:
            return "" 
            
    return text.strip()

def generate_silence(duration_ms):
    return AudioSegment.silent(duration=duration_ms)

def produce_episode(news_content):
    print("--- STARTING DEBUG PRODUCTION ---")
    check_assets()
    settings = get_show_settings()
    rufus_loc = get_rufus_location()
    sponsor_msg = load_sponsor()
    
    audio_segments = []
    full_script_text = ""
    
    # LOAD ASSETS
    try:
        music_intro = AudioSegment.from_mp3(ASSETS_DIR / "intro.mp3")
        music_outro = AudioSegment.from_mp3(ASSETS_DIR / "outro.mp3")
        sfx_transition = AudioSegment.from_mp3(ASSETS_DIR / "transition.mp3") - 3
    except:
        print(" >> [WARN] Assets missing. Using silence.")
        music_intro = AudioSegment.silent(duration=1000)
        music_outro = AudioSegment.silent(duration=1000)
        sfx_transition = AudioSegment.silent(duration=500)

    # SEGMENT LOOP
    for segment in settings['segments']:
        seg_name = segment['name']
        print(f" >> Processing {seg_name}...")
        
        # 1. TRANSITION STING
        if segment.get("transition", False):
            print(f"    --> [SFX] Transition Sting")
            audio_segments.append(sfx_transition)
            audio_segments.append(generate_silence(500))

        # 2. GENERATE AUDIO
        draft = draft_segment(segment, news_content, settings, rufus_loc, sponsor_msg)
        final_script = punch_up_script(draft)
        full_script_text += f"\n{final_script}"
        
        lines = final_script.split('\n')
        for line in lines:
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker = match.group(1).upper()
                text = clean_text(match.group(2))
                if not text: continue
                
                # Verify length to save money (Double check)
                if len(text) > 1000: text = text[:1000] 
                
                temp_file = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=VOICES[speaker], input=text).stream_to_file(temp_file)
                seg = AudioSegment.from_mp3(temp_file)
                audio_segments.append(seg)
                audio_segments.append(generate_silence(200))

        # 3. COLD OPEN LOGIC (The Hook)
        if seg_name == "HOOK":
            print(" >> ⚡ INJECTING COLD OPEN SEQUENCE ⚡")
            audio_segments.append(generate_silence(500)) # Breath
            audio_segments.append(music_intro)           # MUSIC START
            
            fixed_intro_path = AUDIO_DIR / "fixed_intro.mp3"
            if not fixed_intro_path.exists():
                client.audio.speech.create(model="tts-1-hd", voice=VOICES["ALEX"], input=INTRO_TEXT).stream_to_file(fixed_intro_path)
            audio_segments.append(AudioSegment.from_mp3(fixed_intro_path)) # "Welcome to AI Edge"
            
            audio_segments.append(generate_silence(1000)) # Dramatic Pause

    # OUTRO
    print(" >> Adding Outro Music...")
    audio_segments.append(music_outro)
    
    # EXPORT
    print(" >> Stitching...")
    final_mix = sum(audio_segments)
    final_name = f"podcast_{datetime.date.today()}.mp3"
    final_path = AUDIO_DIR / final_name
    final_mix.export(final_path, format="mp3")
    
    # METADATA
    print(" >> Metadata & RSS...")
    meta = generate_metadata(full_script_text)
    update_rss_feed(meta, final_name, os.path.getsize(final_path))
    
    print(f"DONE: {final_path}")

# --- HELPERS ---
def generate_metadata(text):
    prompt = 'Generate JSON: {"title": "Clickbait Title", "summary": "Short summary", "hashtags": "#tag"}'
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content": f"{prompt}\n{text[:2000]}"}], response_format={"type": "json_object"})
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
        owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}name").text = RSS_SETTINGS["author"]
        ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = RSS_SETTINGS["email"]
        image = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        image.set("href", RSS_SETTINGS["image"])
    else:
        tree = ET.parse(rss_path)
        root = tree.getroot()
        channel = root.find("channel")
    item = ET.Element("item")
    ET.SubElement(item, "title").text = meta["title"]
    ET.SubElement(item, "description").text = meta["summary"]
    ET.SubElement(item, "pubDate").text = formatdate(localtime=False, usegmt=True)
    encl = ET.SubElement(item, "enclosure")
    encl.set("url", f"{RSS_SETTINGS['link']}/{fname}")
    encl.set("length", str(fsize))
    encl.set("type", "audio/mpeg")
    channel.insert(0, item) # Insert at top
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
