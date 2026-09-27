"""Reuse approved monthly cast artwork without text overlays or face cropping."""
import datetime
import json
import shutil
from pathlib import Path


def monthly_cover(date, root=Path('.')):
    root = Path(root)
    month = datetime.date.fromisoformat(date).month
    manifest_path = root / 'assets/cover_rotation_manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    name = manifest.get('rotation_pattern', {}).get(str(month))
    if name:
        relative = Path(name) if str(name).startswith('assets/') else Path('assets') / name
    else:
        relative = Path(manifest.get('selected_cover') or 'assets/cover_trio_master.png')
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Artwork must be a repository-relative approved asset')
    if not (root / relative).is_file():
        raise FileNotFoundError(f'Approved monthly artwork unavailable: {relative}')
    return relative


def create_art(title, date, root=Path('.')):
    # Preserve the interface; episode titles belong in metadata, never on faces.
    root = Path(root)
    relative = monthly_cover(date, root)
    source = root / relative
    directory = root / 'episode_art'
    directory.mkdir(exist_ok=True)
    paths = {'source': relative.as_posix(), 'policy': 'monthly_cast_art_unchanged'}
    for label in ('cover', 'thumbnail'):
        path = directory / f'{date}-{label}{source.suffix}'
        shutil.copyfile(source, path)
        paths[label] = str(path)
    return paths
