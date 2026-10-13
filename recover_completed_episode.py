"""Restore an already-rendered, reviewed artifact; never invoke generation/TTS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET


def restore(source, date, expected_sha256, root=Path('.')):
    source, root = Path(source), Path(root)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('Invalid episode date')
    audio = source / f'podcast_{date}.mp3'
    if hashlib.sha256(audio.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('Completed master does not match approved recovery hash')
    for filename, field in [('final_acceptance_report.json','pass'),
                            ('grounded_fact_check.json','pass'),
                            ('production_delivery_report.json','passed')]:
        if json.loads((source/filename).read_text()).get(field) is not True:
            raise ValueError('Recovery review failed: ' + filename)
    recovered = ET.parse(source/'feed.xml').getroot().find('channel')
    suffix = f'/podcast_{date}.mp3'
    matches = [i for i in recovered.findall('item') if i.find('enclosure') is not None
               and i.find('enclosure').get('url','').endswith(suffix)]
    if len(matches) != 1:
        raise ValueError('Recovery feed must contain one matching episode')
    feed = ET.parse(root/'feed.xml'); channel = feed.getroot().find('channel')
    if any(i.find('enclosure') is not None and i.find('enclosure').get('url','').endswith(suffix)
           for i in channel.findall('item')):
        raise ValueError('Episode already exists; do not overwrite it')
    for file in source.iterdir():
        if not file.is_file() or file.name == 'feed.xml':
            continue
        if file.name.startswith((f'podcast_{date}.', f'clip_{date}.')):
            target = root/'episode_audio'/file.name
        elif file.suffix == '.json' or file.name.startswith((f'script_{date}', f'script_pre_tts_{date}', f'script_fact_candidate_{date}')):
            target = root/file.name
        else:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    first = next((n for n, child in enumerate(channel) if child.tag == 'item'), len(channel))
    channel.insert(first, matches[0])
    feed.write(root/'feed.xml', encoding='utf-8', xml_declaration=True)
    (root/'completed_recovery_report.json').write_text(json.dumps({
        'date':date,'audio_sha256':expected_sha256,'new_tts_calls':0,
        'basis':'Restored completed artifact; original editorial and fact reports preserved'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    restore(args.source, args.date, args.sha256)
