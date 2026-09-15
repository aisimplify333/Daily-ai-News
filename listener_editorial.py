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
