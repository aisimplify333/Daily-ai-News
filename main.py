import os
import json
import random
import datetime
import feedparser
import re
import glob
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment, effects
from duckduckgo_search import DDGS
from email.utils import formatdate

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

# YOUR CREDENTIALS (SPOTIFY AUTHENTICATION)
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"
AUTHOR_NAME = "AI Simplify Media"

# AUTO-GENERATED HOSTING URL (Spotify looks here)
HOSTING_URL = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/episode_audio/"

# Ensure Directory Exists
if AUDIO_DIR.exists():
    if not AUDIO_DIR.is_dir():
        try: os.remove(AUDIO_DIR)
        except: pass
        AUDIO_DIR.mkdir(exist_ok=True)
else:
    AUDIO_DIR.mkdir(exist_ok=True)

# Assets
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"
TRANSITION_SFX = BASE_DIR / "transition.mp3"

# CAST
CAST = {
    "ALEX": "onyx",    # Host: The anchor. Fast, serious, data-driven.
    "JAMIE": "nova",   # Humanist: The conscience. Interrupts. Worried about people.
    "RUFUS": "fable",  # Cynic: The shark. British. Hates hype. Loves profit.
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "shorting tech stocks in London",
    "analyzing burn rates in Hong Kong",
    "inspecting supply chains in Taiwan",
    "watching the energy crisis in Texas",
    "fighting regulators in Brussels"
]

# --- 2. FEEDS (Data Heavy) ---
FEED_SOURCES = {
    "TITANS": [
        "https://openai.com/blog/rss.xml",
        "https://blogs.microsoft.com/ai/feed/",
        "https://news.google.com/rss/search?q=Nvidia+Stock+Price+News&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=OpenAI+Revenue+Data&hl=en-US&gl=US&ceid=US:en"
    ],
    "INFRA": ["https://www.datacenterdynamics.com/rss/", "https://www.semianalysis.com/feed"],
    "MONEY": ["https://finance.yahoo.com/news/rssindex", "https://techcrunch.com/category/venture/feed/"],
    "LEGAL": ["https://news.google.com/rss/search?q=AI+Lawsuit+Regulation&hl=en-US&gl=US&ceid=US:en"]
}

# --- 3. INTEL ENGINE ---
def deep_search_fallback(query):
    print(f"   ⚠️ DEEP SEARCH: {query}...")
    results = []
    try:
        ddgs = DDGS()
        # Search for HARD NUMBERS
        search_results = ddgs.text(f"{query} market cap price revenue {datetime.date.today().year}", max_results=3)
        for r in search_results: results.append(r['title'])
    except: pass
    return results

def is_hard_news(title):
    fluff = ["how to", "guide", "best of", "gift", "deal", "game", "review", "monitor"]
    return not any(x in title.lower() for x in fluff)

