"""Model-based listening review of retained audio; no synthesis or cast changes."""
import hashlib
import json
import os
from pathlib import Path
from google import genai
from google.genai import types


def review(client, rows, folder, kind):
    parts = [types.Part.from_text(text='Listen to each supplied audio file. Return JSON only: {"assets":[{"name":"exact label","pass":true,"reason":"specific audible observations","clarity":1,"naturalness":1}]}. Scores 1-5. '+
        ('Sound effects: pass only if the sound matches its brief, has no intelligible speech, alarms, recognizable music or startling harsh transients, and would work quietly under spoken dialogue or as its stated short sonic ID. ' if kind == 'sound' else
         'Speech: check intelligibility, missing/cut words, spoken acting tags, obvious synthesis glitches and whether delivery fits a conversational podcast. Evaluate the supplied script, not its factual truth. Fictional samples are clearly labeled. ')+
        'Do not infer quality from filenames. If audio cannot be heard or evaluated, pass=false. This is automated listening review, not human approval.')]
    for row in rows:
        name = row.get('name', 'war_room')
        path = folder/row['file']
        parts += [types.Part.from_text(text='LABEL: '+name+'\nBRIEF: '+row.get('prompt', row.get('text','Fictional multi-speaker war room'))),
                  types.Part.from_bytes(data=path.read_bytes(), mime_type='audio/mpeg')]
    response = client.models.generate_content(model=os.getenv('AUDIO_REVIEW_MODEL','gemini-3.1-flash-lite'),
        contents=parts, config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0.2, max_output_tokens=5000))
    payload = json.loads(response.text)
    results = {r['name']:r for r in payload.get('assets',[]) if isinstance(r,dict) and isinstance(r.get('name'),str)}
    for row in rows:
        name = row.get('name','war_room')
        result = results.get(name)
        if not result or type(result.get('pass')) is not bool or not result.get('reason'):
            raise RuntimeError('Incomplete audio review: '+name)
        result['sha256'] = hashlib.sha256((folder/row['file']).read_bytes()).hexdigest()
    return results


def main():
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    root = Path('specialty_audio')
    sounds = json.loads((root/'library/manifest.json').read_text())
    auditions = json.loads((root/'auditions/manifest.json').read_text())
    sound_rows = [r for r in sounds['sounds'] if r['status']=='generated']
    voice_rows = [r for r in auditions['takes'] if r['status']=='complete' and not r['name'].startswith('war_room_')]
    voice_rows.append(dict(auditions['war_room'],name='war_room'))
    report = {'basis':'automated model listening; not human listening', 'human_listened':False,
              'model':os.getenv('AUDIO_REVIEW_MODEL','gemini-3.1-flash-lite'), 'sounds':{}, 'auditions':{}}
    output = root/'audio_review.json'
    try:
        report['sounds'] = review(client, sound_rows, root/'library', 'sound')
        output.write_text(json.dumps(report,indent=2))
        # Small batches keep individual performances identifiable to the reviewer.
        for start in range(0,len(voice_rows),4):
            report['auditions'].update(review(client,voice_rows[start:start+4],root/'auditions','speech'))
            output.write_text(json.dumps(report,indent=2))
        for row in sound_rows:
            verdict = report['sounds'][row['name']]
            row['automated_listening_review'] = verdict
            if verdict['pass'] and verdict['sha256'] == row['sha256']:
                row.update(listening_review='approved', review_by='automated_audio_model', enabled_in_daily=True)
            else:
                row.update(listening_review='rejected', review_by='automated_audio_model', enabled_in_daily=False)
        sounds['daily_integration'] = 'reviewed_sound_assets_only; production_cast_unchanged'
        (root/'library/manifest.json').write_text(json.dumps(sounds,indent=2))
        report['complete'] = True
        output.write_text(json.dumps(report,indent=2))
    except Exception as exc:
        report.update(complete=False,error=type(exc).__name__)
        output.write_text(json.dumps(report,indent=2))
        raise SystemExit('Audio review incomplete: '+type(exc).__name__) from None

if __name__ == '__main__':
    main()
