import os
import json
import random
import datetime
import feedparser
import re
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment
from duckduckgo_search import DDGS
from email.utils import formatdate

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

# YOUR CREDENTIALS
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"
AUTHOR_NAME = "AI Simplify Media"

# HOSTING URLS (Auto-Generated)
HOSTING_URL = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/episode_audio/"
COVER_ART_URL = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/cover.png"

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
    "ALEX": "onyx",    # Host: Urgent, Breaking News Voice.
    "JAMIE": "nova",   # Humanist: Alarmed, Worried about the future.
    "RUFUS": "fable",  # Cynic: Ruthless, Hates Hype, Loves Money.
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "watching the final trading bell in London",
    "tracking 2026 futures in Hong Kong",
    "monitoring capital flight in Taiwan",
    "calculating year-end burn rates in Texas",
    "toasting to the collapse of regulation in Brussels"
]

# --- 2. THE "PREDATOR" SEARCH ENGINE (Big Money / Big Crisis) ---
# We hunt for "Acquisitions," "China," "Lawsuits," and "Crashes"
FEED_SOURCES = {
    "WAR_ROOM": [
        "https://news.google.com/rss/search?q=AI+Acquisition+China+US+Tech+War&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=Nvidia+Stock+Crash+Shortage&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=OpenAI+Lawsuit+Copyright+NYT&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=Deepfake+Fraud+Scam+Millions&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=VC+AI+Funding+Billions&hl=en-US&gl=US&ceid=US:en"
    ],
    "MONEY": [
        "https://finance.yahoo.com/news/rssindex",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html" 
    ]
}

# --- 3. INTEL ENGINE (WITH CRISIS FILTER) ---
def deep_search_fallback(query):
    print(f"   ⚠️ DEEP SEARCH (Hunting for Conflict): {query}...")
    results = []
    try:
        ddgs = DDGS()
        # Search for HIGH STAKES keywords
        search_results = ddgs.text(f"{query} billion lawsuit crash china ban {datetime.date.today().year}", max_results=5)
        for r in search_results: results.append(r['title'])
    except: pass
    return results

def filter_for_crisis(stories):
    # The "Bouncer": Prioritizes High Stakes Headlines
    high_stakes_keywords = ["billion", "trillion", "lawsuit", "sue", "china", "fraud", "crash", "ban", "scam", "war", "acquisition", "drop", "risk", "bankruptcy", "ethics"]
    
    gold_stories = []
    regular_stories = []
    
    for s in stories:
        clean_s = s.lower()
        if any(x in clean_s for x in high_stakes_keywords):
            gold_stories.append(s)
        else:
            regular_stories.append(s)
            
    # Return Gold first, then regular
    final_list = gold_stories + regular_stories
    return final_list[:5] 

def gather_intel():
    print(" >> 📡 GATHERING 'WAR ROOM' INTEL...")
    raw_stories = []
    
    for url in FEED_SOURCES["WAR_ROOM"] + FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "how to" not in entry.title.lower():
                    raw_stories.append(entry.title)
        except: pass
    
    if len(raw_stories) < 5: 
        raw_stories += deep_search_fallback("Top AI Business Crisis News")
    
    # APPLY THE GATEKEEPER
    final_headlines = filter_for_crisis(list(set(raw_stories)))
    return {"headlines": final_headlines}

def get_sponsors():
    # UPDATED: Enterprise Grade Sponsors for Higher CPM feel
    return [
        {"name": "Oracle Cloud", "copy": "Train models faster. Cut your cloud bill in half. Oracle.com."},
        {"name": "NetSuite", "copy": "Stop the cash burn. Get visibility. NetSuite.com."},
        {"name": "ElevenLabs", "copy": "The voice of the future. Scale globally. ElevenLabs.io."}
    ]

# --- 4. THE WRITER (NYE / SORKIN EDITION) ---
def generate_text(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.95, # Max Creativity
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content.strip()

def clean_text_for_audio(text):
    # THE FIREWALL: Removes stage directions
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text)
    forbidden = ["Structure:", "Length:", "Note:", "Tone:", "Alex:", "Jamie:", "Rufus:"]
    for word in forbidden:
        if text.startswith(word): text = text.replace(word, "").strip()
    text = text.replace('"', '').replace("'", "").replace("...", ".").replace("AI", "A.I.")
    return text.strip()

