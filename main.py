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
    "ALEX": "onyx",    # The Anchor: Serious, pacing, the "voice of record."
    "JAMIE": "nova",   # The Humanist: Empathetic, worried, interrupts with "Wait a minute."
    "RUFUS": "fable",  # The Cynic: British, money-focused, dismissive of PR.
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "on the trading floor in London",
    "monitoring the pre-market in Hong Kong",
    "tracking silicon shipments in Taiwan",
    "watching energy grids in Texas",
    "at the regulator's office in Brussels"
]

# --- 2. FEEDS (Data Rich) ---
FEED_SOURCES = {
    "TITANS": [
        "https://openai.com/blog/rss.xml",
        "https://blogs.microsoft.com/ai/feed/",
        "https://news.google.com/rss/search?q=Nvidia+Stock+News&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=OpenAI+Release+Data&hl=en-US&gl=US&ceid=US:en"
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
        "https://news.google.com/rss/search?q=AI+Regulation+EU+China+Lawsuit&hl=en-US&gl=US&ceid=US:en",
        "https://restofworld.org/feed/"
    ]
}

# --- 3. INTEL ENGINE ---
def deep_search_fallback(query):
    print(f"   ⚠️ DEEP SEARCH: {query}...")
    results = []
    try:
        ddgs = DDGS()
        # Searching for specific DATA: numbers, prices, dates
        search_results = ddgs.text(f"{query} statistics data {datetime.date.today().year}", max_results=3)
        for r in search_results: results.append(r['title'])
    except: pass
    return results

def is_hard_news(title):
    fluff = ["how to", "guide", "best of", "gift", "deal", "game", "review", "monitor"]
    return not any(x in title.lower() for x in fluff)

def gather_intel():
    print(" >> 📡 GATHERING THE 5 HEADLINES...")
    intel = {"headlines": [], "money": [], "legal": []}
    
    # Headlines (Titans + Infra)
    stories = []
    for url in FEED_SOURCES["TITANS"] + FEED_SOURCES["INFRA"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title): stories.append(entry.title)
        except: pass
    
    if len(stories) < 5: stories += deep_search_fallback("Top AI Business News Today")
    # De-duplicate and take top 5
    intel["headlines"] = list(set(stories))[:5]
    
    # Money Specific
    money_stories = []
    for url in FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title: money_stories.append(entry.title)
        except: pass
    if not money_stories: money_stories = ["Global Tech Market Cap Shift"]
    intel["money"] = money_stories[:1]

    # Legal/Global Specific
    legal_stories = []
    for url in FEED_SOURCES["LEGAL_GLOBAL"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                legal_stories.append(entry.title)
        except: pass
    if not legal_stories: legal_stories = ["Global AI Safety Mandates"]
    intel["legal"] = legal_stories[:1]
    
    return intel

def get_sponsors():
    return [
        {"name": "ElevenLabs", "copy": "The standard for AI voice. Scale your content globally. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Stop drowning in tabs. Notion AI organizes your business. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. Daily business news without the jargon. MorningBrew.com."}
    ]

# --- 4. THE WRITER (SANITIZED) ---
def generate_text(system_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.85, # Higher temp = More "Chemistry/Chaos"
        messages=[{"role": "system", "content": system_prompt}]
    )
    return response.choices[0].message.content.strip()

def clean_text_for_audio(text):
    # THE FIREWALL: Remove stage directions
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text)
    
    # Remove Prompt Leaks
    forbidden = ["Structure:", "Length:", "Note:", "Tone:", "Alex:", "Jamie:", "Rufus:"]
    for word in forbidden:
        if text.startswith(word):
            text = text.replace(word, "").strip()

    text = text.replace('"', '').replace("'", "")
    text = text.replace("...", ".") 
    text = text.replace("AI", "A.I.")
    return text.strip()

