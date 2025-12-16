import subprocess
import sys

# --- STEP 0: INSTALL NEW GOOGLE SDK ---
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
AUTHOR_NAME = "AI Smplify Media"

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
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

# --- HELPER: GET NEWS ---
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

# --- CRITICAL: DYNAMIC MODEL FINDER ---
def find_best_model(client):
    print("--- DIAGNOSTIC: LISTING AVAILABLE MODELS ---")
    valid_model = None
    try:
        # We ask the API what models it has
        all_models = list(client.models.list())
        for m in all_models:
            # The name usually comes back as 'models/gemini-1.5-flash-001'
            name = m.name
            print(f"Found: {name}") 
            
            # LOGIC: Prefer 1.5 Flash (Fast/Cheap), then 1.5 Pro, then 1.0 Pro
            if "gemini-1.5-flash" in name and "latest" not in name:
                valid_model = name
                # Keep looking just in case we find a better match, but store this
            
        # If we didn't find Flash, look for Pro
        if not valid_model:
            for m in all_models:
                if "gemini-1.5-pro" in m.name:
                    valid_model = m.name
                    break
        
        # If we still have nothing, take ANYTHING that says gemini
        if not valid_model:
            for m in all_models:
                if "gemini" in m.name and "vision" not in m.name:
                    valid_model = m.name
                    break
                    
    except Exception as e:
        print(f"Error listing models: {e}")
    
    # Clean the name (New SDK sometimes hates the 'models/' prefix)
    if valid_model and valid_model.startswith("models/"):
        valid_model = valid_model.replace("models/", "")
        
    print(f"--- SELECTED MODEL: {valid_model} ---")
    return valid_model

# --- MAIN SCRIPT GENERATOR ---
def generate_script(raw_news, sponsor):
    if not GEMINI_API_KEY: 
        print("Error: Gemini Key Missing")
        return None
    
    print("Initializing Client...")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Client Init Error: {e}")
        return None

    # FIND THE MODEL DYNAMICALLY
    target_model = find_best_model(client)
    if not target_model:
        print("CRITICAL: No valid Gemini models found for this API key.")
        return None

    # SPONSOR
    sponsor_txt = "our amazing sponsors"
    if sponsor:
        sponsor_txt = f"{sponsor.get('name')} - {sponsor.get('copy')}"

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
    - **CONFLICT:** Jamie must aggressively disagree with Alex.
    
    STRUCTURE:
    1. HOOK (2 min): High energy intro. Roadmap topics. Catchphrase: "Let's get to it."
    2. DEEP DIVE (5 min): Debate Story #1. High conflict.
    3. FIELD REPORT (3 min): Alex throws to Rufus. Rufus covers Law/Money.
    4. MID-ROLL (45 sec): Jamie reads: "{sponsor_txt}". Natural flow.
    5. STORY 2 (3 min): Social impact debate.
    6. SPEED ROUND (2 min): Headlines.
    7. OUTRO (1 min): Alex credits sponsor. Sign off.

    RAW NEWS:
    {raw_news}
    """

    try:
        print(f"Generating content with {target_model}...")
        response = client.models.generate_content(
            model=target_model,
            contents=prompt
        )
        print("Script generated successfully.")
        return response.text
    except Exception as e:
        print(f"Generation Failed: {e}")
        return None

# --- AUDIO GENERATION ---
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
        
        if "ALEX" in text.upper()[:10]: 
            current_voice = "onyx"
            text = re.sub(r'^.*?ALEX.*?:', '', text, flags=re.IGNORECASE).strip()
        elif "JAMIE" in text.upper()[:10]:
            current_voice = "nova"
            text = re.sub(r'^.*?JAMIE.*?:', '', text, flags=re.IGNORECASE).strip()
        elif "RUFUS" in text.upper()[:10]:
            current_voice = "fable"
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
        combined_audio = AudioSegment.from_file("intro.mp3") + combined_audio
    if os.path.exists("outro.mp3"):
        combined_audio += AudioSegment.from_file("outro.mp3")

    combined_audio.export(OUTPUT_FILE, format="mp3")
    print(f"Success! Podcast saved to {OUTPUT_FILE}")

# --- RSS FEED ---
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
