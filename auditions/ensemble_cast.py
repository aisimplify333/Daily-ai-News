"""Bounded voice auditions; never imports production or publishes an episode."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import requests
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

# Fictional rehearsal, not reporting. Same words and edit across every casting.
# speaker, words, acting, xAI wrapper, vocal event
SCENE = [
    ('ALEX', 'Imagine our new AI assistant promises to give everyone Friday afternoon off. I want that to work.', 'Hopeful, conversational, a little excited', '', ''),
    ('JAMIE', 'So do I. Who checks its work while everyone is leaving?', 'Friendly challenge, quick reply', 'emphasis', ''),
    ('RUFUS', 'Apparently the assistant has appointed a committee. We have automated the work and retained the meeting. Splendid.', 'Deadpan British sarcasm, let Splendid land quietly', 'decrease-intensity', ''),
    ('ALEX', 'Oh, come on. One bad meeting does not make the whole idea useless.', 'Brief genuine frustration, affectionate disagreement, rising energy', 'build-intensity', ''),
    ('JAMIE', 'One? Rufus sent a calendar invitation to discuss the calendar invitation.', 'Playful teasing, amused but intelligible', '', 'chuckle'),
    ('RUFUS', 'That was a consultation. Entirely different stationery.', 'Dry British retort, absolutely straight-faced', 'slow', ''),
    ('ALEX', 'All right, you got me. But seriously, what would change your mind?', 'Brief spontaneous laugh, then sincere curiosity', '', 'laugh'),
    ('RUFUS', 'Show me one ordinary task done properly. Count the checking time. If people really get an hour back, I will happily be wrong.', 'British, serious and measured, then warm concession', 'decrease-intensity', ''),
    ('JAMIE', 'There it is. That is what I wanted. An hour with your kids, or a walk before it gets dark. Something you actually feel.', 'Joy turning into sincere warmth, no sales voice', 'soft', ''),
    ('ALEX', 'Exactly. Start small, check the result, and give the time back to the person. No victory parade for a demo.', 'Warm confident payoff, brisk and connected to friends', 'emphasis', ''),
    ('RUFUS', 'Shame. I had already formed the parade committee.', 'British, amused self-deprecation, small genuine chuckle', '', 'chuckle'),
    ('JAMIE', 'Of course you had. Friday afternoon, then. All three of us.', 'Genuine brief laughter, warm invitation to friends', '', 'laugh'),
]
CASTS = {
    'current': {'ALEX': ('openai', 'onyx'), 'RUFUS': ('openai', 'fable')},
    'grok': {'ALEX': ('grok', 'kepler'), 'RUFUS': ('grok', 'leo')},
    'gemini': {'ALEX': ('gemini', 'Charon'), 'RUFUS': ('gemini', 'Iapetus')},
}
OUT = Path('auditions/ensemble_output')

def request_audio(provider, voice, row):
    speaker, text, style, wrapper, event = row
    if provider == 'grok':
        spoken = f'<{wrapper}>{text}</{wrapper}>' if wrapper else text
        if event:
            spoken = f'[{event}] ' + spoken
        url = 'https://api.x.ai/v1/tts'
        headers = {'Authorization': 'Bearer ' + os.environ['XAI_API_KEY']}
        payload = {'text': spoken, 'voice_id': voice, 'language': 'en',
                   'output_format': {'codec': 'mp3', 'sample_rate': 44100, 'bit_rate': 192000}}
        model = 'xai-tts'
    elif provider == 'openai':
        url = 'https://api.openai.com/v1/audio/speech'
        headers = {'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']}
        payload = {'model': 'tts-1-hd', 'voice': voice, 'input': text, 'response_format': 'mp3'}
        model = 'tts-1-hd'
    else:
        model = 'gemini-3.8-flash-tts'
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        headers = {'x-goog-api-key': os.environ['GEMINI_API_KEY']}
        accent = 'Natural British male voice. ' if speaker == 'RUFUS' else 'Natural American male host. '
        spoken = ('<laugh> ' if event else '') + text
        payload = {'contents': [{'role': 'user', 'parts': [{'text': spoken,
                    'speech_metadata': {'style': accent + style + '. Close microphone conversation with friends; no announcer delivery.'}}]}],
                   'generationConfig': {'responseModalities': ['AUDIO'],
                    'speechConfig': {'voiceConfig': {'voice': voice}}}}
    response = requests.post(url, headers=headers, json=payload, timeout=(10, 150))
    if not response.ok:
        # Never log request headers, credential-bearing URLs, or raw provider errors.
        raise RuntimeError(f'{provider} HTTP {response.status_code}')
    if provider == 'gemini':
        parts = response.json()['candidates'][0]['content']['parts']
        inline = next(p['inlineData'] for p in parts if 'inlineData' in p)
        data = base64.b64decode(inline['data'])
        if not data.startswith(b'RIFF'):
            raise RuntimeError('Expected Gemini WAV; refusing to guess sample format')
        clip = AudioSegment.from_file(io.BytesIO(data), format='wav')
    else:
        data = response.content
        clip = AudioSegment.from_file(io.BytesIO(data), format='mp3')
    if not 500 < len(clip) < 60000 or clip.dBFS == float('-inf'):
        raise RuntimeError('Invalid duration or silent audio')
    return clip, {'provider': provider, 'voice': voice, 'model': model,
                  'characters': len(text), 'seconds': len(clip)/1000}

def render(job):
    key, provider, voice, index = job
    try:
        clip, meta = request_audio(provider, voice, SCENE[index])
        path = OUT / f'{key}.wav'
        clip.export(path, format='wav').close()
        return key, {'status': 'ok', 'file': path.name, **meta}
    except Exception as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        return key, {'status': 'failed', 'provider': provider, 'voice': voice, 'error': message}

def main():
    if os.getenv('GITHUB_RUN_ATTEMPT', '1') != '1':
        raise RuntimeError('Paid reruns disabled; review the preserved artifact first')
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i, row in enumerate(SCENE):
        if row[0] == 'JAMIE':
            jobs.append((f'jamie_{i}', 'grok', 'ursa', i))
        else:
            for name, cast in CASTS.items():
                provider, voice = cast[row[0]]
                jobs.append((f'{name}_{i}', provider, voice, i))
    assert len(jobs) == 28
    manifest = {'hypothetical': True, 'listened': False, 'production_changed': False,
                'maximum_requests': 28, 'retry_count': 0, 'takes': {}, 'mixes': {},
                'limitation': 'Compares complete voice-and-direction packages, not isolated models. Baseline has no acting tags. Gemini chuckles use its documented laugh event. All versions use identical Jamie audio and gaps.'}
    (OUT/'TRANSCRIPT.txt').write_text('\n'.join(f'{r[0]}: {r[1]} [Direction: {r[2]}]' for r in SCENE))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for key, result in pool.map(render, jobs):
            manifest['takes'][key] = result
            (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2))
    # Single-role replacements isolate each casting decision; no extra API calls.
    mixes = {'A_current': ('current','current'), 'B_grok': ('grok','grok'),
             'C_gemini': ('gemini','gemini'), 'D_grok_alex': ('grok','current'),
             'E_grok_rufus': ('current','grok'), 'F_gemini_alex': ('gemini','current'),
             'G_gemini_rufus': ('current','gemini')}
    for name, (alex, rufus) in mixes.items():
        keys = [f'jamie_{i}' if r[0]=='JAMIE' else f'{alex if r[0]=="ALEX" else rufus}_{i}' for i,r in enumerate(SCENE)]
        if any(manifest['takes'][k]['status'] != 'ok' for k in keys):
            manifest['mixes'][name] = {'status': 'blocked', 'reason': 'Missing take; no substitute voice'}
            continue
        mix = AudioSegment.empty()
        for key in keys:
            clip = AudioSegment.from_wav(OUT/manifest['takes'][key]['file'])
            start = max(0, detect_leading_silence(clip, silence_threshold=-45)-35)
            end = max(0, detect_leading_silence(clip.reverse(), silence_threshold=-45)-60)
            clip = clip[start:len(clip)-end if end else len(clip)]
            clip = clip.apply_gain(-20 - clip.dBFS)
            mix += clip + AudioSegment.silent(duration=100)
        wav = OUT/f'{name}.wav'
        mix.export(wav, format='wav').close()
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(wav),'-af',
                        'loudnorm=I=-16:TP=-1.5:LRA=11','-b:a','192k',str(OUT/f'{name}.mp3')],check=True)
        manifest['mixes'][name] = {'status': 'ok', 'seconds': len(mix)/1000}
    (OUT/'LISTEN_FIRST.txt').write_text('Start with A_current, then E_grok_rufus and G_gemini_rufus. Compare D/F for Alex, then B/C for both. Jamie takes are identical. Score believable tension, British accent, comic timing, laughter, warmth, and clarity 1-5. Reject spoken tags, accent drift, forced laughter or lost words. No winner has been selected. Fictional rehearsal only.')
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest['mixes']))
    if any(t['status'] != 'ok' for t in manifest['takes'].values()):
        raise SystemExit('Some candidates failed; inspect partial artifact')

if __name__ == '__main__':
    main()
