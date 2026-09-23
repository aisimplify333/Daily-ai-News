"""Four matched, bounded Jamie auditions. Does not modify or publish an episode."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grok_tts_v4 import render_jamie
from hybrid_tts_router_v3_1 import infer_mood

SCENES = [
    "I love that. Give me back the hour I lose to admin, and then we can talk. But I want to see the results first.",
    "I'm glad. If this gives people another way to get help, that matters. We still need to know who can actually use it.",
    "Did you just cite yourself as a source? Rufus, your research department is getting remarkably efficient.",
    "I'm curious. What did they actually measure? Time saved after setup would tell me more than another polished demo.",
]

if __name__ == '__main__':
    out = Path('jamie_emotion_audition');out.mkdir(exist_ok=True)
    results = []
    for index, line in enumerate(SCENES, 1):
        for version, enabled in [('baseline', 'false'), ('directed', 'true')]:
            os.environ['JAMIE_EMOTIONAL_DIRECTION'] = enabled
            mood = infer_mood(line, 'JAMIE') if enabled == 'true' else 'neutral'
            path = out / f'{index:02d}_{version}.mp3'
            result = render_jamie(line, mood, path, primary_only=True)
            results.append({'file': path.name, 'text': line, 'condition': version, **result})
    (out/'manifest.json').write_text(json.dumps({'listened': False, 'purpose': 'matched text, same Ursa voice; compare delivery only', 'takes': results}, indent=2))
