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

# --- CONFIGURATION (YOU MUST FILL THESE IN!) ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"  
AUTHOR_NAME = "AI Simplify Media"

# --- HOST PERSONAS ---
# Host A (Alex): The News Anchor (Voice: Onyx)
# Host B (Jamie): The Color Commentator (Voice: Nova)

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/artificial-intelligence/index.xml",
    "https://venturebeat.com/category/ai/feed/",
    "https://arstechnica.com/tag/ai/feed/"
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
                news_items.append(f"Source: {feed.feed.title}. Headline: {entry.title}. Details: {summary[:300]}")
        except: pass
    
    if not news_items: return None
    random.shuffle(news_items)
    return "\n\n".join(news_items[:6])

# --- STEP 3: WRITE THE SCRIPT (CRASH PROOF UPDATE) ---
def generate_script(raw_news, sponsor):
    if not GEMINI_API_KEY: return None
    genai.configure(api_key=GEMINI_API_KEY)
    
    model_name = 'gemini-1.5-flash' 
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name:
                model_name = m.name
                break
    except: pass
    
    print(f"Using Script Writer: {model_name}")
    model = genai.GenerativeModel(model_name)

    # --- THE FIX IS HERE ---
    sponsor_txt = ""
    if sponsor:
        # We use .get() now. If 'copy' is missing, it defaults to a generic message.
        sponsor_name = sponsor.get('name', 'Our Sponsors')
        sponsor_copy = sponsor.get('copy', 'Check out the link in the description.')
        sponsor_txt = f"SPONSOR SEGMENT: Host B (Jamie) should casually mention: 'By the way, today is supported by {sponsor_name}. {sponsor_copy}'"

    prompt = f"""
    You are the Showrunner for "The AI Edge", a daily deep-dive podcast (aiming for 12-15 minutes).
    
    CHARACTERS:
    - ALEX (Host A): The Insider. Professional, deep voice.
    - JAMIE (Host B): The Skeptic. High energy, curious, asks questions.

    STRUCTURE:
    1. THE HOOK: Start right in the middle of a debate about the top story.
    2. DEEP DIVE (approx 800 words): Focus heavily on the first story. Alex explains, Jamie interrupts.
    3. AD BREAK: Jamie says: "Wait, hold on, we gotta pay the bills. Back in a sec."
    4. SPEED ROUND (approx 600 words): Cover the other stories quickly.
    5. THE TAKEAWAY: End with a practical tip.

    RAW NEWS:
    {raw_news}

    {sponsor_txt}

    FORMAT REQUIREMENTS:
    - Output MUST be a valid JSON list of objects.
    - Each object must have "speaker" ("Alex" or "Jamie") and "text".
    - Example: [{{"speaker": "Alex", "text": "Welcome back."}}, {{"speaker": "Jamie", "text": "Let's dive in!"}}]
    - Total word count aim: ~1500-1800 words.
    - KEEP SENTENCES SHORT. No monologues. Fast banter.
    """

    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        print(f"Script Generation Failed: {e}")
        return None

# --- STEP 4: GENERATE AUDIO (OPENAI TTS) ---
def generate_audio_openai(script_json):
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY missing.")
        return
        
    client = OpenAI(api_key=OPENAI_API_KEY)
    combined_audio = AudioSegment.empty()
    
    print(f"Generating audio for {len(script_json)} lines...")
    
    for i, line in enumerate(script_json):
        speaker = line.get("speaker", "Alex")
        text = line.get("text", "")
        if not text: continue
        
        voice_id = "onyx" if "Alex" in speaker else "nova"
        
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice_id,
                input=text
            )
            
            chunk_file = f"chunk_{i}.mp3"
            response.stream_to_file(chunk_file)
            
            audio_chunk = AudioSegment.from_file(chunk_file)
            combined_audio += audio_chunk
            combined_audio += AudioSegment.silent(duration=300)
            
            os.remove(chunk_file)
            
        except Exception as e:
            print(f"Error generating line {i}: {e}")

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
