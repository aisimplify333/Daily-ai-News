"""Bounded, retained specialty auditions. Never changes the production cast."""
import hashlib
import html
import io
import json
import os
from pathlib import Path
import urllib.request
from pydub import AudioSegment
from specialty_audio.inspect_account import get_json

ROOT = Path('specialty_audio/auditions')
CAP = 10000
TRAILER = "Your next meeting does not need another AI headline. It needs a point of view. Join Alex, Jamie and Rufus for what changed, who wins, and what you can do next. A little argument. A little British understatement. The AI Edge. Follow the show."
RUFUS = "Picture a boardroom where the demonstration has gone perfectly. Naturally, nobody has tried it with an actual customer yet. The useful question is not whether the machine can impress the room. It is whether it can help the person who has to do the work on Monday."
SPONSOR = "Too many AI headlines. Too little time to work out what matters. The Ledger brings five focused briefings to the decisions facing you and your team. Find The Ledger in The AI Edge show notes."


def select_voices(catalog):
    # Use available provider voices; never clone or modify anyone's voice.
    voices = sorted((v for v in catalog if v.get('category') == 'premade' or
                     (v.get('category') == 'professional' and (v.get('sharing') or {}).get('status') == 'enabled')), 
                    key=lambda v: (v.get('name', ''), v['voice_id']))
    british = [v for v in voices if v.get('labels', {}).get('gender') == 'male'
               and any(k in v.get('labels', {}).get('accent', '').lower()
                       for k in ('british', 'english'))]
    if len(voices) < 4 or len(british) < 2:
        raise RuntimeError('Insufficient verified catalog voices for the requested comparison')
    # Compare four different narrators, including male and female choices.
    female = [v for v in voices if v.get('labels', {}).get('gender') == 'female']
    male = [v for v in voices if v.get('labels', {}).get('gender') == 'male']
    narrators = (female[:2] + male[:2]) if len(female) >= 2 and len(male) >= 2 else voices[:4]
    return narrators, (british[:3] if len(british) >= 3 else british[:2]+british[:1])


def save(report):
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT/'manifest.json').write_text(json.dumps(report, indent=2))


