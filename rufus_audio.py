"""Reusable Rufus entrance. No provider calls; missing audio never stops the show."""
import re
import json
import hashlib
from pathlib import Path


def entrance_due(speaker, text, segment, already_played=False):
    return (not already_played and segment == 3 and speaker == 'ALEX' and
            bool(re.search(r'Rufus,\s*take us (?:on location|to the global desk)\.', str(text), re.I)))


def prepare_entrance(destination, source=None, audit=None):
    from pydub import AudioSegment
    if source is None:
        from specialty_audio.studio_package import load_package, asset_audit
        clips, package = load_package()
        if clips:
            clips['rufus'].export(destination, format='mp3', bitrate='192k').close()
            if audit is not None:
                audit.update(asset_audit(package, 'rufus'))
            return Path(destination)
    default_asset = source is None
    source = Path(source) if source else Path(__file__).parent / 'specialty_audio/library/rufus_entrance.mp3'
    try:
        if default_asset:
            manifest = json.loads((source.parent/'manifest.json').read_text())
            row = next((r for r in manifest.get('sounds', []) if r.get('name') == 'rufus_entrance'), {})
            if (row.get('listening_review') != 'approved' or row.get('enabled_in_daily') is not True
                    or hashlib.sha256(source.read_bytes()).hexdigest() != row.get('sha256')):
                return None
        with source.open("rb") as stream:
            clip = AudioSegment.from_file(stream)[:2000]
        if not len(clip) or clip.dBFS == float('-inf'):
            return None
        clip = clip.apply_gain(-20 - clip.dBFS)
        if clip.max_dBFS > -3:
            clip = clip.apply_gain(-3 - clip.max_dBFS)
        clip.fade_in(20).fade_out(120).export(destination, format='mp3', bitrate='192k').close()
        if audit is not None:
            audit.update(applied=True, asset=source.name, provider='elevenlabs', duration_seconds=len(clip)/1000, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        return Path(destination)
    except Exception as exc:
        # No raw provider/file contents in logs. Keep speech even with damaged media.
        print('[rufus-entrance] unavailable: ' + type(exc).__name__)
        return None
