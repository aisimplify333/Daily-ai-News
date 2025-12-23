import subprocess
import sys

# --- STEP 0: INSTALL SDK ---
def install_sdk():
    try:
        print("Installing Google GenAI SDK...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai"])
    except Exception as e:
        print(f"Install error: {e}")

install_sdk()

# --- IMPORTS ---
import os
import random
import re
import json
import feedparser
import datetime
import xml.etree.ElementTree as ET 
from email.utils import formatdate
from pydub import AudioSegment
from openai import OpenAI

# Try importing the new library
try:
    from google import genai
except ImportError:
    print("Retrying import...")
    from google import genai

# --- CONFIGURATION ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"  
AUTHOR_NAME = "AI Simplify Media (Alex, Jamie & Rufus)" 

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theregister.com/software/ai_ml/headlines.atom", 
    "https://hnrss.org/newest?q=AI",  
    "https://www.reddit.com/r/ArtificialInteligence/top/.rss?t=day",
    "https://futurism.com/feed",
    "https://garymarcus.substack.com/feed",
    "https://www.wired.com/feed/category/ai/latest/rss"
]

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# --- DATE FIX: Explicitly calculate the Weekday String ---
TODAY = datetime.date.today()
# Formats as "Tuesday, December 23, 2025" so the AI never guesses wrong
TODAY_STR = TODAY.strftime("%A, %B %d, %Y")

OUTPUT_FILE = f"podcast_{TODAY}.mp3"
NOTES_FILE = f"podcast_{TODAY}.txt" 
SPONSORS_FILE = "sponsors.json"

# --- HELPER: GET SPONSOR ---
def get_sponsor():
    if not os.path.exists(SPONSORS_FILE): return None
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                return random.choice(data)
    except: return None
    return None

# --- HELPER: GET NEWS (ELASTIC CAPACITY) ---
def get_latest_news(limit_per_feed=5, total_limit=25):
    print(f"Scanning web for AI news (Limit: {total_limit} items)...")
    news_items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=headers['User-Agent'])
            if not feed.entries: continue
            for entry in feed.entries[:limit_per_feed]: 
                summary = re.sub('<[^<]+?>', '', entry.summary if 'summary' in entry else entry.title)
                news_items.append(f"Source: {feed.feed.title}. Headline: {entry.title}. Details: {summary[:600]}")
        except: pass
    
    if not news_items: return None
    random.shuffle(news_items)
    return "\n\n".join(news_items[:total_limit]) 

# --- SMART CALENDAR & LENGTH LOGIC ---
def get_episode_config():
    weekday = TODAY.weekday()
    month = TODAY.month
    day = TODAY.day
    
    config = {
        "type": "DAILY_NEWS",
        "length_str": "20 Minutes",
        "min_words": "3500",
        "fetch_limit": 5,   
        "total_items": 25,  
        "focus": "Fast-paced, covering today's headlines. 'Man on the Street' reports from Rufus."
    }
    
    # Holiday Logic (45 Mins)
    if (month == 12 and day >= 24) or (month == 1 and day == 1): 
        config["type"] = "HOLIDAY_SPECIAL"
        config["length_str"] = "45 Minutes"
        config["min_words"] = "8000"
        config["fetch_limit"] = 10  
        config["total_items"] = 50  
        config["focus"] = "END OF YEAR SPECTACULAR. Use your INTERNAL KNOWLEDGE + news. Nostalgic, dramatic, comprehensive."
        return config

    # Weekend Logic (30 Mins)
    if weekday == 5: # Saturday
        config["type"] = "WEEKLY_RECAP"
        config["length_str"] = "30 Minutes"
        config["min_words"] = "5000"
        config["fetch_limit"] = 7
        config["total_items"] = 35
        config["focus"] = "SATURDAY EDITION. Synthesize these stories. Rufus provides 'Weekend Market Analysis' from the street."
        return config
        
    if weekday == 6: # Sunday
        config["type"] = "DEEP_DIVE"
        config["length_str"] = "30 Minutes"
        config["min_words"] = "5000"
        config["fetch_limit"] = 7
        config["total_items"] = 35
        config["focus"] = "SUNDAY DEEP DIVE. Pick ONLY ONE major theme. Debate it. Rufus provides the legal/money angle."
        return config
    
    return config

# --- GENERATION WITH RETRY ---
def generate_content_with_retry(client, prompt):
    model_priority = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
    for model_name in model_priority:
        print(f"Attempting generation with model: {model_name}...")
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text
        except Exception as e:
            print(f"❌ Error with {model_name}: {e}")
            continue
    return None

