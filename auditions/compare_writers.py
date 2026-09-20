"""Four text-only calls. No retries, fallbacks, TTS, publication or production edits."""
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from listener_editorial import EDITORIAL_DIRECTION

SYSTEM = 'You are the lead writer of The AI Edge. Produce original, factual, engaging ensemble podcast dialogue. Return only the requested scene and title. Do not identify your model or provider.'
RUBRIC = {'clarity_and_payoff':25,'responsive_chemistry':25,'distinct_cast':20,'earned_humor':15,'momentum_and_shareability':15}

def call(provider, prompt):
    if provider == 'sonnet':
        model='claude-sonnet-4-6'
        url='https://api.anthropic.com/v1/messages'
        headers={'x-api-key':os.environ['ANTHROPIC_API_KEY'],'anthropic-version':'2023-06-01'}
        payload={'model':model,'max_tokens':2400,'system':SYSTEM,'messages':[{'role':'user','content':prompt}]}
    else:
        model='grok-4.3'
        url='https://api.x.ai/v1/chat/completions'
        headers={'Authorization':'Bearer '+os.environ['XAI_API_KEY']}
        payload={'model':model,'max_tokens':2400,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}]}
    headers['Content-Type']='application/json'
    start=time.monotonic()
    try:
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
        with urllib.request.urlopen(req, timeout=180) as response:
            result=json.load(response)
        if provider == 'sonnet':
            text='\n'.join(x['text'] for x in result.get('content',[]) if x.get('type')=='text')
            finish=result.get('stop_reason')
        else:
            text=result['choices'][0]['message'].get('content') or ''
            finish=result['choices'][0].get('finish_reason')
        return {'text':text,'model_requested':model,'model_returned':result.get('model'), 'usage':result.get('usage'), 'finish':finish,'seconds':round(time.monotonic()-start,2)}
    except urllib.error.HTTPError as e:
        return {'text':'','model_requested':model,'error':'HTTP '+str(e.code)}
    except Exception as e:
        return {'text':'','model_requested':model,'error':type(e).__name__}

def main():
    if os.environ.get('GITHUB_RUN_ATTEMPT','1') != '1':
        raise SystemExit('No automatic repeat spending: audition only runs on attempt 1.')
    if not all(os.environ.get(k) for k in ('ANTHROPIC_API_KEY','XAI_API_KEY')):
        raise SystemExit('Provider credentials missing; no calls made.')
    slate=json.loads(Path('auditions/frozen_sources.json').read_text())
    all_results={'rubric':RUBRIC,'basis':'Script-only pilot, two topics, one sample per model per topic. Score adherence to frozen source packet, not independent source verification. Provider defaults for sampling; no shared seed. Maximum 4 requests, 2400 output tokens each.','blind':[], 'reveal':{}}
    for scene,story in enumerate(slate,1):
        prompt='Write a 420-480 spoken-word scene, approximately three minutes, for The AI Edge. Audience: busy AI-curious listeners who want useful news and enjoy this cast. Begin with TITLE: and a specific 6-14-word factual title. Then only ALEX:, JAMIE:, RUFUS: lines. No intro music, ads, stage directions, or signoff. Explain what changed early, explore genuine competing interpretations, and finish with a concrete useful takeaway. Short responsive turns; no host exceeds 55 words at once. Do not imitate any named writer. No invented history, listener submissions, quotes, numbers or claims. This is a frozen September 15 editorial test, not current reporting. Only the following packet supplies factual claims; unknowns must remain unknown.\n\n'+EDITORIAL_DIRECTION+'\n\nSOURCE PACKET:\n'+json.dumps(story,ensure_ascii=False)
        pair=[]
        for provider in ('sonnet','grok'):
            pair.append((provider,call(provider,prompt)))
        random.SystemRandom().shuffle(pair)
        for label,(provider,result) in zip(('A','B'),pair):
            sample=f'{scene}{label}'
            all_results['blind'].append({'id':sample,'source':story,'script':result['text'],'word_count':len(re.findall(r"\b[\w\u2019'-]+\b",result['text'])),'complete':bool(result['text']) and result.get('finish') in ('stop','end_turn'),'error':result.get('error'),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
            all_results['reveal'][sample]={'provider':provider,**{k:v for k,v in result.items() if k!='text'}}
    out=Path('audition_results');out.mkdir(exist_ok=True)
    (out/'results.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2))
    print('AUDITION_RESULT_JSON='+json.dumps(all_results,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
