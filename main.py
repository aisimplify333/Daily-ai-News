import subprocess
import sys
import time

# --- STEP 0: AUTO-INSTALL SDK ---
def install_sdk():
    try:
        import google.genai
    except ImportError:
        print("Installing Google GenAI SDK...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai"])

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

# Safe import for Gemini
try:
    from google import genai
    from google.genai import types
except ImportError:
    from google import genai

# --- CONFIGURATION ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"  
AUTHOR_NAME = "AI Simplify Media (Alex, Jamie & Rufus)" 

# Namespace Variables
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

# --- DATE SYSTEM ---
TODAY = datetime.date.today()
TODAY_STR = TODAY.strftime("%A, %B %d, %Y")

OUTPUT_FILE = f"podcast_{TODAY}.mp3"
NOTES_FILE = f"podcast_{TODAY}.txt" 
SPONSORS_FILE = "sponsors.json"

# --- HELPER: SPONSOR ROTATION ---
def get_sponsor():
    if not os.path.exists(SPONSORS_FILE): return None
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                return random.choice(data)
    except: return None
    return None

# --- HELPER: NEWS FETCHER ---
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

# --- EPISODE STRATEGY ENGINE ---
def get_episode_config():
    weekday = TODAY.weekday()
    month = TODAY.month
    day = TODAY.day
    
    config = {
        "type": "DAILY_NEWS",
        "length_str": "20 Minutes",
        "min_words": "4800", 
        "fetch_limit": 5,   
        "total_items": 30,  
        "focus": "Fast-paced but deep. Cover the headlines, then debate the impact."
    }
    
    # Holiday Logic
    if (month == 12 and day >= 24) or (month == 1 and day == 1): 
        config["type"] = "HOLIDAY_SPECIAL"
        config["length_str"] = "45 Minutes"
        config["min_words"] = "8500" 
        config["fetch_limit"] = 12  
        config["total_items"] = 60  
        config["focus"] = "END OF YEAR SPECTACULAR. Use your INTERNAL KNOWLEDGE + news. Nostalgic, dramatic, comprehensive."
        return config

    # Saturday Logic
    if weekday == 5: 
        config["type"] = "WEEKLY_RECAP"
        config["length_str"] = "30 Minutes"
        config["min_words"] = "6500" 
        config["fetch_limit"] = 8
        config["total_items"] = 40
        config["focus"] = "SATURDAY EDITION. Synthesize these stories. Rufus provides 'Weekend Market Analysis' from the street."
        return config
    
    # Sunday Logic
    if weekday == 6: 
        config["type"] = "DEEP_DIVE"
        config["length_str"] = "30 Minutes"
        config["min_words"] = "6500" 
        config["fetch_limit"] = 8
        config["total_items"] = 40
        config["focus"] = "SUNDAY DEEP DIVE. Pick ONLY ONE major theme. Debate it. Rufus provides the legal/money angle."
        return config
    
    return config

