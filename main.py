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

# --- THE "HIGH-VOLTAGE" BRAIN ---
PERSONA_FEEDS = {
    "ALEX": [ # HARD TECH & SECURITY
        "https://venturebeat.com/category/ai/feed/",
        "https://www.securityweek.com/rss",                     # <--- Cyber Threats (High Stakes)
        "https://techcrunch.com/category/artificial-intelligence/feed/"
    ],
    "JAMIE": [ # THE SKEPTIC & DEV TOOLS
        "https://dev.to/feed/tag/ai",                           
        "https://garymarcus.substack.com/feed",                 
        "https://futurism.com/feed",                            
        "https://hnrss.org/newest?q=AI"                         
    ],
    "RUFUS": [ # MONEY, LAW, & GEOPOLITICS
        "https://www.lawfaremedia.org/feeds/rss",               # <--- National Security Law (The "Bite")
        "https://www.politico.eu/section/technology/feed/",     # <--- EU Regulation/Conflict
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

# --- NEWS GATHERING (STEALTH MODE) ---
def fetch_news():
    print(" >> 📡 INGESTING GLOBAL CONFLICT DATA...")
    data_brains = {"ALEX": "", "JAMIE": "", "RUFUS": ""}
    # Fake User-Agent to bypass firewalls
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    for persona, urls in PERSONA_FEEDS.items():
        collected_text = ""
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    feed = feedparser.parse(io.BytesIO(response.content))
                    for entry in feed.entries[:2]: 
                        title = entry.title
                        # Aggressive summary cleaning
                        summary = re.sub('<[^<]+?>', '', entry.summary)[:350]
                        collected_text += f"SOURCE: {title} | INTEL: {summary}\n"
            except Exception: pass
        
        if not collected_text: collected_text = "No intel found. Rely on general training data."
        data_brains[persona] = collected_text
        
    return data_brains

# --- 20-MINUTE SHOW STRUCTURE ---
def get_show_settings():
    return {
        "type": "Daily News Unfiltered", 
        "tone": "High Energy, Aggressive, CONFLICT-HEAVY. INTERRUPT OFTEN.", 
        "segments": [
            # BLOCK A: THE HOOK (Must Bite)
            {"name": "HOOK", "words": 75, "cast": "ALEX_JAMIE", "transition": False}, 
            {"name": "INTRO_FORMAT", "words": 60, "cast": "ALEX_SOLO", "transition": False},
            
            # BLOCK B: DEEP DIVE (The Tech)
            {"name": "TOP_STORY_DEEP_DIVE", "words": 1600, "cast": "ALEX_JAMIE", "transition": True},
            
            # SPONSOR 1
            {"name": "SPONSOR_BREAK_1", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},

            # BLOCK C: GEOPOLITICS & LAW (The "Bite" Segment)
            {"name": "RUFUS_GLOBAL_CONFLICT", "words": 1400, "cast": "RUFUS_POLITICS", "transition": True},
            
            # BLOCK D: TOOLS (The Dev Angle)
            {"name": "JAMIE_TOOL_REVIEWS", "words": 1200, "cast": "JAMIE_TOOLS", "transition": True},

            # SPONSOR 2
            {"name": "SPONSOR_BREAK_2", "words": 200, "cast": "JAMIE_SPONSOR", "transition": True},

            # BLOCK E: MONEY (The Markets)
            {"name": "RUFUS_MARKETS_VC", "words": 1000, "cast": "RUFUS_MONEY", "transition": True},
            
            # BLOCK F: OUTRO
            {"name": "SPEED_ROUND", "words": 600, "cast": "ALL_THREE", "transition": True}, 
            {"name": "OUTRO_CTA", "words": 300, "cast": "ALEX_CTA", "transition": False} 
        ]
    }

def get_rufus_location():
    locs = ["The Hague International Court", "The Pentagon Briefing Room", "Shenzhen Manufacturing Hub", "The London Stock Exchange"]
    return random.choice(locs)

# --- SPONSOR ROTATION ---
used_sponsors = []
def load_sponsor():
    global used_sponsors
    default_ads = [
        "ElevenLabs. The most realistic AI audio platform. Go to elevenlabs dot io.",
        "Notion AI. Your connected workspace. Write, plan, and think with AI at notion dot so."
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
    
    # Rotation Logic
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

# --- INTELLIGENT WRITER ---
def draft_segment(seg, brains, settings, loc, sponsor):
    seg_name = seg["name"]
    
    # CONTEXT ROUTING
    if "RUFUS" in seg["cast"]:
        active_context = f"GEOPOLITICS/LAW/MONEY (RUFUS):\n{brains['RUFUS']}"
    elif "TOOLS" in seg["cast"]:
         active_context = f"DEV TOOLS & SKEPTICISM (JAMIE):\n{brains['JAMIE']}"
    else:
        active_context = f"HARD TECH (ALEX):\n{brains['ALEX']}\n\nSKEPTIC (JAMIE):\n{brains['JAMIE']}"

    # 1. THE PERFECT COLD OPEN ALGORITHM
    if seg_name == "HOOK":
        system_prompt = f"""
        **ROLE:** Executive Producer.
        **TASK:** Write a 75-word Cold Open Hook.
        **SOURCE:** Use the most shocking stat in: \n{active_context[:2000]}
        **RULES:**
        1. **FORBIDDEN:** Do NOT say "Hello", "Welcome", "Hi".
        2. **START:** Start immediately with the problem. (e.g., "Nvidia just lost 40 billion...")
        3. **CONFLICT:** Jamie MUST interrupt Alex with a cynical counter-point within the first 10 seconds.
        4. **END:** End on a cliffhanger.
        """
        return client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}]).choices[0].message.content

    # 2. INTRO
    if seg_name == "INTRO_FORMAT":
        return f"ALEX: Welcome to The AI Edge. I'm Alex. We are going deep today. Jamie is tearing apart the latest tools, and Rufus is live at {loc} covering the regulatory war brewing in Europe. Let's get into it."

    # 3. SPONSORS
    if seg["cast"] == "JAMIE_SPONSOR":
        return f"JAMIE: Quick pause. We gotta keep the lights on. {sponsor}"

    # 4. SEGMENT PROMPTS
    if seg["cast"] == "RUFUS_POLITICS":
        cast_instr = f"""
        **CAST:** ALEX throws to RUFUS at {loc}.
        **TOPIC:** WAR, LAW, & GEOPOLITICS.
        **SOURCE:** Use the 'GEOPOLITICS/LAW' context (Lawfare, Politico).
        **RUFUS:** Cynical. Focus on how Governments are fighting back against AI. Mention specific laws or lawsuits.
        """
    elif seg["cast"] == "RUFUS_MONEY":
        cast_instr = """
        **CAST:** RUFUS (Solo).
        **TOPIC:** FOLLOW THE MONEY. VC Funding, IPOs.
        **RUFUS:** "It's all about the liquidity."
        """
    elif seg["cast"] == "JAMIE_TOOLS":
        cast_instr = """
        **CAST:** JAMIE (Solo).
        **TOPIC:** TOOL REVIEW. Pick a specific tool from the context.
        **JAMIE:** Brutally honest. "Is this trash or treasure?"
        """
    elif seg["cast"] == "ALEX_CTA":
        cast_instr = """
        **CAST:** ALEX (Solo).
        **TOPIC:** THE HARD CLOSE.
        **SCRIPT:** "If this episode gave you an edge, do me a favor. Send it to one friend who needs to wake up. Just one. We'll see you tomorrow."
        """
    else: # ALEX_JAMIE
        cast_instr = "**CAST:** ALEX & JAMIE. **TOPIC:** Main Tech Headlines. Debate the impact."

    system_prompt = f"""
    Write **{seg_name}**. Target {seg['words']} words.
    **TONE:** {settings['tone']}
    **CONTEXT:** {active_context}
    **RULES:**
    1. **NO HALLUCINATIONS.** Use the context.
    2. **DIALOGUE ONLY.**
    3. **MAKE IT LONG.** Dive deep.
    {cast_instr}
    """
    
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}]).choices[0].message.content

