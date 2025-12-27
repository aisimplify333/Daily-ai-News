import os
import json
import random
import re
import datetime
import feedparser
import requests
import io
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment

# --- CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)
ASSETS_DIR = BASE_DIR / "assets"

SPOTIFY_URL = "https://open.spotify.com/show/YOUR_SHOW_ID_HERE" 
VOICES = {"ALEX": "onyx", "JAMIE": "nova", "RUFUS": "fable"}

# --- HOLIDAY CALENDAR (US) ---
US_HOLIDAYS = [
    (1, 1),   # New Year's
    (7, 4),   # Independence Day
    (12, 25), # Christmas
    (11, 27), # Thanksgiving (Approx)
    (10, 31)  # Halloween (Special)
]

# --- THE DATA ENGINE (ALL FEEDS) ---
# We fetch EVERYTHING for context, then filter by show type.
ALL_FEEDS = {
    "TECH": [
        "https://venturebeat.com/category/ai/feed/",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://feeds.arstechnica.com/arstechnica/index"
    ],
    "SKEPTIC": [
        "https://garymarcus.substack.com/feed",
        "https://futurism.com/feed",
        "https://dev.to/feed/tag/ai"
    ],
    "POLITICS_MONEY": [
        "https://www.lawfaremedia.org/feeds/rss",
        "https://www.politico.eu/section/technology/feed/",
        "https://news.crunchbase.com/feed/",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
    ]
}

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Deep dives into AI, Technology, and the Future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology"
}

# --- LOGIC: DETERMINE SHOW TYPE ---
def get_show_type():
    today = datetime.date.today()
    
    # 1. CHECK HOLIDAY
    if (today.month, today.day) in US_HOLIDAYS:
        return "HOLIDAY_SPECIAL"
    
    # 2. CHECK WEEKEND
    if today.weekday() == 5: # Saturday
        return "WEEKLY_WRAP"
    if today.weekday() == 6: # Sunday
        return "SUNDAY_DEBATE"
        
    # 3. DEFAULT
    return "DAILY_NEWS"

