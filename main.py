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

def get_latest_news(limit_per_feed=5, total_limit=50): # Increased fetch limit for more content
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
        "length_str": "25 Minutes", # Increased target
        "min_words": "4000",       # Forced high word count
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

# --- ENGINE: DAISY-CHAIN GENERATION (The 20-Minute Enforcer) ---

def call_openai_gpt4o(prompt, temperature=0.85): # High temp for more "Yapping/Banter"
    """The Gold Standard Engine."""
    if not OPENAI_API_KEY:
        logging.error("❌ OpenAI Key missing. Cannot run Pro Engine.")
        return None
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": "You are an expert podcast showrunner. You write LONG, DETAILED, MESSY scripts. You never summarize. You always elaborate. You love tangents and debates."},
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
        **SPONSOR BLOCK (MUST BE LONG - 2 Minutes):**
        Sponsor: "{sponsor['name']}"
        Copy: "{sponsor['copy']}"
        **DIRECTIVE:** JOINT READ. 
        - Jamie introduces it from a "Tech/Efficiency" angle.
        - Rufus interrupts with the "Smart Money/Savings" angle.
        - They argue about whether it's worth it.
        - Alex settles the debate.
        """

    # 2. STEP 1: THE BLUEPRINT (Generate the Run of Show)
    logging.info("🔹 STEP 1/4: Generating Blueprint...")
    blueprint_prompt = f"""
    Analyze these news stories and create a RUN OF SHOW for a 25-minute episode.
    Date: {TODAY_STR}
    
    NEWS DATA:
    {news_data}
    
    OUTPUT FORMAT:
    - HOT TAKE (The Cold Open Story): [Story Name]
    - ACT 1 (Speed Round): [Story A], [Story B], [Story C]
    - ACT 2 (Deep Dive): [The Biggest Story] - Connection to [Another Story]
    - ACT 3 (Future/Money): [Market Impact / Prediction]
    
    Just return the bullet points.
    """
    blueprint = call_openai_gpt4o(blueprint_prompt, temperature=0.5)
    if not blueprint: return None
    logging.info(f"Blueprint Generated:\n{blueprint}")

    # 3. STEP 2: ACT 1 (Teaser + Speed Round) - FORCED LENGTH
    logging.info("🔹 STEP 2/4: Writing Act 1 (Target: 1200 Words)...")
    act1_prompt = f"""
    Role: Podcast Writer.
    Blueprint: {blueprint}
    News Data: {news_data}
    Characters: ALEX (Host), JAMIE (Skeptic), RUFUS (Cynic/British).
    
    INSTRUCTIONS:
    - **COLD OPEN (THE DATA HOOK):** Start with a SHOCKING STAT. High adrenaline.
    - Insert `[INTRO MUSIC]` tag on a new line.
    - **ACT 1 (The Speed Round):** - Do NOT rush. Spend 3-4 minutes on EACH of the 3 stories.
        - Have Jamie and Rufus interrupt Alex constantly with questions.
        - Go down "Rabbit Holes" about the implications.
    - END with Alex saying "But the real story today is..." (Teasing Act 2).
    - **LENGTH REQUIREMENT:** MINIMUM 1200 WORDS.
    """
    act1 = call_openai_gpt4o(act1_prompt)

    # 4. STEP 3: ACT 2 (The Deep Dive + Sponsor) - FORCED LENGTH
    logging.info("🔹 STEP 3/4: Writing Act 2 (Target: 1800 Words)...")
    act2_prompt = f"""
    Role: Podcast Writer.
    Previous Context: {act1[-500:]} (End of Act 1)
    Blueprint: {blueprint}
    News Data: {news_data}
    Sponsor Info: {sponsor_txt}
    
    INSTRUCTIONS:
    - Write **ACT 2 (The Deep Dive)**.
    - **THE SPONSOR READ:** This must be a full 2-minute conversation/debate in the middle.
    - **THE DEEP DIVE:**
        - Pick the MAIN story.
        - Discuss the history.
        - Discuss the technology.
        - Discuss the politics.
        - Debate the ethics.
    - END with Alex saying "But what does this mean for our wallets? Rufus?"
    - **LENGTH REQUIREMENT:** MINIMUM 1800 WORDS. DO NOT SUMMARIZE.
    """
    act2 = call_openai_gpt4o(act2_prompt)

    # 5. STEP 4: ACT 3 (The Close) & ASSETS
    logging.info("🔹 STEP 4/4: Writing Act 3 & Assets (Target: 1000 Words)...")
    act3_prompt = f"""
    Role: Podcast Writer.
    Previous Context: {act2[-500:]} (End of Act 2)
    Blueprint: {blueprint}
    
    INSTRUCTIONS:
    - Write **ACT 3 (Future & Money)**. 
    - Rufus gives a detailed market prediction.
    - Jamie disagrees.
    - Alex wraps up.
    - **CALL TO ACTION:** "Share this with one friend."
    - **LENGTH REQUIREMENT:** MINIMUM 1000 WORDS.
    
    AFTER THE SCRIPT, Add `|||SEPARATOR|||` and then write:
    1. Viral Title
    2. Show Notes Summary
    3. 1 LinkedIn Post & 3 Tweets.
    """
    act3_and_assets = call_openai_gpt4o(act3_prompt)

    # 6. STITCH IT TOGETHER
    full_script = f"{act1}\n\n{act2}\n\n{act3_and_assets}"
    return full_script

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

    # REMOVE METADATA BEFORE AUDIO PROCESSING
    clean_script = script_content.split("|||SEPARATOR|||")[0]
    lines = clean_script.split('\n')
    current_voice = "onyx" 
    
    skip_phrases = ["PART 3", "THE SCRIPT", "SEPARATOR", "SHOW NOTES", "END OF SCRIPT", "SIGNOFF", "MARKETING ASSETS", "ACT 1", "ACT 2", "ACT 3", "TEASER"]
    sfx_triggers = ["DEEP DIVE", "MID-ROLL", "MARKET REPORT"]

    logging.info(f"Processing {len(lines)} lines of dialogue...")
    
    for i, line in enumerate(lines):
        text = line.strip()
        if not text: continue
        
        # MUSIC TRIGGER LOGIC
        if "[INTRO MUSIC]" in text.upper():
            if intro_music:
                logging.info("   🎵 [TRIGGER] Playing Intro Music...")
                combined_audio += intro_music
            continue 

        if any(x in text.upper() for x in skip_phrases): continue
        if any(x in text.upper() for x in sfx_triggers) and transition:
            if len(combined_audio) > 10000: combined_audio += transition

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
        
        title = f"AI News: {date_str}"
        desc = "Latest AI updates."
        rich_content = "Latest AI updates."
        
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                rich_content = content.replace("\n", "<br/>") 
                lines = content.split('\n')
                for line in lines:
                    if line.lower().startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                        break
                for line in lines:
                    if "Title:" not in line and len(line) > 20:
                        desc = line
                        break

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title 
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
        # PARSE AND SAVE
        try:
            parts = full_text.split("|||SEPARATOR|||")
            script_body = parts[0]
            marketing_assets = parts[1] if len(parts) > 1 else "No marketing assets."
            
            # Save Marketing
            with open(MARKETING_FILE, "w", encoding="utf-8") as f:
                f.write(marketing_assets.strip())
            
            # Save Script/Notes
            with open(NOTES_FILE, "w", encoding="utf-8") as f:
                f.write("See Marketing File for assets.\n" + script_body[:500])
                
            generate_audio(script_body)
            update_rss_feed()
            print("\n🎉 PRODUCTION COMPLETE. Ready for git push.")
        except Exception as e:
            logging.error(f"Parsing Error: {e}")
            # Fallback save
            with open("DEBUG_SCRIPT.txt", "w") as f: f.write(full_text)
    else:
        logging.critical("❌ ALL generation attempts failed. Check Quota/API Keys.")
        sys.exit(1)
