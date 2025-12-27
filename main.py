import os
import json
import random
import re
import datetime
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment
from duckduckgo_search import DDGS

# --- CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)
ASSETS_DIR = BASE_DIR / "assets"

SPOTIFY_URL = "https://open.spotify.com/show/YOUR_SHOW_ID_HERE" 

# --- VOICE CAST ---
# ALEX (Host): Tech Optimist.
# JAMIE (Co-Host): Female (Shimmer). Skeptic.
# RUFUS (The Realist): Male. Money & Power.
VOICES = {"ALEX": "onyx", "JAMIE": "shimmer", "RUFUS": "fable"}

# --- THE "SPONSOR MAGNET" SEARCH ENGINE ---
SEARCH_MISSIONS = {
    "TOOLS": [ # TARGET: Specific Apps & Software (The Money Maker)
        "top new AI apps for productivity released this week",
        "best new AI coding tools for developers December 2025",
        "new AI video generation tools launched today",
        "Cursor vs Windsurf vs GitHub Copilot latest updates",
        "new SaaS AI startups launching this week"
    ],
    "TECH": [ # TARGET: The Big Models (The Hype)
        "DeepSeek V3 vs GPT-5 vs Gemini 2.0 benchmarks",
        "major AI research breakthroughs today",
        "open source AI model leaderboard updates"
    ],
    "SKEPTIC": [ # TARGET: The Drama
        "AI hallucinations failures and risks news today",
        "lawsuits against AI companies copyright artists 2025",
        "AI bias discrimination reports this week"
    ],
    "GLOBAL": [ # TARGET: The Power & Money
        "venture capital AI funding trends Series A news",
        "Nvidia stock analysis AI chip market trends",
        "new AI regulation laws EU US China"
    ]
}

# --- FAILSAFE DATA ---
BACKUP_DATA = """
[TOOLS] NEW APP: 'Cursor 2.0' launches with fully autonomous coding agents.
[TECH] DEEPSEEK V3: Chinese firm releases model beating GPT-4 at 1/10th cost.
[GLOBAL] VC TRENDS: Andreessen Horowitz invests $500M in AI Agents.
[SKEPTIC] LAWSUIT: NYT sues OpenAI over copyright infringement in training data.
[TOOLS] VIDEO AI: Sora finally releases public beta, creators are stunned.
"""

def fetch_news():
    print(" >> 🔍 SCANNING FOR TOOLS & NEWS...")
    data_text = ""
    
    try:
        with DDGS() as ddgs:
            for category, queries in SEARCH_MISSIONS.items():
                print(f"    Searching {category}...")
                for query in queries:
                    results = ddgs.text(query, region='wt-wt', safesearch='off', timelimit='d', max_results=2)
                    if results:
                        for r in results:
                            clean_body = r['body'].replace("\n", " ")
                            data_text += f"[{category}] {r['title']}: {clean_body}\n"
    except Exception as e:
        print(f" !! SEARCH FAILURE: {e}")
            
    if len(data_text) < 1000:
        return BACKUP_DATA
    
    print(f" >> INGESTED {len(data_text)} CHARACTERS.")
    return data_text

def get_show_structure():
    return "DAILY_TOOL_SHOW", [
        # THE COLD OPEN: 40 WORDS. 
        {"name": "HOOK", "words": 40, "cast": "ALEX_JAMIE", "trans": False},
        
        {"name": "INTRO", "words": 100, "cast": "ALEX_SOLO", "trans": False},
        
        # BLOCK 1: NEW TOOLS & APPS (Alex Hypes, Jamie Tests)
        # This is where we talk about the "Tools" that attract sponsors.
        {"name": "BLOCK_1_TOOLS_AND_MODELS", "words": 1500, "cast": "ALEX_JAMIE", "trans": True},
        
        # SPONSOR 1 (Fits naturally after Tool talk)
        {"name": "SPONSOR_1", "words": 250, "cast": "JAMIE_SPONSOR", "trans": True},
        
        # BLOCK 2: ETHICS & SKEPTICISM (Jamie Leads)
        {"name": "BLOCK_2_ETHICS_RISK", "words": 1500, "cast": "JAMIE_ALEX", "trans": True},
        
        # BLOCK 3: MONEY, VC & POLITICS (Rufus Leads)
        {"name": "BLOCK_3_VC_POLITICS", "words": 1500, "cast": "RUFUS_SOLO", "trans": True},
        
        {"name": "SPONSOR_2", "words": 250, "cast": "JAMIE_SPONSOR", "trans": True},
        
        {"name": "OUTRO", "words": 400, "cast": "ALEX_CTA", "trans": False}
    ]

def get_asset(name):
    if (ASSETS_DIR / name).exists(): return ASSETS_DIR / name
    if (BASE_DIR / name).exists(): return BASE_DIR / name
    return None

