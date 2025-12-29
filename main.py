import os
import json
import random
import datetime
import feedparser
import re
import shutil
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment, effects
from duckduckgo_search import DDGS

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Paths
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

# Clean Start
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
# NOTE: We are IGNORING sponsors.json to prevent "Meta" jokes.

# THE CAST
CAST = {
    "ALEX": "onyx",    # The Brain: Huberman-style depth.
    "JAMIE": "nova",   # The Heart: Bartlett-style vulnerability.
    "RUFUS": "fable",  # The Wallet: Succession-style cynicism.
    "SPONSOR 1": "onyx",
    "SPONSOR 2": "nova",
    "SPONSOR 3": "onyx",
    "SPONSOR": "onyx"
}

RUFUS_LOCATIONS = [
    "analyzing chip supply chains in Taiwan",
    "watching the pre-market movers in New York",
    "reviewing data center energy audits in Virginia",
    "tracking insider trading filings in London",
    "monitoring sovereign wealth funds in Dubai"
]

# --- 2. HARD NEWS FEEDS (TITANS ONLY) ---
FEED_SOURCES = {
    "TITANS": [
        "https://openai.com/blog/rss.xml",
        "https://ai.googleblog.com/feeds/posts/default",
        "https://blogs.microsoft.com/ai/feed/",
        # Google News Bridges for Hard News
        "https://news.google.com/rss/search?q=Nvidia+Stock+AI&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=OpenAI+Release+Date&hl=en-US&gl=US&ceid=US:en"
    ],
    "INFRASTRUCTURE": [
        "https://www.datacenterdynamics.com/rss/",
        "https://www.semianalysis.com/feed",
        "https://www.anandtech.com/rss/"
    ],
    "FINANCE": [
        "https://finance.yahoo.com/news/rssindex",
        "https://techcrunch.com/category/enterprise/feed/",
        "https://blog.palantir.com/feed"
    ]
}

# --- 3. INTELLIGENCE GATHERING (STRICT FILTER) ---
def deep_search_fallback(query):
    print(f"   ⚠️ FEED LOW. SCOURING WEB FOR DATA: {query}...")
    results = []
    try:
        ddgs = DDGS()
        # "News" implies recency. "Data" implies numbers.
        search_results = ddgs.text(f"{query} statistics data {datetime.date.today()}", max_results=3)
        for r in search_results: results.append(f"DATA POINT: {r['title']} - {r['body']}")
    except: pass
    return results

def is_hard_news(title):
    """
    STRICT FILTER: Rejects startups, reviews, and fluff.
    Must sound like it belongs on Bloomberg.
    """
    title_lower = title.lower()
    # The "Trash" List
    fluff = ["how to", "guide", "best of", "gift", "deal", "sale", "review", "monitor", "game", "sauron", "startup"]
    for word in fluff:
        if word in title_lower: return False
    
    # The "Must Have" (Optional but good heuristic)
    # We let the feed source quality do most of the work, but filter obvious junk.
    return True