# --- MAIN SCRIPT GENERATOR ---
def generate_script(config, sponsor):
    if not GEMINI_API_KEY: return None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except: return None

    raw_news = get_latest_news(config["fetch_limit"], config["total_items"])
    if not raw_news: return None

    sponsor_txt = "our amazing sponsors"
    if sponsor:
        sponsor_txt = f"{sponsor.get('name')} - {sponsor.get('copy')}"

    print(f"--- EPISODE TYPE: {config['type']} | TARGET: {config['length_str']} ---")

    prompt = f"""
    You are the Showrunner for "The AI Edge" (AI Simplify Media).
    Current Date: {TODAY_STR}.
    Episode Type: {config['type']}.
    Target Length: {config['length_str']} (Minimum {config['min_words']} Words).
    Focus: {config['focus']}
    
    CHARACTERS:
    1. ALEX (Host): Optimistic, professional American. Uses fillers ("Look," "I mean,").
    2. JAMIE (Co-host): Skeptical, interrupts often. Uses short sentences.
    3. RUFUS (Correspondent): BRITISH ACCENT. Law & Money Expert. Dry wit.
       - **STYLE:** Rufus is "Man on the Street". He reports from "outside the courthouse" or "Wall Street". 
       - **SOUND:** Formal but cynical. Uses British terms ("Rubbish," "Scheme," "Proper").

    INSTRUCTIONS:
    - **DYNAMISM:** Write messy! Real people interrupt. Use "Hang on," "Wait," "Exactly."
    - **STRUCTURE:** Alex & Jamie debate in the studio. They MUST "throw it over" to Rufus in the field MULTIPLE TIMES (3-4 times).
    - **RUFUS INTERACTION:** Don't just give Rufus one block. Go back and forth. 
      (e.g., Alex: "Rufus, what's the legal take?" -> Rufus replies -> Jamie argues -> Rufus replies).
    - **CLEAN DIALOGUE:** **DO NOT** write stage directions in the spoken text (e.g. do NOT write "(laughs)" or "in a dry tone"). Only write what they SAY.
    
    - **OUTPUT FORMAT:** 1. First, write the SHOW NOTES (Clean format).
      2. Then write "|||SEPARATOR|||"
      3. Then write the SCRIPT.
    
    SHOW NOTES FORMAT:
    Title: [Catchy Title]
    Summary: [2-3 sentences hooking the listener]
    
    SCRIPT FORMAT:
    ALEX: (text) / JAMIE: (text) / RUFUS: (text)

    RAW NEWS INPUT:
    {raw_news}
    """
    
    full_response = generate_content_with_retry(client, prompt)
    if not full_response: return None
    
    if "|||SEPARATOR|||" in full_response:
        parts = full_response.split("|||SEPARATOR|||")
        
        # --- CLEAN SHOW NOTES ---
        raw_notes = parts[0].strip()
        clean_notes = re.sub(r'^[\*#]*SHOW NOTES.*$', '', raw_notes, flags=re.MULTILINE | re.IGNORECASE)
        clean_notes = re.sub(r'FORMAT:', '', clean_notes, flags=re.IGNORECASE).strip()
        
        with open(NOTES_FILE, "w") as f:
            f.write(clean_notes)
            
        return parts[1].strip()
    else:
        return full_response

