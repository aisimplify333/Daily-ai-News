import os
import json
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from email.utils import formatdate

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
METADATA_FILE = BASE_DIR / "episode_metadata.json"
FEED_FILE = BASE_DIR / "feed.xml"

# REPLACE THIS with your actual GitHub username/repo if known, 
# otherwise we default to the raw GitHub URL structure.
# Example: "https://github.com/YourName/Daily-ai-News/raw/main"
GITHUB_BASE_URL = "https://github.com/Daily-ai-News/Daily-ai-News/raw/main" 

def update_rss_feed():
    print(" >> 📡 UPDATING RSS FEED...")

    # 1. Load the Fresh Metadata
    if not METADATA_FILE.exists():
        print(" ❌ No metadata found. Skipping feed update.")
        return

    with open(METADATA_FILE, "r") as f:
        meta = json.load(f)

    # 2. Parse the Existing Feed
    if not FEED_FILE.exists():
        print(" ❌ No feed.xml found to update.")
        return

    ET.register_namespace('itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
    tree = ET.parse(FEED_FILE)
    root = tree.getroot()
    channel = root.find("channel")

    # 3. Check if episode already exists (prevent duplicates)
    episode_title = meta['title']
    for item in channel.findall("item"):
        if item.find("title").text == episode_title:
            print(f" ⚠️ Episode '{episode_title}' already in feed. Skipping.")
            return

    # 4. Create New Item
    new_item = ET.Element("item")

    # Title
    title = ET.SubElement(new_item, "title")
    title.text = meta['title']

    # Description (Show Notes)
    desc = ET.SubElement(new_item, "description")
    desc.text = meta['description']

    # Enclosure (The MP3 Link)
    # We construct the URL to point to the 'episode_audio' folder
    filename = Path(meta['file']).name
    mp3_url = f"{GITHUB_BASE_URL}/episode_audio/{filename}"
    
    enclosure = ET.SubElement(new_item, "enclosure")
    enclosure.set("url", mp3_url)
    enclosure.set("type", "audio/mpeg")
    enclosure.set("length", "30000000") # Approx length in bytes (optional but good)

    # GUID (Unique ID)
    guid = ET.SubElement(new_item, "guid")
    guid.text = mp3_url # Using URL as GUID is standard simple practice
    guid.set("isPermaLink", "true")

    # PubDate (RFC 822 format for Spotify)
    pub_date = ET.SubElement(new_item, "pubDate")
    pub_date.text = formatdate(usegmt=True)

    # Add to Feed (Insert at top)
    channel.insert(0, new_item) # Index 0 puts it at the top of the list (newest)

    # 5. Save
    tree.write(FEED_FILE, encoding="UTF-8", xml_declaration=True)
    print(f" ✅ FEED UPDATED: Added '{episode_title}'")

if __name__ == "__main__":
    update_rss_feed()
