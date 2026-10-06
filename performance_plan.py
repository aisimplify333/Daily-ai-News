"""Validated, non-spoken direction for the exact final script; no audio quality claims."""
import hashlib
import json
import re
from pathlib import Path
from dialogue_direction import sponsor_text

MOODS = {'neutral','explainer','dry_wit','amused','pressure','pushback','interruption',
         'concern','concession','delight','warmth','curiosity','disbelief'}

def normalized(text):
    return ' '.join(re.findall(r"[\w']+", text.lower().replace('’', "'")))

def turns(script):
    return [{'id':i, 'speaker':m[1], 'text':m[2]} for i,m in enumerate(
        re.finditer(r'^(ALEX|JAMIE|RUFUS):\s*(.+)$', script, re.M))]

def build_plan(script, request, path='performance_plan.json', scene_context=None):
    rows = turns(script)
    prompt = '''Direct this exact podcast script. Return only JSON {"directions":[{"id":0,"mood":"curiosity","reason":"brief reason grounded in this reply and the preceding turn"}]}.
One entry per turn. Allowed moods: ''' + ', '.join(sorted(MOODS)) + '''.
Do not rewrite or add speech. Use context: interested questions can be curious; a colleague's
useful reframing can earn warmth; an absurd observation can be dry or amused. Let real
usefulness earn delight, stakes earn concern, and disagreement earn pushback. Never force
emotion into every turn or assign delight to harm. Do not use keyword matching. Give Jamie
contextual direction, not automatic neutral. Sponsor reads are neutral. Laughter is optional,
not implied by every amused turn. Preserve each host's identity.
TURNS:\n''' + json.dumps(rows, ensure_ascii=False)
    from crew_direction import CREW_DIRECTION
    prompt = CREW_DIRECTION + '\nDAILY SCENE BRIEFS (planning, not new facts):\n' + json.dumps(scene_context or {}, ensure_ascii=False) + '\n' + prompt
    report = {'scene_context': scene_context or {}, 'script_sha256':hashlib.sha256(script.encode()).hexdigest(),
              'basis':'requested performance, not listening', 'listened':False,
              'directions':[], 'issues':[]}
    try:
        raw = request(prompt)
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
        data = json.loads(raw)
        seen = set()
        for item in data.get('directions', []):
            idx, mood = item.get('id'), item.get('mood')
            if type(idx) is not int or not 0 <= idx < len(rows) or idx in seen or mood not in MOODS:
                continue
            seen.add(idx)
            row = rows[idx]
            report['directions'].append(dict(row, mood='neutral' if sponsor_text(row['text']) else mood,
                                             reason=str(item.get('reason', ''))[:240]))
        if len(seen) != len(rows):
            report['issues'].append(f'Only {len(seen)}/{len(rows)} turns received valid direction; unmatched turns use existing heuristics.')
    except Exception as exc:
        report['issues'].append('Performance plan unavailable; existing heuristics retained: ' + type(exc).__name__)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report

_cache = {'stamp':None, 'rows':[]}
def planned_mood(text, speaker, path='performance_plan.json'):
    if sponsor_text(text):
        return 'neutral'
    p = Path(path)
    try:
        stamp = (str(p.resolve()), p.stat().st_mtime_ns)
        if stamp != _cache['stamp']:
            _cache.update(stamp=stamp, rows=json.loads(p.read_text()).get('directions', []))
    except (OSError, ValueError):
        return None
    body = normalized(text)
    if not body:
        return None
    rows = [r for r in _cache['rows'] if r.get('speaker') == speaker and r.get('mood') in MOODS]
    exact = [r for r in rows if normalized(r.get('text','')) == body]
    if exact:
        moods = {r['mood'] for r in exact}
        return next(iter(moods)) if len(moods) == 1 else None
    # TTS may split a long turn or merge adjacent turns; never match tiny fragments.
    if len(body.split()) >= 6:
        matches = [r for r in rows if len(normalized(r.get('text','')).split()) >= 6 and
                   (body in normalized(r['text']) or normalized(r['text']) in body)]
        moods = {r['mood'] for r in matches if r['mood'] != 'neutral'}
        if len(moods) == 1:
            return next(iter(moods))
    return None

