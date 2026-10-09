import hashlib
import json
from pathlib import Path
from pydub.generators import Sine
from specialty_audio.mixer import choose_bed, mix_reviewed_bed


def test_scene_must_be_explicitly_imagined():
    assert choose_bed('I am in the boardroom.') is None
    assert choose_bed('Picture a boardroom.') == 'office'


def test_unreviewed_asset_never_plays(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({'sounds':[{'name':'office','listening_review':'pending','enabled_in_daily':True}]}))
    assert mix_reviewed_bed('missing.mp3', tmp_path/'mix.mp3', 'Imagine an office.', tmp_path) is None


def test_reviewed_mix_preserves_duration_and_corruption_falls_back(tmp_path):
    from pydub import AudioSegment
    voice = tmp_path/'voice.wav'; bed = tmp_path/'office.wav'
    Sine(240).to_audio_segment(duration=7000).apply_gain(-19).export(voice, format='wav').close()
    Sine(100).to_audio_segment(duration=5000).apply_gain(-20).export(bed, format='wav').close()
    row = {'name':'office','file':bed.name,'listening_review':'approved','enabled_in_daily':True,
           'sha256':hashlib.sha256(bed.read_bytes()).hexdigest()}
    (tmp_path/'manifest.json').write_text(json.dumps({'sounds':[row]}))
    result = mix_reviewed_bed(voice, tmp_path/'mixed.mp3', 'Imagine an office.', tmp_path)
    assert result and abs(len(AudioSegment.from_file(result))-7000) < 30
    bed.write_bytes(b'corrupt')
    assert mix_reviewed_bed(voice, tmp_path/'mixed2.mp3', 'Imagine an office.', tmp_path) is None
