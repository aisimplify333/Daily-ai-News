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
YOUR_EMAIL = "aisimplify3333@GMAIL.COM"  
AUTHOR_NAME = "AI Simplify Media"

# --- CONFIGURATION: BALANCED SOURCE LIST ---
RSS_FEEDS = [
    # OPTIMIST SOURCES (Tech & Business)
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    # SKEPTIC/LEGAL SOURCES (Fuel for Rufus & Jamie)
    "https://www.theregister.com/software/ai_ml/headlines.atom", 
    "https://futurism.com/feed",                                 
    "https://garymarcus.substack.com/feed",                      
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
            for entry in feed.entries[:3]: 
                summary = re.sub('<[^<]+?>', '', entry.summary if 'summary' in entry else entry.title)
                news_items.append(f"Source: {feed.feed.title}. Headline: {entry.title}. Details: {summary[:500]}")
        except: pass
    
    if not news_items: return None
    random.shuffle(news_items)
    return "\n\n".join(news_items[:12]) 

# --- STEP 3: WRITE THE SCRIPT (SMART FAIL-OVER) ---
def generate_script(raw_news, sponsor):
    if not GEMINI_API_KEY: 
        print("Error: Gemini Key Missing")
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 1. IDENTIFY MODELS
    pro_model = None
    flash_model = None
    
    try:
        print("Scanning available Gemini models...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name
                # Avoid 'latest' or 'exp' to reduce 404/Quota risks
                if "gemini-1.5-pro" in name and "latest" not in name and "exp" not in name:
                    pro_model = name
                if "gemini-1.5-flash" in name and "latest" not in name and "exp" not in name:
                    flash_model = name
    except Exception as e:
        print(f"Error listing models: {e}")

    # Fallbacks if scan fails
    if not pro_model: pro_model = "models/gemini-1.5-pro"
    if not flash_model: flash_model = "models/gemini-1.5-flash"

    # --- PREPARE PROMPT ---
    sponsor_txt = ""
    sponsor_name = "The AI Edge Supporters"
    if sponsor:
        sponsor_name = sponsor.get('name', 'Our Sponsor')
        copy = sponsor.get('copy', 'Link in bio.')
        sponsor_txt = f"SPONSOR DETAILS: Name: {sponsor_name}. Copy: {copy}."

    prompt = f"""
    You are the Showrunner for "The AI Edge".
    Target Length: 15 Minutes (Minimum 2800 Words).
    
    CHARACTERS:
    1. ALEX (Host): Optimistic, professional American anchor.
    2. JAMIE (Co-host): Skeptical, passionate, critical American pundit. (USE CAPS FOR ANGER).
    3. RUFUS (Correspondent): British/Formal accent. Reports "Law & Money".

    INSTRUCTIONS:
    - **FORMAT:** ALEX: (text) / JAMIE: (text) / RUFUS: (text)
    - **RUFUS:** Serious tone. Uses words like "Legislation" and "Antitrust."
    
    STRUCTURE & SPONSORS:
    1. THE HOOK (2 mins): 
       - ALEX: "Welcome back to The AI Edge!"
       - JAMIE: Hypes the conflict.
       - ROADMAP: Alex lists the 3 specific topics coming up.
       - CATCHPHRASE: "Let's get to it."

    2. THE HOT TAKE (5 mins): Alex & Jamie debate Story #1. Jamie interrupts frequently.

    3. THE FIELD REPORT (3 mins): 
       - Alex throws to Rufus in London.
       - RUFUS reports on Regulation/Lawsuits.
       - Rufus signs off "Back to you, Alex."

    4. MID-ROLL AD (45 sec): 
       - Jamie interrupts: "Hold on, quick shoutout."
       - Jamie reads: "{sponsor_txt}"
       - Make it sound natural.

    5. SECOND STORY (3 mins): Social impact debate.

    6. SPEED ROUND (2 mins): Headlines.

    7. OUTRO & POST-ROLL (1 min): 
       - Alex: "That's the Edge for today."
       - **POST-ROLL:** Alex says: "Huge thank you to {sponsor_name} for making this show possible. Check the link in the description."
       - JAMIE: "See ya!"

    RAW NEWS:
    {raw_news}
    """

    # --- ATTEMPT 1: TRY PRO (High Intelligence) ---
    try:
        print(f"Attempting generation with PRO model: {pro_model}")
        model = genai.GenerativeModel(pro_model)
        response = model.generate_content(prompt)
        print("Success with PRO model.")
        return response.text
    except Exception as e:
        print(f"PRO model failed (likely Rate Limit): {e}")
        print("Switching to FLASH backup...")
    
    # --- ATTEMPT 2: FLASH BACKUP (High Reliability) ---
    try:
        model = genai.GenerativeModel(flash_model)
        response = model.generate_content(prompt)
        print("Success with FLASH model.")
        return response.text
    except Exception as e:
        print(f"CRITICAL: Both models failed. {e}")
        return None

# --- STEP 4: GENERATE AUDIO (3 VOICE SUPPORT) ---
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
        
        # --- DETECT 3 VOICES ---
        if "ALEX" in text.upper()[:10]: 
            current_voice = "onyx"  # Deep Male (Anchor)
            text = re.sub(r'^.*?ALEX.*?:', '', text, flags=re.IGNORECASE).strip()
            
        elif "JAMIE" in text.upper()[:10]:
            current_voice = "nova"  # Energetic Female (Pundit)
            text = re.sub(r'^.*?JAMIE.*?:', '', text, flags=re.IGNORECASE).strip()
            
        elif "RUFUS" in text.upper()[:10]:
            current_voice = "fable" # British/Formal Male (Reporter)
            text = re.sub(r'^.*?RUFUS.*?:', '', text, flags=re.IGNORECASE).strip()
            
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
