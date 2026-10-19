import hashlib
import json
from editorial_selection import balanced_story_order
from specialty_audio.mixer import choose_bed, mix_welcome_music


def story(name, score, tier=2):
    return {'headline':name, 'source_tier':tier, 'editorial_scores':dict.fromkeys(
        ['human_consequence','novelty','explanatory_value','evidence_depth'], score)}


def test_stronger_verified_story_can_displace_first_lead():
    rows=[story('Company raises funding',2),story('Useful model release',4),story('Untrusted claim',5,1)]
    assert balanced_story_order(rows)[0]['headline']=='Useful model release'
    assert len(balanced_story_order(rows))==3
    assert rows[0]['headline']=='Company raises funding'


def test_incomplete_scores_preserve_order_without_inventing_score():
    rows=[story('First',2),story('Second',5)]
    del rows[0]['editorial_scores']['novelty']
    assert balanced_story_order(rows)[0]['headline']=='First'


def test_risk_committee_requires_imagination_marker():
    assert choose_bed('Picture a risk committee meeting.')=='office'
    assert choose_bed('A risk committee meeting approved the deal.') is None


def test_music_approval_hash_level_duration(tmp_path):
    from pydub import AudioSegment
    from pydub.generators import Sine
    voice=tmp_path/'voice.wav'; bed=tmp_path/'music.wav'
    Sine(300).to_audio_segment(duration=9000).apply_gain(-15).export(voice,format='wav').close()
    Sine(120).to_audio_segment(duration=15000).export(bed,format='wav').close()
    row={'file':bed.name,'sha256':hashlib.sha256(bed.read_bytes()).hexdigest()}
    manifest={'enabled_in_daily':False,'candidate_review_passed':True,'assets':{'welcome_music':row}}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    assert mix_welcome_music(voice,tmp_path/'out.mp3',tmp_path) is None
    manifest['enabled_in_daily']=True
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    audit={}; out=mix_welcome_music(voice,tmp_path/'out.mp3',tmp_path,audit)
    assert out and abs(len(AudioSegment.from_file(out))-9000)<30
    assert audit['duration_seconds']==7.2 and audit['bed_dbfs']<=-34
    bed.write_bytes(b'corrupt')
    assert mix_welcome_music(voice,tmp_path/'bad.mp3',tmp_path) is None