def load_sponsor():
    try:
        with open(BASE_DIR / "sponsors.json") as f: 
            return random.choice(json.load(f)["sponsors"])["read_copy"]
    except: return "This show is sponsored by ElevenLabs. Go to elevenlabs dot io."

# --- INTELLIGENT WRITER ---
def generate_script(seg, context, show_type, sponsor):
    print(f"   ...Writing {seg['name']}")
    
    # SYSTEM PROMPT: THE LENS & CHEMISTRY
    lens_instruction = ""
    if "RUFUS" in seg["name"] or "VC_POLITICS" in seg["name"]:
        lens_instruction = "FOCUS ONLY on lines tagged [GLOBAL]. Discuss Venture Capital, Stock Prices, and Regulations. Ignore technical specs."
    elif "ETHICS" in seg["name"] or "SKEPTIC" in seg["name"]:
        lens_instruction = "FOCUS ON lines tagged [SKEPTIC]. Discuss Lawsuits, Hallucinations, Job Loss, and Safety."
    elif "TOOLS" in seg["name"] or "TECH" in seg["name"]:
        lens_instruction = "FOCUS ON lines tagged [TOOLS] and [TECH]. Name specific Apps. Discuss features. Alex loves them, Jamie doubts them."

    sys_msg = f"""
    You are the Writer for 'The AI Edge'.
    **CONTEXT:** \n{context[:15000]} 
    
    **SEGMENT:** {seg['name']}
    **LENGTH:** Target {seg['words']} words. WRITE LONG.
    
    **THE CHEMISTRY:**
    - **ALEX (Host):** Male. Tech Optimist. Excited about [TOOLS].
    - **JAMIE (Co-Host):** Female (Shimmer). Skeptic. "Does this actually work or is it hype?"
    - **RUFUS (The Realist):** Male. Cynical. Follows the [GLOBAL] money.
    
    **THE LENS:**
    {lens_instruction}
    
    **RULES:**
    1. **NO NARRATION.** Dialogue ONLY.
    2. **USE DATA.** Quote specific numbers/prices.
    3. **NAME DROP.** Mention specific App names from the search results.
    4. **FORMAT:** ALEX: [Text] / JAMIE: [Text]
    """
    
    user_msg = f"Write {seg['name']}."
    
    if seg["name"] == "HOOK":
        user_msg += """
        CRITICAL: Write a 40-WORD COLD OPEN.
        1. Start with a SHOCKING STAT or NEW TOOL RELEASE.
        2. Jamie (Female) INTERRUPTS Alex immediately.
        3. NO 'Hello'. Start mid-crisis.
        """
    elif "SPONSOR" in seg["name"]:
        user_msg = f"Jamie reads ad: {sponsor}. Make it sound like a recommendation, not just an ad."
    elif "RUFUS" in seg["name"]:
        user_msg += " Rufus monologue on the collision of VC Money and Global Politics."
    elif "OUTRO" in seg["name"]:
        user_msg += " Alex signs off. 'Share this with one friend.'"
    
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
    return res.choices[0].message.content

def produce_episode():
    print("--- STARTING PRODUCTION ---")
    context = fetch_news()
    show_type, structure = get_show_structure()
    
    audio_segs = []
    
    m_intro = AudioSegment.from_mp3(get_asset("intro.mp3")) if get_asset("intro.mp3") else AudioSegment.silent(1000)
    m_outro = AudioSegment.from_mp3(get_asset("outro.mp3")) if get_asset("outro.mp3") else AudioSegment.silent(1000)
    s_trans = AudioSegment.from_mp3(get_asset("transition.mp3")) if get_asset("transition.mp3") else AudioSegment.silent(500)

    full_script = ""

    for seg in structure:
        script = generate_script(seg, context, show_type, load_sponsor())
        full_script += script + "\n"
        
        lines = script.split('\n')
        for line in lines:
            if ":" not in line: continue
            
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker, text = match.group(1).upper(), match.group(2).strip()
                if not text: continue
                
                voice = VOICES.get(speaker, "onyx")
                temp = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(temp)
                audio_segs.append(AudioSegment.from_mp3(temp))
        
        if seg["name"] == "HOOK":
            audio_segs.append(m_intro)
        elif seg.get("trans"):
            audio_segs.append(s_trans)

    audio_segs.append(m_outro)
    final = sum(audio_segs)
    
    fname = f"podcast_{datetime.date.today()}.mp3"
    final.export(AUDIO_DIR / fname, format="mp3")
    
    with open("viral_caption.txt", "w") as f: f.write(f"🚀 {show_type} EPISODE\n\n{full_script[:200]}")
    print(f"DONE: {fname}")

if __name__ == "__main__":
    produce_episode()
