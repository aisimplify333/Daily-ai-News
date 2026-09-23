"""Original typographic episode artwork; source title only, no image/model calls."""
from html import escape
from pathlib import Path
import textwrap


def artwork_svg(title, date, wide=False):
    width,height=(1600,900) if wide else (3000,3000)
    scale=width/1600
    size=76 if wide else 120
    lines=textwrap.wrap(title,width=32 if wide else 20)
    size=min(size, int((height/scale-360)/max(1,len(lines))/1.25))
    rows=''.join(f'<text x="100" y="{(280 if wide else 380)+i*size*1.25}" font-size="{size}" font-weight="700">{escape(line)}</text>' for i,line in enumerate(lines))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 1600 {height/scale}">
<rect width="1600" height="{height/scale}" fill="#101921"/><rect x="100" y="65" width="105" height="10" fill="#b4ee86"/>
<g fill="#f4f1e8" font-family="DejaVu Sans, sans-serif"><text x="100" y="155" font-size="64" font-weight="700">THE AI EDGE</text>{rows}
<text x="100" y="{height/scale-110}" font-size="30" fill="#b4ee86">ALEX · JAMIE · RUFUS</text><text x="100" y="{height/scale-60}" font-size="26">{escape(date)} · What changed. Who wins. What you do next.</text></g></svg>'''


def create_art(title,date,root=Path('.')):
    import cairosvg
    directory=Path(root)/'episode_art';directory.mkdir(exist_ok=True)
    paths={}
    for label,wide in [('cover',False),('thumbnail',True)]:
        svg=artwork_svg(title,date,wide)
        path=directory/f'{date}-{label}.png'
        cairosvg.svg2png(bytestring=svg.encode(),write_to=str(path))
        paths[label]=str(path)
    return paths
