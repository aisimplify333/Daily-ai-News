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

# Your Spotify/iTunes RSS Settings
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Deep dives into AI, Technology, and the Future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology"
}

# Hosting logic for GitHub Pages
RAW_AUDIO_BASE = "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/episode_audio"
VOICES = {"ALEX": "onyx", "JAMIE": "shimmer", "RUFUS": "fable"}SPOTIFY_URL = "https://open.spotify.com/show/YOUR_SHOW_ID_HERE" 

# --- THE REVENUE ENGINE (AFFILIATE DATABASE) ---
# Replace these placeholder links with your real affiliate IDs once you sign up
AFFILIATE_DATABASE = {
    "CURSOR": "https://cursor.com/?ref=your_id",
    "NOTION": "https://notion.so/?aff=your_id",
    "ELEVENLABS": "https://elevenlabs.io/?get=your_id",
    "DESCRIPT": "https://www.descript.com/?lmref=your_id"
}

# --- VOICE CAST ---
VOICES = {"ALEX": "onyx", "JAMIE": "shimmer", "RUFUS": "fable"}

# --- THE "SPONSOR MAGNET" SEARCH ENGINE ---
SEARCH_MISSIONS = {
    "TOOLS": [
        "top new AI apps for productivity released this week",
        "best new AI coding tools for developers December 2025",
        "new AI video generation tools launched today",
        "Cursor vs Windsurf vs GitHub Copilot latest updates",
        "new SaaS AI startups launching this week"
    ],
    "TECH": [
        "DeepSeek V3 vs GPT-5 vs Gemini 2.0 benchmarks",
        "major AI research breakthroughs today",
        "open source AI model leaderboard updates"
    ],
    "SKEPTIC": [
        "AI hallucinations failures and risks news today",
        "lawsuits against AI companies copyright artists 2025",
        "AI bias discrimination reports this week"
    ],
    "GLOBAL": [
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
        {"name": "HOOK", "words": 40, "cast": "ALEX_JAMIE", "trans": False},
        {"name": "INTRO", "words": 100, "cast": "ALEX_SOLO", "trans": False},
        {"name": "BLOCK_1_TOOLS_AND_MODELS", "words": 1500, "cast": "ALEX_JAMIE", "trans": True},
        {"name": "SPONSOR_1", "words": 250, "cast": "JAMIE_SPONSOR", "trans": True},
        {"name": "BLOCK_2_ETHICS_RISK", "words": 1500, "cast": "JAMIE_ALEX", "trans": True},
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
    print(f"    ...Writing {seg['name']}")
    
    # 1. Monetization Instruction: Turns Alex into a natural affiliate recommender
    monetization_prompt = f"""
    **REVENUE RULE:** If the news mentions any of these tools: {list(AFFILIATE_DATABASE.keys())},
    ALEX must naturally say: "I've actually been using [Tool Name] for my workflow, it's a game changer. 
    Check the link in our show notes to try it out."
    """

    lens_instruction = ""
    if "RUFUS" in seg["name"] or "VC_POLITICS" in seg["name"]:
        lens_instruction = "FOCUS ONLY on lines tagged [GLOBAL]. Discuss Venture Capital and Regulation."
    elif "ETHICS" in seg["name"] or "SKEPTIC" in seg["name"]:
        lens_instruction = "FOCUS ON lines tagged [SKEPTIC]. Discuss Lawsuits and Safety."
    elif "TOOLS" in seg["name"] or "TECH" in seg["name"]:
        lens_instruction = "FOCUS ON lines tagged [TOOLS] and [TECH]. Name specific Apps."

    sys_msg = f"""
    You are the Writer for 'The AI Edge'.
    {monetization_prompt}
    **CONTEXT:** \n{context[:15000]} 
    **SEGMENT:** {seg['name']}
    **LENGTH:** Target {seg['words']} words. WRITE LONG.
    **THE CHEMISTRY:** Alex (Optimist), Jamie (Skeptic), Rufus (Money-focused).
    **THE LENS:** {lens_instruction}
    **RULES:** Dialogue ONLY. Quote specific data. NO NARRATION.
    """
    
    user_msg = f"Write {seg['name']}."
    if seg["name"] == "HOOK":
        user_msg += " CRITICAL: 40-WORD COLD OPEN. Start with a SHOCKING STAT. Jamie INTERRUPTS immediately."
    elif "SPONSOR" in seg["name"]:
        user_msg = f"Jamie reads ad: {sponsor}. Make it sound like a recommendation."
    elif "OUTRO" in seg["name"]:
        user_msg += " Alex signs off. 'Share this with one friend.' Mention links are in the description."
    
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
    return res.choices[0].message.content

def produce_episode():
    print("--- STARTING PRODUCTION ---")
    context = fetch_news()
    show_type, structure = get_show_structure()
    audio_segs = []
    full_script = ""

    # Assets
    m_intro = AudioSegment.from_mp3(get_asset("intro.mp3")) if get_asset("intro.mp3") else AudioSegment.silent(1000)
    m_outro = AudioSegment.from_mp3(get_asset("outro.mp3")) if get_asset("outro.mp3") else AudioSegment.silent(1000)
    s_trans = AudioSegment.from_mp3(get_asset("transition.mp3")) if get_asset("transition.mp3") else AudioSegment.silent(500)

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
    
    # --- SMART CAPTION ENGINE ---
    # Scans the script and only lists links for tools actually discussed
    links_to_include = ""
    for tool, link in AFFILIATE_DATABASE.items():
        if tool.lower() in full_script.lower():
            links_to_include += f"🔗 Try {tool.capitalize()}: {link}\n"

    caption = f"""
🚀 NEW EPISODE: {show_type}

{full_script[:200]}...

👇 LISTEN & RESOURCES:
{SPOTIFY_URL}

{links_to_include}
#AI #TechNews #Podcast
    """.strip()

    with open("viral_caption.txt", "w") as f: 
        f.write(caption)
        
    print(f"DONE: {fname}")

if __name__ == "__main__":
    produce_episode()
