import os
import json
import random
import re
import datetime
from pathlib import Path
from openai import OpenAI
from pydub import AudioSegment
from duckduckgo_search import DDGS

# --- 1. CONFIGURATION & DIRECTORIES ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
AUDIO_DIR.mkdir(exist_ok=True)
ASSETS_DIR = BASE_DIR / "assets"

# --- 2. IDENTITY & PUBLISHING (SPOTIFY/APPLE) ---
RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Unfiltered Daily News in AI. Data, Politics, and the Future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com", 
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology"
}
# The raw URL required for Spotify to stream audio files
RAW_AUDIO_BASE = "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/episode_audio"

# --- 3. REVENUE ENGINE (MONETIZATION) ---
AFFILIATE_DATABASE = {
    "CURSOR": "https://cursor.com/?ref=your_id",
    "NOTION": "https://notion.so/?aff=your_id",
    "ELEVENLABS": "https://elevenlabs.io/?get=your_id"
}

# --- 4. THE CAST (CHEMISTRY) ---
VOICES = {"ALEX": "onyx", "JAMIE": "shimmer", "RUFUS": "fable"}

# --- 5. DEEP SEARCH ENGINE (THE "15 FEEDS") ---
SEARCH_MISSIONS = {
    "TOOLS": [
        "top new AI productivity apps launched today", 
        "best new AI coding agents December 2025", 
        "SaaS AI startups funding news"
    ],
    "TECH": [
        "DeepSeek V3 vs GPT-5 technical benchmarks", 
        "AI research paper breakthroughs arxiv", 
        "LLM leaderboard updates"
    ],
    "SKEPTIC": [
        "AI hallucinations failures examples", 
        "copyright lawsuits OpenAI Perplexity", 
        "AI bias ethics reports 2025"
    ],
    "GLOBAL": [
        "venture capital AI investment trends", 
        "US EU China AI regulation laws", 
        "Nvidia AMD stock market analysis"
    ]
}

# Failsafe Data (Prevents "Empty Show" crashes)
BACKUP_DATA = """[TOOLS] Cursor 2.0 launches. [TECH] DeepSeek V3 beats GPT-4. [GLOBAL] A16Z invests $500M in Agents. [SKEPTIC] NYT sues Perplexity."""

def fetch_news():
    print(" >> 🔍 EXECUTING DEEP SEARCH...")
    data_text = ""
    try:
        with DDGS() as ddgs:
            for category, queries in SEARCH_MISSIONS.items():
                for query in queries:
                    results = ddgs.text(query, region='wt-wt', safesearch='off', timelimit='d', max_results=1)
                    if results:
                        for r in results:
                            data_text += f"[{category}] {r['title']}: {r['body']}\n"
    except Exception as e:
        print(f" !! SEARCH WARNING: {e}")
    
    # Use backup if search fails or returns too little data
    return data_text if len(data_text) > 500 else BACKUP_DATA

