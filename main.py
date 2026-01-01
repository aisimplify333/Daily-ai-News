import os
import json
import re
import datetime
from pathlib import Path
from email.utils import formatdate
import xml.etree.ElementTree as ET

# LIBRARIES
from openai import OpenAI
from google import genai
from google.genai import types
from pydub import AudioSegment
import fetch_news 

# --- 1. ENVIRONMENT & SETUP ---
def require_env(name):
    val = os.environ.get(name)
    if not val:
        print(f" ❌ MISSING ENV VAR: {name}")
    return val

# DUAL BRAINS: Gemini for SOUL, OpenAI for VOICE
client_openai = OpenAI(api_key=require_env("OPENAI_API_KEY"))
client_gemini = genai.Client(api_key=require_env("GEMINI_API_KEY"))

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
INTRO_MUSIC = BASE_DIR / "intro.mp3"
OUTRO_MUSIC = BASE_DIR / "outro.mp3"

if not AUDIO_DIR.exists(): AUDIO_DIR.mkdir(exist_ok=True)

# CAST (The Voices)
CAST = { 
    "ALEX": "onyx",    # The Host
    "JAMIE": "nova",   # The Heart
    "RUFUS": "fable"   # The Brain
}

# --- 2. INTEL ENGINE ---
def gather_intel():
    print(" >> 📡 GATHERING INTEL FROM EMAILS...")
    try:
        data = fetch_news.get_todays_newsletters()
        if isinstance(data, (dict, list)):
            return json.dumps(data, indent=2)
        if data: 
            return str(data)
    except Exception as e:
        print(f"    ⚠️ EMAIL ERROR: {e}")

    print("    ⚠️ INBOX EMPTY/ERROR. USING EMPIRE TEST DATA.")
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

# --- 3. THE SHOWRUNNER (GEMINI 1.5 SOUL ENGINE) ---
def generate_segment(system_prompt, content_context):
    full_prompt = f"{system_prompt}\n\nCONTEXT:\n{content_context}"
    
    # Config for High Creativity & Length
    conf = types.GenerateContentConfig(
        temperature=0.9,
        max_output_tokens=5000 
    )

    try:
        # ATTEMPT 1: 1.5 Flash (The Soul)
        response = client_gemini.models.generate_content(
            model="gemini-1.5-flash",
            contents=full_prompt,
            config=conf
        )
        return response.text.strip()
    except Exception as e:
        print(f"    ⚠️ 1.5 FLASH FAILED ({e}). SWITCHING TO BACKUP...")
        try:
            # ATTEMPT 2: 2.0 Flash (Newer Model, sometimes safer)
            response = client_gemini.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=full_prompt,
                config=conf
            )
            return response.text.strip()
        except Exception as e2:
            print(f"    ❌ ALL MODELS FAILED: {e2}")
            return "ALEX: We are offline. See you tomorrow."

def write_full_script(intel, sponsors):
    print(" >> ✍️  WRITING ACT I (THE HOOK & CHEMISTRY)...")
    prompt_act1 = """
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
    prompt_act3 = """
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

def iter_utterances(script):
    pattern = re.compile(r'^\s*(ALEX|JAMIE|RUFUS|SPONSOR)\s*:?\s*(.*)', re.IGNORECASE)
    current_speaker = None
    buffer = []
    
    for line in script.splitlines():
        line = line.strip()
        if not line: continue
        
        match = pattern.match(line)
        if match:
            if current_speaker and buffer:
                yield current_speaker, " ".join(buffer)
            current_speaker = match.group(1).upper()
            if current_speaker == "SPONSOR": current_speaker = "RUFUS"
            buffer = [match.group(2)]
        else:
            if current_speaker:
                buffer.append(line)
                
    if current_speaker and buffer:
        yield current_speaker, " ".join(buffer)

