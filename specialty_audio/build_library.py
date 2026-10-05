"""One-time bounded specialty production; never called by the daily episode job."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request

from pydub import AudioSegment

ROOT = Path('specialty_audio/library')
MODEL = 'eleven_text_to_sound_v2'
MAX_CREDITS = 10000
# A conservative reservation per short SFX request, not a provider price quote.
RESERVATION = 1000
BRIEFS = [
    ('conference', 10, 'Quiet technology conference foyer, distant indistinct crowd murmur, soft footsteps, spacious interior. No intelligible words, announcements, applause or music.'),
    ('factory', 10, 'Quiet modern factory floor ambience, gentle steady mechanical hum, occasional distant machine movement. No alarms, impacts, voices or music.'),
    ('office', 10, 'Subtle small office ambience, quiet ventilation, sparse soft keyboard taps and paper movement. No voices, ringing phones or music.'),
    ('server_room', 10, 'Soft steady server room ventilation, layered low fan hum, clean restrained texture. No beeps, alarms, voices or music.'),
    ('city', 10, 'Quiet city sidewalk atmosphere, distant traffic and light footsteps, calm daytime exterior. No horns, sirens, intelligible voices or music.'),
    ('legislative_hall', 10, 'Quiet large civic building hallway, restrained room tone, occasional distant footsteps with a little natural reverberation. No speeches, voices or music.'),
    ('edge_signature', 3, 'Original short audio logo: three crisp warm electronic tones rising with a subtle soft percussive tick, clean confident final resolution. Restrained news podcast identity, no voice, no cinematic boom, no recognizable existing melody.'),
    ('rufus_entrance', 2, 'Short restrained sonic punctuation: a light mechanical click followed by a warm dry resonant pluck, curious and witty, clean ending. No voice, laughter, fanfare or recognizable melody.'),
]


def get_account(key):
    req = urllib.request.Request('https://api.elevenlabs.io/v1/user/subscription',
                                 headers={'xi-api-key': key})
    with urllib.request.urlopen(req, timeout=30) as response:
        account = json.load(response)
    used, limit = account.get('character_count'), account.get('character_limit')
    if type(used) is not int or type(limit) is not int:
        raise RuntimeError('Cannot determine remaining allowance')
    if account.get('tier') == 'free' or account.get('status') != 'active':
        raise RuntimeError('Active paid account required')
    return {'remaining': max(0, limit - used), 'reset': account.get('next_character_count_reset_unix')}


def save(report):
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'manifest.json').write_text(json.dumps(report, indent=2))


def build_sounds(key, report):
    before = get_account(key)
    report['allowance_before'] = before
    spent = report['accounted_credits']
    for name, seconds, prompt in BRIEFS:
        path = ROOT / (name + '.mp3')
        prior = next((x for x in report['sounds'] if x['name'] == name), None)
        if path.exists() and prior and prior.get('status') == 'generated':
            if hashlib.sha256(path.read_bytes()).hexdigest() == prior.get('sha256'):
                continue
            raise RuntimeError('Saved asset checksum changed')
        if spent + RESERVATION > MAX_CREDITS or get_account(key)['remaining'] < RESERVATION:
            raise RuntimeError('Credit reservation unavailable; preserved completed assets')
        # Save the attempt before POST. No automatic retries after uncertain results.
        if prior:
            raise RuntimeError('Prior incomplete attempt requires inspection; refusing duplicate spend')
        row = {'name': name, 'status': 'attempted', 'prompt': prompt, 'seconds_requested': seconds}
        report['sounds'].append(row)
        save(report)
        body = json.dumps({'text': prompt, 'duration_seconds': seconds,
                           'prompt_influence': 0.4, 'model_id': MODEL}).encode()
        req = urllib.request.Request('https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128',
            data=body, headers={'xi-api-key': key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read()
            charge = response.headers.get('character-cost')
        path.write_bytes(data)
        clip = AudioSegment.from_file(path)
        if not seconds * 700 <= len(clip) <= (seconds + 2) * 1000 or clip.rms == 0:
            raise RuntimeError('Generated audio failed duration/silence check')
        charge = int(charge) if charge and charge.isdigit() else RESERVATION
        spent += charge
        row.update(status='generated', file=path.name, seconds=len(clip)/1000,
                   accounted_credits=charge, sha256=hashlib.sha256(data).hexdigest(),
                   listening_review='pending', enabled_in_daily=False)
        report['accounted_credits'] = spent
        save(report)
    report['allowance_after'] = get_account(key)


def build_promos(report):
    """Preserve real turn timing and cast voices; use existing published clip + CTA."""
    candidates = sorted(Path('episode_audio').glob('clip_????-??-??.mp3'), reverse=True)
    for clip_path in candidates:
        if len(report['promos']) >= 3:
            break
        date = clip_path.stem.removeprefix('clip_')
        output = ROOT / f'promo_{date}.mp3'
        if any(x['date'] == date for x in report['promos']):
            continue
        timeline_path = clip_path.with_name(f'podcast_{date}.timeline.json')
        master_path = clip_path.with_name(f'podcast_{date}.mp3')
        if not timeline_path.exists() or not master_path.exists():
            continue
        timeline = json.loads(timeline_path.read_text())
        follow = next((x for x in timeline.get('rows', []) if x.get('kind') == 'speech'
                       and 'follow the ai edge now' in x.get('text', '').lower()), None)
        if not follow:
            continue
        excerpt = AudioSegment.from_file(clip_path)
        if not 20000 <= len(excerpt) <= 45000:
            continue
        master = AudioSegment.from_file(master_path)
        cta = master[round(follow['start'] * 1000):round(follow['end'] * 1000)]
        if not 500 <= len(cta) <= 15000:
            continue
        promo = excerpt.fade_in(30).fade_out(80) + AudioSegment.silent(180) + cta
        signature = ROOT / 'edge_signature.mp3'
        if signature.exists():
            sound = AudioSegment.from_file(signature)[:3000]
            sound = sound.apply_gain(-23 - sound.dBFS).fade_out(200)
            promo += sound
        promo.export(output, format='mp3', bitrate='192k').close()
        report['promos'].append({'date': date, 'file': output.name, 'seconds': len(promo)/1000,
            'source_clip': str(clip_path), 'cta_range': [follow['start'], follow['end']],
            'listening_review': 'pending', 'social_publication': 'not_posted'})
        save(report)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = ROOT / 'manifest.json'
    report = json.loads(manifest.read_text()) if manifest.exists() else {
        'version': 1, 'sounds': [], 'promos': [], 'accounted_credits': 0,
        'daily_integration': 'disabled_pending_audio_review', 'errors': []}
    key = os.getenv('AI_EDGE_PODCAST_ELEVENLABS', '').strip()
    try:
        if not key:
            raise RuntimeError('Expected ElevenLabs secret is missing')
        build_sounds(key, report)
    except Exception as error:
        # Never publish raw API error bodies, credentials or account details.
        report['errors'].append('Sound generation stopped: ' + type(error).__name__)
    try:
        build_promos(report)
    except Exception as error:
        report['errors'].append('Promo assembly stopped: ' + type(error).__name__)
    save(report)
    print(json.dumps({'sounds': len([x for x in report['sounds'] if x['status']=='generated']),
                      'promos': len(report['promos']), 'errors': report['errors'],
                      'accounted_credits': report['accounted_credits']}))
    if report['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
