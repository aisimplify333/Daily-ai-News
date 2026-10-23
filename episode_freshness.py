"""Compare proposed episodes against the actual published feed, including recovery."""
import datetime as dt
import html
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


def normalized(text):
    return " ".join(re.findall(r"[a-z0-9]+", html.unescape(str(text)).lower()))


def same_headline(a, b):
    a, b = normalized(a), normalized(b)
    if not a or not b:
        return False
    stop = {"the", "a", "an", "for", "of", "to", "and", "in", "with", "ai"}
    x, y = set(a.split()) - stop, set(b.split()) - stop
    return a == b or (len(x & y) >= 4 and (
        len(x & y) / max(1, len(x | y)) >= .65 or
        SequenceMatcher(None, a, b).ratio() >= .80))


def canonical_url(value):
    parts = urlsplit(str(value or ""))
    # AP serves the same article with either an ID-only or descriptive slug URL.
    if parts.netloc.lower().removeprefix("www.") == "apnews.com":
        article_id = re.search(r"/article/(?:[^/]*-)?([a-f0-9]{32})/?$", parts.path, re.I)
        if article_id:
            return "apnews.com/article/" + article_id[1].lower()
    return (parts.netloc.lower() + parts.path.rstrip("/")).lower() if parts.netloc else ""


def published_history(date_str, root=Path(".")):
    """RSS is durable history; in-progress continuity must not define publication."""
    root = Path(root)
    today = dt.date.fromisoformat(date_str)
    history = []
    feed = root / "feed.xml"
    if feed.exists():
        for item in ET.parse(feed).findall("./channel/item"):
            enc = item.find("enclosure")
            url = enc.get("url", "") if enc is not None else item.findtext("guid", "")
            match = re.search(r"podcast_(\d{4}-\d{2}-\d{2})\.mp3", url)
            if not match:
                continue
            day = dt.date.fromisoformat(match[1])
            if not 0 < (today - day).days <= 14:
                continue
            description = html.unescape(item.findtext("description", ""))
            headlines = re.findall(r"^\s*[•]\s*(.+)$", description, re.M)
            history.append({"date": match[1], "title": item.findtext("title", ""),
                            "stories": [{"headline": h} for h in headlines]})
    meta = root / "episode_metadata.json"
    if meta.exists():
        data = json.loads(meta.read_text())
        day = dt.date.fromisoformat(data["date"])
        if 0 < (today - day).days <= 14:
            history.append(data)
    return history


def repeated_story(story, history):
    headline = story.get("headline") or story.get("title") or ""
    url = canonical_url(story.get("source_url") or story.get("link"))
    key = story.get("event_key")
    for episode in history:
        for old in episode.get("stories", []):
            old_url = canonical_url(old.get("source_url") or old.get("link"))
            if ((key and key == old.get("event_key")) or
                (url and url == old_url) or
                same_headline(headline, old.get("headline") or old.get("title") or "")):
                return episode.get("date", "prior episode")
    return ""


def assert_fresh_episode(stories, date_str, title="", root=Path(".")):
    history = published_history(date_str, root)
    for story in stories[:3]:
        previous = repeated_story(story, history)
        if previous:
            raise ValueError(f"Previously aired story from {previous}; fresh research required: "
                             + str(story.get("headline") or story.get("title")))
    if title and any(same_headline(title, e.get("title", "")) for e in history):
        raise ValueError("Episode title repeats a published episode; new title required")
