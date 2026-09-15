"""Local performance shaping and measured transition checks; no provider calls."""
import os
import re


def performance_settings(text, speaker, mood="neutral"):
    """Small pitch-preserving tempo/level changes; sponsor and Jamie stay baseline."""
    if os.getenv("DYNAMIC_PERFORMANCE_ENABLED", "true").lower() != "true":
        return 1.0, 0.0
    if speaker.upper() not in {"ALEX", "RUFUS"} or re.search(
        r"the ledger|t-h-e-l-e-d-g-r|subscribe", text, re.I
    ):
        return 1.0, 0.0
    if mood in {"pushback", "interruption"}:
        return 1.04, 0.35
    if mood == "pressure":
        return 1.025, 0.2
    if mood in {"concern", "concession", "explainer"}:
        return 0.975, -0.25
    if mood == "amused":
        return 1.025, 0.0
    if mood == "dry_wit" and len(text.split()) <= 18:
        return 0.985, -0.15
    return 1.0, 0.0


def measured_transition_checks(audio, timeline):
    results = []
    for row in timeline.get("rows", []):
        if row.get("kind") != "transition":
            continue
        start, end = float(row["start"]), float(row["end"])
        clip = audio[round(start * 1000):round(end * 1000)]
        level = float(clip.dBFS)
        level = level if level != float("-inf") else -120.0
        results.append({"segment": row.get("segment"), "start": start,
                        "end": end, "dbfs": round(level, 2),
                        "audible_level": end - start >= 0.5 and level >= -26.0})
    return results
