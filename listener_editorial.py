"""Free editorial diagnostics; never an entertainment rating or publishing gate."""
import re
from collections import Counter


EDITORIAL_DIRECTION = """
LISTENER-FIRST EDITORIAL DIRECTION:
- NEWS EDITOR: Explain the actual new development early. Distinguish an announcement
  from availability, a company claim from independent evidence, and a forecast from
  an observed result. State the useful answer now; curiosity comes from consequences,
  not withholding basic news. Importance beats outrage and name recognition.
- SCENE WRITER: Each story has its own question, strongest competing interpretations,
  revealing evidence and useful payoff. Do not carry the lead's argument into every
  story. Let one story be discovery or delighted curiosity when facts warrant it.
- RELATIONSHIP EDITOR: Alex asks the audience's question and connects the answer to
  life or work. Jamie challenges a specific claim, with a reason and warmth underneath.
  Rufus finds the absurd incentive and lands a concise, understated British observation.
  His humour needs an original thought, not inserted British vocabulary. Let others
  tease him back. No assigned villain, loser or compulsory change of mind.
- EARNED COMEDY: Setup from the news or another host's actual words, then an unexpected
  but intelligible response. Let a good punchline land; do not explain it or stack
  three jokes on it. Do not force a joke into tragic news. Never add Ha/Wait/Precisely
  to satisfy counters. Warm agreement and honest uncertainty can also be entertaining.
- EXECUTIVE PRODUCER: Cut any exchange that repeats a settled point without new
  evidence, a stronger objection or a changed consequence. Replace repetition rather
  than adding runtime. Budget the three discussions near 40/30/30, not one long finale.
- SHARE EDITOR: Within each story, aim for one natural 3-6 turn exchange that names
  the subject, explains a surprising sourced detail, and lands a useful or funny payoff.
  It should make sense to a colleague or friend without the intro. No invented quote,
  statistic, audience reaction, or sensational hook. Do not say 'shareable moment'.
- CONTINUITY: Use only supplied episode history. Revisit a prediction when new evidence
  changes it; never invent a resolved outcome or pretend an old question received votes.
  End with a concrete takeaway and something checkable to watch, not vague anxiety.

ORIGINAL ENSEMBLE NEWSROOM VOICE:
Newsroom substance, ensemble-comedy chemistry, and the urgency of a good workplace
drama. Use these general craft techniques in The AI Edge's own voice. Do not imitate
any named writer, show, character, signature cadence, catchphrase or scene.
- CAUSAL HANDOFFS: A reply answers, challenges, clarifies or unexpectedly develops the
  previous speaker's specific point. If a reply could follow any line, rewrite it.
  Avoid three independent speeches connected only by speaker names.
- LIVE OBJECTIVES: Let each host pursue a concrete question in this story. Make the
  best opposing case credible. Tension comes from what someone stands to gain or lose,
  not raised volume, insults, fake deadlines or invented behind-the-scenes motives.
- RHYTHM: Mix short questions and quick comebacks with enough explanation to understand
  the evidence. Use brief bursts of exchange, then room for an important fact to land.
  Momentum does not mean everyone speaks fast all the time. Preserve pronunciation,
  factual qualifiers and intelligibility; do not add stage directions to spoken text.
- ALEX: Confident, curious and occasionally funny. Ask what actually changes, follow
  a surprising answer, and translate the consequence. Bring the room together without
  recapping every exchange or delivering a grand closing speech.
- JAMIE: Passionate and mischievous. Name the overlooked human consequence, defend
  an opportunity when warranted, and allow genuine excitement. Respond to Rufus's
  exact observation rather than a stock objection. Never default to permanent outrage.
- RUFUS: Spot the absurd incentive behind the money or policy. Deliver an original,
  economical observation almost incidentally; do not announce the joke. He can enjoy
  being teased, acknowledge a limit, or discover that Jamie has the better evidence.
- AFFECTION AND SURPRISE: Let a colleague sharpen another's thought, enjoy a good
  point, or take a joke before returning it. Change alliances only when the facts
  justify it. Agreement, discovery and unresolved uncertainty are valid scene endings.
- SCENE MOVEMENT: Establish the development, explore a real tension, let a relevant
  fact change the discussion, and leave with a useful consequence. Vary the order
  naturally; never force a twist or a winner. Alex gives a short navigation cue when
  moving to the next distinct story, without dragging the old argument with him.
- REVISION: Silently check handoffs, intelligibility, earned humour, evidence and
  listener payoff. Replace inert lines within the existing word budget. Output the
  requested script or planning JSON only, never this checklist or production labels.
These are editorial instructions, not evidence of listener retention or a 10/10 score.
""".strip()


def story_turns(script):
    """Count editorial dialogue separately from house ads and navigation."""
    rows = {2: [], 3: [], 4: []}
    segment = None
    for line in (script or '').splitlines():
        header = re.match(r'^###\s*SEGMENT\s*([1-5])\b', line, re.I)
        if header:
            segment = int(header[1])
            continue
        turn = re.match(r'^(ALEX|JAMIE|RUFUS):\s*(.+)', line.strip(), re.I)
        if segment in rows and turn:
            text = turn[2]
            if re.search(r'the ledger|theledgr|t-h-e-l-e-d-g-r|sponsor|follow the ai edge', text, re.I):
                continue
            rows[segment].append((turn[1].upper(), text))
    return rows


def editorial_diagnostics(script):
    rows = story_turns(script)
    counts = {segment: sum(len(re.findall(r"\b[\w'-]+\b", text)) for _, text in turns)
              for segment, turns in rows.items()}
    total = sum(counts.values())
    sentences = Counter()
    for turns in rows.values():
        for _, text in turns:
            for sentence in re.split(r'[.!?]+', text):
                normalized = ' '.join(re.findall(r'\w+', sentence.lower()))
                if len(normalized.split()) >= 9:
                    sentences[normalized] += 1
    repeated = [text for text, count in sentences.items() if count > 1]
    flags = []
    if total >= 300:
        if any(count / total > .50 for count in counts.values()):
            flags.append('story_pacing_dominance: one discussion exceeds half of editorial words')
        if any(count / total < .15 for count in counts.values()):
            flags.append('story_pacing_thin: one discussion has under 15 percent of editorial words')
    if repeated:
        flags.append('recycled_dialogue: repeated substantial sentences; replace with new evidence or cut')
    return {
        'basis': 'transcript heuristics only; no listening or audience measurement',
        'blocking': False,
        'story_words': counts,
        'story_word_shares': {k: round(v / total, 3) if total else 0 for k, v in counts.items()},
        'repeated_sentences': repeated[:12],
        'flags': flags,
    }


def expansion_segment(script):
    """Deepen the most underweight existing story, not always the final discussion."""
    rows = story_turns(script)
    counts = editorial_diagnostics(script)['story_words']
    available = [segment for segment in rows if rows[segment]]
    if not available:
        return None
    weights = {2: .4, 3: .3, 4: .3}
    return min(available, key=lambda segment: counts[segment] / weights[segment])
