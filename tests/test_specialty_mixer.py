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


def test_software_company_and_conference_room_are_office_scenes():
    assert choose_bed('Picture a midsize software company in New York.') == 'office'
    assert choose_bed('Imagine a conference room.') == 'office'
    assert choose_bed('Imagine a conference in London.') == 'conference'
    assert choose_bed('The software company announced a launch.') is None


def test_signature_approval_hash_and_audit(tmp_path):
    from specialty_audio.mixer import reviewed_signature
    clip = tmp_path/'signature.wav'
    Sine(500).to_audio_segment(duration=3000).export(clip, format='wav').close()
    row = {'name':'edge_signature', 'file':clip.name, 'enabled_in_daily':True,
           'listening_review':'approved', 'sha256':hashlib.sha256(clip.read_bytes()).hexdigest()}
    (tmp_path/'manifest.json').write_text(json.dumps({'sounds':[row]}))
    audit = {}; result = reviewed_signature(tmp_path, audit)
    assert result is not None and len(result) == 3000 and result.max_dBFS <= -3
    assert audit['applied'] and audit['sha256'] == row['sha256']
    clip.write_bytes(b'bad')
    audit = {}; assert reviewed_signature(tmp_path, audit) is None
    assert not audit['applied']


def test_oct15_imagined_tech_company_matches_existing_office_bed():
    assert choose_bed("Picture this: you're a legal strategist at a large tech company in New York.") == 'office'
    assert choose_bed('A large tech company announced results.') is None
    assert choose_bed('Picture the global desk.') is None



def test_global_dispatch_uses_specific_setting_before_city():
    assert choose_bed('Imagine Dreamforce in San Francisco.') == 'conference'
    assert choose_bed('Picture a data center outside Shanghai.') == 'server_room'
    assert choose_bed('Imagine Parliament in London.') == 'legislative_hall'
    assert choose_bed('Picture Hong Kong at street level.') == 'city'
    assert choose_bed('Rufus is in Shanghai.') is None
