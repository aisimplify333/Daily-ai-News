"""Optional reviewed atmosphere under one imagined Rufus entrance. No API calls."""
import hashlib
import json
import re
from pathlib import Path


def choose_bed(text):
    if not re.search(r'\b(?:picture|imagine)\b', text, re.I):
        return None
    for name, pattern in [('office', r'\b(?:office|boardroom|risk committee meeting|board meeting|conference room|software company|(?:large )?tech company|developer team)\b'),
                          ('conference', r'\b(?:conference|convention)\b'),
                          ('factory', r'factory|manufacturing floor'),
                          ('server_room', r'server room|data cent'),
                          ('legislative_hall', r'legislative hall|parliament|congressional hall'),
                          ('city', r'sidewalk|street corner|wall street')]:
        if re.search(pattern, text, re.I):
            return name
    return None


def mix_reviewed_bed(voice_path, destination, text, root=None, audit=None):
    """No approved match/corrupt asset: retain exact speech. Never lengthen it."""
    from pydub import AudioSegment
    root = Path(root) if root else Path(__file__).parent/'library'
    if audit is not None:
        audit.update(applied=False, reason="no_approved_matching_asset")
    try:
        name = choose_bed(text)
        if not name:
            return None
        manifest = json.loads((root/'manifest.json').read_text())
        row = next((r for r in manifest.get('sounds', []) if r.get('name') in (name, name+'_v2')
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
        if audit is not None:
            audit.update(applied=True, reason="mixed", asset=row['file'], sha256=row['sha256'],
                         provider="elevenlabs", duration_seconds=len(bed)/1000,
                         bed_dbfs=round(bed.dBFS, 2))
        return Path(destination)
    except Exception:  # Optional media must never block the spoken show.
        return None


def reviewed_signature(root=None, audit=None):
    """Use the retained ElevenLabs logo between stories, with legacy fallback."""
    from pydub import AudioSegment
    root = Path(root) if root else Path(__file__).parent/'library'
    if audit is not None:
        audit.update(applied=False, reason="signature_unavailable_legacy_fallback")
    try:
        manifest = json.loads((root/'manifest.json').read_text())
        row = next(r for r in manifest.get('sounds', []) if r.get('name') == 'edge_signature'
                   and r.get('listening_review') == 'approved' and r.get('enabled_in_daily') is True)
        if Path(row['file']).name != row['file']:
            return None
        path = root/row['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row.get('sha256'):
            return None
        clip = AudioSegment.from_file(path)
        if not clip.rms or not 500 <= len(clip) <= 4000:
            return None
        clip = clip.apply_gain(-20-clip.dBFS)
        if clip.max_dBFS > -3:
            clip = clip.apply_gain(-3-clip.max_dBFS)
        if audit is not None:
            audit.update(applied=True, reason="signature_loaded", asset=row['file'],
                         sha256=row['sha256'], provider="elevenlabs", duration_seconds=len(clip)/1000)
        return clip.fade_in(20).fade_out(120)
    except Exception:
        return None


def mix_welcome_music(voice_path, destination, root=None, audit=None):
    """Only the caller's welcome slot; never an automatic bed under debate."""
    from pydub import AudioSegment
    root = Path(root) if root else Path(__file__).parent/'studio_v2'
    if audit is not None:
        audit.update(applied=False, reason='welcome_music_unavailable')
    try:
        manifest = json.loads((root/'manifest.json').read_text())
        if manifest.get('enabled_in_daily') is not True or manifest.get('candidate_review_passed') is not True:
            return None
        row = manifest['assets']['welcome_music']
        if Path(row['file']).name != row['file']:
            return None
        path = root/row['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            return None
        voice = AudioSegment.from_file(voice_path)
        bed = AudioSegment.from_file(path)[:min(7200,len(voice))]
        if not voice.rms or not bed.rms:
            return None
        bed = bed.apply_gain(min(-34,voice.dBFS-20)-bed.dBFS).fade_in(120).fade_out(min(1000,len(bed)))
        mixed=voice.overlay(bed)
        if mixed.max_dBFS > -1:
            mixed=mixed.apply_gain(-1-mixed.max_dBFS)
        mixed.export(destination,format='mp3',bitrate='192k').close()
        if audit is not None:
            audit.update(applied=True,asset=row['file'],provider='elevenlabs',
                         sha256=row['sha256'],duration_seconds=len(bed)/1000,
                         bed_dbfs=round(bed.dBFS,2))
        return Path(destination)
    except Exception:
        return None
