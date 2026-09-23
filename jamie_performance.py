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
    # Natural reactions occur inside a turn, not only in its first words.
    natural = (
        ("curiosity", r"\b(?:the (?:thing|part) (?:that )?i find interesting|that reframe is interesting|i wanted this story because|the thing that genuinely gets me|i hadn\'t thought about that)\b"),
        ("delight", r"\b(?:it\'s|it is|that\'s|that is) (?:genuinely |actually )?(?:extraordinary|exciting|wonderful|brilliant)\b"),
        ("warmth", r"\b(?:thanks for spending|thank you for joining|that gives people (?:another|a real) (?:option|chance))\b"),
    )
    for mood, pattern in patterns + tuple(sorted(natural, key=lambda row: row[0] == "curiosity")):
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
    sentences = list(re.finditer(r"[^.!?]+(?:[.!?](?=\s|$)|$)", text))
    selected = next((m for m in sentences if emotional_intent(m.group().strip()) == mood and len(m.group().split()) <= 28), None)
    if selected:
        start, end = selected.span()
        return text[:start] + f"<{tag}>" + text[start:end] + f"</{tag}>" + text[end:]
    first = re.match(r"^(.+?[.!?])(?=\s|$)", text)
    end = first.end() if first else len(text)
    # Long factual passages should not get an entire dramatic read.
    if len(text[:end].split()) > 28:
        return text
    return f"<{tag}>{text[:end]}</{tag}>" + text[end:]