def render(key, report, name, text, voice, stability=0.5):
    payload = {'text': text, 'model_id': 'eleven_v3',
               'voice_settings': {'stability': stability}}
    identity = hashlib.sha256(json.dumps([payload, voice['voice_id']], sort_keys=True).encode()).hexdigest()
    existing = next((r for r in report['takes'] if r['name'] == name), None)
    path = ROOT/(name+'.mp3')
    if existing:
        if (existing['status'] == 'complete' and existing['request_sha256'] == identity
                and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == existing['sha256']):
            return path
        raise RuntimeError('Prior incomplete or changed take: inspect before spending again')
    reserve = max(500, len(text)*2)
    if report['reserved_credits'] + reserve > CAP:
        raise RuntimeError('Audition budget reached')
    account = get_json('/v1/user/subscription', key)
    if account.get('character_limit', 0) - account.get('character_count', 0) < reserve:
        raise RuntimeError('Insufficient included allowance')
    row = {'name': name, 'status': 'attempted', 'text': text,
           'voice_id': voice['voice_id'], 'voice_name': voice.get('name'),
           'voice_labels': voice.get('labels', {}), 'model': 'eleven_v3',
           'stability': stability, 'request_sha256': identity,
           'listening_review': 'pending', 'approved_for_production': False}
    report['takes'].append(row)
    report['reserved_credits'] += reserve
    save(report)  # persist intent before a paid POST; no automatic POST retries
    req = urllib.request.Request('https://api.elevenlabs.io/v1/text-to-speech/'+voice['voice_id']+'?output_format=mp3_44100_128',
          data=json.dumps(payload).encode(), headers={'xi-api-key': key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as response:
        data = response.read()
        charge = response.headers.get('character-cost')
    raw = ROOT/(name+'.raw.mp3')
    raw.write_bytes(data)
    clip = AudioSegment.from_file(io.BytesIO(data), format='mp3')
    if not 1000 < len(clip) < 120000 or not clip.rms:
        raise RuntimeError('Audio duration or silence check failed; raw take retained')
    clip = clip.apply_gain(min(-19-clip.dBFS, -1-clip.max_dBFS))
    clip.export(path, format='mp3', bitrate='192k').close()
    row.update(status='complete', file=path.name, raw_file=raw.name,
               seconds=len(clip)/1000, peak_dbfs=clip.max_dBFS,
               sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               provider_reported_credits=int(charge) if charge and charge.isdigit() else None)
    save(report)
    return path


def make_page(report):
    cards = []
    for row in report['takes']:
        if row['status'] != 'complete' or row['name'].startswith('war_room_'):
            continue
        cards.append('<article><h2>'+html.escape(row['name'])+'</h2><audio controls preload="none" src="'+row['file']+'"></audio><p>'+html.escape(row['text'])+'</p></article>')
    if report.get('war_room'):
        cards.append('<article><h2>Fictional war room — complete exchange</h2><audio controls preload="none" src="war_room.mp3"></audio><p>A short performance comparison, not actual news or listener testimony.</p></article>')
    page = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>The AI Edge — specialty auditions</title><style>body{font:18px system-ui;background:#101827;color:#edf4ff;max-width:850px;margin:40px auto;padding:20px}article{padding:24px;background:#1b2940;margin:20px 0;border-radius:12px}audio{width:100%}p{line-height:1.6}</style><h1>The AI Edge: specialty auditions</h1><p>These are candidates, not changes to the daily cast. Compare matching scripts on headphones and a phone speaker. Judge clarity, warmth, dry wit and whether the performance sounds like a person talking. Voice identities and settings are retained in manifest.json. No listening winner has been assigned.</p>'+''.join(cards)
    (ROOT/'index.html').write_text(page)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    p = ROOT/'manifest.json'
    report = json.loads(p.read_text()) if p.exists() else {'takes': [], 'reserved_credits': 0, 'daily_cast_changed': False}
    report.pop('diagnostic', None)
    key = os.environ['AI_EDGE_PODCAST_ELEVENLABS']
    try:
        catalog = get_json('/v2/voices?page_size=100&include_custom_rates=false', key)
        report['catalog_categories'] = sorted(set(str(v.get('category')) for v in catalog.get('voices', [])))
        report['default_voice_catalog'] = [{'voice_id':v['voice_id'], 'name':v.get('name'), 'labels':v.get('labels', {})} for v in catalog.get('voices', []) if v.get('category') == 'premade' or (v.get('category') == 'professional' and (v.get('sharing') or {}).get('status') == 'enabled')]
        narrators, british = select_voices(catalog.get('voices', []))
        report['rufus_comparison_note'] = 'Three performance candidates; if only two British male catalog voices are available, candidate 3 repeats candidate 1 at creative stability.'
        for i, voice in enumerate(narrators, 1):
            render(key, report, f'trailer_{i}', TRAILER, voice)
        for i, voice in enumerate(british, 1):
            render(key, report, f'rufus_candidate_{i}', RUFUS, voice,
                   0.0 if i == 3 and voice['voice_id'] == british[0]['voice_id'] else 0.5)
        for i, (tag, stability) in enumerate([('[warmly] ', 0.5), ('[confident] ', 0.5), ('[conversational] ', 0.0)], 1):
            render(key, report, f'sponsor_treatment_{i}', tag+SPONSOR, narrators[0], stability)
        render(key, report, 'fictional_voicemail', 'This is a fictional listener scenario. Hi, team. My boss asked me to put AI into our workflow. I asked which problem we were solving. We now have a meeting to decide what the meeting should be about. What should I ask first?', narrators[1])
        turns = [('A', narrators[0], 'Fictional war room. The demo worked. What would make you trust this with a real customer?'),
                 ('B', narrators[1], 'Give it the awkward case. The refund that does not fit the form. That is where the time goes.'),
                 ('C', british[0], 'An excellent proposal. Testing the thing we intend to use it for. Radical, but I am prepared to support it.'),
                 ('D', narrators[0], 'One workflow. One awkward case. A person who can take over. Now we have a useful test.')]
        clips = [AudioSegment.from_file(render(key, report, 'war_room_'+n, t, v)) for n,v,t in turns]
        total = clips[0]
        for clip in clips[1:]: total += AudioSegment.silent(140)+clip
        total.export(ROOT/'war_room.mp3', format='mp3', bitrate='192k').close()
        report['war_room'] = {'file': 'war_room.mp3', 'fictional': True, 'listening_review': 'pending'}
        report['status'] = 'generated_pending_listening'
    except Exception as exc:
        report['status'] = 'blocked_'+type(exc).__name__
        if isinstance(exc, RuntimeError): report['diagnostic'] = str(exc)[:300]
        raise
    finally:
        save(report)
        make_page(report)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Audition stopped: '+type(exc).__name__+'; inspect retained manifest. No automatic paid retry.') from None
