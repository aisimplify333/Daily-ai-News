"""Four bounded Gemini takes to compare Alex with the revised Rufus direction."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pydub import AudioSegment
from gemini_cast_tts import render_wav

scene = [
 ('ALEX','Charon','curiosity','Warm, grounded American host; a genuine question.',
  'An agent that handles the tedious work sounds useful. Rufus, what would you let it do first?'),
 ('RUFUS','Iapetus','dry_wit','Brisk, unmistakably southern English. Lighter register than Alex. Understate the final phrase.',
  'Sort my receipts. A modest beginning. I would rather establish competence before appointing it Chancellor of the Exchequer.'),
 ('ALEX','Charon','warmth','Affectionate, responsive, smiling slightly. Do not imitate Rufus.',
  'You have given it a promotion and a parliamentary hearing in the same sentence.'),
 ('RUFUS','Iapetus','amused','A small genuine chuckle, then brisk English clarity. Keep the accent and clipped ending.',
  'Heh. Fair point. Start small, check the work, then give it more room. I do actually want the thing to succeed.'),
]
out=Path('auditions/rufus_contrast_output');out.mkdir(parents=True,exist_ok=True)
joined=AudioSegment.empty()
for i,(speaker,voice,mood,note,text) in enumerate(scene):
    path=out/f'{i+1:02d}_{speaker.lower()}.wav'
    render_wav(text,speaker,mood,voice,'gemini-3.8-flash-tts',note,path,os.environ['GEMINI_API_KEY'])
    take=AudioSegment.from_wav(path)
    # Match the approved pitch-preserving production speed for each host.
    import subprocess
    sped=out/f'{i+1:02d}_{speaker.lower()}_speed.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-filter:a',
                    'atempo=1.12' if speaker=='RUFUS' else 'atempo=1.01',str(sped)],check=True)
    joined += AudioSegment.from_wav(sped) + AudioSegment.silent(duration=90)
joined.export(out/'alex_rufus_contrast.mp3',format='mp3',bitrate='192k')
(out/'manifest.json').write_text(json.dumps({'purpose':'Accent and identity listening audition; no episode publishing',
    'listened':False,'scene':scene},indent=2))
