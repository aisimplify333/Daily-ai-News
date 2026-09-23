"""Conservative Jamie intent cues and speech-only direction; no new factual words.

Controls: https://docs.x.ai/developers/model-capabilities/audio/text-to-speech
Intent is a heuristic, not a measurement of the resulting performance.
"""
import os
import re


def emotional_intent(text):
    if os.getenv("JAMIE_EMOTIONAL_DIRECTION", "true").lower() != "true":
        return None
    # Explicit personal reactions only; don't turn every 'family' into concern
    # or every 'great' (including quoted marketing) into a laugh.
    text = text.replace("’", "'")
    patterns = (
        ("delight", r"^(?:oh[,!]\s*)?(?:(?:i (?:love|am excited about)|i'm excited about)\b|that(?:'s| is) (?:wonderful|brilliant|genuinely useful)\b)"),
        ("warmth", r"^(?:honestly[, ]+)?(?:that matters to me|i care about|i'm glad|i am glad|that's a relief|that is a relief)\b"),
        ("disbelief", r"^(?:you(?:'re| are) kidding|did you just|seriously\?|really\?)"),
        ("curiosity", r"^(?:i(?:'m| am) curious|what surprises me|here's what i want to understand)\b"),
    )
    for mood, pattern in patterns:
        if re.search(pattern, text.strip(), re.I):
            return mood
    return None


def direct_delivery(text, mood):
    """Wrap at most one short sentence; preserve words and factual qualifiers."""
    if os.getenv("JAMIE_EMOTIONAL_DIRECTION", "true").lower() != "true":
        return text
    tag = {"delight": "build-intensity", "warmth": "soft",
           "disbelief": "emphasis", "curiosity": "slow"}.get(mood)
    if not tag:
        return text
    first = re.match(r"^(.+?[.!?])(?=\s|$)", text)
    end = first.end() if first else len(text)
    # Long factual passages should not get an entire dramatic read.
    if len(text[:end].split()) > 28:
        return text
    return f"<{tag}>{text[:end]}</{tag}>" + text[end:]
