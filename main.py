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
    "ALEX": "onyx",   # Anchor: Deep, Huberman-style gravitas
    "JAMIE": "nova",  # Disruptor: Skeptical, Diary of a CEO interviewer style
    "RUFUS": "fable"  # Correspondent: British, Institutional
}

# BRANDING
INTRO_TEXT = "Welcome to the AI Edge. Unpacking the systems shaping our future. Introducing Alex, Jamie, and Rufus."

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Deep dives into AI, Technology, and the Future of the Human Experience.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.jpg",
    "category": "Technology"
}

# --- 2. FORMAT LOGIC (DURATION, DEPTH & SFX) ---

def get_show_settings():
    today = datetime.date.today()
    
    # YEAR END SPECIAL (Target: 45 Mins)
    if today.month == 12 and today.day >= 26:
        return {
            "type": "Year End Special",
            "tone": "Epic, existential, historical analysis. Focus on the trajectory of the human species.",
            "duration": "45 min",
            "segments": [
                {"name": "HOOK", "words": 300, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "Q1_DEEP_ANALYSIS", "words": 1500, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "RUFUS_MACRO_ECONOMICS", "words": 1000, "cast": "RUFUS_FOCUS", "transition": True}, # <--- SFX
                {"name": "MID_ROLL", "words": 200, "cast": "JAMIE_SOLO", "transition": True},
                {"name": "Q3_SOCIETAL_IMPACT", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "FUTURE_PREDICTIONS", "words": 1500, "cast": "ALL_THREE", "transition": False},
                {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
            ]
        }
    
    # WEEKEND DEEP DIVE (Target: 30 Mins)
    elif today.weekday() >= 5:
        return {
            "type": "Weekend Deep Dive",
            "tone": "Philosophical, debate-heavy. 'Diary of a CEO' style depth.",
            "duration": "30 min",
            "segments": [
                {"name": "HOOK", "words": 300, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "MAIN_TOPIC_DEEP_DIVE", "words": 1800, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "RUFUS_LONDON_REPORT", "words": 1000, "cast": "RUFUS_FOCUS", "transition": True}, # <--- SFX
                {"name": "MID_ROLL", "words": 200, "cast": "JAMIE_SOLO", "transition": True},
                {"name": "ETHICAL_DEBATE", "words": 1500, "cast": "ALL_THREE", "transition": True},
                {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
            ]
        }
    
    # DAILY NEWS (Target: 20 Mins)
    else:
        return {
            "type": "Daily News Unfiltered",
            "tone": "Hard-hitting, analytical, fast-paced but deep.",
            "duration": "20 min",
            "segments": [
                {"name": "HOOK", "words": 300, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "TOP_STORY_MECHANISMS", "words": 1200, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "RUFUS_MARKETS_LAW", "words": 800, "cast": "RUFUS_FOCUS", "transition": True}, # <--- SFX
                {"name": "MID_ROLL", "words": 200, "cast": "JAMIE_SOLO", "transition": True},
                {"name": "SECONDARY_STORY_IMPACT", "words": 1000, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "SPEED_ROUND_WRAP", "words": 600, "cast": "ALL_THREE", "transition": True},
                {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
            ]
        }

def get_rufus_location():
    return random.choice(["London", "The City of London", "Canary Wharf", "Zurich", "Hong Kong", "Singapore"])

def load_sponsor():
    """Robust Sponsor Loader."""
    sponsor_path = BASE_DIR / "sponsors.json"
    try:
        if not sponsor_path.exists():
            print(f" >> [WARN] No sponsors.json found at {sponsor_path}")
            return "This episode is brought to you by AI Simplify Media. Future-proofing your business."
        
        with open(sponsor_path, "r") as f:
            data = json.load(f)
            
        if "sponsors" in data and data["sponsors"]:
            choice = random.choice(data["sponsors"])
            print(f" >> [SPONSOR] Loaded: {choice['name']}")
            return choice["read_copy"]
        else:
            return "This episode is brought to you by AI Simplify Media."
    except Exception as e:
        print(f" >> [ERROR] Sponsor load failed: {e}")
        return "This episode is brought to you by AI Simplify Media."

# --- 3. THE WRITER (THE "HUBERMAN" ENGINE) ---

def draft_segment(segment_data, news_context, settings, rufus_loc, sponsor_txt):
    seg_name = segment_data["name"]
    cast_mode = segment_data["cast"]
    min_words = segment_data["words"]
    
    # CAST RULES
    if cast_mode == "ALEX_JAMIE":
        cast_prompt = "**CAST:** ALEX and JAMIE. (NO RUFUS). focus on dialogue and debate."
    elif cast_mode == "RUFUS_FOCUS":
        cast_prompt = f"**CAST:** ALEX (Toss) and RUFUS (Main). Alex throws to Rufus in {rufus_loc}. Rufus covers MONEY/LAW."
    elif cast_mode == "ALL_THREE":
        cast_prompt = f"**CAST:** ALEX, JAMIE, RUFUS. Group discussion."
    elif cast_mode == "ALEX_SOLO":
        cast_prompt = "**CAST:** ALEX Only."
    elif cast_mode == "JAMIE_SOLO":
        cast_prompt = "**CAST:** JAMIE Only."

    # STYLE INSTRUCTIONS (The "Huberman/CEO" Layer)
    style_prompt = """
    **STYLE GUIDE (CRITICAL):**
    - Do NOT just report the news. Analyze the **MECHANISMS** and **PSYCHOLOGY**.
    - Be like **Andrew Huberman** or **Steven Bartlett (Diary of a CEO)**: Go deep. Ask "Why does this matter to the human species?"
    - Use "First Principles" thinking. 
    - **ALEX:** Intellectual, deep, structured.
    - **JAMIE:** Existential, skeptical, focuses on the human cost.
    - **RUFUS:** Institutional, cynical, focuses on the money flow.
    """

    # OUTRO INSTRUCTION
    outro_instr = ""
    if "OUTRO" in seg_name:
        outro_instr = """
        **OUTRO GOAL:** Alex must give a 'Huberman-style' protocol or takeaway. 
        Then, a DRAMATIC Call to Action: "If you want to understand the future, you must share this show. Help us build the signal in the noise."
        """

    system_prompt = f"""
    You are the Showrunner for 'The AI Edge'. Write the **{seg_name}** segment.
    **TARGET LENGTH:** You MUST write at least **{min_words} words**. Go DEEP. Expand on every point.
    
    {cast_prompt}
    {style_prompt}
    
    **TONE:** {settings['tone']}
    {outro_instr}
    **SPONSOR (If applicable):** {sponsor_txt}
    
    **FORMAT:** ALEX: [Text] / JAMIE: [Text] / RUFUS: [Text]
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Write segment: {seg_name}. Base content: {news_context[:4000]}"}
        ]
    )
    return response.choices[0].message.content

def punch_up_script(draft_script):
    """The Realism Engine."""
    system_prompt = """
    You are a Script Doctor.
    1. **RUFUS:** British Syntax ("Rubbish", "Indeed", "The Exchequer", "Old boy").
    2. **JAMIE:** Interruptions ("--"). Cynical tone.
    3. **ALEX:** Deep voice of reason.
    4. **REMOVE:** Any "Welcome to the show" lines (The code handles the intro).
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": draft_script}],
        temperature=0.9
    )
    return response.choices[0].message.content

# --- 4. PRODUCTION ENGINE (SFX & LAYERING) ---

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
    print("--- STARTING PLATINUM PRODUCTION ---")
    settings = get_show_settings()
    rufus_loc = get_rufus_location()
    sponsor_msg = load_sponsor()
    
    print(f"Format: {settings['type']} | Duration Target: {settings['duration']}")
    
    audio_segments = []
    full_script_text = ""
    
    # LOAD ASSETS (Robust)
    try:
        music_intro = AudioSegment.from_mp3(ASSETS_DIR / "intro.mp3")
        music_outro = AudioSegment.from_mp3(ASSETS_DIR / "outro.mp3")
        # Load Transition
        sfx_transition = AudioSegment.from_mp3(ASSETS_DIR / "transition.mp3")
        sfx_transition = sfx_transition - 3 # Reduce volume slightly
    except:
        print(" >> [WARN] Assets missing. Using silence fallback.")
        music_intro = AudioSegment.silent(duration=1000)
        music_outro = AudioSegment.silent(duration=1000)
        sfx_transition = AudioSegment.silent(duration=500)

    # SEGMENT LOOP
    for segment in settings['segments']:
        seg_name = segment['name']
        print(f" >> Processing {seg_name} ({segment['words']} words)...")
        
        # 1. INSERT TRANSITION STING (If Flagged)
        if segment.get("transition", False):
            print(f"    --> [SFX] Inserting Transition Sting")
            audio_segments.append(sfx_transition)
            audio_segments.append(generate_silence(500))

        # 2. Draft & Punch-Up
        draft = draft_segment(segment, news_content, settings, rufus_loc, sponsor_msg)
        final_script = punch_up_script(draft)
        full_script_text += f"\n{final_script}"
        
        # 3. Voice Gen
        lines = final_script.split('\n')
        for line in lines:
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker = match.group(1).upper()
                text = clean_text(match.group(2))
                if not text: continue
                
                temp_file = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=VOICES[speaker], input=text).stream_to_file(temp_file)
                seg = AudioSegment.from_mp3(temp_file)
                audio_segments.append(seg)
                audio_segments.append(generate_silence(200)) # 0.2s Breath

        # 4. THE THUNDERBOLT: FORCE INTRO SEQUENCE (After Hook)
        if seg_name == "HOOK":
            print(" >> ⚡ INJECTING COLD OPEN SEQUENCE ⚡")
            
            # Silence -> Intro Music -> Fixed Voice -> Silence
            audio_segments.append(generate_silence(500))
            audio_segments.append(music_intro)
            
            fixed_intro_path = AUDIO_DIR / "fixed_intro.mp3"
            if not fixed_intro_path.exists():
                client.audio.speech.create(model="tts-1-hd", voice=VOICES["ALEX"], input=INTRO_TEXT).stream_to_file(fixed_intro_path)
            audio_segments.append(AudioSegment.from_mp3(fixed_intro_path))
            
            audio_segments.append(generate_silence(1000))

    # OUTRO
    audio_segments.append(music_outro)
    
    # EXPORT
    print(" >> Stitching Master File...")
    final_mix = sum(audio_segments)
    final_name = f"podcast_{datetime.date.today()}.mp3"
    final_path = AUDIO_DIR / final_name
    final_mix.export(final_path, format="mp3")
    
    # METADATA & RSS
    print(" >> Metadata & RSS...")
    meta = generate_metadata(full_script_text)
    update_rss_feed(meta, final_name, os.path.getsize(final_path))
    
    with open("episode_metadata.json", "w") as f:
        json.dump(meta, f, indent=4)
        
    print(f"DONE: {final_path}")

# --- HELPERS ---

def generate_metadata(text):
    prompt = 'Generate JSON: {"title": "Clickbait Title", "summary": "Deep, 3-sentence summary", "hashtags": "#tag"}'
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
        news = "Discuss the existential impact of Artificial Intelligence on the human condition."
    
    produce_episode(news)
