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

def build_plan(script, request, path='performance_plan.json', scene_context=None,
               fallback_request=None, batch_size=24):
    rows = turns(script)
    prompt = '''Direct this exact podcast script. Return only JSON {"directions":[{"id":0,"mood":"curiosity","reason":"brief reason grounded in this reply and the preceding turn"}]}.
One entry per turn. Allowed moods: ''' + ', '.join(sorted(MOODS)) + '''.
Do not rewrite or add speech. Use context: interested questions can be curious; a colleague's
useful reframing can earn warmth; an absurd observation can be dry or amused. Let real
usefulness earn delight, stakes earn concern, and disagreement earn pushback. Never force
emotion into every turn or assign delight to harm. Do not use keyword matching. Give Jamie
contextual direction, not automatic neutral. Sponsor reads are neutral. Laughter is optional,
not implied by every amused turn. Preserve each host's identity.
Return a short reason (at most 12 words). IDs are global: do not renumber.
Direct only TARGET TURNS; neighboring turns are context, not output.
'''
    from crew_direction import CREW_DIRECTION
    prompt = CREW_DIRECTION + '\nDAILY SCENE BRIEFS (planning, not new facts):\n' + json.dumps(scene_context or {}, ensure_ascii=False) + '\n' + prompt
    report = {'scene_context': scene_context or {}, 'script_sha256':hashlib.sha256(script.encode()).hexdigest(),
              'basis':'requested performance, not listening', 'listened':False,
              'directions':[], 'issues':[]}
    directed = {}
    report['requested_calls'] = 0
    report['attempts'] = []
    batch_size = max(1, min(32, int(batch_size)))
    for start in range(0, len(rows), batch_size):
        target = rows[start:start + batch_size]
        pending = {row['id'] for row in target}
        context = rows[max(0, start - 2):start + batch_size + 2]
        # At most two attempts per small batch; preserve valid entries from attempt one.
        for attempt in range(2):
            if not pending:
                break
            request_fn = fallback_request if attempt and fallback_request else request
            batch_prompt = prompt + '\nCONTEXT TURNS:\n' + json.dumps(context, ensure_ascii=False)
            batch_prompt += '\nTARGET TURNS:\n' + json.dumps(
                [row for row in target if row['id'] in pending], ensure_ascii=False)
            record = {'start': start, 'attempt': attempt + 1,
                      'provider': 'fallback' if attempt and fallback_request else 'primary'}
            report['requested_calls'] += 1
            try:
                raw = request_fn(batch_prompt)
                raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
                data = json.loads(raw)
                if not isinstance(data, dict) or not isinstance(data.get('directions'), list):
                    raise ValueError('Expected directions list')
                candidates = {}
                duplicates = set()
                for item in data['directions']:
                    if not isinstance(item, dict):
                        continue
                    idx, mood = item.get('id'), item.get('mood')
                    if type(idx) is not int or idx not in pending or mood not in MOODS:
                        continue
                    if idx in candidates:
                        duplicates.add(idx)
                    candidates[idx] = item
                for idx, item in candidates.items():
                    if idx in duplicates:
                        continue
                    row = rows[idx]
                    directed[idx] = dict(row, mood='neutral' if sponsor_text(row['text']) else item['mood'],
                                         reason=str(item.get('reason', ''))[:240])
                    pending.remove(idx)
            except Exception as exc:
                record['error_type'] = type(exc).__name__
            record['missing_ids'] = sorted(pending)
            report['attempts'].append(record)
    report['directions'] = [directed[idx] for idx in sorted(directed)]
    report['complete'] = bool(rows) and len(directed) == len(rows)
    report['status'] = 'complete' if report['complete'] else 'incomplete'
    if not report['complete']:
        report['issues'].append(f'Only {len(directed)}/{len(rows)} turns received valid direction after bounded recovery.')
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