def gather_intel():
    print(" >> 📡 GATHERING HEADLINES...")
    intel = {"headlines": [], "money": [], "legal": []}
    stories = []
    for url in FEED_SOURCES["TITANS"] + FEED_SOURCES["INFRA"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title): stories.append(entry.title)
        except: pass
    
    if len(stories) < 5: stories += deep_search_fallback("Top AI Business News Financials")
    intel["headlines"] = list(set(stories))[:5]
    
    # Money
    money_stories = []
    for url in FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title: money_stories.append(entry.title)
        except: pass
    if not money_stories: money_stories = ["Global Tech Market Cap Crash"]
    intel["money"] = money_stories[:1]

    # Legal
    legal_stories = []
    for url in FEED_SOURCES["LEGAL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                legal_stories.append(entry.title)
        except: pass
    if not legal_stories: legal_stories = ["Global AI Safety Regulation Bills"]
    intel["legal"] = legal_stories[:1]
    
    return intel

def get_sponsors():
    return [
        {"name": "ElevenLabs", "copy": "Scale your content globally. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Organize your business. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. MorningBrew.com."}
    ]

# --- 4. THE WRITER (CHARACTER ENGINES) ---
def generate_text(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.9, # High creativity for banter
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content.strip()

def clean_text_for_audio(text):
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text)
    # The Firewall against reading instructions
    forbidden = ["Structure:", "Length:", "Note:", "Tone:", "Alex:", "Jamie:", "Rufus:"]
    for word in forbidden:
        if text.startswith(word): text = text.replace(word, "").strip()
    text = text.replace('"', '').replace("'", "").replace("...", ".").replace("AI", "A.I.")
    return text.strip()

def write_script_objects(intel, sponsors, rufus_loc):
    print(" >> ✍️  WRITING SHOW...")
    today = datetime.date.today().strftime("%A, %B %d")
    segments = []
    headlines = intel['headlines']
    while len(headlines) < 5: headlines.append("Global Market Update")
    
    # 1. COLD OPEN (Hardcoded)
    segments.append({"speaker": "ALEX", "text": f"Breaking news: {headlines[0]}. This changes the timeline."})
    segments.append({"speaker": "ALEX", "text": f"Good morning. It is {today}. I'm Alex, and this is the AI Edge. Here is the rundown of the top 5 stories."})
    
    for i, h in enumerate(headlines):
        segments.append({"speaker": "ALEX", "text": f"Story Number {i+1}: {h}."})
    segments.append({"speaker": "ALEX", "text": f"But first, a word from {sponsors[0]['name']}."})

    # 2. THE LEAD (Heated Debate)
    print(f"    ...Story 1: {headlines[0]}")
    segments.append({"speaker": "ALEX", "text": f"Let's dive into Story Number One: {headlines[0]}. Jamie, walk us through the numbers."})
    prompt_s1 = f"""
    Write a HEATED DEBATE (ALEX & JAMIE) about: {headlines[0]}.
    - ALEX: Stick to HARD DATA. Mention Billions, Dates, Specs.
    - JAMIE: Be ALARMED. Interrupt Alex. Ask "Who pays for this?" or "What about the jobs?"
    - CHEMISTRY: Alex is annoyed by the interruption but answers with facts.
    - LENGTH: 14 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_s1})

    # 3. THE MONEY (The "Attack")
    print(f"    ...Story 2: {headlines[1]}")
    segments.append({"speaker": "ALEX", "text": f"I hear you, Jamie. It's risky. Now, let's pivot to Story Number Two: {headlines[1]}. For the financial reality check, we go live to Rufus {rufus_loc}."})
    segments.append({"type": "sfx"})
    prompt_s2 = f"""
    Write a HOSTILE MONOLOGUE for RUFUS about {headlines[1]}.
    - TONE: British, Arrogant, Cynical.
    - INSTRUCTION: Do NOT be positive. Find the flaw. Mention "Cash Burn," "Dilution," or "Vaporware."
    - METAPHOR: Use a sharp metaphor (e.g. "Putting lipstick on a pig").
    - LENGTH: 12 PARAGRAPHS.
    """
    segments.append({"type": "monologue", "speaker": "RUFUS", "prompt": prompt_s2})
    
    segments.append({"speaker": "ALEX", "text": f"Brutal, Rufus. Back to you in a moment. Supported by {sponsors[1]['name']}."})

    # 4. THE WATCHDOG (Legal)
    print(f"    ...Story 3: {headlines[2]}")
    segments.append({"speaker": "ALEX", "text": f"Moving on to Story Number Three: {headlines[2]}. This is our Watchdog segment. Rufus, are the regulators asleep?"})
    prompt_s3 = f"""
    Write a DIALOGUE (RUFUS & ALEX) about {headlines[2]}.
    - RUFUS: "Comatose, Alex." Mock the regulators for being slow.
    - ALEX: Defend the tech companies slightly.
    - RUFUS: Shut Alex down with a legal fact.
    - LENGTH: 10 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "RUFUS", "prompt": prompt_s3})

    # 5. RAPID FIRE (All 3)
    print(f"    ...Rapid Fire")
    segments.append({"speaker": "ALEX", "text": f"Well, we find ourselves in the Rapid Fire segment. Jamie, Rufus, let's debate {headlines[3]} and {headlines[4]}."})
    prompt_rapid = f"""
    Write a 3-WAY ARGUMENT (ALEX, JAMIE, RUFUS) on {headlines[3]} and {headlines[4]}.
    - Fast paced. Interruptions allowed.
    - JAMIE: "That sounds dangerous."
    - RUFUS: "It sounds profitable."
    - ALEX: "It sounds inevitable."
    - LENGTH: 12 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_rapid})

    segments.append({"speaker": "ALEX", "text": f"That is the Edge for today. We'll be back tomorrow. {sponsors[2]['copy']}"})
    return segments

# --- 6. RSS GENERATOR (SPOTIFY AUTHENTICATED) ---
def update_rss_feed():
    print(" >> 📡 UPDATING SPOTIFY RSS FEED...")
    
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>The AI Edge</title>
    <description>Daily AI News, Finance, and Regulation.</description>
    <language>en-us</language>
    <itunes:category text="Technology"/>
    <itunes:explicit>no</itunes:explicit>
    <itunes:author>{AUTHOR_NAME}</itunes:author>
    <itunes:owner>
        <itunes:name>{AUTHOR_NAME}</itunes:name>
        <itunes:email>{YOUR_EMAIL}</itunes:email>
    </itunes:owner>
    """
    
    files = sorted(list(AUDIO_DIR.glob("*.mp3")), key=os.path.getmtime, reverse=True)
    
    for file_path in files:
        filename = file_path.name
        meta_path = file_path.with_suffix(".json")
        if meta_path.exists():
            with open(meta_path, "r") as f: meta = json.load(f)
            title = meta.get("title", filename)
            desc = meta.get("description", "Daily AI Update")
        else:
            title = filename.replace(".mp3", "").replace("podcast_", "AI Edge: ")
            desc = "Daily AI News Analysis."

        file_size = os.path.getsize(file_path)
        pubDate = formatdate(os.path.getmtime(file_path))
        file_url = f"{HOSTING_URL}{filename}"

        rss += f"""
    <item>
      <title>{title}</title>
      <description>{desc}</description>
      <enclosure url="{file_url}" length="{file_size}" type="audio/mpeg"/>
      <guid>{file_url}</guid>
      <pubDate>{pubDate}</pubDate>
    </item>"""

    rss += "\n  </channel>\n</rss>"
    
    with open(BASE_DIR / "feed.xml", "w") as f: f.write(rss)
    print(f" ✅ FEED UPDATED: {BASE_DIR / 'feed.xml'}")

