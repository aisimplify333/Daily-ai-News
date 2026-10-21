"""Contextual edit decisions. Timing is a craft heuristic, not a quality score."""
import os
import re


PERFORMANCE_DIRECTION = """
PERFORMANCE AND DIALOGUE EDIT:
Write speakable replies that follow what a friend just said. Allow short reactions,
a complete explanation, and space for a consequential fact. Pace follows meaning.
Build audible contrast: brisk short back-and-forth when the friends challenge or
tease, then a slower, quieter sentence when the human consequence lands. Resume
with warmth or curiosity rather than holding one dramatic pitch throughout.
Use contractions, short rebuttals, a deliberate pause before a dry payoff, and
occasional earned laughter from a friend. Sarcasm targets a claim or the cast's
pretensions, not vulnerable people. Never add audience laughter or a laugh track.
A challenge needs an answer and a response to that answer; let the third friend
complicate the point instead of instantly summarizing it. Preserve useful detail.
Never say "in the supplied reporting", "the existing discussion", or other
writer-room instructions on air; attribute uncertainty naturally to the source.
Preserve the strongest personal responses while cutting repeated exposition. Do not
expand a lively exchange into three essays or explain a punchline after it lands.
No canned laughter, automatic Ha/Wait filler, or spoken acting labels. A written
laugh is optional and must be earned. An unfinished thought must receive a response;
never cut off names, numbers, negations or factual qualifications. Preserve source
facts, sponsor wording, navigation and runtime. The shared friendship brief defines
the cast; delivery should not turn a curious question into an interrogation.
""".strip()


def sponsor_text(text):
    return bool(re.search(r"the\s*ledger|theledgr|t-h-e-l-e-d-g-r|brought to you by|subscribe", text or "", re.I))


def boundary_pause(text, speaker, next_text="", next_speaker="", mood="neutral",
                   baseline_ms=100, continuation=False):
    """Return silence AFTER a complete chunk. Never overlap or trim spoken audio."""
    baseline_ms = max(0, min(500, int(baseline_ms)))
    if os.getenv("DIALOGUE_DIRECTION_ENABLED", "true").lower() != "true":
        return {"milliseconds": baseline_ms, "reason": "baseline"}
    if sponsor_text(text) or sponsor_text(next_text):
        return {"milliseconds": 320, "reason": "sponsor_boundary"}
    if continuation:
        return {"milliseconds": 45, "reason": "same_turn_continuation"}
    if next_speaker not in {"ALEX", "JAMIE", "RUFUS"}:
        return {"milliseconds": baseline_ms, "reason": "structural_boundary"}
    body, reply = (text or "").strip(), (next_text or "").strip()
    if next_speaker == speaker:
        return {"milliseconds": 90, "reason": "same_speaker"}
    # Written interruption only. Preserve the entire audio and every spoken word.
    if body.endswith(("—", "–")) or reply.startswith(("—", "–")):
        return {"milliseconds": 25, "reason": "written_interruption"}
    if body.endswith("?"):
        return {"milliseconds": 85, "reason": "question_to_answer"}
    # infer_mood defaults Rufus to dry_wit, so this is deliberately described as
    # short-observation space, not a claim that a joke was detected.
    if speaker == "RUFUS" and mood == "dry_wit" and len(body.split()) <= 18:
        return {"milliseconds": 210, "reason": "short_rufus_observation"}
    if mood in {"concern", "concession", "warmth"}:
        return {"milliseconds": 180, "reason": "reflective_response"}
    if len(reply.split()) <= 9:
        return {"milliseconds": 65, "reason": "short_reply"}
    return {"milliseconds": 110, "reason": "conversational_handoff"}

