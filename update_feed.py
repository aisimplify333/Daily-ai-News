# update_feed.py
import datetime
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Optional, List

FEED_XML_PATH = Path("feed.xml")
EPISODE_DIR = Path("episode_audio")

SITE_URL = "https://aisimplify333.github.io/Daily-ai-News/"
AUDIO_BASE_URL = "https://aisimplify333.github.io/Daily-ai-News/episode_audio/".rstrip("/") + "/"
COVER_URL = "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png"

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily AI News Drama: raw, human, high-stakes conversations about the future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "category": "Technology",
    "explicit": "no",
    "image": COVER_URL,
}

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("itunes", ITUNES_NS)  # IMPORTANT: no manual xmlns:itunes anywhere

def q(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"

def _rfc2822(dt: datetime.datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

def _date_from_filename(name: str) -> Optional[str]:
    m = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", name)
    return m.group(1) if m else None

def _is_real_episode_file(p: Path) -> bool:
    n = p.name.lower()
    return n.startswith("podcast_") and n.endswith(".mp3") and "_seg_" not in n

def build_channel(channel: ET.Element):
    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = _rfc2822(datetime.datetime.now(datetime.timezone.utc))

    ET.SubElement(channel, q("author")).text = RSS_SETTINGS["author"]
    ET.SubElement(channel, q("explicit")).text = RSS_SETTINGS["explicit"]

    cat = ET.SubElement(channel, q("category"))
    cat.set("text", RSS_SETTINGS["category"])

    img = ET.SubElement(channel, q("image"))
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, q("owner"))
    ET.SubElement(owner, q("name")).text = RSS_SETTINGS["author"]
    ET.SubElement(owner, q("email")).text = RSS_SETTINGS["email"]

def make_item(title: str, description: str, mp3_filename: str, length_bytes: int, pubdate_rfc2822: str) -> ET.Element:
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = (description or "")[:6000]

    audio_url = AUDIO_BASE_URL + mp3_filename

    guid = ET.SubElement(item, "guid")
    guid.set("isPermaLink", "false")
    guid.text = audio_url

    ET.SubElement(item, "pubDate").text = pubdate_rfc2822

    enc = ET.SubElement(item, "enclosure")
    enc.set("url", audio_url)
    enc.set("length", str(int(length_bytes)))
    enc.set("type", "audio/mpeg")

    # Optional but fine:
    # dur = ET.SubElement(item, q("duration"))
    # dur.text = ""

    return item

def rebuild_feed(limit: int = 60):
    mp3s: List[Path] = sorted(
        [p for p in EPISODE_DIR.glob("podcast_*.mp3") if _is_real_episode_file(p)],
        key=lambda p: p.name,
        reverse=True,
    )

    rss = ET.Element("rss", {"version": "2.0"})  # DO NOT set xmlns:itunes here
    channel = ET.SubElement(rss, "channel")
    build_channel(channel)

    for mp3 in mp3s[:limit]:
        datestr = _date_from_filename(mp3.name) or datetime.date.today().isoformat()
        try:
            dt = datetime.datetime.strptime(datestr, "%Y-%m-%d").replace(
                hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc
            )
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc)

        title = f"{RSS_SETTINGS['title']} — {datestr}"
        desc = f"Listen: {SITE_URL}listen/"

        channel.append(
            make_item(
                title=title,
                description=desc,
                mp3_filename=mp3.name,
                length_bytes=mp3.stat().st_size,
                pubdate_rfc2822=_rfc2822(dt),
            )
        )

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    print("✅ feed.xml rebuilt cleanly (itunes namespace OK).")

if __name__ == "__main__":
    rebuild_feed()
