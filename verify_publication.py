"""Verify listener-visible delivery independently of a generation/push success."""
import argparse
import datetime as dt
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

BASE = 'https://aisimplify333.github.io/Daily-ai-News'


def fetch(url, headers=None, limit=2_000_000):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', **(headers or {})})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, response.headers, response.read(limit)


def check(date, getter=fetch):
    _, _, feed = getter(BASE + '/feed.xml')
    root = ET.fromstring(feed)
    expected = f'podcast_{date}.mp3'
    matches = [item for item in root.findall('.//item')
               if (item.find('enclosure') is not None and
                   urlparse(item.find('enclosure').get('url', '')).path.endswith('/' + expected))]
    if len(matches) != 1:
        raise ValueError('Expected exactly one dated episode in the public feed')
    item = matches[0]
    enclosure = item.find('enclosure')
    url = enclosure.get('url', '')
    if urlparse(url).scheme != 'https':
        raise ValueError('Audio URL must use HTTPS')
    status, headers, audio = getter(url, {'Range': 'bytes=0-4095'}, 4096)
    if status not in (200, 206) or len(audio) < 128:
        raise ValueError('Public audio is missing or empty')
    if not (audio.startswith(b'ID3') or (audio[0] == 255 and audio[1] & 224 == 224)):
        raise ValueError('Public audio does not have an MP3 header')
    status, _, page = getter(BASE + f'/episodes/{date}/')
    if status != 200 or expected.encode() not in page:
        raise ValueError('Episode page does not link the dated audio')
    return {'pass': True, 'date': date, 'title': item.findtext('title'),
            'audio_url': url, 'page_url': BASE + f'/episodes/{date}/',
            'pub_date': item.findtext('pubDate'),
            'verified_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'listening_review': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    parser.add_argument('--attempts', type=int, default=1)
    parser.add_argument('--interval', type=float, default=20)
    args = parser.parse_args()
    for attempt in range(max(1, args.attempts)):
        try:
            result = check(args.date)
        except Exception as error:
            result = {'pass': False, 'date': args.date, 'error_type': type(error).__name__,
                      'reason': str(error)[:250], 'attempt': attempt + 1}
        Path('public_delivery_report.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
        if result['pass']:
            return 0
        if attempt + 1 < args.attempts:
            time.sleep(max(0, min(args.interval, 60)))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
