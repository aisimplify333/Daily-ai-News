import re
import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, List

# ---------- CONFIG ----------
FEED_XML_PATH = Path("feed.xml")
EPISODE_DIR = Path("episode_audio")

# GitHub Pages base (must match your Pages site)
SITE_BASE = "https://aisimplify333.github.io/Daily-ai-News/"
FEED_URL = SITE_BASE + "feed.xml"
AUDIO_BASE_URL = SITE_BASE + "episode_audio/"
COVER_URL = SITE_BASE + "cover.png"

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": SITE_BASE,  # site/home, not the audio folder
    "description": "Daily AI News, Finance, and Regulation.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "category": "Technology",
    "explicit": "no",
    "image": COVER_URL,
    "type": "episodic",  # optional but helpful
}

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"

# IMPORTANT: register namespaces (do NOT manually set xmlns:* attrs later)
ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("atom", ATOM_NS)

def itunes(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"

def atom(tag: str) -> str:
    return f"{{{ATOM_NS}}}{tag}"

def rfc2822_now() -> str:
    dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

def rfc2822_from_date(datestr: str) -> str:
    # datestr like YYYY-MM-DD
    try:
        dt = datetime.datetime.strptime(datestr, "%Y-%m-%d").replace(
            hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc
        )
    except Exception:
        dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

def parse_date_from_filename(name: str) -> Optional[str]:
    m = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", name)
    return m.group(1) if m else None

def is_segment_item(item_el: ET.Element) -> bool:
    title = (item_el.findtext("title") or "").strip().lower()
    if title.startswith("seg_") or title.startswith("segment") or title.startswith("clip_"):
        return True
    enc = item_el.find("enclosure")
    if enc is not None:
        url = (enc.get("url") or "").lower()
        if "/seg_" in url or "_seg_" in url or "seg_" in url:
            return True
    return False

def read_existing_real_items() -> List[ET.Element]:
    items: List[ET.Element] = []
    if not FEED_XML_PATH.exists():
        return items
    try:
        tree = ET.parse(FEED_XML_PATH)
        root = tree.getroot()
        channel = root.find("channel")
        if channel is None:
            return items
        for it in channel.findall("item"):
            if is_segment_item(it):
                continue
            enc = it.find("enclosure")
            url = (enc.get("url") or "").lower() if enc is not None else ""
            if "podcast_" not in url:
                continue
            items.append(it)
    except Exception:
        return []
    return items

def dedupe_items(items: List[ET.Element]) -> List[ET.Element]:
    seen = set()
    out = []
    for it in items:
        enc = it.find("enclosure")
        url = (enc.get("url") or "").strip().lower() if enc is not None else ""
        guid = (it.findtext("guid") or "").strip().lower()
        key = url or guid or (it.findtext("title") or "").strip().lower()
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

    # Atom self-link (helps validators/Spotify)
    al = ET.SubElement(channel, atom("link"))
    al.set("href", FEED_URL)
    al.set("rel", "self")
    al.set("type", "application/rss+xml")

    ET.SubElement(channel, itunes("author")).text = RSS_SETTINGS["author"]
    ET.SubElement(channel, itunes("explicit")).text = RSS_SETTINGS["explicit"]
    ET.SubElement(channel, itunes("type")).text = RSS_SETTINGS.get("type", "episodic")

    cat = ET.SubElement(channel, itunes("category"))
    cat.set("text", RSS_SETTINGS["category"])

    img = ET.SubElement(channel, itunes("image"))
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, itunes("owner"))
    ET.SubElement(owner, itunes("name")).text = RSS_SETTINGS["author"]
    ET.SubElement(owner, itunes("email")).text = RSS_SETTINGS["email"]

def make_item(
    title: str,
    description: str,
    mp3_filename: str,
    length_bytes: int,
    pubdate: str,
    duration_seconds: int = 0,
) -> ET.Element:
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = (description or "")[:6000]
    ET.SubElement(item, "pubDate").text = pubdate

    audio_url = AUDIO_BASE_URL + mp3_filename

    guid = ET.SubElement(item, "guid")
    guid.set("isPermaLink", "false")
    guid.text = audio_url

    enc = ET.SubElement(item, "enclosure")
    enc.set("url", audio_url)
    enc.set("length", str(int(length_bytes)))
    enc.set("type", "audio/mpeg")

    if duration_seconds and duration_seconds > 0:
        ET.SubElement(item, itunes("duration")).text = str(int(duration_seconds))

    # optional, but harmless
    ep_img = ET.SubElement(item, itunes("image"))
    ep_img.set("href", RSS_SETTINGS["image"])

    return item

def rebuild_feed(new_episode_meta: dict | None = None):
    existing_items = dedupe_items(read_existing_real_items())

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    build_channel(channel)

    if new_episode_meta:
        channel.append(
            make_item(
                title=new_episode_meta["title"],
                description=new_episode_meta.get("description", ""),
                mp3_filename=new_episode_meta["mp3_filename"],
                length_bytes=int(new_episode_meta.get("length_bytes", 0)),
                pubdate=new_episode_meta.get("pubdate") or rfc2822_now(),
                duration_seconds=int(new_episode_meta.get("duration_seconds", 0)),
            )
        )

    for it in existing_items:
        channel.append(it)

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    print("✅ feed.xml rebuilt cleanly (segments removed; namespaces normalized).")

if __name__ == "__main__":
    rebuild_feed()
