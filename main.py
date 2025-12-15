import feedparser
import datetime
import os
import asyncio
import edge_tts
import google.generativeai as genai
import re
import json
import random
import xml.etree.ElementTree as ET
from email.utils import formatdate
from pydub import AudioSegment

# --- CONFIGURATION ---
# !!! CHANGE THIS TO YOUR ACTUAL GITHUB USERNAME !!!
GITHUB_USERNAME = "aisimplify333" 
REPO_NAME = "Daily-ai-News"

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/artificial-intelligence/index.xml"
]
GOOGLE_API_KEY = os.environ.get('GEMINI_API_KEY')
VOICE = "en-US-ChristopherNeural"
TODAY = datetime.date.today()
OUTPUT_FILE = f"podcast_{TODAY}.mp3"
TEMP_VOICE_FILE = "temp_voice.mp3"
SPONSORS_FILE = "sponsors.json"

# --- STEP 1: GET SPONSOR ---
def get_sponsor():
    if not os.path.exists(SPONSORS_FILE):
        return None
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                sponsor = random.choice(data)
                return f"Today's episode is brought to you by {sponsor.get('name')}. {sponsor.get('copy')}"
    except Exception:
        return None
    return None

# --- STEP 2: GET NEWS ---
def get_latest_news():
    print("Scanning the web for AI news...")
    news_items = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=headers['User-Agent'])
            if not feed.entries: continue
            for entry in feed.entries[:3]:
                summary = entry.summary if 'summary' in entry else entry.title
                clean_summary = re.sub('<[^<]+?>', '', summary)
                news_items.append(f"Source: {feed.feed.title}. Headline: {entry.title}. Details: {clean_summary[:300]}")
        except Exception as e:
            print(f"Error reading feed {url}: {e}")

    if not news_items:
        return None
    return "\n\n".join(news_items)

# --- STEP 3: REWRITE WITH AI (AUTO-DETECT) ---
def rewrite_script(raw_news, sponsor_text=None):
    if not GOOGLE_API_KEY:
        print("Error: GEMINI_API_KEY not found.")
        return None

    genai.configure(api_key=GOOGLE_API_KEY)
    
    print("Asking Google for available models...")
    working_model = None
    priority_models = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-flash']
    
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for p_model in priority_models:
            for av_model in available_models:
                if p_model in av_model:
                    working_model = av_model
                    break
            if working_model: break
            
        if not working_model:
            for m in available_models:
                if 'gemini' in m:
                    working_model = m
                    break
    except Exception as e:
        print(f"Error listing models: {e}")

    if not working_model:
        working_model = 'gemini-1.5-flash'

    print(f"SUCCESS: Using AI Model -> {working_model}")
    model = genai.GenerativeModel(working_model)

    prompt = f"""
    You are the host of "The AI Edge", a daily 3-minute news podcast.
    {f"MENTION SPONSOR: {sponsor_text}" if sponsor_text else ""}
    News: {raw_news}
    Task: Write a lively, engaging script. 
    - Start: "Welcome back to The AI Edge."
    - Style: Conversational, like a radio DJ.
    - End: "That's your AI Edge for today. See you tomorrow."
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.replace("*", "")
    except Exception as e:
        print(f"AI Generation Failed: {e}")
        return None

# --- STEP 4: GENERATE AUDIO ---
async def generate_audio(text):
    print(f"Generating audio...")
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(TEMP_VOICE_FILE)
    
    print("Mixing audio...")
    try:
        voice = AudioSegment.from_file(TEMP_VOICE_FILE)
        intro = AudioSegment.from_file("intro.mp3") if os.path.exists("intro.mp3") else AudioSegment.silent(1000)
        outro = AudioSegment.from_file("outro.mp3") if os.path.exists("outro.mp3") else AudioSegment.silent(1000)
        final = intro + voice + outro
        final.export(OUTPUT_FILE, format="mp3")
        print(f"DONE! Saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Audio mixing error: {e}")

# --- STEP 5: GENERATE RSS FEED (NEW!) ---
def generate_rss_feed():
    print("Generating feed.xml...")
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    
    rss = ET.Element("rss", version="2.0", **{"xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"})
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "The AI Edge: Daily News"
    ET.SubElement(channel, "description").text = "Your daily dose of AI news, generated by AI."
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "link").text = base_url
    
    # Scan for MP3 files
    for filename in sorted(os.listdir(".")):
        if filename.endswith(".mp3") and filename.startswith("podcast_"):
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = f"AI News: {filename.replace('podcast_', '').replace('.mp3', '')}"
            ET.SubElement(item, "description").text = "Today's top AI stories."
            ET.SubElement(item, "guid").text = f"{base_url}/{filename}"
            ET.SubElement(item, "enclosure", url=f"{base_url}/{filename}", length="0", type="audio/mpeg")
            
            # Simple date handling
            try:
                date_str = filename.replace("podcast_", "").replace(".mp3", "")
                pub_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                ET.SubElement(item, "pubDate").text = formatdate(pub_date.timestamp())
            except:
                pass

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write("feed.xml", encoding="utf-8", xml_declaration=True)
    print("feed.xml created successfully!")

# --- MAIN ---
if __name__ == "__main__":
    news = get_latest_news()
    sponsor = get_sponsor()
    if news:
        script = rewrite_script(news, sponsor)
        if script:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            loop.run_until_complete(generate_audio(script))
            generate_rss_feed() # <--- THIS IS THE MAGIC LINE
    else:
        print("No news found.")
