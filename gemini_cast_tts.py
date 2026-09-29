"""Gemini 3.8 delivery: separate acting from verbatim text; bounded requests."""
import base64
import os
import re
import threading
import time
import requests

_lock = threading.Lock()
_last_call = 0.0

def payload(text, speaker, mood, voice, note):
    persona = {
        'ALEX': 'American male host. Resonant lower register, grounded gravitas, warm and conversational. Brisk responsive timing; never a slow announcer.',
        'RUFUS': 'Contemporary British male. Crisp, brisk conversational pace, quick dry wit and affectionate sarcasm. Short pauses, no languid drawl. Keep the accent through laughter and serious moments.',
    }.get(speaker, 'Warm conversational co-host.')
    sponsor = 'the ledger' in text.lower() or 't-h-e-l-e-d-g-r' in text.lower()
    spoken = text
    explicit_laugh = re.match(r'^(?:ha|hah|heh)[.!]+\\s*', text, re.I)
    if mood == 'amused' and explicit_laugh and not sponsor:
        spoken = '<laugh> ' + text[explicit_laugh.end():]
    persona += (' Respond as a colleague in an ongoing exchange. Vary emphasis and pace within the line '
                'as its meaning changes; keep short reactions quick and serious conclusions grounded. '
                'A brief laugh only when explicitly cued, then recover into clear speech. '
                'Keep the established vocal identity; avoid constant intensity or a sales cadence.')
    style = persona + ' ' + ( 'Sincere, clear sponsor read; no laughter.' if sponsor else note)
    return {'contents': [{'role': 'user', 'parts': [{'text': spoken, 'speech_metadata': {'style': style}}]}],
            'generationConfig': {'responseModalities': ['AUDIO'],
                                 'speechConfig': {'voiceConfig': {'voice': voice}}}}

def render_wav(text, speaker, mood, voice, model, note, path, api_key):
    global _last_call
    # Production callers are sequential, but keep pacing safe if that changes.
    with _lock:
        gap = max(0, float(os.getenv('GEMINI_TTS_MIN_INTERVAL', '6')) - (time.monotonic()-_last_call))
        time.sleep(gap)
        _last_call = time.monotonic()
        response = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
            headers={'x-goog-api-key': api_key},
            json=payload(text, speaker, mood, voice, note), timeout=(10, 180))
    if not response.ok:
        if response.status_code == 429:
            time.sleep(20)
        raise RuntimeError(f'Gemini TTS HTTP {response.status_code}')
    parts = response.json()['candidates'][0]['content']['parts']
    inline = next(p['inlineData'] for p in parts if 'inlineData' in p)
    audio = base64.b64decode(inline['data'])
    if len(audio) < 500 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE':
        raise RuntimeError('Gemini 3.8 did not return a valid WAV container')
    path.write_bytes(audio)