def chunk_text(text, limit=4000):
    text = re.sub(r'[\(\[].*?[\)\]]', '', text).replace('"', '').replace('*', '').strip()
    if len(text) <= limit: return [text]
    
    chunks = []
    while len(text) > limit:
        split_idx = text.rfind('.', 0, limit)
        if split_idx == -1: split_idx = limit
        chunks.append(text[:split_idx+1])
        text = text[split_idx+1:].strip()
    chunks.append(text)
    return chunks

def update_rss_feed(audio_path, show_notes):
    rss_file = BASE_DIR / "feed.xml"
    today_str = datetime.date.today().isoformat()
    
    if not rss_file.exists():
        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The AI Edge</title>
    <link>https://aisimplify333.github.io/Daily-ai-News/episode_audio/</link>
    <description>Daily AI News, Finance, and Regulation.</description>
    <language>en-us</language>
  </channel>
</rss>"""
        with open(rss_file, "w") as f: f.write(rss)

    try:
        tree = ET.parse(rss_file)
        root = tree.getroot()
        channel = root.find("channel")
        
        item = ET.Element("item")
        ET.SubElement(item, "title").text = f"Daily AI Edge: {today_str}"
        ET.SubElement(item, "description").text = show_notes
        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", f"https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}")
        enclosure.set("length", str(os.path.getsize(audio_path)))
        enclosure.set("type", "audio/mpeg")
        ET.SubElement(item, "guid").text = f"https://aisimplify333.github.io/Daily-ai-News/episode_audio/{audio_path.name}"
        ET.SubElement(item, "pubDate").text = formatdate(os.path.getmtime(audio_path))
        
        channel.insert(0, item) 
        tree.write(rss_file, encoding="UTF-8", xml_declaration=True)
    except Exception as e:
        print(f"⚠️ RSS UPDATE FAILED: {e}")

def produce_episode():
    intel = gather_intel()
    sponsors = get_sponsors()
    full_script = write_full_script(intel, sponsors)
    
    today_str = datetime.date.today().isoformat()
    episode_title = f"Daily AI Edge: {today_str}"
    show_notes = f"{today_str} | {episode_title}\n\nTOPICS:\n{intel[:500]}...\n\n#AI #TechNews"
    
    with open(BASE_DIR / "viral_caption.txt", "w") as f: f.write(show_notes)
    meta = {"title": episode_title, "date": today_str, "headlines": [intel[:100]]}
    with open(BASE_DIR / "episode_metadata.json", "w") as f: json.dump(meta, f)

    print(" >> 🎙️  RECORDING (EMPIRE QUALITY)...")
    audio_clips = []
    
    if INTRO_MUSIC.exists(): 
        audio_clips.append(AudioSegment.from_mp3(INTRO_MUSIC)[:15000].fade_out(2000))

    seg_idx = 0
    for speaker, text in iter_utterances(full_script):
        if speaker in CAST:
            chunks = chunk_text(text)
            for chunk in chunks:
                if len(chunk) < 2: continue
                try:
                    path = AUDIO_DIR / f"seg_{seg_idx}.mp3"
                    with client_openai.audio.speech.with_streaming_response.create(
                        model="tts-1-hd", voice=CAST[speaker], input=chunk
                    ) as response:
                        response.stream_to_file(path)
                    audio_clips.append(AudioSegment.from_mp3(path))
                    seg_idx += 1
                except Exception as e:
                    print(f"    ⚠️ TTS ERROR: {e}")

    print(" >> 🎚️  MIXING...")
    full_audio = AudioSegment.empty()
    for clip in audio_clips:
        full_audio += clip + AudioSegment.silent(duration=150) 
        
    if OUTRO_MUSIC.exists(): 
        full_audio += AudioSegment.from_mp3(OUTRO_MUSIC)[:10000].fade_in(2000)
    
    outfile = AUDIO_DIR / f"podcast_{today_str}.mp3"
    full_audio.export(outfile, format="mp3", bitrate="192k")
    print(f" ✅ EPISODE COMPLETE: {outfile}")
    update_rss_feed(outfile, show_notes)

if __name__ == "__main__":
    produce_episode()
