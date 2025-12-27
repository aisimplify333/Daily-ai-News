import os
import json
import random
import re
import datetime
import feedparser
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

# --- THE TRUTH ENGINE (LEGAL & MONEY UPGRADE) ---
PERSONA_FEEDS = {
    "ALEX": [ # HARD TECH & ENTERPRISE NEWS
        "https://venturebeat.com/category/ai/feed/",
        "https://www.theregister.com/software/ai_ml/headlines.atom",
        "https://www.wired.com/feed/category/ai/latest/rss",
        "https://techcrunch.com/category/artificial-intelligence/feed/"
    ],
    "JAMIE": [ # THE SKEPTIC & THE HYPE
        "https://garymarcus.substack.com/feed",  
        "https://futurism.com/feed",             
        "https://www.reddit.com/r/ArtificialInteligence/top/.rss?t=day", 
        "https://hnrss.org/newest?q=AI"          
    ],
    "RUFUS": [ # MONEY, LAW & POLICY (UPDATED)
        "https://news.crunchbase.com/feed/",                                # <--- VC Money Flow
        "https://www.technologyreview.com/feed/topic/tech-policy/",         # <--- AI Law & Regulation
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", # <--- Public Markets
        "https://hai.stanford.edu/news/rss"                                 # <--- Ethics/Policy
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

# --- NEWS GATHERING ---
def fetch_news():
    print(" >> 📡 INGESTING DATA FROM VENDOR FEEDS...")
    data_brains = {"ALEX": "", "JAMIE": "", "RUFUS": ""}
    
    for persona, urls in PERSONA_FEEDS.items():
        collected_text = ""
        for url in urls:
            try:
                feed = feedparser.parse(url)
                # We take the top 2 stories from each feed
                for entry in feed.entries[:2]: 
                    title = entry.title
                    summary = re.sub('<[^<]+?>', '', entry.summary)[:300]
                    collected_text += f"SOURCE: {title} | KEY FACT: {summary}\n"
            except Exception as e:
                print(f"    ! Feed Error {url}: {e}")
        
        if not collected_text:
            collected_text = "No RSS data available. State that 'We are waiting on the morning numbers'."
        
        data_brains[persona] = collected_text
        
    return data_brains

# --- FORMAT LOGIC ---
def get_show_settings():
    return {
        "type": "Daily News Unfiltered", 
        "tone": "High Energy, Aggressive, FACT-BASED. INTERRUPT OFTEN.", 
        "segments": [
            {"name": "HOOK", "words": 40, "cast": "ALEX_JAMIE", "transition": False}, 
            {"name": "INTRO_FORMAT", "words": 40, "cast": "ALEX_SOLO", "transition": False},
            {"name": "TOP_STORY_MECHANISMS", "words": 1200, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "RUFUS_MARKETS_LAW", "words": 800, "cast": "RUFUS_FOCUS", "transition": True},
            {"name": "MID_ROLL", "words": 250, "cast": "JAMIE_SPONSOR", "transition": True},
            {"name": "SECONDARY_STORY_IMPACT", "words": 1000, "cast": "ALEX_JAMIE", "transition": True},
            {"name": "SPEED_ROUND_WRAP", "words": 600, "cast": "ALL_THREE", "transition": True}, 
            {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False} 
        ]
    }

def get_rufus_location():
    locs = ["London Stock Exchange", "Canary Wharf", "Zurich", "Hong Kong Port", "Wall Street"]
    return random.choice(locs)

def load_sponsor():
    default_ad = "This episode is sponsored by Cursor. Stop coding like it's 2010. Get Cursor dot com."
    paths = [BASE_DIR / "sponsors.json", ASSETS_DIR / "sponsors.json"]
    for p in paths:
        try:
            with open(p) as f: 
                data = json.load(f)
                return random.choice(data["sponsors"])["read_copy"]
        except: pass
    return default_ad

def get_asset(name):
    if (ASSETS_DIR / name).exists(): return ASSETS_DIR / name
    if (BASE_DIR / name).exists(): return BASE_DIR / name
    return None

# --- WRITER (FACTUAL & PERSONA DRIVEN) ---
def draft_segment(seg, brains, settings, loc, sponsor):
    seg_name = seg["name"]
    
    # 1. BUILD CONTEXT (ROUTING)
    if "RUFUS" in seg["cast"]:
        active_context = f"VC MONEY & LEGAL POLICY (RUFUS ONLY):\n{brains['RUFUS']}"
    else:
        active_context = f"VERIFIED NEWS (ALEX):\n{brains['ALEX']}\n\nSKEPTIC/HYPE DATA (JAMIE):\n{brains['JAMIE']}"

    # 2. THE HOOK
    if seg_name == "HOOK":
        system_prompt = f"""
        You are the Producer. Write the **COLD OPEN HOOK**.
        **MANDATORY:** Quote a specific NUMBER or TOOL from the Verified News.
        **CONTEXT:** {active_context[:1500]}
        **FORMAT:** JAMIE INTERRUPTS ALEX. MAX 40 WORDS.
        """
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}])
        return response.choices[0].message.content

    # 3. INTRO
    if seg_name == "INTRO_FORMAT":
        return "ALEX: Welcome to The AI Edge. I'm Alex, Jamie is digging through the Reddit threads to fight the hype, and we'll hit Rufus for the legal and money beat shortly. Let's go."

    # 4. SPONSOR
    if seg["cast"] == "JAMIE_SPONSOR":
        return f"JAMIE: Quick break for our partner. {sponsor}"

    # 5. SEGMENT GENERATION
    if seg["cast"] == "RUFUS_FOCUS":
        cast_instr = f"""
        **CAST:** ALEX throws to RUFUS.
        **ALEX LINE:** "Let's go live to {loc}. Rufus, what's the lawsuit and money situation?"
        **RUFUS:** Speaks in First Person. Must quote 'VC MONEY & LEGAL POLICY'. Focus on Regulation, Funding Rounds, and Stock drops.
        """
    elif seg["cast"] == "ALEX_JAMIE":
        cast_instr = """
        **CAST:** ALEX/JAMIE. 
        **PROTOCOL:** 1. ALEX: Presents a FACT from 'VERIFIED NEWS'.
        2. JAMIE: Attacks it using 'SKEPTIC DATA'.
        **PACING:** FAST. INTERRUPTIONS.
        """
    elif seg["cast"] == "ALL_THREE":
        cast_instr = "**CAST:** ALL. Rapid fire wrap up."
    elif seg["cast"] == "ALEX_SOLO":
        cast_instr = "**CAST:** ALEX Only. Sign-off."

    system_prompt = f"""
    Write **{seg_name}**. Target {seg['words']} words.
    **TONE:** {settings['tone']}
    **SOURCE MATERIAL:** Use the provided CONTEXT. 
    **CRITICAL RULES:**
    1. **NO HALLUCINATIONS:** If it's not in the data, do not make it up.
    2. **DIALOGUE ONLY:** NO stage directions.
    3. **NO RE-INTRODUCTIONS.** 4. **NO SUMMARIES.** Just stop talking when done.
    {cast_instr}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"DATA CONTEXT:\n{active_context}"}
        ]
    )
    return response.choices[0].message.content

def punch_up(text):
    system = """
    Script Doctor.
    1. REMOVE text in brackets [].
    2. REMOVE non-dialogue lines.
    3. DELETE phrases like "That's it for...", "Moving on...", "In summary...".
    4. ADD "--" for interruptions.
    """
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system}, {"role": "user", "content": text}])
    return response.choices[0].message.content

# --- PRODUCTION ---
def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text).replace('**', '')
    for bad in ["Welcome to Top Story", "Welcome back", "Hello listeners"]:
        if bad.lower() in text.lower(): return ""
    return text.strip()

def produce_episode():
    # 1. FETCH REAL DATA
    brains = fetch_news()
    
    # 2. COMBINE TEXT FOR METADATA
    full_data_text = brains["ALEX"] + brains["JAMIE"] + brains["RUFUS"]
    print(f"--- HOLLYWOOD BUILD (FACTUAL MODE: {len(full_data_text)} chars) ---")
    
    settings = get_show_settings()
    loc = get_rufus_location()
    sponsor = load_sponsor()
    
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
        
        # Pass the 'brains' dictionary instead of raw news
        draft = draft_segment(seg, brains, settings, loc, sponsor)
        
        if seg["name"] not in ["INTRO_FORMAT", "MID_ROLL"]: 
            script = punch_up(draft)
        else:
            script = draft
            
        full_script += script + "\n"
        
        for line in script.split('\n'):
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker, text = match.group(1).upper(), clean_text(match.group(2))
                if not text: continue
                
                voice = VOICES.get(speaker, "onyx")
                f = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(f)
                
                seg_audio = AudioSegment.from_mp3(f)
                audio_segs.append(seg_audio)
        
        if seg["name"] == "HOOK":
            print(" >> ⚡ INJECTING THUNDERBOLT INTRO ⚡")
            audio_segs.append(AudioSegment.silent(300))
            audio_segs.append(m_intro)
            audio_segs.append(AudioSegment.silent(300))

    audio_segs.append(m_outro)
    final = sum(audio_segs)
    fname = f"podcast_{datetime.date.today()}.mp3"
    final.export(AUDIO_DIR / fname, format="mp3")
    
    meta = generate_meta(full_script)
    with open("episode_metadata.json", "w") as f: json.dump(meta, f)
    save_caption(meta)
    print(f"DONE: {fname}")

def generate_meta(text):
    prompt = 'Generate JSON: {"title": "Clickbait Title", "hook": "Viral Hook", "hashtags": ["#tag"]}'
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": f"{prompt}\n{text[:2000]}"}], response_format={"type": "json_object"})
    return json.loads(res.choices[0].message.content)

def save_caption(meta):
    with open("viral_caption.txt", "w") as f:
        f.write(f"🚀 {meta['title']}\n\n{meta['hook']}\n\n👇 Listen on Spotify:\n{SPOTIFY_URL}\n\n{' '.join(meta['hashtags'])}")

if __name__ == "__main__":
    produce_episode()
