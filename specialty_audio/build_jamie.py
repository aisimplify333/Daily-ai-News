"""One retained ElevenLabs signature, enabled only after automated audio review."""
import hashlib
import json
import os
from pathlib import Path
from pydub import AudioSegment
from specialty_audio import build_studio_package as base
from specialty_audio.review_audio import review

ROOT = Path('specialty_audio/jamie')
BRIEF = ('Original three-second AI discovery podcast jingle: warm bright plucked keys, '
         'a playful rising three-note electronic motif and a soft confident resolved finish. '
         'Curious, delighted, inviting, intimate studio sound with a clean short tail. '
         'No voices, spoken words, laughter, crowd, horns, alarms, harsh hits or existing melody.')


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT/'manifest.json'
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text())
        if saved.get('enabled_in_daily') and (ROOT/'jamie.mp3').exists() and hashlib.sha256((ROOT/'jamie.mp3').read_bytes()).hexdigest() == saved.get('sha256'):
            return
    base.ROOT, base.BRIEF = ROOT, BRIEF
    source = base.commission()  # retained request ledger prevents duplicate spend
    assets = {}
    base.export('jamie', base.level(AudioSegment.from_file(source), -22).fade_in(15).fade_out(180), assets)
    from google import genai
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    verdict = review(client, [{'name':'jamie', 'file':'jamie.mp3', 'prompt':BRIEF}], ROOT, 'sound')['jamie']
    manifest = dict(assets['jamie'], enabled_in_daily=verdict['pass'] is True,
                    provider='elevenlabs', review=verdict,
                    review_basis='automated isolated-audio review; not human listening')
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    if not manifest['enabled_in_daily']:
        raise RuntimeError('Jamie jingle needs revision; rejected asset not enabled')


if __name__ == '__main__':
    main()
