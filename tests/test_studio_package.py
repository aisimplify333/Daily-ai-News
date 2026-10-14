import hashlib
import json
from pydub.generators import Sine
from specialty_audio.studio_package import load_package, asset_audit


def package(root):
    assets={}
    for name in ['rufus','transition']:
        p=root/(name+'.wav')
        Sine(440).to_audio_segment(duration=3000).apply_gain(-15).export(p,format='wav').close()
        assets[name]={'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'seconds':3}
    manifest={'enabled_in_daily':True,'version':'test','review_basis':'test fixture','assets':assets}
    (root/'manifest.json').write_text(json.dumps(manifest))
    return manifest


def test_only_internal_cues_are_loaded(tmp_path):
    package(tmp_path)
    clips,audit=load_package(tmp_path)
    assert set(clips)=={'transition','rufus'}
    assert asset_audit(audit,'rufus')['duration_seconds']==3


def test_unreviewed_or_corrupt_package_falls_back_as_whole(tmp_path):
    m=package(tmp_path)
    m['enabled_in_daily']=False
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    assert load_package(tmp_path)[0]=={}
    package(tmp_path)
    (tmp_path/'rufus.wav').write_bytes(b'changed')
    assert load_package(tmp_path)[0]=={}
