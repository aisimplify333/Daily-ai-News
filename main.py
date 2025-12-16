import feedparser
import datetime
import os
import asyncio
import google.generativeai as genai
import re
import json
import random
import xml.etree.ElementTree as ET
from email.utils import formatdate
from pydub import AudioSegment
from openai import OpenAI

# --- CONFIGURATION (FILL THESE IN!) ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"  
AUTHOR_NAME = "AI Simplify Media"

# --- CONFIGURATION ---
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/artificial-intelligence/index.xml",
    "https://venturebeat.com/category/ai/feed/",
    "https://arstechnica.com/tag/ai/feed/",
    "https://www.wired.com/feed/category/ai/latest/rss"
]

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
TODAY = datetime.date.today()
OUTPUT_FILE = f"podcast_{TODAY}.mp3"
SPONSORS_FILE = "sponsors.json"

# --- STEP 1: GET SPONSOR ---
def get_sponsor():
    if not os.path.exists(SPONSORS_FILE): return None
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                return random.choice(data)
    except: return None
    return None

# --- STEP 2: GET NEWS ---
def get_latest_news():
    print("Scanning the web for AI news...")
    news_items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=headers['User-Agent'])
            if not feed.entries: continue
            for entry in feed.entries[:4]: 
                summary = re.sub('<[^<]+?>', '', entry.summary if 'summary' in entry else entry.title)
                news_items.append(f"Source: {feed.feed.title}. Headline: {entry.title}. Details: {summary[:500]}")
        except: pass
    
    if not news_items: return None
    random.shuffle(news_items)
    return "\n\n".join(news_items[:10])

# --- STEP 3: WRITE THE SCRIPT (THE "HEATED" PROMPT) ---
def generate_script(raw_news, sponsor):
    if not GEMINI_API_KEY: 
        print("Error: Gemini Key Missing")
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    
    # --- SMART MODEL SELECTOR ---
    model_name = None
    available_models = []
    try:
        print("Scanning available Gemini models...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        # 1. Look for reliable 1.5 Flash
        for m in available_models:
            if "gemini" in m and "1.5" in m and "flash" in m:
                model_name = m
                break
        
        # 2. Fallback to any Pro (excluding 2.5)
        if not model_name:
             for m in available_models:
                if "gemini" in m and "pro" in m and "2.5" not in m:
                    model_name = m
                    break
    except Exception as e:
        print(f"Error listing models: {e}")

    if not model_name:
        model_name = "models/gemini-pro"
    
    print(f"Using Script Writer: {model_name}")
    model = genai.GenerativeModel(model_name)

    sponsor_txt = ""
    if sponsor:
        name = sponsor.get('name', 'Our Sponsor')
        copy = sponsor.get('copy', 'Link in bio.')
        sponsor_txt = f"NOTE: At minute 8, have JAMIE say: 'Big thanks to {name}. {copy}'"

    # --- UPDATED PROMPT: INSTRUCTIONS FOR VOLUME/ANGER ---
    prompt = f"""
    You are the Showrunner for "The AI Edge".
    Target Length: 15 Minutes.
    
    CHARACTERS:
    - ALEX: Main host. Optimistic, professional.
    - JAMIE: Co-host. Skeptical, passionate, gets angry easily.

    INSTRUCTIONS:
    - Write a script formatted: ALEX: (text) / JAMIE: (text)
    - **USE CAPS LOCK FOR EMPHASIS.** - If they are arguing, use UPPERCASE to signal loudness.
      - Example: JAMIE: "Are you kidding? THAT IS DANGEROUS!"
    - **Create Conflict:** Alex loves the tech. Jamie fears it. They must interrupt each other.
    
    STRUCTURE:
    1. THE HOOK (1-2 mins): High energy welcome + Roadmap of topics + Catchphrase "Let's get to it."
    2. THE HOT TAKE (6 mins): Debate the #1 story. Jamie interrupts frequently. 
    3. AD BREAK (30 sec): Jamie reads the sponsor.
    4. SECOND STORY (4 mins): Discuss impact on society.
    5. SPEED ROUND (3 mins): Rapid fire headlines.
    6. OUTRO: Quick sign off.

    RAW NEWS:
    {raw_news}
    {sponsor_txt}
    """

    try:
        response = model.generate_content(prompt)
        print("Script generated successfully.")
        return response.text
    except Exception as e:
        print(f"Script Generation Failed: {e}")
        return None

# --- STEP 4: GENERATE AUDIO (FAIL-SAFE MODE) ---
def generate_audio_openai(script_text):
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY missing.")
        return
        
    client = OpenAI(api_key=OPENAI_API_KEY)
    combined_audio = AudioSegment.empty()
    
    lines = script_text.split('\n')
    print(f"Processing {len(lines)} lines...")
    
    current_voice = "onyx" 
    
    count = 0
    for line in lines:
        text = line.strip()
        if not text: continue 
        
        # --- DETECT VOICE CHANGE ---
        if "ALEX" in text.upper()[:10]: 
            current_voice = "onyx"
            text = re.sub(r'^.*?ALEX.*?:', '', text, flags=re.IGNORECASE).strip()
            
        elif "JAMIE" in text.upper()[:10]:
            current_voice = "nova"
            text = re.sub(r'^.*?JAMIE.*?:', '', text, flags=re.IGNORECASE).strip()
            
        # Remove asterisks but KEEP exclamation points and CAPS for emphasis
        text = text.replace("*", "").replace("#", "")
        
        if not text or len(text) < 2: continue
            
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=current_voice,
                input=text
            )
            
            chunk_file = f"chunk_{count}.mp3"
            response.stream_to_file(chunk_file)
            
            audio_chunk = AudioSegment.from_file(chunk_file)
            combined_audio += audio_chunk
            combined_audio += AudioSegment.silent(duration=150) 
            
            os.remove(chunk_file)
            count += 1
            if count % 5 == 0: print(f"Generated {count} lines...")
            
        except Exception as e:
            print(f"Error on line {count}: {e}")

    print("Mixing final track...")
    if os.path.exists("intro.mp3"):
        intro = AudioSegment.from_file("intro.mp3")
        combined_audio = intro + combined_audio
        
    if os.path.exists("outro.mp3"):
        outro = AudioSegment.from_file("outro.mp3")
        combined_audio += outro

    combined_audio.export(OUTPUT_FILE, format="mp3")
    print(f"Success! Podcast saved to {OUTPUT_FILE}")

# --- STEP 5: RSS FEED ---
def generate_rss_feed():
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss = ET.Element("rss", version="2.0") 
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "The AI Edge: Daily Deep Dive"
    ET.SubElement(channel, "description").text = "Daily AI news, debated and decoded."
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
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = f"AI News: {filename.replace('podcast_', '').replace('.mp3', '')}"
            ET.SubElement(item, "description").text = "Today's top stories, discussed."
            ET.SubElement(item, "guid").text = f"{base_url}/{filename}"
            ET.SubElement(item, "enclosure", url=f"{base_url}/{filename}", length="0", type="audio/mpeg")
            try:
                dt = datetime.datetime.strptime(filename.replace("podcast_", "").replace(".mp3", ""), "%Y-%m-%d")
                ET.SubElement(item, "pubDate").text = formatdate(dt.timestamp())
            except: pass

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write("feed.xml", encoding="utf-8", xml_declaration=True)

# --- MAIN ---
if __name__ == "__main__":
    news = get_latest_news()
    sponsor = get_sponsor()
    if news:
        script = generate_script(news, sponsor)
        if script:
            generate_audio_openai(script)
            generate_rss_feed()
    else:
        print("No news found.")
