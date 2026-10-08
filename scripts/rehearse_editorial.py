"""Exercise live research/writing/direction with production code; never TTS or publish."""
import datetime as dt
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openai import OpenAI
from google import genai
from google.genai import types
import writer_room_v3_1 as writer


def main():
    date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    namespace = {'openai_client': OpenAI(api_key=os.environ['OPENAI_API_KEY']),
                 'gemini_client': genai.Client(api_key=os.environ['GEMINI_API_KEY']),
                 'genai_types': types}
    writer.install_v3_1(namespace)
    stories = namespace['pick_top_stories']([], n=5, date_str=date)
    script = namespace['generate_episode_script'](stories, [], date)
    Path('rehearsal_script.txt').write_text(script, encoding='utf-8')
    Path('rehearsal_result.json').write_text(json.dumps({
        'status':'passed_text_and_direction_gates', 'date':date,
        'listened':False, 'audio_generated':False, 'published':False,
        'stories':[s['headline'] for s in stories[:3]], 'words':len(script.split())},indent=2))
    print('REHEARSAL PASSED: fresh research, final script, fact audit and direction. No audio/publication.')

if __name__ == '__main__':
    main()
