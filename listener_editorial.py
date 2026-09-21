"""Free editorial diagnostics; never an entertainment rating or publishing gate."""
import re
from collections import Counter
from dialogue_direction import PERFORMANCE_DIRECTION


EDITORIAL_DIRECTION = """
EDITORIAL BRIEF — The AI Edge:
1. Explain consequential AI developments from the last 24-48 hours. Newsworthiness
   and source quality come first. Three stories need separate questions and payoffs.
   Identify what changed, who benefits and what the listener can do or watch.
2. Curiosity, delight, disagreement and affection can all move a scene. Seek actual
   useful progress without a positivity quota. Never manufacture danger or hope.
   No permanent villains, designated loser or required change of mind.
3. Every exchange adds evidence, a revealing example, a genuine objection or a changed
   implication. If it repeats a settled point, cut it. Do not force one thesis across
   all stories or pad the runtime. Target roughly 40/30/30 discussion time.
4. Preserve source qualifications. Proposals are not agreements; allegations are not
   findings. A vendor claim is not independent proof. Missing from a short summary
   does not mean nonexistent. Never invent listener submissions, votes or testimonials.
5. Include a natural self-contained exchange a listener could send to a friend:
   name the subject, explain the surprising fact, then land a useful or funny payoff.
   Never announce a 'shareable moment'. Use supplied history only; retire stale bits.
6. Explain the headline early and end with a specific answer or honest uncertainty.
   Keep the opening brief, give each story audible navigation, and leave the listener
   more capable. Instructions and automated checks are not entertainment ratings.
""".strip() + "\n\n" + PERFORMANCE_DIRECTION


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
