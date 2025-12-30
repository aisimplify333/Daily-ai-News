import os
import json
import random
import datetime
import feedparser
import re
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment, effects
from duckduckgo_search import DDGS

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

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
    "ALEX": "onyx",    # Host: Deep, fast, authoritative.
    "JAMIE": "nova",   # Co-Host: Warm, skeptical, human-focused.
    "RUFUS": "fable",  # Analyst: British, cynical, money-focused.
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "on the trading floor in London",
    "monitoring the pre-market in New York",
    "tracking chip shipments in Taiwan",
    "analyzing energy grids in Texas",
    "at the regulator's office in Brussels"
]

# --- 2. FEEDS (Hard News) ---
FEED_SOURCES = {
    "TITANS": [
        "https://openai.com/blog/rss.xml",
        "https://blogs.microsoft.com/ai/feed/",
        "https://news.google.com/rss/search?q=Nvidia+Stock+News&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=TSMC+Production+News&hl=en-US&gl=US&ceid=US:en"
    ],
    "INFRA": [
        "https://www.datacenterdynamics.com/rss/",
        "https://www.semianalysis.com/feed"
    ],
    "MONEY": [
        "https://finance.yahoo.com/news/rssindex",
        "https://techcrunch.com/category/venture/feed/"
    ],
    "LEGAL_GLOBAL": [
        "https://news.google.com/rss/search?q=AI+Regulation+EU+US+China&hl=en-US&gl=US&ceid=US:en",
        "https://restofworld.org/feed/"
    ]
}

# --- 3. INTEL ---
def deep_search_fallback(query):
    print(f"   ⚠️ SEARCHING: {query}...")
    results = []
    try:
        ddgs = DDGS()
        search_results = ddgs.text(f"{query} 2025 data", max_results=3)
        for r in search_results: results.append(r['title'])
    except: pass
    return results

def is_hard_news(title):
    fluff = ["how to", "guide", "best of", "gift", "deal", "game", "review"]
    return not any(x in title.lower() for x in fluff)

