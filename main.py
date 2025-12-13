import os
import feedparser
import edge_tts
import google.generativeai as genai
import asyncio
import html
from datetime import datetime, timezone
from email.utils import format_datetime

# --- CONFIGURATION ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"  # Must match your GitHub Repo capitalization exactly
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/artificial-intelligence/index.xml"
]
VOICE = "en-US-EricNeural"

# --- STEP 1: GET NEWS ---
def get_latest_news():
    print("Scanning the web for AI news...")
    news_items = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                for entry in feed.entries[:3]:
                    news_items.append(f"- {entry.title}: {entry.summary[:200]}...")
        except:
            continue
    if not news_items: return "General AI news update."
    return "\n".join(news_items[:5])

# --- STEP 2: GET SPONSORS ---
def get_sponsors():
    try:
        with open('sponsors.json', 'r') as f: return f.read()
    except: return "No sponsors."

# --- STEP 3: GENERATE SCRIPT ---
def generate_script(news, sponsors):
    print("Connecting to AI Brain...")
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    
    # Auto-select best model
    target_model = "models/gemini-1.5-flash"
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name:
                target_model = m.name; break
    except: pass
    
    print(f"Using Model: {target_model}")
    model = genai.GenerativeModel(target_model)
    
    prompt = f"""
    You are the host of 'AI Daily'. Today is {datetime.now().strftime('%B %d, %Y')}.
    News: {news}
    Sponsors: {sponsors}
    TASK: Write a 3-minute script.
    1. Intro: "Welcome to AI Daily for [Date]."
    2. Cover 3 news items.
    3. Insert a natural ad read for ONE sponsor.
    4. Outro.
    """
    response = model.generate_content(prompt)
    return response.text

# --- STEP 4: GENERATE AUDIO ---
async def generate_audio(text, filename):
    print(f"Synthesizing audio to {filename}...")
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(filename)

# --- STEP 5: UPDATE RSS FEED (FIXED FOR SPOTIFY) ---
def update_rss(audio_filename, script_summary):
    rss_file = "feed.xml"
    base_url = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
    file_url = f"{base_url}/{audio_filename}"
    now = format_datetime(datetime.now(timezone.utc))
    
    # Clean the text
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

    # FIXED HEADER WITH AUTHOR & EMAIL
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

    with open(rss_file, "w") as f:
        f.write(final_content)
    print("RSS Feed rebuilt successfully.")

# --- MAIN ---
if __name__ == "__main__":
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: Run 'export GEMINI_API_KEY=...' first.")
    else:
        news = get_latest_news()
        sponsors = get_sponsors()
        script = generate_script(news, sponsors)
        today_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"podcast_{today_str}.mp3"
        
        asyncio.run(generate_audio(script, filename))
        update_rss(filename, script)
        print("Done! Ready to push.")
        