def punch_up(text):
    if "send it to one friend" in text.lower(): return text 
    system = "Script Doctor. Remove 'In conclusion'. Remove stage directions. Add interruptions ('--')."
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system}, {"role": "user", "content": text}]).choices[0].message.content

def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text).replace('**', '')
    if "Welcome back" in text: return ""
    return text.strip()

def produce_episode():
    brains = fetch_news()
    settings = get_show_settings()
    loc = get_rufus_location()
    
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
        draft = draft_segment(seg, brains, settings, loc, sponsor)
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
        
        if seg["name"] == "HOOK":
            audio_segs.append(AudioSegment.silent(300))
            audio_segs.append(m_intro)
            audio_segs.append(AudioSegment.silent(300))

    audio_segs.append(m_outro)
    final = sum(audio_segs)
    fname = f"podcast_{datetime.date.today()}.mp3"
    final.export(AUDIO_DIR / fname, format="mp3")
    
    # Metadata & Socials
    meta = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Gen JSON {title, hook, hashtags}"}, {"role": "user", "content": full_script[:2000]}], response_format={"type": "json_object"}).choices[0].message.content
    meta = json.loads(meta)
    with open("episode_metadata.json", "w") as f: json.dump(meta, f)
    with open("viral_caption.txt", "w") as f: f.write(f"🚀 {meta['title']}\n\n{meta['hook']}\n\n👇 Listen:\n{SPOTIFY_URL}\n\n{' '.join(meta['hashtags'])}")
    print(f"DONE: {fname}")

if __name__ == "__main__":
    produce_episode()
