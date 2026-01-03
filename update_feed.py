import re
import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import quote

FEED_XML_PATH = Path("feed.xml")
EPISODE_DIR = Path("episode_audio")

AUDIO_BASE_URL = "https://aisimplify333.github.io/Daily-ai-News/episode_audio/"
COVER_URL = "https://aisimplify333.github.io/Daily-ai-News/cover.png"
SITE_URL = "https://aisimplify333.github.io/Daily-ai-News/"

RSS_SETTINGS = {
    "title": "The AI Edge",
    "link": SITE_URL,
    "description": "Daily AI News Drama: raw, human, high-stakes conversations about the future.",
    "author": "AI Simplify Media",
    "email": "aisimplify333@gmail.com",
    "category": "Technology",
    "explicit": "no",
    "image": COVER_URL,
}

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("atom", ATOM_NS)

STRICT_RE = re.compile(r"^podcast_(\d{4}-\d{2}-\d{2})\.mp3$")

def q(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"

def rfc2822_from_date(datestr: str) -> str:
    try:
        dt = datetime.datetime.strptime(datestr, "%Y-%m-%d").replace(
            hour=12, minute=0, second=0, tzinfo=datetime.timezone.utc
        )
    except Exception:
        dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S -0000")

def safe_url(filename: str) -> str:
    return AUDIO_BASE_URL.rstrip("/") + "/" + quote(filename)

def build_channel(channel: ET.Element):
    ET.SubElement(channel, "title").text = RSS_SETTINGS["title"]
    ET.SubElement(channel, "description").text = RSS_SETTINGS["description"]
    ET.SubElement(channel, "link").text = RSS_SETTINGS["link"]
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_from_date(datetime.date.today().isoformat())

    atom_link = ET.SubElement(channel, f"{{{ATOM_NS}}}link")
    atom_link.set("href", SITE_URL.rstrip("/") + "/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    cat = ET.SubElement(channel, q("category"))
    cat.set("text", RSS_SETTINGS["category"])

    ET.SubElement(channel, q("explicit")).text = RSS_SETTINGS["explicit"]
    ET.SubElement(channel, q("author")).text = RSS_SETTINGS["author"]
    ET.SubElement(channel, q("type")).text = "episodic"

    img = ET.SubElement(channel, q("image"))
    img.set("href", RSS_SETTINGS["image"])

    owner = ET.SubElement(channel, q("owner"))
    ET.SubElement(owner, q("name")).text = RSS_SETTINGS["author"]
    ET.SubElement(owner, q("email")).text = RSS_SETTINGS["email"]

def make_item(title: str, description: str, mp3_filename: str, length_bytes: int, pubdate: str, duration_seconds: int):
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "description").text = (description or "")[:6000]

    url = safe_url(mp3_filename)

    enc = ET.SubElement(item, "enclosure")
    enc.set("url", url)
    enc.set("length", str(int(length_bytes)))
    enc.set("type", "audio/mpeg")

    guid = ET.SubElement(item, "guid")
    guid.set("isPermaLink", "false")
    guid.text = url

    ET.SubElement(item, "pubDate").text = pubdate

    dur = ET.SubElement(item, q("duration"))
    if duration_seconds:
        dur.text = str(int(duration_seconds))

    ET.SubElement(item, q("episodeType")).text = "full"

    ep_img = ET.SubElement(item, q("image"))
    ep_img.set("href", RSS_SETTINGS["image"])
    return item

def rebuild_feed():
    mp3s = []
    for p in sorted(EPISODE_DIR.glob("podcast_*.mp3"), key=lambda x: x.name, reverse=True):
        m = STRICT_RE.match(p.name)
        if not m:
            continue
        mp3s.append((p, m.group(1)))

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    build_channel(channel)

    for p, datestr in mp3s:
        channel.append(
            make_item(
                title=f"{RSS_SETTINGS['title']} — {datestr}",
                description=f"Listen: {SITE_URL}",
                mp3_filename=p.name,
                length_bytes=p.stat().st_size,
                pubdate=rfc2822_from_date(datestr),
                duration_seconds=0,
            )
        )

    ET.ElementTree(rss).write(FEED_XML_PATH, encoding="utf-8", xml_declaration=True)
    print(f"✅ feed.xml rebuilt cleanly ({len(mp3s)} strict episodes).")

if __name__ == "__main__":
    rebuild_feed()
