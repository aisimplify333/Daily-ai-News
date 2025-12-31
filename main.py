import os
import json
import re
import datetime
from pathlib import Path
from openai import OpenAI
import google.generativeai as genai 
from pydub import AudioSegment
from email.utils import formatdate
import html
import fetch_news 

# --- 1. STUDIO CONFIGURATION ---
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# CONFIGURING THE BRAIN (GEMINI 1.5 PRO-002 FOR MAX CREATIVITY)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY")) 
model = genai.GenerativeModel('gemini-1.5-pro-002') 

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

if not AUDIO_DIR.exists(): AUDIO_DIR.mkdir(exist_ok=True)

# CAST (The Voices)
CAST = { 
    "ALEX": "onyx",    # The Host (Curious, High Energy)
    "JAMIE": "nova",   # The Heart (Vulnerable, Slow, Empathic)
    "RUFUS": "fable"   # The Brain (Fast, Cynical, Authoritative)
}

# --- 2. INTEL ENGINE ---
def gather_intel():
    print(" >> 📡 GATHERING INTEL FROM EMAILS...")
    newsletter_data = fetch_news.get_todays_newsletters()
    
    # IF EMAILS EXIST, USE THEM. IF NOT, USE YOUR "EMPIRE" TEST DATA.
    if newsletter_data: 
        return newsletter_data
    else:
        print("    ⚠️ INBOX EMPTY. USING EMPIRE TEST DATA.")
        return """
        STORY 1: Anthropic's Claude Sonnet 4.5 released. This model upgrade introduces smarter reasoning, stronger memory tools, and the ability to run multi-hour tasks without constant resets. It is a significant step forward for agentic AI.
        STORY 2: OpenAI hits $500 Billion valuation. After a secondary share sale to investors, OpenAI reached this staggering number, showcasing the company's absolute dominance in the AI market.
        STORY 3: Meta's AI-driven advertising sparks privacy debates. Meta is using AI-generated chatbot conversations to fuel ads, highlighting specific ethical implications of AI in advertising.
        """

def get_sponsors():
    return [
        {"name": "Oracle Cloud", "copy": "Stop burning cash. Oracle Cloud is built for GPU workloads. Visit Oracle.com."},
        {"name": "NetSuite", "copy": "Visibility is survival. NetSuite gives you the data to survive the crash. NetSuite.com."},
        {"name": "ElevenLabs", "copy": "This show is 100% AI. Scale your content with ElevenLabs.io."}
    ]

# --- 3. THE SHOWRUNNER (SOUL ENGINE) ---
def generate_segment(system_prompt, content_context):
    full_prompt = f"{system_prompt}\n\nCONTEXT:\n{content_context}"
    
    # SAFETY: Allow cynicism/banter without triggering "Harassment" blocks
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    ]
    
    response = model.generate_content(
        full_prompt,
        generation_config=genai.types.GenerationConfig(candidate_count=1, temperature=0.9),
        safety_settings=safety_settings
    )
    return response.text.strip()

def write_full_script(intel, sponsors):
    print(" >> ✍️  WRITING ACT I (THE HOOK & CHEMISTRY)...")
    prompt_act1 = f"""
    You are the Showrunner for 'The AI Edge' Daily Podcast.
    
    THE VIBE: 
    - This is NOT a news reading. This is a "Succession" style drama about the tech world.
    - Fast-paced. Characters should INTERRUPT each other.
    - NO polite corporate speak. Use real language.
    
    THE CHARACTERS:
    - ALEX (Host): The "Joe Rogan" proxy. He asks the "dumb" questions the listener is thinking. High energy. 
      *MANDATORY:* He must physically introduce the team every time.
    - JAMIE (Co-Host): The "Steven Bartlett" proxy. Deeply vulnerable. She worries about the HUMAN cost. Uses "I feel" statements.
    - RUFUS (Analyst): The "Huberman/Matt Levine" proxy. Cynical. He cares about MONEY. He explains *how* the scam works.
    
    TASK: Write ACT 1 (Intro + Story 1).
    1. COLD OPEN (0:00-0:30): Start MID-ARGUMENT about Story 1 (Claude 4.5). Jamie is panicked about "Agents that never sleep", Rufus sees "Infinite Labor." High tension.
    2. MUSIC INTRO: Write [MUSIC].
    3. THE WELCOME: Alex says "Good morning." States the Date. 
       - ALEX MUST SAY: "With me is the conscience of the show, Jamie. Say hello Jamie." (Jamie responds with a mood check).
       - ALEX MUST SAY: "And checking in from the field... Rufus." (Rufus responds with a cynical location/trade).
    4. STORY 1 DEEP DIVE: Claude Sonnet 4.5. Alex asks what "Multi-hour tasks" means. Jamie fears autonomous agents. Rufus explains the cost savings of firing humans.
    
    LENGTH: 1500 words (approx 8-10 mins). 
    FORMAT: Standard Dialogue (ALEX: ... JAMIE: ...).
    """
    script_act1 = generate_segment(prompt_act1, intel)

    print(" >> ✍️  WRITING ACT II (THE MECHANICS & MONEY)...")
    prompt_act2 = f"""
    Write ACT 2 of 'The AI Edge'.
    
    TASK: Cover Story 2 ($500B Valuation) and the Native Ad.
    1. TRANSITION: Alex moves to Story 2 (OpenAI's Money).
    2. THE DEBATE: $500 Billion. Is it a bubble? Rufus breaks down the valuation metrics. Jamie asks if one company should own the future.
    3. NATIVE AD (THE RUFUS MOMENT): Rufus interrupts to read this ad IN CHARACTER: {sponsors[0]['name']} - {sponsors[0]['copy']}. 
       *CRITICAL:* He must weave it into his analysis as advice. "Look, if you want to survive this valuation war..."
       
    LENGTH: 1500 words (approx 8-10 mins).
    """
    script_act2 = generate_segment(prompt_act2, intel)

    print(" >> ✍️  WRITING ACT III (THE FUTURE & OUTRO)...")
    prompt_act3 = f"""
    Write ACT 3 of 'The AI Edge'.
    
    TASK: Cover Story 3 (Meta Privacy) and the Sign-Off.
    1. STORY 3: Meta reading chatbot logs for ads.
    2. JAMIE'S MOMENT: Jamie gets vulnerable. "Our thoughts are now billboards."
    3. THE CTA: Alex asks listeners to "Subscribe and Share if you want to survive the AI wave."
    4. SIGN OFF: Alex says "See you tomorrow."
    
    LENGTH: 1500 words (approx 8-10 mins).
    """
    script_act3 = generate_segment(prompt_act3, intel)
    
    return f"{script_act1}\n{script_act2}\n{script_act3}"

