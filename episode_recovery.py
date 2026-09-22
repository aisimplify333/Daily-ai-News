"""Explicit same-day recovery of saved research and writing; normal QA still runs."""
import datetime as dt
import json
import os
from pathlib import Path


def load_recovery(date_str):
    folder = os.getenv("EPISODE_RECOVERY_DIR", "").strip()
    if not folder:
        return None
    root = Path(folder)
    slate = json.loads((root / "grounded_story_slate.json").read_text())
    decision = json.loads((root / "story_slate_decision.json").read_text())
    now = dt.datetime.now(dt.timezone.utc)
    if date_str != now.date().isoformat() or slate.get("date") != date_str or decision.get("date") != date_str:
        raise ValueError("Recovery requires today's matching dated research and storyboard")
    stories = slate.get("selected", [])
    board = decision.get("v3_3_debate_board", {})
    if len(stories) != 5 or not board.get("published_title"):
        raise ValueError("Incomplete recovery research or storyboard")
    for story in stories:
        published = dt.datetime.fromisoformat(story["published_at"].replace("Z", "+00:00"))
        age = (now - published).total_seconds() / 3600
        if not -6 <= age <= 48 or not story.get("grounded") or not story.get("facts"):
            raise ValueError("Recovery source is stale or incomplete; fresh research required")
    script = (root / f"script_fact_repaired_{date_str}.txt").read_text()
    if not script.strip():
        raise ValueError("Empty recovery script")
    return {"stories": stories, "board": board, "script": script}