def write_script_objects(intel, sponsors, rufus_loc):
    print(" >> ✍️  WRITING NYE SPECIAL (EXTENDED CUT)...")
    # HARDCODED NYE DATE FOR THE SPECIAL
    today_display = "Wednesday, December 31st" 
    
    segments = []
    headlines = intel['headlines']
    while len(headlines) < 5: headlines.append("Global Market Year-End Review")
    
    # 1. COLD OPEN (Urgent)
    segments.append({"speaker": "ALEX", "text": f"Breaking news: {headlines[0]}. The year is ending with a bang."})
    segments.append({"speaker": "ALEX", "text": f"Good morning. It is {today_display}. I'm Alex. This is the AI Edge. It is the final trading day of 2025."})
    
    for i, h in enumerate(headlines):
        segments.append({"speaker": "ALEX", "text": f"Story {i+1}: {h}."})
    segments.append({"speaker": "ALEX", "text": f"But first, a word from {sponsors[0]['name']}."})

    # 2. THE LEAD (The "War" Story)
    print(f"    ...Story 1: {headlines[0]}")
    segments.append({"speaker": "ALEX", "text": f"Let's end the year with the big one: {headlines[0]}. Jamie, hit us with the numbers. Do not hold back."})
    
    prompt_s1 = f"""
    Write a HEATED NYE DEBATE (ALEX & JAMIE) about: {headlines[0]}.
    - CONTEXT: It is Dec 31st.
    - ALEX: Focus on the MONEY/POWER. Mention Billions.
    - JAMIE: First line MUST BE: "The numbers are terrifying, Alex." Then she mentions the New Year's anxiety.
    - TONE: High stakes. End of the world vibes.
    - LENGTH: 21 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_s1})

    # 3. THE MONEY (The "Grinch")
    print(f"    ...Story 2: {headlines[1]}")
    segments.append({"speaker": "ALEX", "text": f"Terrifying. Now, for the final reality check of 2025, we go live to Rufus {rufus_loc}."})
    segments.append({"type": "sfx"})
    prompt_s2 = f"""
    Write a SCATHING NYE MONOLOGUE for RUFUS about {headlines[1]}.
    - TONE: Cynical. He hates "New Year's Hope."
    - CONTENT: Explain why this news {headlines[1]} proves 2026 will be a financial bloodbath.
    - METAPHOR: "Champagne on the Titanic."
    - LENGTH: 19 PARAGRAPHS.
    """
    segments.append({"type": "monologue", "speaker": "RUFUS", "prompt": prompt_s2})
    
    segments.append({"speaker": "ALEX", "text": f"Always a ray of sunshine, Rufus. Supported by {sponsors[1]['name']}."})

    # 4. THE WATCHDOG (The Legal Threat)
    print(f"    ...Story 3: {headlines[2]}")
    segments.append({"speaker": "ALEX", "text": f"Story Three: {headlines[2]}. Rufus, is the law finally catching up?"})
    prompt_s3 = f"""
    Write a DIALOGUE (RUFUS & ALEX) about {headlines[2]}.
    - RUFUS: "The lawyers are the only ones making money, Alex."
    - CONTENT: Focus on the LAWSUIT/REGULATION aspect.
    - LENGTH: 18 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "RUFUS", "prompt": prompt_s3})

    # 5. RAPID FIRE (Predictions)
    print(f"    ...Rapid Fire Predictions")
    segments.append({"speaker": "ALEX", "text": f"Final segment of the year. Jamie, Rufus. Give me your 2026 Prediction based on {headlines[3]}."})
    prompt_rapid = f"""
    Write a 3-WAY NYE PREDICTION BATTLE (ALEX, JAMIE, RUFUS) on {headlines[3]} and {headlines[4]}.
    - JAMIE: Predicts a social crisis.
    - RUFUS: Predicts a market crash.
    - ALEX: Predicts a tech breakthrough.
    - FAST PACED. INTERRUPTIONS.
    - LENGTH: 21 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_rapid})

    segments.append({"speaker": "ALEX", "text": f"That is the Edge for 2025. We'll see you on the other side. Happy New Year. {sponsors[2]['copy']}"})
    return segments
    
# --- 6. RSS GENERATOR (SPOTIFY VERIFIED) ---
def update_rss_feed():
    print(" >> 📡 UPDATING SPOTIFY RSS FEED...")
    
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>The AI Edge</title>
    <description>Daily AI News, Finance, and Regulation.</description>
    <link>{HOSTING_URL}</link>
    <language>en-us</language>
    <itunes:category text="Technology"/>
    <itunes:explicit>no</itunes:explicit>
    <itunes:author>{AUTHOR_NAME}</itunes:author>
    <itunes:image href="{COVER_ART_URL}"/>
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
      <itunes:duration>1320</itunes:duration>
      <itunes:image href="{COVER_ART_URL}"/>
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
    
    # SEO SHOCK HEADLINES for TWITTER/SPOTIFY
    show_notes = f"""
    {today_str} | NYE SPECIAL: The {intel['headlines'][0]} Crisis
    
    THE WAR ROOM RUNDOWN:
    • {intel['headlines'][0]}
    • {intel['headlines'][1]}
    • {intel['headlines'][2]}
    
    IN THIS EPISODE:
    It's the final broadcast of 2025. Alex, Jamie, and Rufus break down the year's biggest financial risks and predict the 2026 crash.
    
    #AI #MarketCrash #China #TechWar #Investing #2026Predictions #{intel['headlines'][0].split()[0]}
    """
    
    meta = {
        "title": f"NYE SPECIAL: {intel['headlines'][0]} & 2026 Predictions",
        "description": show_notes,
        "date": today_str
    }
    
    # Save Viral Caption for Twitter Bot
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