# --- LOGIC: GET STRUCTURE BASED ON TYPE ---
def get_show_settings(show_type):
    print(f" >> 🗓️ DETECTED SHOW TYPE: {show_type}")
    
    if show_type == "HOLIDAY_SPECIAL":
        # 45 MINUTES (Massive Deep Dive)
        return {
            "tone": "Philosophical, Future-Looking, Epic.",
            "segments": [
                {"name": "HOOK", "words": 100, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "INTRO_SPECIAL", "words": 100, "cast": "ALEX_SOLO", "transition": False},
                {"name": "DEEP_DIVE_PART_1", "words": 2000, "cast": "ALL_THREE", "transition": True},
                {"name": "SPONSOR_1", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},
                {"name": "DEEP_DIVE_PART_2", "words": 2000, "cast": "ALL_THREE", "transition": True},
                {"name": "SPONSOR_2", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},
                {"name": "DEEP_DIVE_PART_3", "words": 2000, "cast": "ALL_THREE", "transition": True},
                {"name": "OUTRO_EPIC", "words": 500, "cast": "ALEX_CTA", "transition": False}
            ]
        }
        
    elif show_type == "SUNDAY_DEBATE":
        # 30 MINUTES (Alex vs Jamie)
        return {
            "tone": "Argumentative, Heated, No Script.",
            "segments": [
                {"name": "HOOK_FIGHT", "words": 100, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "INTRO_DEBATE", "words": 100, "cast": "ALEX_SOLO", "transition": False},
                {"name": "ROUND_1_THESIS", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "SPONSOR_1", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},
                {"name": "ROUND_2_ANTITHESIS", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "ROUND_3_SYNTHESIS", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "OUTRO_VOTE", "words": 300, "cast": "ALEX_CTA", "transition": False}
            ]
        }
        
    elif show_type == "WEEKLY_WRAP":
        # 30 MINUTES (Review of the Week)
        return {
            "tone": "Reflective, Analytical, Summary.",
            "segments": [
                {"name": "HOOK", "words": 100, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "INTRO_WRAP", "words": 100, "cast": "ALEX_SOLO", "transition": False},
                {"name": "BEST_STORY_1", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "SPONSOR_1", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},
                {"name": "BEST_STORY_2", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "RUFUS_WEEKLY_MARKET", "words": 1500, "cast": "RUFUS_MONEY", "transition": True},
                {"name": "OUTRO_CTA", "words": 300, "cast": "ALEX_CTA", "transition": False}
            ]
        }

    else: 
        # DAILY NEWS (20 MINUTES)
        return {
            "tone": "High Energy, Fast, Data-Heavy.",
            "segments": [
                {"name": "HOOK", "words": 80, "cast": "ALEX_JAMIE", "transition": False},
                {"name": "INTRO_DAILY", "words": 80, "cast": "ALEX_SOLO", "transition": False},
                {"name": "BLOCK_A_TECH", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
                {"name": "SPONSOR_1", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},
                {"name": "BLOCK_B_POLITICS", "words": 1500, "cast": "RUFUS_POLITICS", "transition": True},
                {"name": "SPONSOR_2", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},
                {"name": "BLOCK_C_MONEY", "words": 1200, "cast": "RUFUS_MONEY", "transition": True},
                {"name": "OUTRO_CTA", "words": 300, "cast": "ALEX_CTA", "transition": False}
            ]
        }

# --- NEWS GATHERING (STEALTH MODE) ---
def fetch_news():
    print(" >> 📡 INGESTING GLOBAL DATA...")
    data_text = ""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    for category, urls in ALL_FEEDS.items():
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    feed = feedparser.parse(io.BytesIO(response.content))
                    for entry in feed.entries[:3]: # Grab Top 3 from EVERY feed
                        title = entry.title
                        summary = re.sub('<[^<]+?>', '', entry.summary)[:400]
                        data_text += f"[{category}] {title} | {summary}\n"
            except: pass
            
    if not data_text: return "System Error: No News Data Found. Use general AI knowledge."
    return data_text

# --- SPONSOR SYSTEM ---
used_sponsors = []
def load_sponsor():
    global used_sponsors
    default_ads = [
        "ElevenLabs. The most realistic AI audio platform. Go to elevenlabs dot io.",
        "Notion AI. Your connected workspace. notion dot so."
    ]
    ads = []
    paths = [BASE_DIR / "sponsors.json", ASSETS_DIR / "sponsors.json"]
    for p in paths:
        try:
            with open(p) as f: 
                data = json.load(f)
                ads = [s["read_copy"] for s in data["sponsors"]]
                break
        except: pass
    if not ads: ads = default_ads
    
    available = [ad for ad in ads if ad not in used_sponsors]
    if not available: 
        used_sponsors = [] 
        available = ads
    choice = random.choice(available)
    used_sponsors.append(choice)
    return choice

def get_asset(name):
    if (ASSETS_DIR / name).exists(): return ASSETS_DIR / name
    if (BASE_DIR / name).exists(): return BASE_DIR / name
    return None

# --- WRITER ---
def draft_segment(seg, data_context, settings, show_type, sponsor):
    seg_name = seg["name"]
    
    # 1. COLD OPEN (HARD CODED RULES)
    if "HOOK" in seg_name:
        return client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": f"Write a 80-word COLD OPEN. JAMIE INTERRUPTS ALEX. Start with a shocking number/stat from:\n{data_context[:2000]}\nRULES: NO 'Hello'. NO 'Welcome'. Start in the middle of the fight."}]).choices[0].message.content

    # 2. INTROS
    if seg_name == "INTRO_DAILY": return "ALEX: Welcome to The AI Edge. I'm Alex. We're tracking the collision of Code, Capital, and Conflict. Let's get to work."
    if seg_name == "INTRO_WRAP": return "ALEX: It's Saturday. The markets are closed, but the code never sleeps. This is The AI Edge Weekly Wrap."
    if seg_name == "INTRO_DEBATE": return "ALEX: It's Sunday. No news reading today. Just the fight. Jamie, you think the industry is lying to us?"
    if seg_name == "INTRO_SPECIAL": return "ALEX: Happy Holidays. The screens are off, but the future is still being written. Welcome to a Special Edition."

    # 3. SPONSORS
    if seg["cast"] == "JAMIE_SPONSOR": return f"JAMIE: Quick break. {sponsor}"

    # 4. CONTENT BLOCKS
    if seg["cast"] == "RUFUS_POLITICS":
        cast_instr = "**CAST:** ALEX & RUFUS. **TOPIC:** Law, War, Regulations. **DATA:** Use [POLITICS_MONEY] tags."
    elif seg["cast"] == "RUFUS_MONEY":
        cast_instr = "**CAST:** RUFUS (Solo). **TOPIC:** Markets, VC, IPOs. **DATA:** Use [POLITICS_MONEY] tags."
    elif seg["cast"] == "ALEX_CTA":
        cast_instr = "**CAST:** ALEX. **SCRIPT:** 'Share this link with one friend. Just one. That is how we win.'"
    else:
        cast_instr = "**CAST:** ALEX & JAMIE. **TOPIC:** Tech & Skepticism. **DATA:** Use [TECH] & [SKEPTIC] tags."

    system_prompt = f"""
    Write **{seg_name}**. Target {seg['words']} words.
    **TONE:** {settings['tone']}
    **SHOW TYPE:** {show_type}
    **DATA SOURCE:** Use the provided context. Quote specific headlines.
    **CONTEXT:** {data_context[:10000]} 
    **RULES:**
    1. **LONG FORM.** This is a {seg['words']} word segment. Go deep.
    2. **DIALOGUE ONLY.**
    3. **NO REPETITION.** Don't re-introduce people.
    {cast_instr}
    """
    
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}]).choices[0].message.content

