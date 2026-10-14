"""Load a versioned, hash-checked sound family. Never generate during daily runs."""
import hashlib
import json
from pathlib import Path
from pydub import AudioSegment

ROOT = Path(__file__).parent/'studio'


def load_package(root=None):
    root = Path(root) if root else ROOT
    try:
        manifest = json.loads((root/'manifest.json').read_text())
        if manifest.get('enabled_in_daily') is not True:
            return {}, {'applied':False, 'reason':'package_not_approved'}
        clips = {}
        for name in ('transition', 'rufus'):
            row = manifest['assets'][name]
            if Path(row['file']).name != row['file']:
                raise ValueError('invalid asset path')
            path = root/row['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('asset hash mismatch')
            clip = AudioSegment.from_file(path)
            bounds = {'intro':(2000,6000),'transition':(500,4000),'rufus':(1500,4500),'outro':(6000,16000)}
            lo, hi = bounds[name]
            if not lo <= len(clip) <= hi or not clip.rms or clip.max_dBFS > -1:
                raise ValueError('asset measurement outside bounds')
            clips[name] = clip
        return clips, {'applied':True,'package':manifest['version'],'provider':'elevenlabs',
                       'review_basis':manifest['review_basis'],'assets':manifest['assets']}
    except Exception as exc:
        return {}, {'applied':False,'reason':'package_unavailable_'+type(exc).__name__}


def asset_audit(package, name):
    if not package.get('applied'):
        return dict(package)
    row = package['assets'][name]
    return {'applied':True,'package':package['package'],'provider':'elevenlabs',
            'asset':row['file'],'sha256':row['sha256'],'duration_seconds':row['seconds']}