def write_script_objects(intel, sponsors, rufus_loc):
    print(" >> ✍️  WRITING SHOW (Broadcast Mode)...")
    today = datetime.date.today().strftime("%A, %B %d")
    segments = []
    
    # Ensure 5 headlines
    headlines = intel['headlines']
    while len(headlines) < 5: headlines.append("Global Market Update")
    
    rundown_text = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])

    # --- SEGMENT 1: COLD OPEN & WELCOME (Hardcoded) ---
    segments.append({"speaker": "ALEX", "text": f"Breaking news: {headlines[0]}. This changes the timeline."})
    
    # Hardcoded Welcome to prevent "Missing Build"
    welcome_text = f"Good morning. It is {today}. I'm Alex, and this is the AI Edge. Here is the rundown of the top 5 stories moving the world today."
    segments.append({"speaker": "ALEX", "text": welcome_text})
    
    # The List
    for i, h in enumerate(headlines):
        segments.append({"speaker": "ALEX", "text": f"Story Number {i+1}: {h}."})
        
    segments.append({"speaker": "ALEX", "text": f"But first, a word from {sponsors[0]['name']}. {sponsors[0]['copy']}"})

    # --- SEGMENT 2: THE LEAD (Alex & Jamie) ---
    print(f"    ...Writing Story 1: {headlines[0]}")
    segments.append({"speaker": "ALEX", "text": f"Let's dive into Story Number One: {headlines[0]}. Jamie, walk us through the numbers."})
    
    prompt_s1 = f"""
    Write a HEATED DISCUSSION between ALEX and JAMIE about: {headlines[0]}.
    - ALEX: Stick to the HARD DATA (Specs, Billions, Dates).
    - JAMIE: Interrupt Alex. Be worried about the human cost/jobs.
    - TONE: Like "The Daily" but more argumentative.
    - LENGTH: 14 PARAGRAPHS (approx 1000 words).
    - FORMAT: Just the dialogue. No "Scene 1" labels.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_s1})

    # --- SEGMENT 3: THE MONEY (Rufus) ---
    print(f"    ...Writing Story 2: {headlines[1]}")
    # Hardcoded Bridge
    segments.append({"speaker": "ALEX", "text": f"I hear you, Jamie. It's risky. Now, let's pivot to Story Number Two: {headlines[1]}. For the financial reality check, we go live to Rufus {rufus_loc}."})
    segments.append({"type": "sfx"})
    
    prompt_s2 = f"""
    Write a CYNICAL MONOLOGUE for RUFUS.
    TOPIC: {headlines[1]}.
    - TONE: British, arrogant, focused purely on ROI and Stock Prices.
    - CONTENT: Mock the hype. Look at the balance sheet.
    - METAPHOR: Use a metaphor like "putting Christmas on layaway."
    - LENGTH: 12 PARAGRAPHS.
    """
    segments.append({"type": "monologue", "speaker": "RUFUS", "prompt": prompt_s2})
    
    # Sponsor 2
    segments.append({"speaker": "ALEX", "text": f"Brutal, Rufus. Back to you in a moment. This update is supported by {sponsors[1]['name']}. {sponsors[1]['copy']}"})

    # --- SEGMENT 4: THE WATCHDOG (Legal/Global) ---
    print(f"    ...Writing Story 3: {headlines[2]}")
    segments.append({"speaker": "ALEX", "text": f"Moving on to Story Number Three: {headlines[2]}. This is our Watchdog segment. Rufus, are the regulators asleep?"})
    
    prompt_s3 = f"""
    Write a DIALOGUE for RUFUS and ALEX.
    TOPIC: {headlines[2]}.
    - RUFUS: "They aren't asleep, Alex. They're comatose."
    - CONTENT: Discuss the EU/China/US legal battle.
    - LENGTH: 10 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "RUFUS", "prompt": prompt_s3})

    # --- SEGMENT 5: RAPID FIRE (Stories 4 & 5) ---
    print(f"    ...Writing Rapid Fire")
    # Hardcoded Bridge
    segments.append({"speaker": "ALEX", "text": f"Well, we find ourselves in the Rapid Fire segment where me, Jamie, and Rufus will discuss the final two topics of the day: {headlines[3]} and {headlines[4]}. Let's debate."})
    
    prompt_rapid = f"""
    Write a 3-WAY DEBATE between ALEX, JAMIE, and RUFUS.
    TOPICS: {headlines[3]} AND {headlines[4]}.
    - Fast paced. Interruptions allowed.
    - JAMIE: "That sounds dangerous."
    - RUFUS: "It sounds profitable."
    - LENGTH: 12 PARAGRAPHS.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_rapid})

    # --- OUTRO ---
    segments.append({"speaker": "ALEX", "text": f"That is the Edge for today. We'll be back tomorrow. {sponsors[2]['copy']}"})

    return segments

# --- 5. PRODUCTION ENGINE ---
def produce_episode():
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    intel = gather_intel()
    sponsors = get_sponsors()
    script_objects = write_script_objects(intel, sponsors, rufus_loc)
    
    # Save SEO
    headlines_text = "\n".join([f"- {h}" for h in intel['headlines']])
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(f"The AI Edge: {intel['headlines'][0]}\n\nRUNDOWN:\n{headlines_text}\n\n#AI #TechNews")

    print(" >> 🎙️  RECORDING (Strict Mode)...")
    audio_clips = []
    
    for item in script_objects:
        # 1. Hardcoded Lines
        if "text" in item:
            text = clean_text_for_audio(item["text"])
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
                print(f"    ✔ Recorded {item['speaker']} (Manual)")
            except Exception as e: print(f"Error: {e}")
            
        # 2. SFX
        elif item.get("type") == "sfx":
            if TRANSITION_SFX.exists(): audio_clips.append(AudioSegment.from_mp3(TRANSITION_SFX))

        # 3. Monologue (Guaranteed Speaker)
        elif item.get("type") == "monologue":
            text = generate_text(item["prompt"])
            clean = clean_text_for_audio(text)
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=clean).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
                print(f"    ✔ Recorded {item['speaker']} (Monologue)")
            except: pass

        # 4. Dialogue (The "Smart Parser")
        elif item.get("type") == "dialogue":
            raw_text = generate_text(item["prompt"])
            lines = raw_text.split('\n')
            current_speaker = item["default"]
            
            for line in lines:
                if not line.strip(): continue
                
                # Check if the line STARTS with a speaker name (ALEX:, JAMIE:, RUFUS:)
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[0].strip().upper() in CAST:
                    current_speaker = parts[0].strip().upper()
                    line_content = parts[1].strip()
                else:
                    line_content = line.strip() # Continue with current speaker
                
                # SANITIZE AGAIN
                clean_line = clean_text_for_audio(line_content)
                
                if clean_line and len(clean_line) > 2: # Ignore empty/short junk
                    voice = CAST[current_speaker]
                    try:
                        path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                        client.audio.speech.create(model="tts-1-hd", voice=voice, input=clean_line).stream_to_file(path)
                        audio_clips.append(AudioSegment.from_mp3(path))
                    except: pass
            print(f"    ✔ Recorded Dialogue Block")

    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(5000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(5000)

    if audio_clips: full_audio += audio_clips.pop(0) # Cold Open
    full_audio += intro[:8000].fade_out(2000)
    
    for clip in audio_clips:
        full_audio += clip
        full_audio += AudioSegment.silent(duration=350)
        
    full_audio += outro[:10000].fade_in(2000)
    
    outfile = AUDIO_DIR / f"podcast_{datetime.date.today()}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    meta = {"file": str(outfile), "title": f"The AI Edge: {intel['headlines'][0]}", "description": "Daily News", "tags": "#AI"}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)
    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
