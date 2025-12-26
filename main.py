import os
import json
import random
import re
import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from email.utils import formatdate
from openai import OpenAI
from pydub import AudioSegment

# --- CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)
ASSETS_DIR = BASE_DIR / "assets"

# *** YOUR SPOTIFY LINK (The Bridge) ***
SPOTIFY_URL = "https://open.spotify.com/show/YOUR_SHOW_ID_HERE" 

VOICES = {"ALEX": "onyx", "JAMIE": "nova", "RUFUS": "fable"}
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily News Unfiltered with Alex, Jamie, and Rufus.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.jpg",
    "category": "Technology"
}

# --- FORMAT LOGIC ---
def get_show_settings():
    today = datetime.date.today()
    if today.month == 12 and today.day >= 26:
        return {"type": "Year End Special", "tone": "Epic, existential.", "segments": [
            {"name": "HOOK", "words": 50, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "Q1_DEEP_ANALYSIS", "words": 1500, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "RUFUS_MACRO_ECONOMICS", "words": 1000, "cast": "RUFUS_FOCUS", "transition": True},
            {"name": "MID_ROLL", "words": 250, "cast": "JAMIE_SOLO", "transition": True},
            {"name": "Q3_SOCIETAL_IMPACT", "words": 1500, "cast": "ALEX_JAMIE", "transition": True},
            {"name": "FUTURE_PREDICTIONS", "words": 1500, "cast": "ALL_THREE", "transition": False},
            {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
        ]}
    elif today.weekday() >= 5:
        return {"type": "Weekend Deep Dive", "tone": "Debate-heavy.", "segments": [
            {"name": "HOOK", "words": 50, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "MAIN_TOPIC_DEEP_DIVE", "words": 1800, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "RUFUS_LONDON_REPORT", "words": 1000, "cast": "RUFUS_FOCUS", "transition": True},
            {"name": "MID_ROLL", "words": 250, "cast": "JAMIE_SOLO", "transition": True},
            {"name": "ETHICAL_DEBATE", "words": 1500, "cast": "ALL_THREE", "transition": True},
            {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
        ]}
    else:
        return {"type": "Daily News", "tone": "Hard-hitting.", "segments": [
            {"name": "HOOK", "words": 50, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "TOP_STORY_MECHANISMS", "words": 1200, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "RUFUS_MARKETS_LAW", "words": 800, "cast": "RUFUS_FOCUS", "transition": True},
            {"name": "MID_ROLL", "words": 250, "cast": "JAMIE_SOLO", "transition": True},
            {"name": "SECONDARY_STORY_IMPACT", "words": 1000, "cast": "ALEX_JAMIE", "transition": True},
            {"name": "SPEED_ROUND_WRAP", "words": 600, "cast": "ALL_THREE", "transition": True},
            {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
        ]}

def get_rufus_location():
    locs = ["standing in the rain outside the LSE", "in a noisy coffee shop in Canary Wharf", "walking through a windy park in Zurich", "overlooking the port in Hong Kong"]
    return random.choice(locs)

def load_sponsor():
    paths = [BASE_DIR / "sponsors.json", ASSETS_DIR / "sponsors.json"]
    for p in paths:
        try:
            with open(p) as f: 
                data = json.load(f)
                return random.choice(data["sponsors"])["read_copy"]
        except: pass
    return "This episode is brought to you by AI Simplify Media."

def get_asset(name):
    if (ASSETS_DIR / name).exists(): return ASSETS_DIR / name
    if (BASE_DIR / name).exists(): return BASE_DIR / name
    return None

# --- WRITER ---
def draft_segment(seg, context, settings, loc, sponsor):
    if seg["name"] == "HOOK":
        prompt = f"Write **HOT CLIP HOOK**. MAX 40 WORDS. Must include DATA POINT (e.g. '40% drop'). Start MID-ARGUMENT. NO INTRO. Context: {context[:500]}"
    else:
        prompt = f"Write **{seg['name']}**. Target {seg['words']} words. Cast: {seg['cast']}. Style: Huberman/Diary of CEO. Analyze MECHANISMS. Tone: {settings['tone']}. Rufus Loc: {loc}. Sponsor: {sponsor}. Context: {context[:3000]}"
    
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": prompt}])
    return response.choices[0].message.content

def punch_up(text):
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": "Script Doctor. 1. Rufus: British. 2. Jamie: Interrupts. 3. Remove 'Welcome back'."}, {"role": "user", "content": text}])
    return response.choices[0].message.content

# --- PRODUCTION ---
def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text).replace('**', '')
    for bad in ["Welcome to the AI Edge", "Welcome back", "Hello listeners"]:
        if bad.lower() in text.lower() and len(text) < 100: return ""
    return text.strip()

def produce_episode(news):
    print("--- HOLLYWOOD BUILD START ---")
    settings = get_show_settings()
    loc = get_rufus_location()
    sponsor = load_sponsor()
    
    audio_segs = []
    full_text = ""
    
    # Assets
    p_intro = get_asset("intro.mp3")
    p_outro = get_asset("outro.mp3")
    p_trans = get_asset("transition.mp3")
    p_voice = get_asset("fixed_intro.mp3") # Pre-generated voice saying "Welcome to AI Edge"
    
    m_intro = AudioSegment.from_mp3(p_intro) if p_intro else AudioSegment.silent(1000)
    m_outro = AudioSegment.from_mp3(p_outro) if p_outro else AudioSegment.silent(1000)
    s_trans = (AudioSegment.from_mp3(p_trans) - 3) if p_trans else AudioSegment.silent(500)

    for seg in settings['segments']:
        print(f" >> Seg: {seg['name']}")
        if seg.get("transition"): audio_segs += [s_trans, AudioSegment.silent(500)]
        
        draft = draft_segment(seg, news, settings, loc, sponsor)
        script = punch_up(draft)
        full_text += script + "\n"
        
        for line in script.split('\n'):
            if ':' in line:
                speaker, text = line.split(':', 1)
                text = clean_text(text)
                if not text: continue
                # Generate Audio
                voice = VOICES.get(speaker.strip().upper(), "onyx")
                f = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(f)
                audio_segs.append(AudioSegment.from_mp3(f))
                audio_segs.append(AudioSegment.silent(250))
        
        if seg["name"] == "HOOK":
            print(" >> ⚡ INJECTING THUNDERBOLT INTRO ⚡")
            audio_segs.append(AudioSegment.silent(500))
            audio_segs.append(m_intro)
            if p_voice: audio_segs.append(AudioSegment.from_mp3(p_voice))
            audio_segs.append(AudioSegment.silent(1000))

    audio_segs.append(m_outro)
    final = sum(audio_segs)
    fname = f"podcast_{datetime.date.today()}.mp3"
    final.export(AUDIO_DIR / fname, format="mp3")
    
    # Metadata & Caption
    meta = generate_meta(full_text)
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
    if Path("marketing.txt").exists(): produce_episode(Path("marketing.txt").read_text())
    else: produce_episode("AI News trends.")
