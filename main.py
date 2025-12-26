import subprocess
import sys
import time
import logging
import requests 

# --- CONFIGURATION: LOGGING & SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def install_requirements():
    """Auto-installs essentials."""
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

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

TODAY = datetime.date.today()
TODAY_STR = TODAY.strftime("%A, %B %d, %Y")
OUTPUT_FILE = f"podcast_{TODAY}.mp3"
NOTES_FILE = f"podcast_{TODAY}.txt" 
MARKETING_FILE = f"marketing_{TODAY}.txt" 
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

def get_latest_news(limit_per_feed=5, total_limit=50): 
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
        "length_str": "25 Minutes", 
        "min_words": "4000",       
        "fetch_limit": 6,   
        "total_items": 40,  
        "focus": "Deep analysis. Extensive banter. Rabbit holes."
    }

    if force_downgrade:
        return config 

    if is_holiday:
        logging.info(f"🎉 Holiday Detected: {is_holiday}")
        config.update({
            "type": "HOLIDAY_SPECIAL",
            "length_str": "35 Minutes",
            "min_words": "6000",
            "focus": f"SPECIAL EDITION for {is_holiday}. Big themes, history, predictions."
        })
        return config

    if TODAY.weekday() == 5: 
        logging.info("📅 Saturday Detected: Weekly Recap Mode.")
        config.update({"type": "WEEKLY_RECAP", "length_str": "35 Minutes", "min_words": "6000", "focus": "Saturday Edition. Market Analysis."})
    elif TODAY.weekday() == 6: 
        logging.info("📅 Sunday Detected: Deep Dive Mode.")
        config.update({"type": "DEEP_DIVE", "length_str": "35 Minutes", "min_words": "6000", "focus": "Sunday Deep Dive. Single Theme Debate."})
    
    return config

# --- ENGINE: GPT-4o (THE IMPERFECTION ENGINE) ---

def call_openai_gpt4o(prompt, temperature=0.9): 
    """Temperature 0.9 + Imperfection Prompt for Maximum Realism."""
    if not OPENAI_API_KEY:
        logging.error("❌ OpenAI Key missing. Cannot run Pro Engine.")
        return None
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": """
                You are a screenplay writer for a high-paced drama (Sorkin style).
                
                CORE RULES FOR HUMAN REALISM:
                1. **IMPERFECTION:** Real people stutter. Use phrases like "I mean...", "Look...", "Wait, no...", "Uhh...". Use these sparingly but effectively.
                2. **INTERRUPTIONS:** Use '--' to cut people off mid-thought.
                3. **SPEED:** Short sentences. Fragments.
                4. **ROLES:** - ALEX/JAMIE: Fast, overlap, high energy.
                   - RUFUS: The "Correspondent." He speaks with authority on MONEY/LAW. He is cynical.
                5. **FORMAT:** Start EVERY line with the speaker's name (ALEX:, JAMIE:, RUFUS:).
                """},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI Error: {e}")
        return None

def generate_script(config, sponsor):
    if not OPENAI_API_KEY: 
        logging.error("CRITICAL: OPENAI_API_KEY is missing.")
        return None

    # 1. FETCH NEWS
    news_data = get_latest_news(config["fetch_limit"], config["total_items"])
    if not news_data: 
        logging.error("No news found.")
        return None

    sponsor_txt = ""
    if sponsor:
        sponsor_txt = f"""
        **SPONSOR BLOCK (2 Minutes):**
        Sponsor: "{sponsor['name']}"
        Copy: "{sponsor['copy']}"
        **DIRECTIVE:** - Jamie starts excited.
        - Rufus cuts in: "But what's the damage?" (Cost).
        - Alex mediates.
        - Make it sound unscripted.
        """

    # 2. STEP 1: THE BLUEPRINT
    logging.info("🔹 STEP 1/4: Generating Blueprint...")
    blueprint_prompt = f"""
    Analyze these news stories and create a RUN OF SHOW for a 25-minute episode.
    Date: {TODAY_STR}
    
    NEWS DATA:
    {news_data}
    
    OUTPUT FORMAT:
    - HOT TAKE (The Cold Open Story): [Story Name]
    - ACT 1 (Speed Round): [Story A], [Story B], [Story C]
    - ACT 2 (Deep Dive): [The Biggest Story]
    - ACT 3 (Future/Money): [Market Impact / Prediction]
    
    Just return the bullet points.
    """
    blueprint = call_openai_gpt4o(blueprint_prompt, temperature=0.5)
    if not blueprint: return None

    # 3. STEP 2: ACT 1 (Teaser + Speed Round)
    logging.info("🔹 STEP 2/4: Writing Act 1 (Target: 1200 Words)...")
    act1_prompt = f"""
    Role: Podcast Writer.
    Blueprint: {blueprint}
    News Data: {news_data}
    Characters: ALEX (Host), JAMIE (Skeptic), RUFUS (Legal/Money Correspondent).
    
    INSTRUCTIONS:
    - **COLD OPEN:** SHOCKING STAT. 15s Argument. `[INTRO MUSIC]` tag.
    - **ACT 1 (Speed Round):** - **PING PONG:** Alex and Jamie must switch turns constantly. 
        - **RUFUS:** Only chimes in TWICE here. He's the "Man on the Street."
        - **IMPERFECTION:** Add a few "Ums" or "I means" to make it sound real.
    - END with Alex teasing Act 2.
