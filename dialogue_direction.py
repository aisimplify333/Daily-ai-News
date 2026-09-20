"""Contextual edit decisions. Timing is a craft heuristic, not a quality score."""
import os
import re


PERFORMANCE_DIRECTION = """
PERFORMANCE AND DIALOGUE EDIT:
- Write a conversation that can be acted: each reply follows a particular word,
  question or implication in the previous turn. Cut generic acknowledgements and
  explanations of a joke. Preserve every factual qualifier while tightening language.
- Rufus's English humour is economical understatement, precision, incongruity and
  mock formality. Notice the small absurd detail inside a serious system. Put the
  surprising word or image at the end. Deliver as an observation, not an announcement
  that a joke is coming. Avoid a stream of 'quite', 'splendid', tea and empire jokes.
  His expertise is credible; he can delight in an invention and laugh at himself.
- Jamie catches the implication, challenges an exact point, or affectionately turns
  Rufus's image back on him. Do not answer every joke with another joke or a compulsory
  laugh. A sincere agreement can be the surprise. Give her joy as well as indignation.
- Alex asks short, consequential questions and follows the answer. He can finish a
  colleague's thought or make a small joke, then restore focus without summarising
  what everyone just heard. Give the other hosts ownership of substantial facts.
- Vary scene rhythm: quick exchange, a complete explanation, an unexpected response,
  then room to absorb it. Never manufacture interruptions or disagreement for a quota.
  Use an ending em dash only for an intentional unfinished thought that the next host
  immediately addresses. Never cut off a number, name, negation or safety qualifier.
- A punchline earns its space through brevity. No written 'pause for laughter', stage
  directions, canned audience reactions or laughter tracks. No automatic Ha/Wait filler.
- Before returning the script, silently edit one scene at a time: identify its
  discovery, preserve the strongest objection, remove repeated explanation, sharpen
  the best earned observation and ensure the next reply responds. Keep source facts,
  sponsor wording, story boundaries, continuity and the runtime budget intact.
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
    if mood in {"concern", "concession"}:
        return {"milliseconds": 180, "reason": "reflective_response"}
    if len(reply.split()) <= 9:
        return {"milliseconds": 65, "reason": "short_reply"}
    return {"milliseconds": 110, "reason": "conversational_handoff"}
