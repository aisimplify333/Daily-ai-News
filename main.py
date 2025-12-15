import feedparser
import datetime
import os
import asyncio
import edge_tts
import google.generativeai as genai
import re
import json
import random
from pydub import AudioSegment

# --- CONFIGURATION ---
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
        print("No sponsors.json found. Skipping.")
        return None
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                sponsor = random.choice(data)
                return f"Today's episode is brought to you by {sponsor.get('name')}. {sponsor.get('copy')}"
    except Exception as e:
        print(f"Error reading sponsors: {e}")
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

# --- STEP 3: REWRITE WITH AI (AUTO-DETECT + CHATTY PERSONALITY) ---
def rewrite_script(raw_news, sponsor_text=None):
    if not GOOGLE_API_KEY:
        print("Error: GEMINI_API_KEY not found.")
        return None

    genai.configure(api_key=GOOGLE_API_KEY)
    
    # --- AUTO-DETECT WORKING MODEL ---
    print("Asking Google for available models...")
    working_model = None
    try:
        # Loop through available models to find one that supports content generation
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name:
                    working_model = m.name
                    break # Stop at the first valid one
    except Exception as e:
        print(f"Error listing models: {e}")

    if not working_model:
        # Fallback if auto-detect fails
        working_model = 'gemini-1.5-flash' 
    
    print(f"SUCCESS: Using AI Model -> {working_model}")
    model = genai.GenerativeModel(working_model)
    # --------------------------------------

    # --- THE CHATTY PROMPT ---
    sponsor_instruction = ""
    if sponsor_text:
        sponsor_instruction = f"IMPORTANT: After the introduction, casually mention this sponsor: '{sponsor_text}'"

    prompt = f"""
    You are the host of "The AI Edge", a daily 3-5 minute news podcast.
    
    {sponsor_instruction}

    Here are the raw news stories from today:
    {raw_news}

    Task: Write a fun, engaging, and professional script.
    - Start exactly with: "Welcome back to The AI Edge, I'm your host."
    - If there is a sponsor, read it naturally early in the show.
    - Group related stories together.
    - Use a conversational tone (like a radio host).
    - End exactly with: "That's your AI Edge for today. See you tomorrow."
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.replace("*", "")
    except Exception as e:
        print(f"AI Generation Failed: {e}")
        return None

# --- STEP 4: GENERATE AUDIO ---
async def generate_audio(text):
    print(f"Generating audio ({len(text)} chars)...")
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(TEMP_VOICE_FILE)
    
    print("Mixing audio...")
    try:
        voice = AudioSegment.from_file(TEMP_VOICE_FILE)
        
        # Load intro/outro if they exist, otherwise silence
        if os.path.exists("intro.mp3"):
            intro = AudioSegment.from_file("intro.mp3")
        else:
            intro = AudioSegment.silent(1000)
            
        if os.path.exists("outro.mp3"):
            outro = AudioSegment.from_file("outro.mp3")
        else:
            outro = AudioSegment.silent(1000)
        
        final = intro + voice + outro
        final.export(OUTPUT_FILE, format="mp3")
        print(f"DONE! Saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Audio mixing error: {e}")

# --- MAIN ---
if __name__ == "__main__":
    news = get_latest_news()
    sponsor = get_sponsor()
    if news:
        script = rewrite_script(news, sponsor)
        if script:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            loop.run_until_complete(generate_audio(script))
    else:
        print("No news found.")
