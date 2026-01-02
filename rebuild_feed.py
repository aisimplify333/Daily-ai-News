import os
import re
import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "episode_audio"
FEED_XML_PATH = BASE_DIR / "feed.xml"

AUDIO_BASE_URL = os.getenv(
    "AUDIO_BASE_URL",
    "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
)

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": "https://github.com/aisimplify333/Daily-ai-News",
    "description": "Daily AI News Drama: raw, human, high-stakes conversations about the future.",
    "author": "AI Simplify Media",
    "email": "aisimplifynewsfeed@gmail.com",
    "image": "https://raw.githubusercontent.com/aisimplify333/Daily-ai-News/main/cover.png",
    "category": "Technology",
}

DATE_RE = re.compile(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3$", re.IGNORECASE)

def rfc2822(dt: datetime.datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def ensure_feed_tree() -> tuple[ET.ElementTree, ET.Element, ET.Element]:
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

    if FEED_XML_PATH.exists():
        tree = ET.parse(FEED_XML_PATH)
        rss = tree.getroot()
        channel = rss.find("channel")
        if channel is None:
            raise RuntimeError("feed.xml exists but missing <channel>.")
        return tree, rss, channel

    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "language").text = "en-us"

    itunes_author = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author")
    itunes_author.text = RSS_SETTINGS["author"]

    owner = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}owner")
    ET.SubElement(owner, "{http://www.itunes.com/dtds/podcast-1.0.dtd}email").text = RSS_SETTINGS["email"]

    img = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
    img.set("href", RSS_SETTINGS["image"])

    tree = ET.ElementTree(rss)
    return tree, rss, channel

def existing_guids(channel: ET.Element) -> set[str]:
    out = set()
    for item in channel.findall("item"):
        g = item.findtext("guid")
        if g:
            out.add(g.strip())
    return out

def build_item(mp3_path: Path) -> ET.Element:
    m = DATE_RE.search(mp3_path.name)
    date_str = m.group(1) if m else mp3_path.stem
    title = f"The AI Edge: {date_str}"
    guid = f"{mp3_path.name}-{date_str}"

    length_bytes = mp3_path.stat().st_size
    pub_dt = datetime.datetime.utcfromtimestamp(mp3_path.stat().st_mtime)

    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "guid").text = guid
    ET.SubElement(item, "pubDate").text = rfc2822(pub_dt)
    ET.SubElement(item, "description").text = f"Daily AI briefing for {date_str}."

    enc = ET.SubElement(item, "enclosure")
    enc.set("url", AUDIO_BASE_URL + mp3_path.name)
    enc.set("type", "audio/mpeg")
    enc.set("length", str(length_bytes))

    # Optional but helpful
    itunes_duration = ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
    itunes_duration.text = "0"

    return item

def main():
    tree, rss, channel = ensure_feed_tree()
    guids = existing_guids(channel)

    mp3s = sorted(AUDIO_DIR.glob("podcast_*.mp3"))
    if not mp3s:
        raise RuntimeError("No podcast_*.mp3 files found in episode_audio/")

    new_items = []
    for mp3 in mp3s:
        guid = f"{mp3.name}-{(DATE_RE.search(mp3.name).group(1) if DATE_RE.search(mp3.name) else mp3.stem)}"
        if guid in guids:
            continue
        new_items.append(build_item(mp3))

    # Collect all items, then sort by pubDate descending
    all_items = list(channel.findall("item")) + new_items

    def item_dt(it: ET.Element) -> float:
        pd = it.findtext("pubDate") or ""
        try:
            # parse minimal: use mtime fallback if needed
            return datetime.datetime.strptime(pd, "%a, %d %b %Y %H:%M:%S GMT").timestamp()
        except Exception:
            return 0.0

    all_items.sort(key=item_dt, reverse=True)

    # Replace items in channel
    for old in list(channel.findall("item")):
        channel.remove(old)
    for it in all_items:
        channel.append(it)

    tree.write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    print(f"✅ Rebuilt feed with {len(all_items)} items. Wrote: {FEED_XML_PATH}")

if __name__ == "__main__":
    main()

