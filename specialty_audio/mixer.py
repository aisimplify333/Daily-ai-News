"""Optional reviewed atmosphere under one imagined Rufus entrance. No API calls."""
import hashlib
import json
import re
from pathlib import Path


def choose_bed(text):
    if not re.search(r'\b(?:picture|imagine)\b', text, re.I):
        return None
    for name, pattern in [('conference', r'conference|convention'),
                          ('factory', r'factory|manufacturing floor'),
                          ('server_room', r'server room|data cent'),
                          ('legislative_hall', r'legislative hall|parliament|congressional hall'),
                          ('office', r'office|boardroom|conference room'),
                          ('city', r'sidewalk|street corner')]:
        if re.search(pattern, text, re.I):
            return name
    return None


def mix_reviewed_bed(voice_path, destination, text, root=None):
    """No approved match/corrupt asset: retain exact speech. Never lengthen it."""
    from pydub import AudioSegment
    root = Path(root) if root else Path(__file__).parent/'library'
    try:
        name = choose_bed(text)
        if not name:
            return None
        manifest = json.loads((root/'manifest.json').read_text())
        row = next((r for r in manifest.get('sounds', []) if r.get('name') == name
                    and r.get('listening_review') == 'approved'
                    and r.get('enabled_in_daily') is True), None)
        if not row or Path(row['file']).name != row['file']:
            return None
        data = (root/row['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row.get('sha256'):
            return None
        voice = AudioSegment.from_file(voice_path)
        bed = AudioSegment.from_file(root/row['file'])[:min(5000, len(voice))]
        if not bed.rms or not voice.rms:
            return None
        bed = bed.apply_gain(min(-34, voice.dBFS-16)-bed.dBFS).fade_in(120).fade_out(min(1200,len(bed)))
        mixed = voice.overlay(bed)
        if mixed.max_dBFS > -1:
            mixed = mixed.apply_gain(-1-mixed.max_dBFS)
        mixed.export(destination, format='mp3', bitrate='192k').close()
        return Path(destination)
    except Exception:  # Optional media must never block the spoken show.
        return None
