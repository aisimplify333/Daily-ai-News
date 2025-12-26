import subprocess
import sys
import time
import logging
import requests  # NO GOOGLE SDK. Direct "Hardline" connection.

# --- CONFIGURATION: LOGGING & SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def install_requirements():
    """Auto-installs essentials. No complex SDKs."""
    required = ["holidays", "feedparser", "pydub", "openai", "requests"]
    for package in required:
        try:
            __import__(package)
        except ImportError:
            logging.info(f"Installing missing dependency: {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_requirements()

# --- IMPORTS ---
import os
import random
import re
import json
import datetime
import holidays  
import feedparser
import xml.etree.ElementTree as ET 
from email.utils import formatdate
from pydub import AudioSegment
from openai import OpenAI

# --- CONSTANTS & CONFIG ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"  
AUTHOR_NAME = "AI Simplify Media (Alex, Jamie & Rufus)" 

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

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

TODAY = datetime.date.today()
TODAY_STR = TODAY.strftime("%A, %B %d, %Y")
OUTPUT_FILE = f"podcast_{TODAY}.mp3"
NOTES_FILE = f"podcast_{TODAY}.txt" 
SPONSORS_FILE = "sponsors.json"

# --- HELPER FUNCTIONS ---

def get_sponsor():
    if not os.path.exists(SPONSORS_FILE): return None
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                return random.choice(data)
    except: return None
    return None

def get_latest_news(limit_per_feed=5, total_limit=30):
    logging.info(f"Fetching up to {total_limit} news items...")
    news_items = []
    headers = {'User-Agent': 'Mozilla/5.0 (AI Simplify Media Bot)'}
    
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=headers['User-Agent'])
            if not feed.entries: continue
            for entry in feed.entries[:limit_per_feed]: 
                title = entry.title if 'title' in entry else 'Unknown Story'
                summary = re.sub('<[^<]+?>', '', entry.summary if 'summary' in entry else title)
                source = feed.feed.title if 'title' in feed.feed else 'Web'
                news_items.append(f"Source: {source} | Headline: {title} | Brief: {summary[:400]}")
        except Exception:
            continue
    
    if not news_items: return None
    random.shuffle(news_items)
    return "\n\n".join(news_items[:total_limit]) 

def get_episode_config(force_downgrade=False):
    us_holidays = holidays.US()
    is_holiday = us_holidays.get(TODAY)
    
    config = {
        "type": "DAILY_NEWS",
        "length_str": "20 Minutes",
        "min_words": "4800", 
        "fetch_limit": 5,   
        "total_items": 30,  
        "focus": "Fast-paced but deep. Headlines + Debate."
    }

    if force_downgrade:
        logging.warning("⚠️ DOWNGRADE ACTIVE: Forcing standard format.")
        return config 

    if is_holiday:
        logging.info(f"🎉 Holiday Detected: {is_holiday}")
        config.update({
            "type": "HOLIDAY_SPECIAL",
            "length_str": "30 Minutes",
            "min_words": "6500",
            "fetch_limit": 8,
            "total_items": 40,
            "focus": f"SPECIAL EDITION for {is_holiday}. Big themes, history, predictions."
        })
        return config

    if TODAY.weekday() == 5: 
        logging.info("📅 Saturday Detected: Weekly Recap Mode.")
        config.update({"type": "WEEKLY_RECAP", "length_str": "30 Minutes", "min_words": "6500", "focus": "Saturday Edition. Market Analysis."})
    elif TODAY.weekday() == 6: 
        logging.info("📅 Sunday Detected: Deep Dive Mode.")
        config.update({"type": "DEEP_DIVE", "length_str": "30 Minutes", "min_words": "6500", "focus": "Sunday Deep Dive. Single Theme Debate."})
    
    return config

# --- CORE AI GENERATION (REST API ENGINE) ---

