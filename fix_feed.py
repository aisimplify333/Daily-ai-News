import os
import json
import glob
from pathlib import Path
from email.utils import formatdate

# --- CONFIGURATION (Must match your Main.py) ---
GITHUB_USERNAME = "aisimplify333"
REPO_NAME = "Daily-ai-News"
YOUR_EMAIL = "aisimplify333@GMAIL.COM"
AUTHOR_NAME = "AI Simplify Media"

# DIRECTORIES
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"

# URLS
HOSTING_URL = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/episode_audio/"
COVER_ART_URL = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}/cover.png" # <--- The Missing Link

def update_rss_feed():
    print(" >> 📡 FIXING SPOTIFY FEED (No Recording)...")
    
    # 1. THE HEADER (Now includes Image and Email)
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>The AI Edge</title>
    <description>Daily AI News, Finance, and Regulation.</description>
    <link>{HOSTING_URL}</link>
    <language>en-us</language>
    <itunes:category text="Technology"/>
    <itunes:explicit>no</itunes:explicit>
    <itunes:author>{AUTHOR_NAME}</itunes:author>
    <itunes:image href="{COVER_ART_URL}"/>
    <itunes:owner>
        <itunes:name>{AUTHOR_NAME}</itunes:name>
        <itunes:email>{YOUR_EMAIL}</itunes:email>
    </itunes:owner>
    """
    
    # 2. THE EPISODES
    files = sorted(list(AUDIO_DIR.glob("*.mp3")), key=os.path.getmtime, reverse=True)
    
    for file_path in files:
        filename = file_path.name
        
        # Try to find the matching JSON file for titles/descriptions
        meta_path = file_path.with_suffix(".json")
        if meta_path.exists():
            with open(meta_path, "r") as f: meta = json.load(f)
            title = meta.get("title", filename)
            desc = meta.get("description", "Daily AI Update")
        else:
            # Fallback if no JSON exists
            title = filename.replace(".mp3", "").replace("podcast_", "AI Edge: ")
            desc = "Daily AI News Analysis."

        file_size = os.path.getsize(file_path)
        pubDate = formatdate(os.path.getmtime(file_path))
        file_url = f"{HOSTING_URL}{filename}"

        rss += f"""
    <item>
      <title>{title}</title>
      <description>{desc}</description>
      <enclosure url="{file_url}" length="{file_size}" type="audio/mpeg"/>
      <guid>{file_url}</guid>
      <pubDate>{pubDate}</pubDate>
      <itunes:duration>1320</itunes:duration>
      <itunes:image href="{COVER_ART_URL}"/>
    </item>"""

    rss += "\n  </channel>\n</rss>"
    
    # 3. SAVE THE FILE
    with open(BASE_DIR / "feed.xml", "w") as f: f.write(rss)
    print(f" ✅ FIXED FEED SAVED: {BASE_DIR / 'feed.xml'}")

if __name__ == "__main__":
    if not AUDIO_DIR.exists():
        print("❌ ERROR: Could not find 'episode_audio' folder.")
    else:
        update_rss_feed()
