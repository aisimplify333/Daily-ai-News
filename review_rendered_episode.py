"""Full-master model audio review with coverage and hashes; never human approval."""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
from pydub import AudioSegment


def windows(milliseconds, size=240000, overlap=10000):
    if milliseconds <= 0 or not 0 <= overlap < size:
        raise ValueError('Invalid audio coverage')
    start = 0
    while start < milliseconds:
        end = min(start + size, milliseconds)
        yield start, end
        if end == milliseconds:
            break
        start = end - overlap


def validate(payload, duration):
    if not isinstance(payload, dict) or payload.get('audio_evaluated') is not True:
        raise ValueError('Model did not evaluate the audio')
    for key in ('observations', 'defects'):
        if not isinstance(payload.get(key), list):
            raise ValueError('Incomplete audio observations')
        for row in payload[key]:
            if not isinstance(row, dict) or not row.get('description') or type(row.get('seconds')) not in (int, float) or not 0 <= row['seconds'] <= duration:
                raise ValueError('Audio observation needs a valid clip timestamp')
    scores = payload.get('scores', {})
    for key in ('intelligibility', 'natural_delivery', 'cast_connection', 'pacing'):
        if type(scores.get(key)) is not int or not 1 <= scores[key] <= 5:
            raise ValueError('Missing audio rating: ' + key)
    return payload


def main():
    from google import genai
    from google.genai import types
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    args = parser.parse_args()
    path = Path(f'episode_audio/podcast_{args.date}.mp3')
    clip = AudioSegment.from_file(path)
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    model = os.getenv('AUDIO_REVIEW_MODEL', 'gemini-3.1-flash-lite')
    report = {'date': args.date, 'basis': 'automated model review of the encoded master',
              'human_listened': False, 'model': model, 'audio_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'duration_seconds': len(clip)/1000, 'complete': False, 'clips': []}
    output = Path('rendered_audio_review.json')
    output.write_text(json.dumps(report, indent=2))
    for start, end in windows(len(clip)):
        buf = io.BytesIO()
        clip[start:end].export(buf, format='mp3', bitrate='96k')
        prompt = '''Evaluate the AUDIO itself for this three-person conversational news podcast.
Alex hosts with curiosity and playful leadership; Jamie brings warmth, mischief and
conviction; Rufus brings restrained dry British wit. Do not infer performance from
transcript, filenames, directions, or planned emotion. Assess the sound you hear.
Check clear speech, natural turn-taking, responsive teasing and warmth, pace variation,
obvious glitches, clipped words, repeated speech, spoken acting tags, distracting
music, and fatigue. Assess transitions/ending/Rufus feature only if audible in this clip.
Do not call the clip boundary a cut-off defect: sections overlap ten seconds.
Do not invent defects or demand jokes during serious facts. Do not fact-check the news.
Return one JSON object with audio_evaluated:boolean, scores:{intelligibility:1-5,
natural_delivery:1-5,cast_connection:1-5,pacing:1-5}, observations:[{seconds:number,
description:string}], defects:[{seconds:number,description:string}]. Use timestamps
relative to this clip and specific audible evidence. Empty defects is permitted.
If audio is inaccessible set audio_evaluated:false. This is model review, not human
listening approval. Do not infer a real studio, microphone technique or human
recording from clear synthetic speech. Describe only audible qualities.
''' + f'CLIP duration: {(end-start)/1000:.3f} seconds. All timestamps must be relative to this clip, between 0 and {(end-start)/1000:.3f}. No episode-global timestamps.'
        result = None
        correction = ''
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model,
                    contents=[types.Part.from_text(text=prompt + correction), types.Part.from_bytes(data=buf.getvalue(), mime_type='audio/mpeg')],
                    config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0.2, max_output_tokens=3000))
                result = validate(json.loads(response.text), (end-start)/1000)
                break
            except Exception as exc:
                if isinstance(exc, ValueError):
                    correction = '\nPrevious response failed local validation: ' + str(exc)[:200] + '. Re-evaluate and return the complete valid JSON object.'
                if attempt == 1:
                    report['error_type'] = type(exc).__name__
                    if isinstance(exc, ValueError):
                        report['validation_error'] = str(exc)[:200]
                    output.write_text(json.dumps(report, indent=2))
                    raise RuntimeError('Rendered audio review incomplete') from None
        result.update(start_seconds=start/1000, end_seconds=end/1000)
        report['clips'].append(result)
        output.write_text(json.dumps(report, indent=2))
        print(f'Reviewed encoded master {start/1000:.0f}-{end/1000:.0f}s', flush=True)
    report['complete'] = True
    report['defects_for_inspection'] = [dict(row, episode_seconds=round(c['start_seconds']+row['seconds'], 2))
                                      for c in report['clips'] for row in c['defects']]
    report['status'] = 'needs_inspection' if report['defects_for_inspection'] else 'no_audible_defects_reported'
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps({'complete': True, 'status': report['status'], 'clips': len(report['clips'])}))


if __name__ == '__main__':
    main()