# --- 6. SEO METADATA AGENT (VIRAL TITLES) ---
def generate_metadata(context):
    """Creates Top-5 Ranking Titles, Summaries, and Hashtags."""
    sys_msg = "You are a Podcast SEO Expert. Create viral metadata based on this news context."
    user_msg = f"""
    CONTEXT: {context[:5000]}
    
    TASK:
    1. TITLE: Catchy, click-baity, under 60 chars. (e.g., "DeepSeek vs GPT-4: The End of OpenAI?")
    2. SUMMARY: 2-3 punchy sentences summarizing the key stories.
    3. TAGS: 5 relevant hashtags (e.g., #AI #Nvidia #Tech).
    
    FORMAT JSON:
    {{"title": "...", "summary": "...", "tags": "..."}}
    """
    try:
        res = client.chat.completions.create(model="gpt-4o", response_format={"type": "json_object"}, messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
        return json.loads(res.choices[0].message.content)
    except:
        return {"title": f"AI Edge: {datetime.date.today()}", "summary": "Daily AI News.", "tags": "#AI"}

# --- 7. DYNAMIC SHOW STRUCTURE (THE "RICHNESS" STANDARD) ---
def get_show_structure():
    """Adjusted for >20min Daily, >30min Weekend, >45min Holiday."""
    now = datetime.datetime.now()
    day = now.strftime("%A")
    today_date = now.strftime("%m-%d")

    # HOLIDAY SPECIAL (Target: 45+ Mins / 8,000 Words)
    if today_date in ["12-25", "01-01", "12-31"]:
        return "HOLIDAY_SPECIAL", [
            {"name": "HOOK", "words": 50},
            {"name": "INTRO", "words": 200},
            {"name": "BLOCK_YEAR_REVIEW", "words": 2500},
            {"name": "SPONSOR_1", "words": 300},
            {"name": "BLOCK_PREDICTIONS", "words": 2500}, # Alex & Jamie Debate
            {"name": "BLOCK_MARKET_OUTLOOK", "words": 2000}, # Rufus Deep Dive
            {"name": "OUTRO", "words": 500}
        ]

    # SATURDAY: WEEKEND DEBATE (Target: 30+ Mins / 6,000 Words)
    if day == "Saturday":
        return "WEEKEND_DEBATE", [
            {"name": "HOOK", "words": 50},
            {"name": "INTRO", "words": 150},
            {"name": "BLOCK_PHILOSOPHY_1", "words": 2500}, # The Thesis
            {"name": "SPONSOR_1", "words": 300},
            {"name": "BLOCK_PHILOSOPHY_2", "words": 2500}, # The Antithesis (Jamie)
            {"name": "OUTRO", "words": 500}
        ]

    # SUNDAY: WEEKLY WRAP (Target: 30+ Mins / 6,000 Words)
    if day == "Sunday":
        return "WEEKLY_WRAP", [
            {"name": "HOOK", "words": 50},
            {"name": "INTRO", "words": 150},
            {"name": "BLOCK_BEST_OF_WEEK", "words": 2500},
            {"name": "SPONSOR_1", "words": 300},
            {"name": "BLOCK_RUFUS_MONEY", "words": 2500}, # Financial Deep Dive
            {"name": "OUTRO", "words": 500}
        ]
    
    # MON-FRI: DAILY NEWS (Target: 25+ Mins / 5,000 Words)
    return "DAILY_TOOL_SHOW", [
        {"name": "HOOK", "words": 50},
        {"name": "INTRO", "words": 150}, # Unfiltered Tagline
        {"name": "BLOCK_1_TOOLS", "words": 1500}, # Monetization here
        {"name": "SPONSOR_1", "words": 250},
        {"name": "BLOCK_2_ETHICS", "words": 1500}, # Jamie's Safety Segment
        {"name": "BLOCK_3_MONEY", "words": 1500}, # Rufus: Politics/Law/VC
        {"name": "OUTRO", "words": 500}
    ]

# --- 8. THE "RICH CONTENT" WRITER ---
def generate_script(seg, context, show_type):
    # LENS: Enforcing the "Unfiltered/Huberman" Style
    lens = "Focus on HARD DATA and NEW TOOLS. Be educational yet exciting."
    if "MONEY" in seg["name"] or "RUFUS" in seg["name"]:
        lens = "RUFUS: Focus strictly on ROI, Stock Prices, and Regulation. Cynical tone."
    elif "ETHICS" in seg["name"]:
        lens = "JAMIE: Focus on Safety, Lawsuits, and Job Loss. Interrupt Alex's optimism."
    elif "DEBATE" in seg["name"] or "PHILOSOPHY" in seg["name"]:
        lens = "DEEP DIVE: Cite studies, history, and philosophy. Huberman-style density."

    # REVENUE LOGIC: Only affects Tools segment
    rev_rule = ""
    if "TOOLS" in seg["name"]:
        rev_rule = f"MONETIZATION: If mentioning {list(AFFILIATE_DATABASE.keys())}, Alex naturally shares his personal workflow use case."

    sys_msg = f"""
    Role: Lead Writer for 'The AI Edge'. Style: Unfiltered, Intellectual, Data-Driven.
    **CONTEXT:** {context[:15000]}
    **SEGMENT:** {seg['name']}
    **CHEMISTRY:** Alex (Optimist Host), Jamie (Realist/Skeptic), Rufus (VC/Cynic).
    **LENS:** {lens}
    {rev_rule}
    **RULES:**
    1. USE SPECIFIC DATA (e.g., "34% increase", "$500M Series A").
    2. REAL CONFLICT: Jamie should challenge Alex. Rufus should mock "ethics."
    3. NO NARRATION. DIALOGUE ONLY. WRITE LONG.
    """
    
    user_msg = f"Write {seg['name']} ({seg['words']} words)."
    
    # HARD-CODED "UNFILTERED" ELEMENTS
    if seg["name"] == "HOOK":
        user_msg = "CRITICAL: 50-WORD COLD OPEN. Start with a SHOCKING FACT. Jamie INTERRUPTS. No 'Hello'."
    elif seg["name"] == "INTRO":
        user_msg = "Alex: 'Welcome to the AI Edge, your space for Daily News in Artificial Intelligence completely unfiltered.' Intro the 3 main stories."
    elif seg["name"] == "OUTRO":
        user_msg = "Alex: 'If you learned one thing, share this with a friend.' Mention links in show notes."

    res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
    return res.choices[0].message.content

# --- 9. RSS FEED GENERATOR (SPOTIFY COMPLIANT) ---
def update_rss_feed(filename, ep_title, ep_desc):
    """Generates the feed.xml that Spotify 'polls' for updates."""
    audio_url = f"{RAW_AUDIO_BASE}/{filename}"
    
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{RSS_SETTINGS['title']}</title>
    <link>{RSS_SETTINGS['link']}</link>
    <language>en-us</language>
    <itunes:author>{RSS_SETTINGS['author']}</itunes:author>
    <itunes:owner>
      <itunes:name>{RSS_SETTINGS['author']}</itunes:name>
      <itunes:email>{RSS_SETTINGS['email']}</itunes:email>
    </itunes:owner>
    <itunes:image href="{RSS_SETTINGS['image']}"/>
    <itunes:category text="{RSS_SETTINGS['category']}"/>
    <description>{RSS_SETTINGS['description']}</description>
    <item>
      <title>{ep_title}</title>
      <description>{ep_desc}</description>
      <pubDate>{datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
      <enclosure url="{audio_url}" length="0" type="audio/mpeg"/>
      <guid isPermaLink="false">{filename}</guid>
      <itunes:duration>45:00</itunes:duration>
    </item>
  </channel>
</rss>"""
    with open("feed.xml", "w") as f:
        f.write(rss_content)

# --- 10. MAIN PRODUCTION LOOP ---
def produce_episode():
    print("--- 🚀 LAUNCHING AI EDGE PRODUCTION ---")
    
    # 1. Fetch & Analyze
    context = fetch_news()
    print(" >> 🧠 GENERATING SEO TITLES & METADATA...")
    meta = generate_metadata(context) 
    print(f"    TITLE: {meta['title']}")
    
    show_type, structure = get_show_structure()
    full_script = ""
    audio_segs = []

    # 2. Asset Loading
    m_intro = AudioSegment.from_mp3(ASSETS_DIR / "intro.mp3") if (ASSETS_DIR / "intro.mp3").exists() else AudioSegment.silent(1000)
    m_outro = AudioSegment.from_mp3(ASSETS_DIR / "outro.mp3") if (ASSETS_DIR / "outro.mp3").exists() else AudioSegment.silent(1000)
    s_trans = AudioSegment.from_mp3(ASSETS_DIR / "transition.mp3") if (ASSETS_DIR / "transition.mp3").exists() else AudioSegment.silent(500)

    # 3. Script & Audio Generation
    for seg in structure:
        script = generate_script(seg, context, show_type)
        full_script += script + "\n"
        
        # TTS Processing
        for line in script.split('\n'):
            if ":" not in line: continue
            match = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.*)', line, re.IGNORECASE)
            if match:
                speaker, text = match.group(1).upper(), match.group(2).strip()
                voice = VOICES.get(speaker, "onyx")
                temp = AUDIO_DIR / "temp.mp3"
                client.audio.speech.create(model="tts-1-hd", voice=voice, input=text).stream_to_file(temp)
                audio_segs.append(AudioSegment.from_mp3(temp))
        
        # Audio Design
        if seg["name"] == "HOOK": audio_segs.append(m_intro)
        elif "BLOCK" in seg["name"]: audio_segs.append(s_trans)

    # 4. Final Export
    audio_segs.append(m_outro)
    final = sum(audio_segs)
    fname = f"podcast_{datetime.date.today()}.mp3"
    final.export(AUDIO_DIR / fname, format="mp3")
    
    # 5. Distribution (RSS & Viral Caption) with NEW METADATA
    update_rss_feed(fname, meta['title'], meta['summary']) 
    
    # Generates the Social Post with SEO Tags
    caption = f"""
🎙️ NEW EPISODE: {meta['title']}

{meta['summary']}

👇 DISCUSSED TODAY:
{meta['tags']}

🎧 LISTEN NOW: {RSS_SETTINGS['link']}
    """
    with open("viral_caption.txt", "w") as f: f.write(caption.strip())

    print(f"✅ DONE: {fname} | Title: {meta['title']}")

if __name__ == "__main__":
    produce_episode()