def gather_intel():
    print(" >> 📡 GATHERING HARD DATA (Filtering out Fluff)...")
    intel = {"titans": [], "infra": [], "money": []}
    
    # 1. Titans (The Big 4)
    for url in FEED_SOURCES["TITANS"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    intel["titans"].append(entry.title)
                    if len(intel["titans"]) >= 3: break
        except: pass
    if len(intel["titans"]) < 1: intel["titans"] += deep_search_fallback("Nvidia OpenAI Microsoft stock news")

    # 2. Infrastructure (Chips/Energy)
    for url in FEED_SOURCES["INFRASTRUCTURE"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if is_hard_news(entry.title):
                    intel["infra"].append(entry.title)
                    if len(intel["infra"]) >= 2: break
        except: pass

    # 3. Finance
    for url in FEED_SOURCES["FINANCE"]:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if "AI" in entry.title and is_hard_news(entry.title):
                    intel["money"].append(entry.title)
                    if len(intel["money"]) >= 3: break
        except: pass
    
    return intel

def get_sponsors():
    # HARDCODED: The ONLY way to guarantee no "I am an AI" jokes.
    return [
        {"name": "ElevenLabs", "copy": "The standard for AI voice. If you need to scale your content globally, you need ElevenLabs. Visit ElevenLabs.io."},
        {"name": "Notion AI", "copy": "Stop drowning in tabs. Notion AI organizes your business, writes your docs, and cleans your workflow. Notion.so."},
        {"name": "Morning Brew", "copy": "Get smarter in 5 minutes. The daily newsletter that breaks down Wall Street without the jargon. Sign up at MorningBrew.com."}
    ]

# --- 4. THE WRITER (SAFE MODE) ---
def generate_segment_with_retry(system_prompt, retries=2):
    """Generates text and CHECKS for cut-offs."""
    for attempt in range(retries):
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.7,
            messages=[{"role": "system", "content": system_prompt}]
        )
        content = response.choices[0].message.content.strip()
        
        # Check if it ends with punctuation
        if content[-1] in ['.', '!', '?', '"']:
            return content
        else:
            print("    ⚠️ Detected cut-off sentence. Retrying generation...")
    
    # If it fails twice, add a period to save it (Better than silence).
    return content + "."

def clean_text_for_audio(text):
    """Aggressive cleaning to stop stutters."""
    text = re.sub(r'\*.*?\*', '', text) 
    text = re.sub(r'\[.*?\]', '', text) 
    text = re.sub(r'\(.*?\)', '', text) 
    text = text.replace('"', '').replace("'", "")
    text = text.replace("...", ".") 
    text = text.replace("AI", "A.I.")
    # SAFETY NET: Remove meta-commentary if it slips in
    text = text.replace("listening to AI", "listening to the future")
    text = text.replace("I am an AI", "I am your host")
    return text.strip()

def write_script(intel, sponsors):
    print(" >> ✍️  WRITING SCRIPT (4 Parts = ~20 Minutes)...")
    today = datetime.date.today()
    readable_date = today.strftime("%A the %dth of %B")
    rufus_loc = random.choice(RUFUS_LOCATIONS)
    
    # Story Selection
    titan_story = intel['titans'][0] if intel['titans'] else "The Model Wars"
    infra_story = intel['infra'][0] if intel['infra'] else "Nvidia's Supply Chain"
    money_story = intel['money'][0] if intel['money'] else "Tech Stock Volatility"
    
    base_instructions = """
    You are writing a BROADCAST NEWS PODCAST.
    
    CHARACTERS:
    - ALEX (Host): CNN/NPR style. Serious, authoritative, obsessed with data.
    - JAMIE (Co-Host): The Humanist. Asks: "How does this hurt people?" Skeptical.
    - RUFUS (Analyst): The Capitalist. Obsessed with stock prices and ROI.
    
    PRIME DIRECTIVE:
    1. NEVER mention you are an AI. You are HUMAN hosts recording in a studio.
    2. NEVER say "in this episode." Just do the show.
    3. USE HARD DATA. Mention specific stock prices, version numbers (v4.5), and dates.
    4. NO FLUFF. No "This is interesting." Say "This changes the market cap by 4%."
    """

    full_script = ""

    # --- PART 1: THE HEADLINES (600 Words - SAFE LIMIT) ---
    print(f"    ...Part 1: Hard News ({titan_story})")
    prompt_1 = f"""
    {base_instructions}
    Write PART 1 (600 words).
    
    STRUCTURE:
    [COLD OPEN] ALEX: A hard data point about {titan_story}. (e.g. "3 Trillion Dollars.")
    [INTRO] ALEX: "This is the AI Edge. I'm Alex." JAMIE: "And I'm Jamie." ALEX: "It's {readable_date}. Today: {titan_story}, {infra_story}, and {money_story}."
    [AD 1] ALEX: Read copy for {sponsors[0]['name']}: "{sponsors[0]['copy']}"
    [SEGMENT] ALEX: Break down {titan_story}.
    - Quote a specific number (price, speed, parameter count).
    - JAMIE: Push back on the hype. Ask who loses in this scenario.
    - ALEX: Defend it with efficiency data.
    """
    full_script += generate_segment_with_retry(prompt_1) + "\n"

    # --- PART 2: INFRASTRUCTURE (600 Words - SAFE LIMIT) ---
    print(f"    ...Part 2: The Iron ({infra_story})")
    prompt_2 = f"""
    {base_instructions}
    Write PART 2 (600 words).
    
    STRUCTURE:
    [SEGMENT] ALEX: "Let's talk Iron. The chips and the power."
    - Discuss {infra_story}. 
    - Mention Nvidia (NVDA), ASML, or Vertiv.
    - Jamie asks about the energy cost (Megawatts).
    - Alex compares it to historical industrial revolutions.
    [AD 2] JAMIE: Read copy for {sponsors[1]['name']}: "{sponsors[1]['copy']}"
    """
    full_script += generate_segment_with_retry(prompt_2) + "\n"

    # --- PART 3: HUMAN IMPACT (600 Words - SAFE LIMIT) ---
    print("    ...Part 3: Society (General Impact)")
    prompt_3 = f"""
    {base_instructions}
    Write PART 3 (600 words).
    
    STRUCTURE:
    [SEGMENT] JAMIE: "We talk about chips, but what about the people?"
    - Discuss a current event regarding AI Safety, Jobs, or Deepfakes.
    - ALEX: Plays Devil's Advocate (Technology creates new jobs).
    - JAMIE: Disagrees. Cites a specific example of displacement.
    """
    full_script += generate_segment_with_retry(prompt_3) + "\n"

    # --- PART 4: THE LEDGER (600 Words - SAFE LIMIT) ---
    print(f"    ...Part 4: The Money ({money_story})")
    prompt_4 = f"""
    {base_instructions}
    Write PART 4 (600 words).
    
    STRUCTURE:
    [SEGMENT] ALEX: "Let's go to Rufus, live {rufus_loc}."
    - RUFUS: "Cheers Alex." Analyze {money_story}.
    - Mention specific tickers (PLTR, MSFT, GOOG).
    - Discuss "CapEx" (Capital Expenditure) and "ROI".
    - RUFUS: Give a cynical prediction for next week's market.
    [OUTRO] ALEX: "Subscribe for the Edge." SPONSOR 3: "{sponsors[2]['copy']}"
    """
    full_script += generate_segment_with_retry(prompt_4)

    return full_script

# --- 5. PRODUCTION ---
def generate_seo_package(script, sponsors):
    print(" >> 🚀 GENERATING SEO METADATA...")
    prompt = f"""
    Generate JSON:
    {{ "title": "Viral Title", "show_notes": "Bulleted list of stories", "hashtags": "#Tags" }}
    SCRIPT START: {script[:2000]}...
    """
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": prompt}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors() 
    script = write_script(intel, sponsors)
    
    with open(BASE_DIR / "debug_script.txt", "w") as f: f.write(script)
    
    seo_data = generate_seo_package(script, sponsors)
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(f"{seo_data['title']}\n\n{seo_data['hashtags']}")
    with open(BASE_DIR / "show_notes.txt", "w") as f: f.write(seo_data['show_notes'])

    print(" >> 🎙️  RECORDING HD LINES...")
    segments = []
    lines = script.split('\n')
    
    for i, line in enumerate(lines):
        if ":" in line:
            parts = line.split(":", 1)
            raw_speaker = parts[0].strip().upper()
            speaker = re.sub(r'[^A-Z0-9 ]', '', raw_speaker).strip() 
            text = parts[1].strip()
            text = clean_text_for_audio(text)
            
            if speaker in CAST and text:
                voice = CAST[speaker]
                try:
                    resp = client.audio.speech.create(model="tts-1-hd", voice=voice, input=text, speed=1.0)
                    path = AUDIO_DIR / f"line_{i:03d}_{speaker}.mp3"
                    resp.stream_to_file(path)
                    seg = AudioSegment.from_mp3(path)
                    seg = effects.strip_silence(seg, silence_thresh=-50, padding=50) 
                    segments.append((speaker, seg))
                    print(f"    ✔ Recorded: {speaker} ({len(text)} chars)")
                except Exception as e:
                    print(f"    ❌ FAILED line {i}: {e}")

    print(" >> 🎚️  MIXING EPISODE...")
    if not segments: return

    full_audio = AudioSegment.empty()
    intro = AudioSegment.from_mp3(INTRO_MUSIC) if INTRO_MUSIC.exists() else AudioSegment.silent(1000)
    outro = AudioSegment.from_mp3(OUTRO_MUSIC) if OUTRO_MUSIC.exists() else AudioSegment.silent(1000)
    sfx = AudioSegment.from_mp3(TRANSITION_SFX) - 6 if TRANSITION_SFX.exists() else AudioSegment.silent(500)

    # Fade in Intro
    if segments:
        intro_dur = 8000 
        full_audio += intro[:intro_dur].fade_out(2000)
        full_audio += segments[0][1]
        segments.pop(0)

    last_speaker = "UNKNOWN"
    for speaker, clip in segments:
        if speaker == "RUFUS" and last_speaker != "RUFUS": 
            full_audio += sfx
        
        if body_audio := full_audio: body_audio += AudioSegment.silent(duration=400)
        full_audio += clip
        last_speaker = speaker

    full_audio += outro[:10000].fade_in(1000)
    
    outfile = AUDIO_DIR / f"podcast_{datetime.date.today()}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    
    meta = {"file": str(outfile), "title": seo_data['title'], "description": seo_data['show_notes'], "tags": seo_data['hashtags']}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)
    print(f" ✅ EPISODE COMPLETE: {outfile}")

if __name__ == "__main__":
    produce_episode()