# --- AUDIO GENERATION (HD + BOOSTED VOLUME + SCRUBBER) ---
def generate_audio_openai(script_text):
    if not OPENAI_API_KEY: return
    client = OpenAI(api_key=OPENAI_API_KEY)
    combined_audio = AudioSegment.empty()
    
    transition_sfx = None
    if os.path.exists("transition.mp3"):
        transition_sfx = AudioSegment.from_file("transition.mp3") - 4
    
    lines = script_text.split('\n')
    current_voice = "onyx" 
    count = 0
    
    forbidden_keywords = [
        "STRUCTURE", "HOOK", "DEEP DIVE", "FIELD REPORT", "MID-ROLL", 
        "STORY 2", "SPEED ROUND", "OUTRO", "RAW NEWS", "WORD COUNT", 
        "SHOW WORDS", "END OF SCRIPT", "SIGNOFF", "STORY#2", "SIGN OFF"
    ]
    sfx_triggers = ["DEEP DIVE", "FIELD REPORT", "MID-ROLL", "STORY 2", "SPEED ROUND", "OUTRO"]
    
    for line in lines:
        text = line.strip()
        if not text: continue 
        text = text.replace("*", "").replace("#", "").strip()
        upper_text = text.upper()

        if any(trigger in upper_text for trigger in sfx_triggers):
             if len(combined_audio) > 5000 and transition_sfx:
                 combined_audio += transition_sfx

        is_numbered = re.match(r'^\d+[\.\)]', text)
        if is_numbered:
            if any(k in upper_text for k in forbidden_keywords) or "MIN)" in upper_text: continue
        if any(upper_text.startswith(k) for k in forbidden_keywords): continue
        if text.startswith("(") and text.endswith(")"): continue

        # --- SPEAKER DETECTION & TEXT CLEANING ---
        # 1. Detect who is speaking
        if "ALEX" in upper_text[:10]: 
            current_voice = "onyx"
            text = re.sub(r'^.*?ALEX.*?:', '', text, flags=re.IGNORECASE)
        elif "JAMIE" in upper_text[:10]:
            current_voice = "nova"
            text = re.sub(r'^.*?JAMIE.*?:', '', text, flags=re.IGNORECASE)
        elif "RUFUS" in upper_text[:10]:
            current_voice = "fable" 
            text = re.sub(r'^.*?RUFUS.*?:', '', text, flags=re.IGNORECASE)
            
        # 2. THE SCRUBBER (The Fix for Stage Directions)
        # Removes anything in parentheses like (laughs) or (dry tone)
        text = re.sub(r'\(.*?\)', '', text) 
        # Removes anything in brackets like [sighs]
        text = re.sub(r'\[.*?\]', '', text)
        # Removes lingering asterisks
        text = text.replace("*", "").replace("#", "").strip()
        
        # 3. Final Check (If the line is now empty after scrubbing, skip it)
        if not text or len(text) < 2: continue
            
        try:
            with client.audio.speech.with_streaming_response.create(
                model="tts-1-hd", 
                voice=current_voice,
                input=text,
                speed=1.05 
            ) as response:
                chunk_file = f"chunk_{count}.mp3"
                response.stream_to_file(chunk_file)
            
            audio_chunk = AudioSegment.from_file(chunk_file)
            audio_chunk = audio_chunk + 5 # Volume Boost
            
            combined_audio += audio_chunk
            combined_audio += AudioSegment.silent(duration=150) 
            os.remove(chunk_file)
            count += 1
        except: pass

    if os.path.exists("intro.mp3"): combined_audio = AudioSegment.from_file("intro.mp3") + combined_audio
    if os.path.exists("outro.mp3"): combined_audio += AudioSegment.from_file("outro.mp3")
    combined_audio.export(OUTPUT_FILE, format="mp3")

# --- RSS FEED ---
def generate_rss_feed():
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss = ET.Element("rss", version="2.0") 
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "The AI Edge: Unfiltered & Automated"
    ET.SubElement(channel, "description").text = "Daily AI news from AI Simplify Media. Alex (Optimist), Jamie (Skeptic) and Rufus (Law & Money Insider) debate the biggest stories in Artificial Intelligence."
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = AUTHOR_NAME
    
    image = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
    image.set("href", f"{base_url}/logo.png") 
    
    owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
    ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = YOUR_EMAIL
    ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}name").text = AUTHOR_NAME
    category = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
    category.set("text", "Technology")

    for filename in sorted(os.listdir("."), reverse=True):
        if filename.endswith(".mp3") and filename.startswith("podcast_"):
            date_str = filename.replace("podcast_", "").replace(".mp3", "")
            notes_file = f"podcast_{date_str}.txt"
            
            description_text = "Today's top stories, discussed." 
            episode_title = f"AI News: {date_str}" 
            
            if os.path.exists(notes_file):
                with open(notes_file, "r") as f:
                    content = f.read().strip()
                    # Final safety clean for display
                    if "Title:" in content:
                        parts = content.split("Summary:")
                        title_part = parts[0].replace("Title:", "").strip()
                        if title_part: episode_title = title_part
                        if len(parts) > 1: description_text = parts[1].strip()
                    else:
                        description_text = content

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = episode_title
            ET.SubElement(item, "description").text = description_text
            ET.SubElement(item, "guid").text = f"{base_url}/{filename}"
            ET.SubElement(item, "enclosure", url=f"{base_url}/{filename}", length="0", type="audio/mpeg")
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                ET.SubElement(item, "pubDate").text = formatdate(dt.timestamp())
            except: pass

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write("feed.xml", encoding="utf-8", xml_declaration=True)

# --- MAIN ---
if __name__ == "__main__":
    config = get_episode_config()
    sponsor = get_sponsor()
    script = generate_script(config, sponsor)
    if script:
        generate_audio_openai(script)
        generate_rss_feed()
    else:
        print("Script generation failed.")