# --- AI GENERATION HANDLER (WITH WAIT TIMER) ---
def generate_content_with_retry(client, prompt):
    # Added 'gemini-2.0-flash-exp' which is often the safer name for the new model
    model_priority = ["gemini-2.0-flash-exp", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    for model_name in model_priority:
        print(f"Attempting generation with model: {model_name}...")
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            # CHECK FOR RATE LIMIT (429)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print(f"⚠️ RATE LIMIT HIT on {model_name}. Waiting 35 seconds to cool down...")
                time.sleep(35) # Wait for quota reset
                try:
                    print(f"🔄 Retrying {model_name} after wait...")
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    return response.text
                except Exception as retry_e:
                    print(f"❌ Retry failed: {retry_e}")
                    continue
            else:
                print(f"❌ Error with {model_name}: {e}")
                continue
    return None

def generate_script(config, sponsor):
    if not GEMINI_API_KEY: 
        print("❌ CRITICAL: GEMINI_API_KEY not found.")
        return None
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except: return None

    raw_news = get_latest_news(config["fetch_limit"], config["total_items"])
    if not raw_news: return None

    sponsor_prompt = ""
    if sponsor:
        print(f"💰 SPONSOR ACTIVE: {sponsor['name']}")
        sponsor_prompt = f"""
        **SPONSOR BLOCK INSTRUCTIONS:**
        The episode is sponsored by "{sponsor['name']}".
        AD COPY: "{sponsor['copy']}"
        **RULE:** RUFUS (and ONLY RUFUS) reads this. He frames it as a "Smart Money/Efficiency Hack."
        """

    print(f"--- TYPE: {config['type']} | TARGET: {config['length_str']} ---")

    prompt = f"""
    You are the Showrunner for "The AI Edge".
    Today's Date: {TODAY_STR} (Use this exact date).
    Episode Type: {config['type']}.
    Target Length: {config['length_str']} (MIN {config['min_words']} Words).
    Focus: {config['focus']}
    
    CHARACTERS:
    1. ALEX (Host): Optimistic American.
    2. JAMIE (Co-host): Skeptical, interrupts often.
    3. RUFUS (Correspondent): BRITISH ACCENT. Law & Money Expert. Dry wit.
    
    {sponsor_prompt}

    INSTRUCTIONS:
    - **REALISM:** Characters interrupt each other. Use incomplete sentences to show this (e.g., "But I--").
    - **RUFUS:** Throw to Rufus 3-4 times.
    - **CLEAN DIALOGUE:** DO NOT write stage directions like (laughs) or [sighs]. Only write spoken words.
    
    **OUTPUT FORMAT (STRICT):**
    
    PART 1: THE SHOW NOTES
    (Do not add meta-headers like "Here are the notes". Start directly with the content.)
    Title: [Catchy Title]
    
    [2-Sentence Summary Hook]
    
    Top Stories:
    - [Bullet]
    - [Bullet]
    
    Sponsor:
    [Sponsor Name/Link]
    
    Keywords:
    #AI #Tech #[Tag3] #[Tag4] ...
    
    |||SEPARATOR|||
    
    PART 2: THE SCRIPT
    ALEX: Welcome to...
    """
    
    full_response = generate_content_with_retry(client, prompt)
    if not full_response: return None
    
    if "|||SEPARATOR|||" in full_response:
        parts = full_response.split("|||SEPARATOR|||")
        
        # --- SHOW NOTES SCRUBBER ---
        raw_notes = parts[0].strip()
        cleaned_lines = []
        for line in raw_notes.split('\n'):
            if "PART 1" in line or "SHOW NOTES" in line.upper() or "Here are" in line:
                continue
            cleaned_lines.append(line)
        
        final_notes = "\n".join(cleaned_lines).strip()
        
        with open(NOTES_FILE, "w") as f:
            f.write(final_notes)
            
        return parts[1].strip()
    else:
        return full_response

# --- AUDIO PRODUCTION ENGINE ---
def generate_audio_openai(script_text):
    if not OPENAI_API_KEY: 
        print("❌ CRITICAL: OPENAI_API_KEY not found.")
        return
    client = OpenAI(api_key=OPENAI_API_KEY)
    combined_audio = AudioSegment.empty()
    
    transition_sfx = None
    if os.path.exists("transition.mp3"):
        transition_sfx = AudioSegment.from_file("transition.mp3") - 4
    
    lines = script_text.split('\n')
    current_voice = "onyx" 
    count = 0
    
    sfx_triggers = ["DEEP DIVE", "FIELD REPORT", "MID-ROLL", "STORY 2", "SPEED ROUND", "OUTRO"]
    
    forbidden_keywords = [
        "STRUCTURE", "HOOK", "DEEP DIVE", "FIELD REPORT", "MID-ROLL", 
        "STORY 2", "SPEED ROUND", "OUTRO", "RAW NEWS", "WORD COUNT", 
        "SHOW WORDS", "END OF SCRIPT", "SIGNOFF", "STORY#2", "SIGN OFF", "PART 2", "THE SCRIPT"
    ]
    
    print("🎙️ Generating Audio Segments...")
    
    for line in lines:
        text = line.strip()
        if not text: continue 
        text = text.replace("*", "").replace("#", "").strip()
        upper_text = text.upper()

        if any(trigger in upper_text for trigger in sfx_triggers):
             if len(combined_audio) > 5000 and transition_sfx:
                 combined_audio += transition_sfx

        if any(upper_text.startswith(k) for k in forbidden_keywords): continue
        if text.startswith("(") and text.endswith(")"): continue

        if "ALEX" in upper_text[:10]: 
            current_voice = "onyx"
            text = re.sub(r'^.*?ALEX.*?:', '', text, flags=re.IGNORECASE)
        elif "JAMIE" in upper_text[:10]:
            current_voice = "nova"
            text = re.sub(r'^.*?JAMIE.*?:', '', text, flags=re.IGNORECASE)
        elif "RUFUS" in upper_text[:10]:
            current_voice = "fable" 
            text = re.sub(r'^.*?RUFUS.*?:', '', text, flags=re.IGNORECASE)
            
        text = re.sub(r'\(.*?\)', '', text) 
        text = re.sub(r'\[.*?\]', '', text)
        text = text.replace("*", "").replace("#", "").strip()
        
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
            audio_chunk = audio_chunk + 5 
            
            combined_audio += audio_chunk
            combined_audio += AudioSegment.silent(duration=150) 
            os.remove(chunk_file)
            count += 1
            if count % 5 == 0: print(f"   Processed {count} lines...")
        except Exception as e: 
            print(f"Skipped line error: {e}")

    if os.path.exists("intro.mp3"): 
        print("Mixing Intro...")
        combined_audio = AudioSegment.from_file("intro.mp3") + combined_audio
    if os.path.exists("outro.mp3"): 
        print("Mixing Outro...")
        combined_audio += AudioSegment.from_file("outro.mp3")
        
    combined_audio.export(OUTPUT_FILE, format="mp3")
    print(f"✅ Audio Complete: {OUTPUT_FILE}")

# --- RSS FEED (WITH SPOTIFY RICH NOTES) ---
def generate_rss_feed():
    print("Generating RSS Feed...")
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("content", CONTENT_NS)
    
    rss = ET.Element("rss", version="2.0") 
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "The AI Edge: Unfiltered & Automated"
    ET.SubElement(channel, "description").text = "Daily AI news from AI Simplify Media."
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, f"{{{ITUNES_NS}}}author").text = AUTHOR_NAME
    
    image = ET.SubElement(channel, f"{{{ITUNES_NS}}}image")
    image.set("href", f"{base_url}/logo.png") 
    
    owner = ET.SubElement(channel, f"{{{ITUNES_NS}}}owner")
    ET.SubElement(owner, f"{{{ITUNES_NS}}}email").text = YOUR_EMAIL
    ET.SubElement(owner, f"{{{ITUNES_NS}}}name").text = AUTHOR_NAME
    category = ET.SubElement(channel, f"{{{ITUNES_NS}}}category")
    category.set("text", "Technology")

    for filename in sorted(os.listdir("."), reverse=True):
        if filename.endswith(".mp3") and filename.startswith("podcast_"):
            date_str = filename.replace("podcast_", "").replace(".mp3", "")
            notes_file = f"podcast_{date_str}.txt"
            
            episode_title = f"AI News: {date_str}" 
            description_text = "Today's top stories, discussed."
            content_encoded_text = "Today's top stories, discussed."
            
            if os.path.exists(notes_file):
                with open(notes_file, "r") as f:
                    full_notes = f.read().strip()
                    content_encoded_text = full_notes.replace("\n", "<br/>") 
                    
                    lines = full_notes.split('\n')
                    for line in lines:
                        if line.lower().startswith("title:"):
                            episode_title = line.split(":", 1)[1].strip()
                            break
                    
                    clean_desc = [l for l in lines if "Title:" not in l and l.strip()]
                    if clean_desc: description_text = clean_desc[0]

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = episode_title
            ET.SubElement(item, "description").text = description_text
            ET.SubElement(item, f"{{{CONTENT_NS}}}encoded").text = content_encoded_text
            ET.SubElement(item, "guid").text = f"{base_url}/{filename}"
            ET.SubElement(item, "enclosure", url=f"{base_url}/{filename}", length="0", type="audio/mpeg")
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                ET.SubElement(item, "pubDate").text = formatdate(dt.timestamp())
            except: pass

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write("feed.xml", encoding="utf-8", xml_declaration=True)
    print("✅ RSS Feed Updated: feed.xml")

# --- EXECUTION ---
if __name__ == "__main__":
    config = get_episode_config()
    sponsor = get_sponsor()
    
    print("🎬 Starting Production...")
    script = generate_script(config, sponsor)
    
    if script:
        generate_audio_openai(script)
        generate_rss_feed()
        print("🎉 Episode Production Complete!")
    else:
        print("❌ Script generation failed. Check API keys or Quota.")
