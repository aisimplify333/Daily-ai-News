"""Observable editorial requirements, separate from subjective entertainment quality."""
import re

HANDOFF = 'Rufus, take us on location.'
RETURN = 'Back to the wider story.'
DESK = 'Rufus, take us to the global desk.'

def feature_status(script):
    segment = re.search(r'^###\s*SEGMENT\s*3\b[^\n]*\n(.*?)(?=^###\s*SEGMENT\s*4\b)',script,re.M|re.S|re.I)
    body = segment[1] if segment else ''
    mode = 'on_location' if HANDOFF in body else 'global_desk' if DESK in body else 'missing'
    start = HANDOFF if mode == 'on_location' else DESK
    content = body.split(start,1)[1].split(RETURN,1)[0] if start in body and RETURN in body else ''
    words = len(re.findall(r"\b[\w'-]+\b", re.sub(r'^(ALEX|JAMIE|RUFUS):','',content,flags=re.M)))
    frame = mode == 'global_desk' or bool(re.search(r'\b(?:picture|imagine)\b',content,re.I))
    return {'mode':mode, 'word_count':words, 'handoff_and_return':bool(content),
            'clearly_framed':frame, 'duration_in_word_band':100 <= words <= 220,
            'present': bool(content) and frame and 'RUFUS:' in content and 'JAMIE:' in content}

def ensure_feature_fallback(script):
    """Label existing reporting as a desk exchange when the generated location scene is absent.
    Never invent a location, presence, observation or interview merely to pass a check.
    """
    if feature_status(script)['present']:
        return script
    match = re.search(r'(^###\s*SEGMENT\s*3\b[^\n]*\n)(.*?)(?=^###\s*SEGMENT\s*4\b)',script,re.M|re.S|re.I)
    if not match or HANDOFF in match[2] or DESK in match[2]:
        return script
    lines = match[2].splitlines()
    start = next((i for i,l in enumerate(lines) if l.startswith('RUFUS:')),None)
    if start is None:
        return script
    words = 0
    end = start
    for i in range(start,len(lines)):
        if re.match(r'^(ALEX|JAMIE|RUFUS):',lines[i]):
            words += len(lines[i].split())-1
            end = i+1
            if words >= 110:
                break
    framed = lines[:start] + ['ALEX: '+DESK] + lines[start:end] + ['ALEX: '+RETURN] + lines[end:]
    return script[:match.start(2)] + '\n'.join(framed) + '\n\n' + script[match.end(2):]

def audit(script):
    feature = feature_status(script)
    from crew_review import spoken_leaks
    issues = ["Spoken production language remains: " + line for line in spoken_leaks(script)]
    if not feature['present']:
        issues.append('Rufus feature missing or incomplete.')
    elif feature['mode'] == 'global_desk':
        issues.append('Global-desk fallback delivered; a sourced on-location scene was not verified.')
    if feature['present'] and not feature['duration_in_word_band']:
        issues.append('Rufus feature outside its 100-220 word budget.')
    return {'basis':'transcript structure only; not a listening rating', 'entertainment_rating':None,
            'rufus_feature':feature, 'issues':issues,
            'requires_editorial_review':['distinct listener consequences across three stories',
                'technical terms explained on first use','everyday examples',
                'responsive warmth, humor and changed viewpoints','self-contained exchange worth sharing']}