def punch_up(text):
    if "share this" in text.lower(): return text 
    system = "Script Doctor. Remove 'In conclusion'. Add interruptions ('--'). Ensure flow."
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system}, {"role": "user", "content": text}]).choices[0].message.content

def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text).replace('**', '')
    if "Welcome back" in text: return ""
    return text.strip()

def produce_episode():
    # 1. SETUP
    show_type = get_show_type()
    settings = get_show_settings(show_type)
    data_context = fetch_news()
    
    audio_segs = []
    full_script = ""
    
    # Assets
    p_intro = get_asset("intro.mp3")
    p_outro = get_asset("outro.mp3")
    p_trans = get_asset("transition.mp3")
    m_intro = AudioSegment.from_mp3(p_intro) if p_intro else AudioSegment.silent(1000)
    m_outro = AudioSegment.from_mp3(p_outro) if p_outro else AudioSegment.silent(1000)
    s_trans = (AudioSegment.from_mp3(p_trans) - 3) if p_trans else AudioSegment.silent(500)

    for seg in settings['segments']:
        print(f" >> Seg: {seg['name']}")
        if seg.get("transition"): audio_segs += [s_trans, AudioSegment.silent(200)] 
        
        sponsor = load_sponsor() 
        draft = draft_segment(seg, data_context, settings, show_type, sponsor)
        script = punch_up(draft)
        full_script += script + "\n"
        
        for line in script.split('\n'):
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker, text = match.group(1).upper(), clean_text(match.group(2))
                if not text: continue
                
                voice = VOICES.get(speaker, "onyx")
                f = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(f)
                audio_segs.append(AudioSegment.from_mp3(f))
        
        if "HOOK" in seg["name"]:
            audio_segs.append(AudioSegment.silent(300))
            audio_segs.append(m_intro)
            audio_segs.append(AudioSegment.silent(300))

    audio_segs.append(m_outro)
    final = sum(audio_segs)
    fname = f"podcast_{datetime.date.today()}.mp3"
    final.export(AUDIO_DIR / fname, format="mp3")
    
    # Metadata
    meta = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Gen JSON {title, hook, hashtags}"}, {"role": "user", "content": full_script[:2000]}], response_format={"type": "json_object"}).choices[0].message.content
    meta = json.loads(meta)
    with open("episode_metadata.json", "w") as f: json.dump(meta, f)
    with open("viral_caption.txt", "w") as f: f.write(f"🚀 {meta['title']}\n\n{meta['hook']}\n\n👇 Listen:\n{SPOTIFY_URL}\n\n{' '.join(meta['hashtags'])}")
    print(f"DONE: {fname}")

if __name__ == "__main__":
    produce_episode()
