"""Four bounded takes through the production Gemini adapter; no publishing."""
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hybrid_tts_router_v3_1 import _gemini_tts_to_file, STATS

out = Path('auditions/alex_output')
out.mkdir(parents=True, exist_ok=True)
text = ('Jamie, I want this technology to work. But a remarkable demonstration is not the same as a dependable colleague. '
        'Who checks the result when everyone is rushing? Rufus, please tell me your answer is not another committee. '
        'All right, fair point. Here is what matters: if this genuinely gives someone an hour back with their family, that is progress. '
        'Start small. Check the evidence. And give the time back to the person.')
rows = []
for speaker, voice, words, speed in [
    *[('ALEX', voice, text, 1.01) for voice in ('Orus', 'Algenib', 'Charon')],
    ('RUFUS', 'Iapetus', 'Another committee? Alex, please. This is a task force. Entirely different biscuits. But seriously, Jamie is right. Count the checking time. If the tool saves an hour and creates two hours of supervision, we have simply given the problem a nicer logo.', 1.12),
]:
    os.environ['GEMINI_TTS_VOICE_' + speaker] = voice
    raw = out / (speaker + '_' + voice + '_raw.mp3')
    _gemini_tts_to_file(words, speaker, 'neutral', raw)
    target = out / (speaker + '_' + voice + '.mp3')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-af', f'atempo={speed},loudnorm=I=-16:TP=-1.5:LRA=11', '-b:a', '192k', str(target)], check=True)
    seconds = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(target)]))
    assert 5 < seconds < 90
    rows.append(dict(speaker=speaker, voice=voice, seconds=seconds, speed=speed, text=words, file=target.name))
    raw.unlink()
    for wav in out.glob('*.wav'):
        wav.unlink()
(out / 'manifest.json').write_text(json.dumps({'takes': rows, 'provider_calls': STATS['calls'], 'listening_review': 'Pending user audition; technical validation only'}, indent=2))
(out / 'README.txt').write_text('Alex: identical passage, lower-register American host direction, 1.01x tempo. Compare Orus, Algenib and Charon for gravitas, warmth and conversational responsiveness. Rufus: Iapetus, brisk British direction, 1.12x tempo without pitch shift. Fictional rehearsal, not an episode. No audio has been published to the feed.\n')
print(json.dumps(rows, indent=2))
