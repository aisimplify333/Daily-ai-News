import os
import json
import re
import datetime
from pathlib import Path
from openai import OpenAI
from google import genai # NEW LIBRARY
from pydub import AudioSegment
from email.utils import formatdate
import html
import fetch_news 

# --- 1. STUDIO CONFIGURATION ---
client_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# CONFIGURING THE NEW BRAIN (Google GenAI SDK)
# This connects to the modern API, giving us access to Flash/Pro 1.5
client_gemini = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL_ID = "gemini-1.5-flash" 

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
    try:
        newsletter_data = fetch_news.get_todays_newsletters()
        if newsletter_data: return newsletter_data
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

# --- 3. THE SHOWRUNNER (SOUL ENGINE) ---
def generate_segment(system_prompt, content_context):
    full_prompt = f"{system_prompt}\n\nCONTEXT:\n{content_context}"
    
    # NEW SYNTAX: Direct call to the new Client
    try:
        response = client_gemini.models.generate_content(
            model=MODEL_ID,
            contents=full_prompt,
            config={
                "temperature": 0.9, # High creativity for banter
            }
        )
        return response.text.strip()
    except Exception as e:
        print(f"    ❌ GENERATION ERROR: {e}")
        return "ALEX: We are having technical difficulties. See you tomorrow."

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
    1. COLD OPEN (0:00-0:30): Start MID-ARGUMENT about Story
