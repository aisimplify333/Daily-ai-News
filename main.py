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

# --- HOST PERSONAS ---
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

# --- STEP 3: WRITE THE SCRIPT (TEXT MODE) ---
def generate_script(raw_news, sponsor):
    if not GEMINI_API_KEY: 
        print("Error: Gemini Key Missing")
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Use Flash for speed and context window
    model_name = 'gemini-1.5-flash' 
    model = genai.GenerativeModel(model_name)

    sponsor_txt = ""
    if sponsor:
        name = sponsor.get('name', 'Our Sponsor')
        copy = sponsor.get('copy', 'Link in bio.')
        sponsor_txt = f"NOTE: At minute 8, have JAMIE say: 'Big thanks to {name}. {copy}'"

    # --- PROMPT: FOCUS ON LENGTH AND FORMAT ---
    prompt = f"""
    You are the Showrunner for "The AI Edge".
    Target Length: 15 Minutes (approx 2000+ words).
    
    CHARACTERS:
    - ALEX: Main host. Deep voice.
    - JAMIE: Co-host. High energy, interrupts.

    INSTRUCTIONS:
    - Write a long, deep-dive podcast script.
    - Format it like a play: "ALEX: text" and "JAMIE: text".
    - You may use **bold** or (parentheses), the system handles it.
    
    STRUCTURE:
    1. INTRO (1 min): High energy.
    2. DEEP DIVE (6 mins): Debate the #1 story.
    3. AD BREAK (30 sec): Jamie reads the sponsor.
    4. SECOND STORY (4 mins): Discuss impact.
    5. SPEED ROUND (3 mins): Headlines.
    6. OUTRO: Sign off.

    RAW NEWS:
    {raw_news}
    {sponsor_txt}
    """

    try:
        response = model.generate_content(prompt)
        print(f"Script generated! Length: {len(response.text)} chars") # Debug print
        return response.text
    except Exception as e:
        print(f"Script Generation Failed: {e}")
        return None

# --- STEP 4: GENERATE AUDIO (UNIVERSAL PARSER) ---
def generate_audio_openai(script_text):
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY missing.")
        return
        
    client = OpenAI(api_key=OPENAI_API_KEY)
    combined_audio = AudioSegment.empty()
    
    # Clean the text to remove asterisks which confuse TTS
    clean_text = script_text.replace("*", "")
    lines = clean_text.split('\n')
    print(f"Processing {len(lines)} lines...")
    
    count = 0
    for line in lines:
        # Regex to find "Alex:" or "Jamie:" with any punctuation/spacing
        # Matches: "Alex:", "ALEX:", "  Jamie says:", "Alex (Host):"
        match = re.match(r'^\s*(Alex|Jamie).*?[:](.*)', line, re.IGNORECASE)
        
        if not match:
            continue # Skip stage directions or empty lines
            
        speaker_name = match.group(1).upper() # "ALEX" or "JAMIE"
        text = match.group(2).strip() # The spoken text
        
        if not text: continue
        if len(text) < 2: continue # Skip noise
        
        # Decide Voice
        if "ALEX" in speaker_name:
            voice_id = "onyx"
        elif "JAMIE" in speaker_name:
            voice_id = "nova"
        else:
            continue 
            
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice_id,
                input=text
            )
            
            chunk_file = f"chunk_{count}.mp3"
            response.stream_to_file(chunk_file)
            
            audio_chunk = AudioSegment.from_file(chunk_file)
            combined_audio += audio_chunk
            combined_audio += AudioSegment.silent(duration=100) # Snappy pacing
            
            os.remove(chunk_file)
            count += 1
            if count % 5 == 0: print(f"Generated {count} lines...")
            
        except Exception as e:
            print(f"Error on line {count}: {e}")

    # If we processed 0 lines, something is wrong with the script format
    if count == 0:
        print("WARNING: 0 lines of audio generated. Check script formatting.")
        print("Sample of script:", script_text[:500])
        return

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
