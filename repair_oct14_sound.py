"""Surgical Oct14 master repair: reuse an aired Alex handoff, insert reviewed SFX.
No TTS or story rewrite. Keep the original master and disclose all edits.
"""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from pydub import AudioSegment
from specialty_audio.studio_package import load_package,asset_audit
from specialty_audio.mixer import mix_reviewed_bed
from audio_engineering import inspect_master

DATE='2026-10-14'
EXPECTED='76b1a66c27ff84f0ad55c1d21f808b51a7b8eb6874b6786b5bc2e6c61fd8ca14'

def main():
    p=Path('episode_audio');audio=p/f'podcast_{DATE}.mp3'
    if hashlib.sha256(audio.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('Unexpected original master')
    master=AudioSegment.from_file(audio)
    tpath=p/f'podcast_{DATE}.timeline.json';timeline=json.loads(tpath.read_text());rows=timeline['rows']
    bad=next(r for r in rows if r.get('text')=='Quite. Rufus, take us on location.')
    redundant=next(r for r in rows if r.get('text')=='Go on then.' and r['start']>bad['start'])
    scene=next(r for r in rows if r.get('text','').startswith('Picture Wall Street'))
    prior=AudioSegment.from_file(p/'podcast_2026-10-13.mp3')
    pt=json.loads((p/'podcast_2026-10-13.timeline.json').read_text())
    hand=next(r for r in pt['rows'] if r.get('speaker')=='ALEX' and r.get('text')=='Fair. Rufus, take us on location.')
    spoken=prior[round(hand['start']*1000):round(hand['end']*1000)].fade_in(5).fade_out(10)
    clips,pack=load_package()
    if not clips:raise RuntimeError('Reviewed sound package unavailable')
    start,end=round(bad['start']*1000),round(scene['start']*1000)
    cue=clips['rufus'];gap=AudioSegment.silent(duration=110)
    replacement=spoken+gap+cue+gap
    delta=(len(replacement)-(end-start))/1000
    revised=master[:start]+replacement+master[end:]
    new_scene=scene['start']+delta
    scratch=Path('/tmp/oct14_sound');scratch.mkdir(exist_ok=True)
    raw=scratch/'speech.wav';mixed=scratch/'speech.mp3';a=round(new_scene*1000);b=a+round((scene['end']-scene['start'])*1000)
    revised[a:b].export(raw,format='wav').close();bed_audit={}
    if not mix_reviewed_bed(raw,mixed,scene['text'],audit=bed_audit):raise RuntimeError('Expected city illustration missing')
    revised=revised[:a]+AudioSegment.from_file(mixed)+revised[b:]
    cue_start=start/1000+len(spoken)/1000+0.11
    out=[]
    for row in rows:
        if row is redundant:continue
        row=dict(row)
        if row['start']>=end/1000:
            row['start']=round(row['start']+delta,3);row['end']=round(row['end']+delta,3)
        if row.get('text')==bad['text']:
            row.update(speaker='ALEX',text=hand['text'],end=round(start/1000+len(spoken)/1000,3),sound_design={})
        if row.get('text')==scene['text']:row['sound_design']=bed_audit
        out.append(row)
    out.append({'kind':'rufus_entrance','segment':3,'start':round(cue_start,3),'end':round(cue_start+len(cue)/1000,3),'sound_design':asset_audit(pack,'rufus')})
    timeline['rows']=sorted(out,key=lambda r:r['start']);timeline['duration_seconds']=len(revised)/1000
    timeline['method']='original measured assembly plus exact local edit offsets'
    tpath.write_text(json.dumps(timeline,indent=2)+'\n')
    # Same master level/headroom, with measured two-pass finishing after the local edit.
    wav=scratch/'master.wav';revised.export(wav,format='wav').close()
    probe=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',str(wav),'-af','loudnorm=I=-16:TP=-2:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    m=json.loads(re.findall(r'\{[^{}]*\}',probe.stderr)[-1])
    filt='loudnorm=I=-16:TP=-2:LRA=11:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:linear=true'.format(**m)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(wav),'-af',filt,'-ar','48000','-ac','2','-b:a','192k',str(audio)],check=True)
    for f in [Path(f'script_{DATE}.txt'),Path(f'script_pre_tts_{DATE}.txt'),p/f'podcast_{DATE}.txt']:
        if f.exists():f.write_text(f.read_text().replace('RUFUS: '+bad['text'],'ALEX: '+hand['text']).replace('ALEX: Go on then.\n',''))
    ch=p/f'podcast_{DATE}.chapters.json';data=json.loads(ch.read_text());changed={}
    def stamp(x):return f'{int(x)//60:02}:{int(x)%60:02}'
    for row in data['chapters']:
        old=row['startTime']
        if old>=end/1000:row['startTime']=round(old+delta,3);changed[stamp(old)]=stamp(row['startTime'])
    ch.write_text(json.dumps(data,indent=2)+'\n')
    side=p/f'podcast_{DATE}.json';sd=json.loads(side.read_text())
    for old,new in changed.items():sd['description']=sd['description'].replace(old+' ',new+' ')
    side.write_text(json.dumps(sd,indent=2)+'\n')
    feed=ET.parse('feed.xml')
    for item in feed.findall('./channel/item'):
        enclosure=item.find('enclosure')
        if enclosure is None or not enclosure.get('url','').endswith(f'podcast_{DATE}.mp3'):continue
        enclosure.set('length',str(audio.stat().st_size))
        for node in item.iter():
            if node.tag.endswith('duration'):node.text=str(round(len(revised)/1000))
            if node.tag=='description' and node.text:
                for old,new in changed.items():node.text=node.text.replace(old+' ',new+' ')
    feed.write('feed.xml',encoding='utf-8',xml_declaration=True)
    engineering=inspect_master(audio);Path('audio_engineering_report.json').write_text(json.dumps(engineering,indent=2)+'\n')
    if engineering['warnings']:raise RuntimeError('Repaired master needs engineering inspection')
    qa=json.loads(Path('audio_qa_report.json').read_text())
    decoded=AudioSegment.from_file(audio)
    qa['transition_measurements']=[{'segment':r.get('segment'),'start':r['start'],'end':r['end'],
        'dbfs':round(decoded[round(r['start']*1000):round(r['end']*1000)].dBFS,2),
        'audible_level':decoded[round(r['start']*1000):round(r['end']*1000)].dBFS > -32}
        for r in timeline['rows'] if r['kind']=='transition']
    qa['transition_count']=len(qa['transition_measurements'])
    qa['repair_basis']='Re-measured repaired encoded master; original signature assets preserved'
    Path('audio_qa_report.json').write_text(json.dumps(qa,indent=2)+'\n')
    design=json.loads(Path('sound_design_report.json').read_text());events=[]
    for row in timeline['rows']:
        info=row.get('sound_design') or {}
        if info.get('applied'):events.append(dict(info,kind=row['kind'],start=row['start'],end=min(row['end'],row['start']+info['duration_seconds'])))
    design.update(events=events,repair='Corrected cast handoff and added missing reviewed cue and city atmosphere')
    Path('sound_design_report.json').write_text(json.dumps(design,indent=2)+'\n')
    Path('oct14_audio_repair_report.json').write_text(json.dumps({'original_sha256':EXPECTED,'final_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'new_tts_calls':0,'duration_delta_seconds':delta,'edits':['Replaced self-introduction with already-aired Alex handoff from October 13','Removed redundant Go on then','Inserted reviewed three-second Rufus cue','Added five-second city illustration under explicitly imagined Wall Street scene'],'opening_closing':'Original master segments preserved; whole-program loudness finishing only','original_fact_and_editorial_reviews':'Preserved as pre-repair evidence; no story claims changed'},indent=2)+'\n')
    print('Repaired completed master without generating voices')

if __name__=='__main__':main()
