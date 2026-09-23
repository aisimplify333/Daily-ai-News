"""Observable episode review. Never convert heuristics into a listening rating."""
import json
from pathlib import Path
from editorial_selection import concentrated, topic_family


def review_episode(stories, timeline, engineering, editor, storyboard):
    second = next((r for r in timeline.get("rows", [])
                   if r.get("kind") == "segment" and r.get("segment") == 2), {})
    start = second.get("start")
    issues = []
    if start is not None and start > 90:
        issues.append("Opening exceeds 90 seconds; inspect preview/callback/sponsor placement.")
    if concentrated(stories):
        issues.append("Three lead stories share a broad subject; review available alternatives.")
    if editor and editor.get("accepted") is not True:
        issues.append("Dialogue revision not retained: " + editor.get("reason", "unknown"))
    if storyboard.get("status") == "source_only_fallback":
        issues.append("All storyboard providers unavailable; source-only plan used.")
    issues.extend(engineering.get("warnings") or [])
    return {"basis": "transcript/assembly/provider telemetry, not listening",
            "listened": False, "entertainment_rating": None, "blocking": False,
            "story_families": [topic_family(s) for s in stories[:3]],
            "first_story_seconds": start, "audio_measurements": engineering.get("measurements"),
            "dialogue_editor_accepted": editor.get("accepted"),
            "storyboard_status": storyboard.get("status", "unknown"), "issues": issues,
            "requires_listening": ["responsive chemistry", "comic timing", "warmth and emotional range",
                                   "intelligibility", "mid-episode fatigue", "shareability"]}


def write_review(stories, timeline, directory="."):
    root = Path(directory)
    def read(name):
        try:
            return json.loads((root / name).read_text())
        except (OSError, ValueError):
            return {}
    report = review_episode(stories, timeline, read("audio_engineering_report.json"),
                            read("dialogue_editor_report.json"), read("storyboard_report.json"))
    # Actual provider-call metadata, never an inferred entertainment score.
    calls = read("hybrid_tts_report.json").get("calls") or []
    jamie = [c for c in calls if c.get("speaker") == "JAMIE"]
    report["jamie_performance"] = {
        "basis": "recorded provider calls; requested delivery is not verified emotion",
        "calls": len(jamie),
        "moods": {m: sum(c.get("mood") == m for c in jamie)
                  for m in sorted({str(c.get("mood", "unknown")) for c in jamie})},
        "listened": False,
    }
    (root / "listener_review_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