def call_gemini_api(model_name, prompt):
    """Direct REST API call. Bypasses Python SDK issues."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        elif response.status_code == 429:
            raise Exception("RATE_LIMIT")
        else:
            logging.error(f"API Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        if "RATE_LIMIT" in str(e): raise e
        logging.error(f"Network/Parse Error: {e}")
        return None

def generate_script(config, sponsor):
    if not GEMINI_API_KEY: 
        logging.error("GEMINI_API_KEY is missing.")
        return None

    news_data = get_latest_news(config["fetch_limit"], config["total_items"])
    if not news_data: 
        logging.error("No news found.")
        return None

    sponsor_txt = ""
    if sponsor:
        sponsor_txt = f"""
        **SPONSOR BLOCK:**
        Sponsor: "{sponsor['name']}"
        Copy: "{sponsor['copy']}"
        **DIRECTIVE:** RUFUS reads this as a "Smart Money" tip.
        """

    system_prompt = f"""
    Role: Showrunner for "The AI Edge".
    Date: {TODAY_STR}.
    Type: {config['type']}.
    Target: {config['length_str']} (Min {config['min_words']} words).
    
    CHARACTERS:
    - ALEX (Host): Optimistic, high energy.
    - JAMIE (Co-host): Skeptical, interrupts Alex.
    - RUFUS (Field Reporter): British, dry wit, financial/legal expert.
    
    {sponsor_txt}

    FORMATTING RULES:
    1. **COLD OPEN:** Start with a 15-second "Teaser" debate (High drama) BEFORE the intro music.
    2. **INTERRUPTIONS:** Use dashes (e.g. "But I--") to show cut-offs.
    3. **NO STAGE DIRECTIONS:** Do not write (laughs). Only spoken words.
    4. **CALL TO ACTION:** End with Alex asking listeners to "Share with one friend" to help the show grow.
    
    OUTPUT STRUCTURE:
    PART 1: SHOW NOTES
    Title: [Write a Viral, Clickable Title (Not just the date)]
    Summary: [2 Sentence Hook]
    ...
    |||SEPARATOR|||
    PART 2: SCRIPT
    ALEX: (Cold Open)...
    """

    models = ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    
    for model_name in models:
        logging.info(f"Attempting generation with {model_name}...")
        try:
            return call_gemini_api(model_name, system_prompt)
        except Exception as e:
            if "RATE_LIMIT" in str(e):
                logging.warning(f"⚠️ Rate Limit on {model_name}. Switching models in 5s...")
                time.sleep(5)
                continue
            else:
                logging.error(f"Unexpected error on {model_name}: {e}")
                continue
    return None

# --- AUDIO ENGINE ---

def clean_text_for_audio(text):
    text = re.sub(r'[\(\[].*?[\)\]]', '', text)
    text = text.replace("*", "").replace("#", "")
    return text.strip()

def generate_audio(script_content):
    if not OPENAI_API_KEY:
        logging.error("OPENAI_API_KEY missing.")
        return

    client = OpenAI(api_key=OPENAI_API_KEY)
    combined_audio = AudioSegment.empty()
    
    try:
        if os.path.exists("intro.mp3"): intro_music = AudioSegment.from_file("intro.mp3")
        else: intro_music = None
        
        if os.path.exists("transition.mp3"): transition = AudioSegment.from_file("transition.mp3") - 4 
        else: transition = None
    except: 
        intro_music = None
        transition = None

    lines = script_content.split('\n')
    current_voice = "onyx" 
    
    skip_phrases = ["PART 2", "THE SCRIPT", "SEPARATOR", "SHOW NOTES", "END OF SCRIPT", "SIGNOFF"]
    sfx_triggers = ["DEEP DIVE", "MID-ROLL", "MARKET REPORT"]

    logging.info(f"Processing {len(lines)} lines of dialogue...")
    
    # Track if we have played the intro music yet (Post-Cold Open)
    intro_played = False

    for i, line in enumerate(lines):
        text = line.strip()
        if not text: continue
        
        if any(x in text.upper() for x in skip_phrases): continue
        if any(x in text.upper() for x in sfx_triggers) and transition:
            if len(combined_audio) > 10000: combined_audio += transition

        # COLD OPEN LOGIC: If we are 4-5 lines in, play the intro music
        if not intro_played and i > 4 and intro_music:
             logging.info("   🎵 Playing Intro Music (Post Cold-Open)...")
             combined_audio += intro_music
             intro_played = True

        upper = text.upper()
        if "ALEX:" in upper: current_voice = "onyx"
        elif "JAMIE:" in upper: current_voice = "nova"
        elif "RUFUS:" in upper: current_voice = "fable"
        
        clean_text = re.sub(r'^(ALEX|JAMIE|RUFUS):\s*', '', text, flags=re.IGNORECASE)
        clean_text = clean_text_for_audio(clean_text)
        
        if len(clean_text) < 2: continue

        try:
            with client.audio.speech.with_streaming_response.create(
                model="tts-1-hd", voice=current_voice, input=clean_text, speed=1.05
            ) as response:
                chunk_path = f"temp_{i}.mp3"
                response.stream_to_file(chunk_path)
            
            segment = AudioSegment.from_file(chunk_path)
            combined_audio += segment + 5 
            combined_audio += AudioSegment.silent(duration=150) 
            os.remove(chunk_path)
            
            if i % 10 == 0: print(f"   Compiled line {i}...")

        except Exception as e:
            logging.warning(f"Audio chunk failed at line {i}: {e}")
            continue

    if os.path.exists("outro.mp3"): combined_audio += AudioSegment.from_file("outro.mp3")

    combined_audio.export(OUTPUT_FILE, format="mp3")
    logging.info(f"✅ SUCCESS: Audio saved to {OUTPUT_FILE}")

# --- RSS GENERATOR ---

def update_rss_feed():
    logging.info("Updating RSS Feed...")
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("content", CONTENT_NS)
    rss = ET.Element("rss", version="2.0") 
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "The AI Edge: Daily News Unfiltered"
    ET.SubElement(channel, "description").text = "Daily AI news, debates, and market analysis."
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = AUTHOR_NAME
    
    img = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", f"{base_url}/logo.png")
    
    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    ET.SubElement(owner, f"{{{ITUNES_NS}}}email").text = YOUR_EMAIL
    ET.SubElement(owner, f"{{{ITUNES_NS}}}name").text = AUTHOR_NAME
    ET.SubElement(channel, f"{{{ITUNES_NS}}}category").set("text", "Technology")

    episodes = []
    for f in os.listdir("."):
        if f.startswith("podcast_") and f.endswith(".mp3"):
            episodes.append(f)
    episodes.sort(reverse=True) 

    for filename in episodes:
        date_str = filename.replace("podcast_", "").replace(".mp3", "")
        txt_path = filename.replace(".mp3", ".txt")
        
        # SMART TITLE EXTRACTION
        title = f"AI News: {date_str}"
        desc = "Latest AI updates."
        rich_content = "Latest AI updates."
        
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                rich_content = content.replace("\n", "<br/>") 
                
                lines = content.split('\n')
                # 1. Try to find an explicit "Title:" line
                for line in lines:
                    if line.lower().startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                        break
                
                # 2. Grab description (first non-title line)
                for line in lines:
                    if "Title:" not in line and len(line) > 20:
                        desc = line
                        break

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title # Now uses the Viral Title
        ET.SubElement(item, "description").text = desc
        ET.SubElement(item, f"{{{CONTENT_NS}}}encoded").text = rich_content
        ET.SubElement(item, "guid").text = f"{base_url}/{filename}"
        ET.SubElement(item, "enclosure", url=f"{base_url}/{filename}", length="0", type="audio/mpeg")
        
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            ET.SubElement(item, "pubDate").text = formatdate(dt.timestamp())
        except: pass

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write("feed.xml", encoding="utf-8", xml_declaration=True)
    logging.info("✅ RSS Feed Updated.")

if __name__ == "__main__":
    print("\n🚀 AI PODCAST AUTOMATION: STARTED\n")
    sponsor = get_sponsor()
    config = get_episode_config()
    
    logging.info("📝 Generating Script...")
    full_text = generate_script(config, sponsor)
    
    if not full_text:
        logging.warning("⚠️ High-Load Generation Failed. Retrying with Standard Config...")
        config = get_episode_config(force_downgrade=True)
        full_text = generate_script(config, sponsor)
        
    if full_text:
        if "|||SEPARATOR|||" in full_text:
            notes, script = full_text.split("|||SEPARATOR|||")
        else:
            notes = "Show notes unavailable."
            script = full_text
            
        notes = "\n".join([line for line in notes.split('\n') if "PART 1" not in line])
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            f.write(notes.strip())
            
        generate_audio(script)
        update_rss_feed()
        print("\n🎉 PRODUCTION COMPLETE. Ready for git push.")
    else:
        logging.critical("❌ ALL generation attempts failed. Check Quota/API Keys.")
        sys.exit(1)
