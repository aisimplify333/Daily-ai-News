import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

# ---------- CONFIG ----------
FEED_XML_PATH = Path("feed.xml")
EPISODE_DIR = Path("episode_audio")

# IMPORTANT: must match your GitHub Pages base
AUDIO_BASE_URL = "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
COVER_URL = "https://aisimplify333.github.io/Daily-ai-News/cover.png"

RSS_SETTINGS = {
    "title": "The AI Edge",
    # Use the site root (not episode_audio/) for the channel link
    "link": "https://aisimplify333.github.io/Daily-ai-News/",
    "description": "Daily AI News, Finance, and Regulation.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "category": "Technology",
    "explicit": "no",
    "image": COVER_URL,
}

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
# Register ONCE. Do NOT also set xmlns:* manually on the root element.
ET.register_namespace("itunes", ITUNES_NS)

def q(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"

def rfc2822_now() -> str:
    dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

def is_real_episode_file(p: Path) -> bool:
    # Only publish full episodes, never segments
    name = p.name.lower()
    return (
        name.startswith("podcast_")
        and name.endswith(".mp3")
        and "_seg_" not in name
        and not name.startswith("seg_")
    )

def read_existing_real_items():
    """Read existing feed items, excluding any seg items."""
    items = []
    if not FEED_XML_PATH.exists():
        return items
    try:
        tree = ET.parse(FEED_XML_PATH)
        root = tree.getroot()
        channel = root.find("channel")
        if channel is None:
            return items
        for it in channel.findall("item"):
            title = (it.findtext("title") or "").lower()
            enc = it.find("enclosure")
            url = (enc.get("url") or "").lower() if enc is not None else ""
            if title.startswith("seg_") or "/seg_" in url or "_seg_" in url:
                continue
            items.append(it)
    except Exception:
        return []
    return items

def dedupe_items(items):
    seen = set()
    out = []
    for it in items:
        guid = (it.findtext("guid") or "").strip().lower()
        enc = it.find("enclosure")
        url = (enc.get("url") or "").strip().lower() if enc is not None else ""
        key = guid or url or (it.findtext("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def build_channel(channel: ET.Element):
    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now()

    cat = ET.SubElement(channel, q("category"))
    cat.set("text", RSS_SETTINGS["category"])

    ET.SubElement(channel, q("explicit")).text = RSS_SETTINGS["explicit"]
    ET.SubElement(channel, q("author")).text = RSS_SETTINGS["author"]

    img = ET.SubElement(channel, q("image"))
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, q("owner"))
    ET.SubElement(owner, q("name")).text = RSS_SETTINGS["author"]
    ET.SubElement(owner, q("email")).text = RSS_SETTINGS["email"]

def make_item(
    title: str,
    description: str,
    mp3_filename: str,
    length_bytes: int,
    pubdate: str,
    duration_seconds: int,
):
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title

    # Keep description under control; Spotify can be sensitive to huge blobs
    ET.SubElement(item, "description").text = (description or "")[:6000]

    audio_url = AUDIO_BASE_URL + mp3_filename

    enc = ET.SubElement(item, "enclosure")
    enc.set("url", audio_url)
    enc.set("length", str(int(length_bytes)))
    enc.set("type", "audio/mpeg")

    guid = ET.SubElement(item, "guid")
    guid.set("isPermaLink", "false")
    guid.text = audio_url

    ET.SubElement(item, "pubDate").text = pubdate

    dur = ET.SubElement(item, q("duration"))
    dur.text = str(int(duration_seconds)) if duration_seconds else ""

    ep_img = ET.SubElement(item, q("image"))
    ep_img.set("href", RSS_SETTINGS["image"])

    return item

def rebuild_feed(new_episode_meta: dict | None = None):
    """
    If new_episode_meta provided, inserts it as the newest item.
    Otherwise, just cleans the existing feed (removes seg items and fixes ordering).
    """
    existing_items = dedupe_items(read_existing_real_items())

    # IMPORTANT: do NOT manually set xmlns:itunes or xmlns:anything here.
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    build_channel(channel)

    # Add newest item first (if provided)
    if new_episode_meta:
        channel.append(
            make_item(
                title=new_episode_meta["title"],
                description=new_episode_meta["description"],
                mp3_filename=new_episode_meta["mp3_filename"],
                length_bytes=new_episode_meta["length_bytes"],
                pubdate=new_episode_meta["pubdate"],
                duration_seconds=new_episode_meta.get("duration_seconds", 0),
            )
        )

    # Then add prior items
    for it in existing_items:
        channel.append(it)

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    print("✅ feed.xml rebuilt cleanly (segments removed).")

if __name__ == "__main__":
    # Running update_feed.py alone will clean the feed even without a new episode
    rebuild_feed()