# --- 4. PRODUCTION ENGINE ---
def clean_text(text):
    # Remove stage directions like (laughs) or [Intro]
    text = re.sub(r'[\(\[].*?[\)\]]', '', text) 
    # Clean up standard text artifacts
    return text.replace('"', '').replace('*', '').strip()

def update_rss_feed(audio_path, show_notes):
    def xml_safe(text): return html.escape(str(text))
    
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The AI Edge</title>
    <link>https://aisimplify333.github.io/Daily-ai-News/episode_audio/</link>
    <description>Daily AI News, Finance, and Regulation.</description>
    <item>
      <title>{audio_path.stem.replace('_', ' ')}</title>
      <description>{xml_safe(show_notes)}</description>
      <enclosure url="https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}" length="{os.path.getsize(audio_path)}" type="audio/mpeg"/>
      <guid>https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}</guid>
      <pubDate>{formatdate(os.path.getmtime(audio_path))}</pubDate>
    </item>
  </channel>
</rss>"""
    with open(BASE_DIR / "feed.xml", "w") as f: f.write(rss)

def produce_episode():
    # 1. Gather Content
    intel = gather_intel()
    sponsors = get_sponsors()
    
    # 2. Write Script (3 Acts x 1500 words = ~30 mins)
    full_script = write_full_script(intel, sponsors)
    
    today_str = datetime.date.today().isoformat()
    episode_title = f"Daily AI Edge: {today_str}"
    
    # 3. Marketing Handshake (Critical for Video/Socials)
    show_notes = f"{today_str} | {episode_title}\n\nTOPICS:\n{intel[:500]}...\n\n#AI #TechNews"
    
    # Save Caption for Twitter Publisher
    with open("viral_caption.txt", "w") as f: f.write(show_notes)
    
    # Save JSON for Thumbnail Generator
    meta = {"title": episode_title, "date": today_str, "headlines": [intel[:100]]}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)

    # 4. Audio Recording
    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")
    audio_clips = []
    
    # Add Intro Music Bed
    if INTRO_MUSIC.exists(): 
        audio_clips.append(AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(2000))

    # Regex to find speakers reliably (ALEX:, JAMIE:, etc.)
    pattern = re.compile(r'^(ALEX|JAMIE|RUFUS|SPONSOR)\s*:?\s*(.*)', re.IGNORECASE)
    
    for line in full_script.split('\n'):
        match = pattern.match(line.strip())
        if match:
            speaker = match.group(1).upper()
            text = match.group(2)
            
            # Map "Sponsor" to Rufus
            if speaker == "SPONSOR": speaker = "RUFUS"
            
            if speaker in CAST and len(text) > 2:
                try:
                    clean_line = clean_text(text)
                    if clean_line:
                        path = AUDIO_DIR / f"seg_{len(audio_clips)}.mp3"
                        # OpenAI HD Voice Generation
                        with client.audio.speech.with_streaming_response.create(
                            model="tts-1-hd", voice=CAST[speaker], input=clean_line
                        ) as response:
                            response.stream_to_file(path)
                        audio_clips.append(AudioSegment.from_mp3(path))
                except Exception as e:
                    print(f"    ⚠️ TTS ERROR: {e}")

    # 5. Mixing
    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    for clip in audio_clips:
        # Tight Overlap for "Sorkin" feel (no gaps)
        full_audio += clip + AudioSegment.silent(duration=150) 
        
    if OUTRO_MUSIC.exists(): 
        full_audio += AudioSegment.from_mp3(OUTRO_MUSIC)[:10000].fade_in(2000)
    
    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    print(f" ✅ EPISODE COMPLETE: {outfile}")
    
    update_rss_feed(outfile, show_notes)

if __name__ == "__main__":
    produce_episode()