# --- 7. PRODUCTION ENGINE ---
def produce_episode():
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    intel = gather_intel()
    sponsors = get_sponsors()
    script_objects = write_script_objects(intel, sponsors, rufus_loc)
    
    today_str = datetime.date.today().isoformat()
    
    # --- SEO & SHOW NOTES GENERATOR ---
    headlines_list = "\n".join([f"• {h}" for h in intel['headlines']])
    
    show_notes = f"""
    {today_str} | The AI Edge Daily Briefing
    
    TODAY'S RUNDOWN:
    {headlines_list}
    
    IN THIS EPISODE:
    Alex and Jamie break down the lead story while Rufus delivers the cynical market reality check.
    
    SPONSORS:
    {sponsors[0]['name']} | {sponsors[1]['name']} | {sponsors[2]['name']}
    
    #AI #TechNews #ArtificialIntelligence #Business #Investing #{intel['headlines'][0].split()[0]}
    """
    
    meta = {
        "title": f"The AI Edge: {intel['headlines'][0]}",
        "description": show_notes,
        "date": today_str
    }
    
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(show_notes)
    
    print(" >> 🎙️  RECORDING...")
    audio_clips = []
    for item in script_objects:
        if "text" in item:
            text = clean_text_for_audio(item["text"])
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
            except: pass
        elif item.get("type") == "sfx":
            if TRANSITION_SFX.exists(): audio_clips.append(AudioSegment.from_mp3(TRANSITION_SFX))
        elif item.get("type") in ["monologue", "dialogue"]:
            text = generate_text(item["prompt"])
            lines = text.split('\n')
            current = item.get("speaker", item.get("default", "ALEX"))
            for line in lines:
                if ":" in line[:10]:
                    parts = line.split(":", 1)
                    if parts[0].strip().upper() in CAST:
                        current = parts[0].strip().upper()
                        line = parts[1]
                clean = clean_text_for_audio(line)
                if len(clean) > 2:
                    try:
                        path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                        client.audio.speech.create(model="tts-1-hd", voice=CAST[current], input=clean).stream_to_file(path)
                        audio_clips.append(AudioSegment.from_mp3(path))
                    except: pass

    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(5000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(5000)

    if audio_clips: full_audio += audio_clips.pop(0)
    full_audio += intro[:8000].fade_out(2000)
    for clip in audio_clips:
        full_audio += clip
        full_audio += AudioSegment.silent(duration=350)
    full_audio += outro[:10000].fade_in(2000)
    
    filename = f"podcast_{today_str}.mp3"
    outfile = AUDIO_DIR / filename
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    with open(outfile.with_suffix(".json"), "w") as f: json.dump(meta, f)
    
    print(f" ✅ EPISODE COMPLETE: {outfile}")
    update_rss_feed()

if __name__ == "__main__":
    produce_episode()
