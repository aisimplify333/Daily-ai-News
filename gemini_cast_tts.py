"""Gemini 3.8 delivery: separate acting from verbatim text; bounded requests."""
import base64
import json
import os
import re
import threading
import time
import requests

_lock = threading.Lock()
_last_call = 0.0

class GeminiTTSHTTPError(RuntimeError):
    def __init__(self, response):
        self.status_code = response.status_code
        self.retry_after = 0.0
        self.quota_ids = []
        try:
            error = response.json().get('error', {})
            for detail in error.get('details', []):
                if detail.get('@type', '').endswith('RetryInfo'):
                    self.retry_after = max(self.retry_after, float(detail.get('retryDelay', '0s').rstrip('s')))
                if detail.get('@type', '').endswith('QuotaFailure'):
                    for violation in detail.get('violations', []):
                        # Keep metric identifiers, never project IDs, raw messages or credentials.
                        value = violation.get('quotaId', '')
                        if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,180}', value):
                            self.quota_ids.append(value)
        except (ValueError, TypeError, AttributeError):
            pass
        try:
            self.retry_after = max(self.retry_after, float(response.headers.get('Retry-After', '0')))
        except (ValueError, TypeError, AttributeError):
            pass
        self.daily_exhausted = any('perday' in q.lower() for q in self.quota_ids)
        self.retryable = self.status_code in (429, 500, 502, 503, 504) and not self.daily_exhausted
        super().__init__('Gemini TTS ' + json.dumps({
            'http_status': self.status_code, 'quota_ids': self.quota_ids,
            'retry_after_seconds': self.retry_after, 'daily_exhausted': self.daily_exhausted}))

def payload(text, speaker, mood, voice, note):
    persona = {
        'ALEX': 'American male host. Resonant lower register, grounded gravitas, warm and conversational. Brisk responsive timing; never a slow announcer.',
        'RUFUS': 'Distinct contemporary southern English male voice with consistent non-rhotic British pronunciation. Lighter, drier mid-register than the American bass of Alex; precise consonants and clipped sentence endings. Use brisk conversational phrasing, no languid drawl or lowered announcer register. Underplay dry wit: let the final word land, without explaining the joke. Affectionate mock formality, occasional genuine warmth. Keep this English accent in every sentence, including laughter and serious facts.',
    }.get(speaker, 'Warm conversational co-host.')
    sponsor = 'the ledger' in text.lower() or 't-h-e-l-e-d-g-r' in text.lower()
    spoken = text
    explicit_laugh = re.match(r'^(?:ha|hah|heh)[.!]+\s*', text, re.I)
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
        gap = max(0, float(os.getenv('GEMINI_TTS_MIN_INTERVAL', '20')) - (time.monotonic()-_last_call))
        time.sleep(gap)
        _last_call = time.monotonic()
        response = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
            headers={'x-goog-api-key': api_key},
            json=payload(text, speaker, mood, voice, note), timeout=(10, 180))
    if not response.ok:
        raise GeminiTTSHTTPError(response)
    parts = response.json()['candidates'][0]['content']['parts']
    inline = next(p['inlineData'] for p in parts if 'inlineData' in p)
    audio = base64.b64decode(inline['data'])
    if len(audio) < 500 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE':
        raise RuntimeError('Gemini 3.8 did not return a valid WAV container')
    path.write_bytes(audio)
