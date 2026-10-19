"""One bounded ElevenLabs commission, derived family, real-cast demo and audio review."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from pydub import AudioSegment
from specialty_audio.build_library import get_account
from specialty_audio.mixer import mix_reviewed_bed
from audio_engineering import inspect_master

ROOT = Path('specialty_audio/studio')
VERSION = 'ai-edge-studio-v1'
BRIEF = '''Three-second original entrance for a witty British AI pundit: crisp soft tick, then three memorable warm mallet/electric-piano notes, two poised notes and a cheeky rising finish. Confident, dry and playful. Clear phone-speaker attack, rounded warmth, short clean decay. Contemporary podcast palette. No voices, laughter, alarms, fanfare, cinematic boom or existing melody.''' 


def write(name, value):
    (ROOT/name).write_text(json.dumps(value, indent=2)+'\n')


def level(clip, target):
    if not clip.rms:
        raise ValueError('silent asset')
    clip = clip.apply_gain(target-clip.dBFS)
    if clip.max_dBFS > -3:
        clip = clip.apply_gain(-3-clip.max_dBFS)
    return clip.set_frame_rate(48000).set_channels(2)


def export(name, clip, assets):
    path = ROOT/(name+'.mp3')
    clip.export(path, format='mp3', bitrate='192k').close()
    decoded = AudioSegment.from_file(path)
    assets[name] = {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'seconds':len(decoded)/1000,'dbfs':round(decoded.dBFS,2),
                    'peak_dbfs':round(decoded.max_dBFS,2)}


def commission():
    ledger = ROOT/'commission.json'
    source = ROOT/'theme_source.mp3'
    previous = []
    if len(BRIEF) > 450:
        raise ValueError('Sound prompt exceeds provider limit')
    if ledger.exists():
        row = json.loads(ledger.read_text())
        if row.get('status') == 'complete' and source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() == row.get('sha256'):
            return source
        if row.get('status') != 'rejected_http_400':
            raise RuntimeError('Prior incomplete commission: inspect retained work, no duplicate request')
        previous = [row]
    key = os.environ['AI_EDGE_PODCAST_ELEVENLABS']
    if get_account(key)['remaining'] < 2000:
        raise RuntimeError('Insufficient allowance for bounded commission')
    row = {'status':'attempted','model':'eleven_text_to_sound_v2','brief':BRIEF,'requested_seconds':3,
           'maximum_requests':1,'credit_reservation':2000,'previous_rejected_requests':previous}
    write('commission.json',row)
    request = urllib.request.Request('https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128',
        data=json.dumps({'text':BRIEF,'duration_seconds':3,'prompt_influence':0.5,'model_id':row['model']}).encode(),
        headers={'xi-api-key':key,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=150) as response:
        data = response.read(); cost = response.headers.get('character-cost')
    source.write_bytes(data)
    clip = AudioSegment.from_file(source)
    if not 2500 <= len(clip) <= 4000 or not clip.rms:
        raise RuntimeError('Commission duration/silence check failed')
    row.update(status='complete',sha256=hashlib.sha256(data).hexdigest(),
               accounted_credits=int(cost) if cost and cost.isdigit() else 2000)
    write('commission.json',row)
    return source


def derive(source):
    # Preserve the existing show opening/closing. Only internal cues are packaged.
    assets = {}
    signature = Path('specialty_audio/library/edge_signature.mp3')
    library = json.loads((signature.parent/'manifest.json').read_text())
    row = next(r for r in library['sounds'] if r['name']=='edge_signature')
    if row.get('listening_review') != 'approved' or hashlib.sha256(signature.read_bytes()).hexdigest()!=row['sha256']:
        raise RuntimeError('Transition source not verified')
    export('transition',level(AudioSegment.from_file(signature),-21).fade_in(10).fade_out(200),assets)
    export('rufus',level(AudioSegment.from_file(source),-19).fade_in(10).fade_out(180),assets)
    return assets


def demonstrate(assets):
    master = AudioSegment.from_file('episode_audio/podcast_2026-10-13.mp3')
    rows = json.loads(Path('episode_audio/podcast_2026-10-13.timeline.json').read_text())['rows']
    output = AudioSegment.empty(); cues=[]
    def append(clip, label):
        nonlocal output
        start=len(output)/1000;output += clip
        cues.append({'label':label,'start':start,'end':len(output)/1000})
    def speech(row, atmosphere=False):
        clip = master[round(row['start']*1000):round(row['end']*1000)]
        if atmosphere:
            raw=ROOT/'demo_voice.wav'; mixed=ROOT/'demo_atmosphere.mp3'
            clip.export(raw,format='wav').close()
            audit={}
            if mix_reviewed_bed(raw,mixed,row['text'],audit=audit):
                clip=AudioSegment.from_file(mixed)
            cues.append({'label':'atmosphere_audit','details':audit,'start':len(output)/1000})
        if row['text'] == 'Welcome to The AI Edge.' and 'welcome_music' in assets:
            music = AudioSegment.from_file(ROOT/assets['welcome_music']['file'])[:len(clip)]
            music = level(music, min(-34, clip.dBFS-20)).fade_out(min(800,len(music)))
            clip = clip.overlay(music)
        append(clip,row['speaker']+': '+row['text'])
        append(AudioSegment.silent(duration=110),'breath')
    for row in rows:
        if row['kind']=='speech' and row['start']<28:speech(row)
    opening=next(r for r in rows if r['kind']=='intro')
    append(master[round(opening['start']*1000):round(opening['end']*1000)],'existing_signature_opening_preserved')
    welcome=next(r for r in rows if r['kind']=='speech' and r['text']=='Welcome to The AI Edge.')
    speech(welcome)
    append(AudioSegment.from_file(ROOT/'transition.mp3'),'story_transition_demonstration')
    for row in rows:
        if row['kind']=='speech' and 502 < row['start'] < 572:
            speech(row, atmosphere=row['speaker']=='RUFUS' and 'Picture' in row['text'])
            if 'take us on location' in row['text']:
                append(AudioSegment.from_file(ROOT/'rufus.mp3'),'new_rufus_motif')
    close=next(r for r in rows if r['kind']=='speech' and 'Follow The AI Edge now.' in r['text'])
    speech(close)
    closing=next(r for r in rows if r['kind']=='outro')
    append(master[round(closing['start']*1000):round(closing['end']*1000)],'existing_signature_closing_preserved')
    raw=ROOT/'demo_unmastered.wav';output.export(raw,format='wav').close()
    final=ROOT/'AI-Edge-Studio-Demonstration.mp3'
    # Two-pass loudness processing; retain codec headroom.
    first=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(raw),'-af','loudnorm=I=-16:TP=-2:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    import re
    measured=json.loads(re.findall(r'\{[^{}]*\}',first.stderr)[-1])
    filt='loudnorm=I=-16:TP=-2:LRA=11:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:linear=true'.format(**measured)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(raw),'-af',filt,'-ar','48000','-ac','2','-b:a','192k',str(final)],check=True)
    report=inspect_master(final);write('engineering.json',report)
    write('demo_timeline.json',{'source':'October 13 published cast excerpts; edited sound demonstration, not a new episode','cues':cues})
    for path in (raw,ROOT/'demo_voice.wav',ROOT/'demo_atmosphere.mp3'):
        path.unlink(missing_ok=True)
    if report['warnings']:
        raise RuntimeError('Demo engineering warnings require inspection')
    return final


def review(demo, assets):
    from google import genai
    from google.genai import types
    prompt='''Listen to this sound-design demonstration and all isolated candidate assets, including music if present. This is an edited
remix of October 13 cast audio, not new news. Evaluate AUDIO, not the brief. Return JSON:
{"audio_evaluated":true,"pass":true,"observations":[{"seconds":0,"description":"specific audible observation"}],
"defects":[],"rufus_distinctive":true,"family_cohesive":true,"speech_clear":true}.
Pass only if speech remains clear, cue entrances/exits are clean, the internal cues fit alongside the preserved opening and closing, Rufus's cue is distinguishable from the ordinary transition and is not a horn, brass fanfare or alarm. Any welcome music must be sparse, instrumental, unobtrusive and free of vocals. Require all these conditions, and
there is no intelligible voice in the instrumental cues, harsh spike, jarring edit,
masked syllable or obvious audio glitch. Identify concrete defects if any. Do not
claim human review, audience recognition, million-dollar quality or invent scores.
If unable to evaluate audio, audio_evaluated=false and pass=false.
Timestamps refer to the demo only. A serious spoken line need not be funny.'''
    parts=[types.Part.from_text(text=prompt),types.Part.from_bytes(data=demo.read_bytes(),mime_type='audio/mpeg')]
    for name,row in assets.items():
        parts += [types.Part.from_text(text='ISOLATED CUE: '+name),types.Part.from_bytes(data=(ROOT/row['file']).read_bytes(),mime_type='audio/mpeg')]
    client=genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    response=client.models.generate_content(model='gemini-3.1-flash-lite',contents=parts,
        config=types.GenerateContentConfig(response_mime_type='application/json',temperature=0.2,max_output_tokens=3000,
            response_schema={'type':'OBJECT','properties':{
                'audio_evaluated':{'type':'BOOLEAN'},'pass':{'type':'BOOLEAN'},
                'rufus_distinctive':{'type':'BOOLEAN'},'family_cohesive':{'type':'BOOLEAN'},'speech_clear':{'type':'BOOLEAN'},
                'observations':{'type':'ARRAY','items':{'type':'OBJECT','properties':{'seconds':{'type':'NUMBER'},'description':{'type':'STRING'}},'required':['seconds','description']}},
                'defects':{'type':'ARRAY','items':{'type':'STRING'}}},
                'required':['audio_evaluated','pass','rufus_distinctive','family_cohesive','speech_clear','observations','defects']}))
    result=json.loads(response.text)
    write('audio_review_response.json', result)
    if isinstance(result, list) and len(result) == 1:
        result = result[0]
    if not isinstance(result, dict):
        raise ValueError('Expected one review object')
    result.update(basis='automated audio model evaluation; not human listening',model='gemini-3.1-flash-lite',demo_sha256=hashlib.sha256(demo.read_bytes()).hexdigest())
    write('audio_review.json',result)
    return (all(result.get(k) is True for k in ['audio_evaluated','pass','rufus_distinctive','family_cohesive','speech_clear'])
            and result.get('defects') == [] and bool(result.get('observations')))


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    manifest={'version':VERSION,'enabled_in_daily':False,'review_basis':'pending','opening_closing':'existing signatures preserved; never replaced by this package','assets':{}}
    write('manifest.json',manifest)
    source=commission();assets=derive(source);manifest['assets']=assets;write('manifest.json',manifest)
    demo=demonstrate(assets)
    passed=review(demo,assets)
    manifest.update(enabled_in_daily=passed,review_basis='automated audio review plus encoded-master measurements; not human listening')
    write('manifest.json',manifest)
    print(json.dumps({'package':VERSION,'enabled_in_daily':passed,'demo':str(demo)}))
    if not passed:raise SystemExit('Audio review requires revision; existing daily sound retained')


if __name__=='__main__':main()