def gather_intel():
    print(" >> 📡 GATHERING THE BIG 5...")
    intel = {"headlines": [], "money": [], "legal": []}
    
    # Headlines (Titans + Infra)
    stories = []
    for url in FEED_SOURCES["TITANS"] + FEED_SOURCES["INFRA"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title): stories.append(entry.title)
        except: pass
    
    if len(stories) < 5: stories += deep_search_fallback("Top AI News Stories Today")
    intel["headlines"] = list(set(stories))[:5]
    
    # Money Specific
    money_stories = []
    for url in FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title: money_stories.append(entry.title)
        except: pass
    if not money_stories: money_stories = ["Tech Market Volatility"]
    intel["money"] = money_stories[:1]

    # Legal/Global Specific
    legal_stories = []
    for url in FEED_SOURCES["LEGAL_GLOBAL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                legal_stories.append(entry.title)
        except: pass
    if not legal_stories: legal_stories = ["Global AI Safety Summit"]
    intel["legal"] = legal_stories[:1]
    
    return intel

def get_sponsors():
    return [
        {"name": "ElevenLabs", "copy": "The standard for AI voice. Scale your content globally. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Stop drowning in tabs. Notion AI organizes your business. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. Daily business news without the jargon. MorningBrew.com."}
    ]

# --- 4. THE WRITER ---
def generate_text(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.75,
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content.strip()

def clean_text(text):
    text = re.sub(r'\*.*?\*', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = text.replace('"', '').replace("'", "")
    return text.strip()

def generate_script_objects(intel, sponsors, rufus_loc):
    print(" >> ✍️  WRITING SHOW (22 Minute Broadcast Mode)...")
    today = datetime.date.today().strftime("%A, %B %d")
    segments = []
    
    headlines = intel['headlines']
    while len(headlines) < 5: headlines.append("Global Tech Update")
    
    rundown_text = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])

    # --- SEGMENT 1: RUNDOWN (Alex) ---
    segments.append({"speaker": "ALEX", "text": f"Breaking news: {headlines[0]}. This is the AI Edge."})
    
    prompt_intro = f"""
    Write a dialogue for ALEX.
    CONTEXT: {today}.
    ALEX: "I'm Alex. Here are the Top 5 Stories you need to know."
    ALEX: Read the list clearly: {rundown_text}.
    ALEX: "We have a packed show. We are going deep on every single one of these. But first, {sponsors[0]['copy']}"
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_intro})

    # --- SEGMENT 2: STORY #1 - THE LEAD (Alex & Jamie) ---
    print(f"    ...Writing Story 1: {headlines[0]}")
    # SIGNPOST:
    segments.append({"speaker": "ALEX", "text": f"Let's begin with Story Number One. The headline is: {headlines[0]}. Jamie, walk us through the numbers."})
    
    prompt_s1 = f"""
    Write a DEEP DIVE on Story #1: {headlines[0]}.
    ALEX: Give the hard specs/news.
    JAMIE: "Alex, looking at this..." Give the human/industry perspective.
    CHEMISTRY: Professional banter.
    LENGTH: 14 PARAGRAPHS (approx 1000 words).
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_s1})

    # --- SEGMENT 3: STORY #2 - THE MONEY (Rufus) ---
    print(f"    ...Writing Story 2: {headlines[1]}")
    # BRIDGE: Agree -> Prep Headline -> Handoff
    segments.append({"speaker": "ALEX", "text": f"I totally agree with you, Jamie. Now, let's shift gears to Story Number Two. The headline is: {headlines[1]}. For the financial breakdown, we go live to Rufus {rufus_loc}."})
    segments.append({"type": "sfx"})
    
    prompt_s2 = f"""
    Write a MONOLOGUE for RUFUS.
    TOPIC: Story #2: {headlines[1]}.
    TONE: Cynical, British.
    CONTENT: "Thanks Alex." Analyze the stock/money angle. Use tickers.
    LENGTH: 12 PARAGRAPHS (approx 800 words).
    """
    segments.append({"type": "monologue", "speaker": "RUFUS", "prompt": prompt_s2})
    
    # Sponsor Break
    segments.append({"speaker": "ALEX", "text": f"Back to you in a second, Rufus. This market update is supported by {sponsors[1]['name']}. {sponsors[1]['copy']}"})

    # --- SEGMENT 4: STORY #3 - LEGAL/GLOBAL (Rufus) ---
    print(f"    ...Writing Story 3: {headlines[2]}")
    # BRIDGE: Agree -> Prep Headline -> Handoff
    segments.append({"speaker": "ALEX", "text": f"You nailed it, Rufus. Moving on to Story Number Three. The headline is: {headlines[2]}. This is our Watchdog segment. Rufus, what are the regulators saying?"})
    
    prompt_s3 = f"""
    Write a DIALOGUE for RUFUS and ALEX.
    TOPIC: Story #3: {headlines[2]}.
    RUFUS: "The regulators are waking up, Alex." Discuss Legal/Global impact.
    ALEX: Ask a clarifying question about the law or China/EU impact.
    RUFUS: Give a sharp prediction.
    LENGTH: 10 PARAGRAPHS (approx 700 words).
    """
    segments.append({"type": "dialogue", "default": "RUFUS", "prompt": prompt_s3})

    # --- SEGMENT 5: STORIES #4 & #5 - RAPID FIRE (All 3) ---
    print(f"    ...Writing Stories 4 & 5")
    # BRIDGE: Agree -> Prep Headlines -> Handoff
    segments.append({"speaker": "ALEX", "text": f"That is a scary thought. Now, we find ourselves in the Rapid Fire segment where me, Jamie, and Rufus will discuss the final two topics: {headlines[3]} and {headlines[4]}. Let's debate."})
    
    prompt_rapid = f"""
    Write a 3-WAY ROUNDTABLE.
    TOPICS: {headlines[3]} AND {headlines[4]}.
    JAMIE: Give a quick take on Story 4.
    RUFUS: Give a cynical take on Story 4 or 5.
    ALEX: Wrap it up.
    LENGTH: 12 PARAGRAPHS (approx 800 words).
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_rapid})

    # --- OUTRO ---
    segments.append({"speaker": "ALEX", "text": f"That is your briefing for today. Subscribe so you don't get left behind. {sponsors[2]['copy']}"})

    return segments

# --- 5. PRODUCTION ---
def produce_episode():
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    intel = gather_intel()
    sponsors = get_sponsors()
    script_objects = generate_script_objects(intel, sponsors, rufus_loc)
    
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(f"Top 5: {intel['headlines'][0]} #AI")

    print(" >> 🎙️  RECORDING...")
    audio_clips = []
    
    for item in script_objects:
        if "text" in item:
            text = clean_text(item["text"])
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
                print(f"    ✔ Recorded {item['speaker']}")
            except: pass
            
        elif item.get("type") == "sfx":
            if TRANSITION_SFX.exists(): audio_clips.append(AudioSegment.from_mp3(TRANSITION_SFX))

        elif item.get("type") == "monologue":
            text = generate_text(item["prompt"])
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=clean_text(text)).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
                print(f"    ✔ Recorded {item['speaker']} (Monologue)")
            except: pass

        elif item.get("type") == "dialogue":
            raw_text = generate_text(item["prompt"])
            lines = raw_text.split('\n')
            current_speaker = item["default"]
            for line in lines:
                if not line.strip(): continue
                if ":" in line[:10]:
                    parts = line.split(":", 1)
                    possible_speaker = parts[0].strip().upper()
                    if possible_speaker in CAST:
                        current_speaker = possible_speaker
                        line = parts[1]
                text = clean_text(line)
                if text:
                    voice = CAST[current_speaker]
                    try:
                        path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                        client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(path)
                        audio_clips.append(AudioSegment.from_mp3(path))
                    except: pass
            print(f"    ✔ Recorded Dialogue")

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
    
    outfile = AUDIO_DIR / f"podcast_{datetime.date.today()}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    meta = {"file": str(outfile), "title": f"AI Edge: {intel['headlines'][0]}", "description": "Daily AI News.", "tags": "#AI"}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)
    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
