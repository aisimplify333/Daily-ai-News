"""Bounded candidate commission; never enables daily playback automatically."""
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from pydub import AudioSegment
from specialty_audio import build_studio_package as base
from specialty_audio.build_library import get_account

ROOT = Path('specialty_audio/studio_v2')
BRIEF = ('Original 2.5-second podcast location entrance: soft field-recorder click, '
         'a quick airy spatial sweep, then two warm wooden mallet notes with a dry playful finish. '
         'Suggest stepping out of a studio into a scene. Intimate, crisp on phone speakers, short clean tail. '
         'No horn, brass, siren, alarm, voices, laughter, crowd, cinematic boom or existing melody.')
MUSIC = ('Original understated instrumental podcast bed: warm electric piano, muted plucked bass '
         'and sparse brushed percussion; conversational, curious, lightly mischievous, approximately '
         '94 BPM. Plenty of empty space for speech. No prominent lead melody, vocals, dramatic risers, '
         'brass or comedy stings. Clean edit points and a natural ending. Do not imitate an existing song.')


def music():
    ledger, path = ROOT/'music_commission.json', ROOT/'music_source.mp3'
    if ledger.exists():
        row = json.loads(ledger.read_text())
        if row.get('status') == 'complete' and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == row.get('sha256'):
            return path
        raise RuntimeError('Prior music attempt retained: inspect before any additional spend')
    key = os.environ['AI_EDGE_PODCAST_ELEVENLABS']
    if get_account(key)['remaining'] < 5000:
        raise RuntimeError('Insufficient reserved allowance')
    row = {'status':'attempted','maximum_requests':1,'requested_seconds':15,'brief':MUSIC,'model':'music_v1'}
    base.write(ledger.name,row)
    request = urllib.request.Request('https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128',
        data=json.dumps({'prompt':MUSIC,'music_length_ms':15000,'force_instrumental':True,'model_id':'music_v1'}).encode(),
        headers={'xi-api-key':key,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=180) as response:
        data=response.read(); cost=response.headers.get('character-cost')
    path.write_bytes(data)
    clip=AudioSegment.from_file(path)
    if not clip.rms or not 13000 <= len(clip) <= 17000:
        raise RuntimeError('Music duration or silence check failed')
    row.update(status='complete',sha256=hashlib.sha256(data).hexdigest(),
               accounted_credits=int(cost) if cost and cost.isdigit() else None)
    base.write(ledger.name,row)
    return path


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    base.ROOT=ROOT; base.BRIEF=BRIEF
    manifest={'version':'ai-edge-studio-v2','enabled_in_daily':False,
              'review_basis':'pending candidate review','assets':{}}
    base.write('manifest.json',manifest)
    source=base.commission()
    assets=base.derive(source)
    bed=music()
    base.export('welcome_music',base.level(AudioSegment.from_file(bed),-32).fade_in(180).fade_out(1500),assets)
    manifest['assets']=assets
    base.write('manifest.json',manifest)
    demo=base.demonstrate(assets)
    passed=base.review(demo,assets)
    manifest.update(candidate_review_passed=passed,
                    review_basis='automated audio model plus encoded-master measurements; not human listening')
    base.write('manifest.json',manifest)
    print(json.dumps({'candidate_review_passed':passed,'enabled_in_daily':False}))
    if not passed:
        raise SystemExit('Candidate failed audio review; daily package unchanged')


if __name__=='__main__': main()
