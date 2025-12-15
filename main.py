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
# Gets the API Key from GitHub Secrets
GOOGLE_API_KEY = os.environ.get('GEMINI_API_KEY')
VOICE = "en-US-ChristopherNeural"
TODAY = datetime.date.today()
OUTPUT_FILE = f"podcast_{TODAY}.mp3"
TEMP_VOICE_FILE = "temp_voice.mp3"
SPONSORS_FILE = "sponsors.json"

# --- STEP 1: GET SPONSOR ---
def get_sponsor():
    """Reads the sponsors.json file and picks a random active sponsor."""
    if not os.path.exists(SPONSORS_FILE):
        print("No sponsors.json found. Skipping sponsor.")
        return None
    
    try:
        with open(SPONSORS_FILE, "r") as f:
            data = json.load(f)
            # Assuming structure is a list of dicts with 'name' and 'copy'
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
    
    # Robust headers to look like a real human (prevents blocking)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
    }

    for url in RSS_FEEDS:
        try:
            print(f"Checking {url}...")
            feed = feedparser.parse(url, agent=headers['User-Agent'])
            
            if not feed.entries:
                continue
                
            for entry in feed.entries[:3]: # Grab top 3 stories per feed
                summary = entry.summary if 'summary' in entry else entry.title
                clean_summary = re.sub('<[^<]+?>', '', summary) # Remove HTML
                clean_text = f"Source: {feed.feed.title}. Headline: {entry.title}. Details: {clean_summary[:300]}"
                news_items.append(clean_text)
                
        except Exception as e:
            print(f"Error reading feed {url}: {e}")
            continue

    if not news_items:
        return None
    
    return "\n\n".join(news_items)

# --- STEP 3: REWRITE WITH AI ---
def rewrite_script(raw_news, sponsor_text=None):
    if not GOOGLE_API_KEY:
        print("Error: GEMINI_API_KEY not found in Secrets.")
        return None

    print("Sending news to Gemini for rewriting...")
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-pro')

    # Add sponsor instruction if exists
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
    
    response = model.generate_content(prompt)
    return response.text.replace("*", "") # Remove bold markdown

# --- STEP 4: GENERATE AUDIO & MIX ---
async def generate_audio(text):
    print("Generating voice audio...")
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(TEMP_VOICE_FILE)
    
    print("Mixing with Intro/Outro...")
    try:
        # Load the generated voice
        voice_audio = AudioSegment.from_file(TEMP_VOICE_FILE)
        
        # Load Intro (or silence if missing)
        if os.path.exists("intro.mp3"):
            intro_audio = AudioSegment.from_file("intro.mp3")
        else:
            print("Warning: intro.mp3 not found. Using silence.")
            intro_audio = AudioSegment.silent(duration=1000)

        # Load Outro (or silence if missing)
        if os.path.exists("outro.mp3"):
            outro_audio = AudioSegment.from_file("outro.mp3")
        else:
            print("Warning: outro.mp3 not found. Using silence.")
            outro_audio = AudioSegment.silent(duration=1000)

        # Mix: Intro -> Voice -> Outro
        final_podcast = intro_audio + voice_audio + outro_audio
        
        # Export final file
        final_podcast.export(OUTPUT_FILE, format="mp3")
        print(f"Success! Saved to {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"Error mixing audio: {e}")

# --- MAIN LOOP ---
if __name__ == "__main__":
    # 1. Get News
    raw_news = get_latest_news()
    
    # 2. Get Sponsor
    sponsor_msg = get_sponsor()
    
    if raw_news:
        # 3. Write Script (News + Sponsor)
        final_script = rewrite_script(raw_news, sponsor_msg)
        
        if final_script:
            # 4. Create Audio
            loop = asyncio.get_event_loop_policy().get_event_loop()
            try:
                loop.run_until_complete(generate_audio(final_script))
            finally:
                pass
        else:
            print("Failed to generate script.")
    else:
        print("No news found today.")