import os
import feedparser
import edge_tts
import google.generativeai as genai
import asyncio
import html
from datetime import datetime, timezone
from email.utils import format_datetime
from pydub import AudioSegment

# --- CONFIGURATION ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/artificial-intelligence/index.xml"
]
VOICE = "en-US-ChristopherNeural"  # Updated to the better voice

# --- STEP 1: GET NEWS ---
def get_latest_news():
    print("Scanning the web for AI news...")
    news_items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                for entry in feed.entries[:3]:
                    news_items.append(f"- {entry.title}: {entry.summary[:200]}...")
        except: continue
    if not news_items: return "General AI news update."
    return "\n".join(news_items[:5])

# --- STEP 2: GET SPONSORS ---
def get_sponsors():
    try:
        with open('sponsors.json', 'r') as f: return f.read()
    except: return "No sponsors."

# --- STEP 3: GENERATE SCRIPT (FIXED MODEL SELECTOR) ---
def generate_script(news, sponsors):
    print("Connecting to AI Brain...")
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    
    # AUTO-DETECT BEST MODEL
    # This loop asks Google what models are available and picks the first valid 'Gemini' one.
    target_model = "models/gemini-pro" # Safe fallback
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name:
                target_model = m.name
                break
    except Exception as e:
        print(f"Model list failed, using fallback: {e}")
    
    print(f"Using Model: {target_model}")
    model = genai.GenerativeModel(target_model)
    
    prompt = f"""
    You are the host of 'The AI Edge'. Today is {datetime.now().strftime('%B %d, %Y')}.
    News: {news}
    Sponsors: {sponsors}
    
    TASK: Write the BODY of the script only. 
    - DO NOT write "Welcome to the AI Edge".
    - DO NOT write "Intro music".
    - Start directly with: "Here is what's happening today..."
    - Cover 3 news items.
    - Insert a natural ad read.
    - End with: "That's your AI Edge for today. See you tomorrow."
    """
    response = model.generate_content(prompt)
    return response.text

# --- STEP 4: GENERATE & MIX AUDIO (TUNED FOR REALISM) ---
async def produce_episode(script_text, filename):
    print("Generating voice parts with 'Broadcaster' tuning...")
    
    # SETTINGS: 
    # rate="-10%"  -> Slows him down to human speaking speed
    # pitch="-5Hz" -> Lowers voice slightly for "Radio DJ" effect
    
    # 1. Generate the Hardcoded Intro
    intro_text = "Welcome to The AI Edge, Your home for Daily News and Tools for the AI industry."
    await edge_tts.Communicate(intro_text, VOICE, rate="-10%", pitch="-5Hz").save("temp_intro_voice.mp3")
    
    # 2. Generate the Main Body (News)
    await edge_tts.Communicate(script_text, VOICE, rate="-10%", pitch="-5Hz").save("temp_body_voice.mp3")
    
    print("Mixing audio layers...")
    
    try:
        music_intro = AudioSegment.from_mp3("intro.mp3")
        music_outro = AudioSegment.from_mp3("outro.mp3")
    except:
        print("WARNING: Music files not found! Using silence instead.")
        music_intro = AudioSegment.silent(duration=1000)
        music_outro = AudioSegment.silent(duration=1000)

    voice_intro = AudioSegment.from_mp3("temp_intro_voice.mp3")
    voice_body = AudioSegment.from_mp3("temp_body_voice.mp3")
    
    # Lower music volume
    music_intro = music_intro - 15  # Quieter to let the deep voice shine
    music_outro = music_outro - 15

    # Mix: Intro Music (fade out) + Voice + Outro Music (fade in)
    final_mix = music_intro.fade_out(2500) + voice_intro + voice_body + music_outro.fade_in(2500)
    
    final_mix.export(filename, format="mp3")
    
    # Cleanup
    if os.path.exists("temp_intro_voice.mp3"): os.remove("temp_intro_voice.mp3")
    if os.path.exists("temp_body_voice.mp3"): os.remove("temp_body_voice.mp3")
    
# --- STEP 5: UPDATE RSS ---
def update_rss(audio_filename, script_summary):
    rss_file = "feed.xml"
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    file_url = f"{base_url}/{audio_filename}"
    now = format_datetime(datetime.now(timezone.utc))
    clean_summary = html.escape(script_summary[:250].replace('\n', ' ')) 
    clean_title = f"AI Daily News - {datetime.now().strftime('%B %d')}"
    
    new_item = f"""    <item>
      <title>{clean_title}</title>
      <description>{clean_summary}...</description>
      <enclosure url="{file_url}" length="4000000" type="audio/mpeg"/>
      <guid>{file_url}</guid>
      <pubDate>{now}</pubDate>
    </item>"""

    existing_items = ""
    if os.path.exists(rss_file):
        try:
            with open(rss_file, 'r') as f:
                content = f.read()
                if "<item>" in content:
                    parts = content.split('<item>')
                    for part in parts[1:]:
                        existing_items += "    <item>" + part.split('</channel>')[0]
        except: pass

    final_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:googleplay="http://www.google.com/schemas/play-podcasts/1.0">
  <channel>
    <title>The AI Edge: Daily News &amp; Tools</title>
    <description>Your daily 5-minute download on the Artificial Intelligence revolution.</description>
    <link>{base_url}</link>
    <language>en-us</language>
    <copyright>2025 AI Simplify Media</copyright>
    <itunes:author>AI Simplify Media</itunes:author>
    <itunes:owner>
        <itunes:name>AI Simplify Media</itunes:name>
        <itunes:email>aisimplify333@gmail.com</itunes:email>
    </itunes:owner>
    <itunes:category text="Technology">
        <itunes:category text="Tech News"/>
    </itunes:category>
    <itunes:image href="{base_url}/logo.png"/>
    <itunes:explicit>no</itunes:explicit>
{new_item}
{existing_items}
  </channel>
</rss>"""
    with open(rss_file, "w") as f: f.write(final_content)
    print("RSS Feed rebuilt successfully.")

# --- MAIN ---
if __name__ == "__main__":
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: Run 'export GEMINI_API_KEY=...' first.")
    else:
        news = get_latest_news()
        sponsors = get_sponsors()
        script_body = generate_script(news, sponsors)
        today_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"podcast_{today_str}.mp3"
        
        asyncio.run(produce_episode(script_body, filename))
        update_rss(filename, script_body)
        print("Done! Episode mixed and rendered.")