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
    "analyzing energy grids in Texas"
]

# --- 2. FEEDS (The "News Desk") ---
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
    ]
}

# --- 3. INTEL (The "Top 5" Engine) ---
def deep_search_fallback(query, count=3):
    print(f"   ⚠️ SEARCHING WEB FOR: {query}...")
    results = []
    try:
        ddgs = DDGS()
        # Search for hard news
        search_results = ddgs.text(f"{query} {datetime.date.today()}", max_results=count)
        for r in search_results: results.append(r['title'])
    except: pass
    return results

def is_hard_news(title):
    fluff = ["how to", "guide", "best of", "gift", "deal", "game", "review", "monitor"]
    return not any(x in title.lower() for x in fluff)

def gather_intel():
    print(" >> 📡 GATHERING THE TOP 5 STORIES...")
    intel = {"headlines": [], "deep_dive": [], "money": []}
    
    # 1. HEADLINES (The Top 5)
    all_stories = []
    # Feed Collection
    for url in FEED_SOURCES["TITANS"] + FEED_SOURCES["INFRA"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title): all_stories.append(entry.title)
        except: pass
    
    # Fallback if feeds are thin
    if len(all_stories) < 5:
        all_stories += deep_search_fallback("Top Artificial Intelligence News Stories Today", 5)
    
    # Select Top 5 Unique Stories
    intel["headlines"] = list(set(all_stories))[:5]

    # 2. MONEY STORY (For Rufus)
    money_stories = []
    for url in FEED_SOURCES["MONEY"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title: money_stories.append(entry.title)
        except: pass
    if not money_stories: money_stories = deep_search_fallback("AI Tech Stock Market News", 1)
    intel["money"] = money_stories[:1] if money_stories else ["Global Tech Market Update"]
    
    return intel

def get_sponsors():
    return [
        {"name": "ElevenLabs", "copy": "The standard for AI voice. Scale your content globally. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Stop drowning in tabs. Notion AI organizes your business. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. Daily business news without the jargon. MorningBrew.com."}
    ]

# --- 4. THE WRITER (STRUCTURED ENGINE) ---
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
    print(" >> ✍️  WRITING SHOW (Locked Structure)...")
    today = datetime.date.today().strftime("%A, %B %d")
    segments = []
    
    # Data Setup
    headlines = intel['headlines']
    # If we somehow have fewer than 5, fill placeholders (Safety Net)
    while len(headlines) < 5: headlines.append("Global AI Market Updates")
    
    top_story = headlines[0]
    money_story = intel['money'][0]
    
    # Formatted List for Prompt
    rundown_list = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])

    # --- SEGMENT 1: COLD OPEN (Alex) ---
    segments.append({"speaker": "ALEX", "text": f"Breaking news: {top_story}. It’s starting."})
    
    # --- SEGMENT 2: THE RUNDOWN (Alex) ---
    # Python Hard-Codes the Intro so it never fails
    segments.append({"speaker": "ALEX", "text": f"I'm Alex. This is the AI Edge for {today}. Here are the top 5 stories you need to know."})
    
    # Alex reads the list one by one
    for i, h in enumerate(headlines):
        segments.append({"speaker": "ALEX", "text": f"Number {i+1}: {h}."})
    
    segments.append({"speaker": "ALEX", "text": f"But first, a word from {sponsors[0]['name']}."})
    segments.append({"speaker": "ALEX", "text": sponsors[0]['copy']})

    # --- SEGMENT 3: DEEP DIVE (Alex & Jamie) ---
    prompt_deep = f"""
    Write a DEEP DIVE dialogue between ALEX and JAMIE.
    TOPIC: {top_story} (The #1 Story).
    ALEX: Provide the HARD SPECS (Numbers, Dates, Costs).
    JAMIE: React with SKEPTICISM regarding the Human Impact.
    CHEMISTRY: They respect each other but disagree.
    LENGTH: 1000 words (approx 8 mins).
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_deep})

    # --- SEGMENT 4: SPONSOR 2 (Jamie) ---
    segments.append({"speaker": "JAMIE", "text": f"This deep dive is supported by {sponsors[1]['name']}. {sponsors[1]['copy']}"})

    # --- SEGMENT 5: RUFUS TRANSITION (Hardcoded) ---
    segments.append({"speaker": "ALEX", "text": f"Now, let's follow the money. We go live to Rufus {rufus_loc}. Rufus, what are the charts saying?"})
    segments.append({"type": "sfx"})

    # --- SEGMENT 6: THE MONEY (Rufus) ---
    prompt_rufus = f"""
    Write a MONOLOGUE for RUFUS.
    TOPIC: {money_story}.
    TONE: Cynical, British, Profit-Obsessed.
    CONTENT: "Thanks Alex." Analyze the stock impact. Mention tickers (NVDA, MSFT).
    LENGTH: 800 words (approx 5 mins).
    """
    segments.append({"type": "monologue", "speaker": "RUFUS", "prompt": prompt_rufus})

    # --- SEGMENT 7: ROUNDTABLE (All 3) ---
    prompt_round = f"""
    Write a 3-WAY DEBATE.
    ALEX: "Rufus, is this sustainable?"
    RUFUS: "Only if the ROI hits."
    JAMIE: "And if it breaks society?"
    DEBATE: The ethics vs profit of {top_story}.
    LENGTH: 600 words.
    """
    segments.append({"type": "dialogue", "default": "ALEX", "prompt": prompt_round})

    # --- SEGMENT 8: OUTRO (Alex) ---
    segments.append({"speaker": "ALEX", "text": f"That's the Edge. Subscribe to stay ahead. {sponsors[2]['copy']}"})

    return segments

# --- 5. PRODUCTION ---
def produce_episode():
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    intel = gather_intel()
    sponsors = get_sponsors()
    script_objects = generate_script_objects(intel, sponsors, rufus_loc)
    
    # --- GENERATE SEO METADATA ---
    # This creates the file you need for Spotify/YouTube
    headlines_text = "\n".join([f"- {h}" for h in intel['headlines']])
    seo_content = f"TITLE: The AI Edge: {intel['headlines'][0]}\n\nSHOW NOTES:\nToday's Top 5 Stories:\n{headlines_text}\n\n#AI #TechNews #{intel['headlines'][0][:10].replace(' ','')}"
    
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(seo_content)
    with open(BASE_DIR / "show_notes.txt", "w") as f: f.write(headlines_text)

    print(" >> 🎙️  RECORDING...")
    audio_clips = []
    
    for item in script_objects:
        # 1. Simple Hardcoded Lines
        if "text" in item:
            text = clean_text(item["text"])
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
                print(f"    ✔ Recorded {item['speaker']}")
            except: pass
            
        # 2. SFX
        elif item.get("type") == "sfx":
            if TRANSITION_SFX.exists(): audio_clips.append(AudioSegment.from_mp3(TRANSITION_SFX))

        # 3. Monologue (Guaranteed Speaker)
        elif item.get("type") == "monologue":
            text = generate_text(item["prompt"])
            voice = CAST[item["speaker"]]
            try:
                path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=clean_text(text)).stream_to_file(path)
                audio_clips.append(AudioSegment.from_mp3(path))
                print(f"    ✔ Recorded {item['speaker']} (Monologue)")
            except: pass

        # 4. Dialogue (Chemistry Parser)
        elif item.get("type") == "dialogue":
            raw_text = generate_text(item["prompt"])
            lines = raw_text.split('\n')
            current_speaker = item["default"]
            
            for line in lines:
                if not line.strip(): continue
                # Check for Speaker Tag
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
            print(f"    ✔ Recorded Dialogue Block")

    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(5000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(5000)

    # 1. Cold Open (First clip)
    if audio_clips: full_audio += audio_clips.pop(0)

    # 2. Intro Music (Fade In/Out)
    full_audio += intro[:8000].fade_out(2000)

    # 3. Rest of Show
    for clip in audio_clips:
        full_audio += clip
        full_audio += AudioSegment.silent(duration=350)

    # 4. Outro
    full_audio += outro[:10000].fade_in(2000)
    
    outfile = AUDIO_DIR / f"podcast_{datetime.date.today()}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    # Metadata for Spotify JSON
    meta = {
        "file": str(outfile), 
        "title": f"The AI Edge: {intel['headlines'][0]}", 
        "description": f"Today's Top 5 Stories:\n{headlines_text}", 
        "tags": "#AI #News #Tech"
    }
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)
    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
