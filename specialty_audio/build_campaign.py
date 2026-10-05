"""Bounded evergreen campaign production. Separate from daily broadcast.

Keeps approved cast; creates reusable voice takes plus nine portrait-motion ads.
These are motion graphics, NOT lip-synced animation. Review before publication.
An uncertain paid attempt stops resume rather than silently charging twice.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment, effects

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gemini_cast_tts import render_wav
from grok_tts_v4 import render_jamie

ROOT = Path('specialty_audio/campaign')
CAST = {'ALEX': ('gemini', 'Charon', 1.01), 'JAMIE': ('grok', 'ursa', 1.05),
        'RUFUS': ('gemini', 'Iapetus', 1.12)}

def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def save(data):
    p = ROOT / 'manifest.json'
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(p)

def font(size):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)

def card(speaker, hook):
    im = Image.new('RGB', (720, 1280), '#071624')
    source = Image.open(f'assets/{speaker.lower()}_master.png').convert('RGB')
    source.thumbnail((720, 780))
    im.paste(source, ((720-source.width)//2, 210+(780-source.height)//2))
    d = ImageDraw.Draw(im)
    d.text((40, 35), 'THE AI EDGE  /  THELEDGR', font=font(27), fill='#58dcf3')
    d.multiline_text((40, 95), '\n'.join(textwrap.wrap(hook, 32)), font=font(34), fill='white', spacing=8)
    d.text((40, 900), speaker.title(), font=font(30), fill='#58dcf3')
    d.text((40, 1215), 'AI-voiced cast • Dramatized conversation', font=font(20), fill='#a9bbc9')
    return im

def stamp(seconds):
    cs = round(seconds*100)
    return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'

def captions(path, rows):
    head = '''[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,DejaVu Sans,36,&H00FFFFFF,&H00FFFFFF,&H00071624,&H00071624,0,0,0,0,100,100,0,0,1,2,0,2,40,40,130,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    events = []
    for row in rows:
        words = row['text'].split()
        for n in range(0, len(words), 7):
            start = row['start'] + row['duration']*n/len(words)
            end = row['start'] + row['duration']*min(n+7,len(words))/len(words)
            text = ' '.join(words[n:n+7]).replace('{','').replace('}','')
            events.append(f'Dialogue: 0,{stamp(start)},{stamp(end)},Default,,0,0,0,,{text}')
    path.write_text(head+'\n'.join(events)+'\n')

def main():
    spec = json.loads(Path('specialty_audio/campaign.json').read_text())
    all_turns = [t for s in spec['scenes'].values() for t in s['turns']] + list(spec['endings'].values())
    if len(all_turns) > 15 or sum(len(t[2]) for t in all_turns) > 4500:
        raise RuntimeError('Campaign exceeds approved bounded batch')
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/'manifest.json').read_text()) if (ROOT/'manifest.json').exists() else {
        'takes': {}, 'outputs': {}, 'social_published': False, 'listening_review': 'pending',
        'visual_review': 'pending', 'animation': 'portrait motion graphics, not lip sync',
        'caption_timing': 'approximate word groups', 'elevenlabs_credits_used': 0}
    save(manifest)
    def take(turn):
        speaker, mood, text = turn
        provider, voice, speed = CAST[speaker]
        key = hashlib.sha256(json.dumps([turn,CAST[speaker]],sort_keys=True).encode()).hexdigest()[:16]
        path = ROOT/f'{key}.wav'
        old = manifest['takes'].get(key)
        if old:
            if old['status'] != 'complete' or not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=old['sha256']:
                raise RuntimeError('Uncertain take requires review: '+key)
            return path
        manifest['takes'][key] = {'speaker':speaker,'provider':provider,'voice':voice,'text':text,'status':'started'}
        save(manifest)
        raw = ROOT/f'{key}.raw.wav'
        if provider == 'gemini':
            render_wav(text,speaker,mood,voice,os.getenv('GEMINI_TTS_MODEL','gemini-3.8-flash-tts'),
                       f'{mood}. Intimate, quick conversational exchange. Respond to the preceding speaker; keep jokes understated.',raw,os.environ['GEMINI_API_KEY'])
        else:
            raw = raw.with_suffix('.mp3')
            render_jamie(text,mood,raw,primary_only=True)
        audio = AudioSegment.from_file(raw)
        if audio.rms == 0 or not 500 < len(audio) < 35000:
            raise RuntimeError('Invalid take duration/silence: '+key)
        effects.normalize(audio,headroom=2).export(path,format='wav')
        paced = ROOT/f'{key}.paced.wav'
        run('ffmpeg','-y','-i',str(path),'-af',f'atempo={speed}','-ar','44100','-ac','1',str(paced))
        paced.replace(path)
        manifest['takes'][key].update(status='complete',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        save(manifest)
        raw.unlink(missing_ok=True)
        return path
    for scene, content in spec['scenes'].items():
        for ending, endturn in spec['endings'].items():
            name = f'{scene}_{ending}'
            if name in manifest['outputs'] and (ROOT/f'{name}.mp4').exists():
                continue
            joined = AudioSegment.silent(duration=0,frame_rate=44100)
            rows, parts = [], []
            for idx,turn in enumerate(content['turns']+[endturn]):
                audio = AudioSegment.from_wav(take(turn)) + AudioSegment.silent(duration=110)
                duration = len(audio)/1000
                rows.append({'speaker':turn[0],'text':turn[2],'start':len(joined)/1000,'duration':duration})
                joined += audio
                still, part = ROOT/f'{name}_{idx}.png', ROOT/f'{name}_{idx}.mp4'
                card(turn[0], content['hook'] if idx<4 else {'podcast':'Follow The AI Edge','newsletter':'Subscribe at theledgr.io','combined':'Listen. Read. Make sense of AI.'}[ending]).save(still)
                run('ffmpeg','-y','-loop','1','-i',str(still),'-vf',"zoompan=z='min(zoom+0.00006,1.025)':d=1:s=720x1280:fps=25",'-t',str(duration),'-an','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(part))
                parts.append(part)
            if not 10 < len(joined)/1000 < 90:
                raise RuntimeError('Campaign duration outside bounds')
            audiofile = ROOT/f'{name}.mp3'
            joined.export(audiofile,format='mp3',bitrate='192k')
            ass = ROOT/f'{name}.ass'; captions(ass,rows)
            listing = ROOT/f'{name}.concat.txt'
            listing.write_text(''.join(f"file '{p.name}'\n" for p in parts))
            run('ffmpeg','-y','-f','concat','-safe','0','-i',str(listing),'-i',str(audiofile),'-vf',f'ass={ass}',
                '-c:v','libx264','-preset','fast','-crf','22','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(ROOT/f'{name}.mp4'))
            (ROOT/f'{name}.timeline.json').write_text(json.dumps(rows,indent=2)+'\n')
            manifest['outputs'][name]={'seconds':len(joined)/1000,'cta':ending,'review':'pending'}
            save(manifest)
            for p in parts: p.unlink()
            for p in ROOT.glob(f'{name}_*.png'): p.unlink()
            listing.unlink()
    print('Campaign outputs preserved:',len(manifest['outputs']))

if __name__=='__main__':
    main()
