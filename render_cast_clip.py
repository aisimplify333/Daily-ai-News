"""Render an approved, continuous master excerpt with speaker portraits and captions.

No new voices, synthetic interview footage, or generative API calls.
"""
import argparse
import json
from pathlib import Path
import subprocess
import textwrap


def run(*args):
    subprocess.run(list(map(str, args)), check=True, capture_output=True)


def stamp(value):
    ms = round(value * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'


def render(master, spec_path, portraits, output):
    spec = json.loads(Path(spec_path).read_text())
    rows = spec['turns']
    start, end = spec['start'], spec['end']
    if not rows or not 15 <= end-start <= 60:
        raise ValueError('Expected a reviewed 15-60 second excerpt')
    if rows[-1]['text'].rstrip().endswith('?'):
        raise ValueError('Do not end a promo on an unanswered question')
    out = Path(output).resolve(); out.mkdir(parents=True, exist_ok=True)
    captions = ['WEBVTT', '']
    for row in rows:
        words = row['text'].split()
        groups = [words[i:i+8] for i in range(0,len(words),8)]
        for i, group in enumerate(groups):
            a = row['start']-start+(row['end']-row['start'])*i/len(groups)
            b = row['start']-start+(row['end']-row['start'])*(i+1)/len(groups)
            captions += [f'{stamp(a)} --> {stamp(b)}', '\n'.join(textwrap.wrap(row['speaker']+': '+' '.join(group), 34)), '']
    (out/'captions.vtt').write_text('\n'.join(captions))
    parts=[]
    for i,row in enumerate(rows):
        duration=(rows[i+1]['start'] if i+1<len(rows) else end)-row['start']
        asset=Path(portraits)/f"{row['speaker'].lower()}_master.png"
        part=out/f'part_{i}.mp4'; parts.append(part)
        filt="scale=720:880:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:145:color=0x101827,setsar=1"
        run('ffmpeg','-y','-v','error','-loop','1','-i',asset,'-t',duration,'-vf',filt,'-an','-r','25','-c:v','libx264','-preset','fast','-crf','24','-pix_fmt','yuv420p',part)
    (out/'parts.txt').write_text(''.join(f"file '{p.name}'\n" for p in parts))
    run('ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',out/'parts.txt','-c','copy',out/'silent.mp4')
    heading = spec.get('display_heading', 'THE AI EDGE | Useful AI, lively debate')
    (out/'heading.txt').write_text('\n'.join(textwrap.wrap(heading, 37)))
    header="drawtext=textfile="+str(out/'heading.txt')+":fontcolor=white:fontsize=30:x=(w-tw)/2:y=40:line_spacing=8"
    footer="drawtext=text='THE AI EDGE  |  Follow for useful AI':fontcolor=white:fontsize=25:x=(w-tw)/2:y=1220"
    filt=header+','+footer+",subtitles="+str(out/'captions.vtt')+":force_style='FontName=DejaVu Sans,FontSize=12,MarginV=60,Outline=2'"
    target=out/'cast_clip.mp4'
    run('ffmpeg','-y','-v','error','-i',out/'silent.mp4','-ss',start,'-i',Path(master).resolve(),'-t',end-start,'-map','0:v','-map','1:a','-vf',filt,'-c:v','libx264','-crf','23','-preset','fast','-c:a','aac','-b:a','192k','-movflags','+faststart',target)
    (out/'review.json').write_text(json.dumps({'source_start':start,'source_end':end,'duration':end-start,'format':'720x1280 portrait cuts; not lip-synced video','caption_timing':'measured turns, estimated word groups','publication':'not_uploaded_to_spotify','editorial_selection':'continuous explanation, analogy, response and punchline; no unanswered ending'},indent=2))
    print(target)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('master');p.add_argument('spec');p.add_argument('portraits');p.add_argument('output')
    a=p.parse_args();render(a.master,a.spec,a.portraits,a.output)
