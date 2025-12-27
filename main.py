import os
import json
import random
import re
import datetime
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

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Deep dives into AI, Technology, and the Future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology"
}

# --- FORMAT LOGIC ---
def get_show_settings():
    return {
        "type": "Daily News Unfiltered", 
        "tone": "High Energy, Aggressive, Tool-Obsessed. INTERRUPT OFTEN.", 
        "segments": [
            {"name": "HOOK", "words": 40, "cast": "ALEX_JAMIE", "transition": False}, 
            {"name": "INTRO_BRANDING", "words": 20, "cast": "ALEX_SOLO", "transition": False},
            {"name": "TOP_STORY_MECHANISMS", "words": 1200, "cast": "ALEX_JAMIE", "transition": False},
            {"name": "RUFUS_MARKETS_LAW", "words": 800, "cast": "RUFUS_FOCUS", "transition": True},
            # MID ROLL IS NOW DEDICATED SPONSOR TIME
            {"name": "MID_ROLL", "words": 250, "cast": "JAMIE_SPONSOR", "transition": True},
            {"name": "SECONDARY_STORY_IMPACT", "words": 1000, "cast": "ALEX_JAMIE", "transition": True},
            {"name": "SPEED_ROUND_WRAP", "words": 600, "cast": "ALL_THREE", "transition": True}, 
            {"name": "OUTRO_VIRAL", "words": 200, "cast": "ALEX_SOLO", "transition": False}
        ]
    }

def get_rufus_location():
    locs = ["London Stock Exchange", "Canary Wharf", "Zurich", "Hong Kong Port"]
    return random.choice(locs)

def load_sponsor():
    # Hard-coded fail-safe if file missing
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

# --- WRITER (CONTINUOUS FLOW MODE) ---
def draft_segment(seg, context, settings, loc, sponsor):
    seg_name = seg["name"]
    
    # 1. THE HOOK (Tools & Data)
    if seg_name == "HOOK":
        system_prompt = f"""
        You are the Producer. Write the **COLD OPEN HOOK**.
        **CRITICAL:**
        1. MENTION A SPECIFIC TOOL or STAT immediately.
        2. JAMIE INTERRUPTS ALEX.
        3. MAX 40 WORDS.
        4. NO GREETINGS. NO "Welcome".
        **CONTEXT:** {context[:500]}
        """
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}])
        return response.choices[0].message.content

    # 2. BRANDING (The ONLY place Alex introduces the show)
    if seg_name == "INTRO_BRANDING":
        return "ALEX: Welcome to The AI Edge. I'm Alex."

    # 3. SPONSOR READ (Force Jamie to read it)
    if seg["cast"] == "JAMIE_SPONSOR":
        return f"JAMIE: Quick break to thank our partner. {sponsor}"

    # 4. CONTINUOUS DYNAMICS (The "No Intro" Rule)
    # This rule is injected into ALL other segments
    anti_intro_rule = "CRITICAL: You are MID-CONVERSATION. DO NOT say 'I'm Alex' or 'I'm Jamie'. DO NOT greet the audience. JUST ARGUE."

    if seg["cast"] == "ALEX_JAMIE":
        cast_instr = f"""
        **CAST:** ALEX and JAMIE.
        **PACING:** FAST. Overlapping.
        **CONTENT:** {anti_intro_rule}
        """
    elif seg["cast"] == "RUFUS_FOCUS":
        cast_instr = f"""
        **CAST:** ALEX throws to RUFUS at {loc}.
        **RUFUS:** {anti_intro_rule} Focus on MONEY/LAW.
        """
    elif seg["cast"] == "ALL_THREE":
        cast_instr = f"**CAST:** ALL. {anti_intro_rule} Rapid fire."
    elif seg["cast"] == "ALEX_SOLO":
        cast_instr = "**CAST:** ALEX Only. Sign-off."

    system_prompt = f"""
    Write **{seg_name}**. Target {seg['words']} words.
    **TONE:** {settings['tone']}
    **CRITICAL RULES:**
    1. **DIALOGUE ONLY.** NO stage directions.
    2. **NO RE-INTRODUCTIONS.** 3. **FORMAT:** ALEX: [Text] / JAMIE: [Text] / RUFUS: [Text]
    {cast_instr}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: {context[:4000]}"}
        ]
    )
    return response.choices[0].message.content

def punch_up(text):
    system = """
    Script Doctor.
    1. REMOVE any text in brackets [].
    2. REMOVE non-dialogue lines.
    3. MAKE IT FASTER. Break long sentences.
    4. ADD "--" to indicate interruptions.
    5. DELETE ANY LINE where Alex says "I'm Alex" (Unless it's the very start).
    """
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system}, {"role": "user", "content": text}])
    return response.choices[0].message.content

# --- PRODUCTION ---
def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text).replace('**', '')
    for bad in ["Welcome to Top Story", "Welcome back", "Hello listeners"]:
        if bad.lower() in text.lower(): return ""
    return text.strip()

def produce_episode(news):
    print("--- HOLLYWOOD BUILD (CONTINUOUS FLOW) ---")
    settings = get_show_settings()
    loc = get_rufus_location()
    sponsor = load_sponsor()
    
    audio_segs = []
    full_text = ""
    
    # Assets
    p_intro = get_asset("intro.mp3")
    p_outro = get_asset("outro.mp3")
    p_trans = get_asset("transition.mp3")
    
    m_intro = AudioSegment.from_mp3(p_intro) if p_intro else AudioSegment.silent(1000)
    m_outro = AudioSegment.from_mp3(p_outro) if p_outro else AudioSegment.silent(1000)
    s_trans = (AudioSegment.from_mp3(p_trans) - 3) if p_trans else AudioSegment.silent(500)

    for seg in settings['segments']:
        print(f" >> Seg: {seg['name']}")
        if seg.get("transition"): audio_segs += [s_trans, AudioSegment.silent(200)] # Short transition
        
        draft = draft_segment(seg, news, settings, loc, sponsor)
        
        # Don't punch up the Sponsor or Branding lines, they need to be clear
        if seg["name"] not in ["INTRO_BRANDING", "MID_ROLL"]: 
            script = punch_up(draft)
        else:
            script = draft
            
        full_text += script + "\n"
        
        for line in script.split('\n'):
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker, text = match.group(1).upper(), clean_text(match.group(2))
                if not text: continue
                
                voice = VOICES.get(speaker, "onyx")
                f = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(f)
                
                # --- THE OVERLAP HACK ---
                # We strip silence and don't add any back.
                # Ideally we would crossfade, but 0 padding creates a 'breathless' pace.
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
    
    meta = generate_meta(full_text)
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
    if Path("marketing.txt").exists(): produce_episode(Path("marketing.txt").read_text())
    else: produce_episode("AI News trends.")
