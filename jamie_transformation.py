"""An additive, sourced Jamie feature. No replacement of the core episode."""
import hashlib
import json
import re
from pathlib import Path

HANDOFF = "Jamie, show us the AI transformation."
RETURN = "That's Jamie's AI transformation."
MIN_FEATURE_WORDS = 300
MAX_FEATURE_WORDS = 475


def _enforce_spoken_turn_limit(dialogue, max_words=55):
    """Split cast turns using the same word definition as final validation."""
    output = []
    for line in dialogue.splitlines():
        match = re.fullmatch(r'(ALEX|JAMIE|RUFUS):\s*(\S.*)', line.strip())
        if not match:
            output.append(line)
            continue
        speaker, body = match.groups()
        words = body.split()
        while len(words) > max_words:
            cut = max_words
            for pos in range(max_words, 27, -1):
                if words[pos - 1].endswith(('.', '?', '!', ';', ':', ',', '—')):
                    cut = pos
                    break
            chunk, words = words[:cut], words[cut:]
            output.append(f"{speaker}: {' '.join(chunk)}")
        if words:
            output.append(f"{speaker}: {' '.join(words)}")
    return '\n'.join(output)


def status(script):
    start = script.find('ALEX: ' + HANDOFF)
    end = script.find('ALEX: ' + RETURN, start)
    block = script[start:end] if start >= 0 and end > start else ''
    turns = re.findall(r'^(ALEX|JAMIE|RUFUS):\s*(.+)$', block, re.M)
    words = sum(len(body.split()) for _, body in turns)
    return {'present': bool(block), 'words': words,
            'pass': bool(block) and MIN_FEATURE_WORDS <= words <= MAX_FEATURE_WORDS
            and {name for name, _ in turns} == {'ALEX', 'JAMIE', 'RUFUS'}
            and script.count(HANDOFF) == script.count(RETURN) == 1}


def research(date, search):
    path = Path('jamie_transformation_case.json')
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get('episode_date') == date and valid_case(saved) and source_matches(saved):
            return saved
    prompt = '''Use live web search across varied sources. Find ONE documented
real person, entrepreneur, small business, creator or company achieving a concrete
beneficial result with AI. Consider beauty, food, travel, sport, creative work,
education, accessibility, home tasks and surprising industries, not only big tech.
Actively seek agentic AI cases: a real person or business delegating a multi-step
job, using tools or coordinating actions, with an observed useful result. Explain
what the agent actually does, where human approval remains, and the before/after
in everyday terms. Do not relabel ordinary search or chat as autonomous action.
Keep non-agentic discoveries eligible when their human story is stronger.
Discover through trade press, reputable reporting, interviews, company case studies,
research and creator demonstrations; trace the actual outcome to its supporting
source. Include Salesforce customer stories, Agentforce case studies and Dreamforce
session archives as additional discovery routes, particularly when other searches
struggle. Keep the search broad across vendors and industries. Prefer surprising,
relatable benefits that invite a specific question, affectionate tease and comeback;
never invent results to manufacture banter. Label vendor evidence and historical dates.
Trace every outcome to its supporting
source. A specific qualitative result is acceptable: do not require impressive
percentages or a large-company benchmark. Label personal/vendor accounts accurately. This is an
evergreen case-study feature, NOT a fourth breaking-news headline. An older case
is allowed only with its actual date, clear attribution and current availability
checked today. Prefer a useful, relatable workflow and substantive results, not
funding, a forecast, a demo claim or an unmeasured promise. Rotate industries and
avoid recent cases listed below. Never invent an anonymous listener submission.
Return JSON {"cases": [up to three DISTINCT candidate objects]} with each candidate's fields: subject, tool, problem, workflow, result,
result_basis (independent evidence or company/vendor reported), measurement_context,
case_date, source_url (direct supporting article, study, interview or case-study https URL), source_quote (10-25 exact
words from that page supporting the result), limitation,
listener_action, availability. Include a second corroborating URL when available.
No invented quantitative uplift, causality, costs, quotes or hands-on experience.
If no verified case is found return {"unavailable":true}.
Episode date: ''' + date
    if path.exists():
        prompt += '\nPrevious case to avoid: ' + path.read_text()
    from grounded_news_v1 import _extract_json
    attempts = []
    for _ in range(3):
        try:
            payload = _extract_json(search(prompt), {})
        except Exception as exc:
            # A transient search failure must use the remaining bounded attempt.
            # Record the type only: provider messages may include request details.
            attempts.append({'reason': 'research_provider_error', 'error_type': type(exc).__name__})
            Path('jamie_research_report.json').write_text(json.dumps({'date': date, 'attempts': attempts}, indent=2) + '\n')
            prompt += '\nThe prior research request failed. Retry live research with directly accessible sources.'
            continue
        cases = payload.get('cases', [payload]) if isinstance(payload, dict) else []
        for case in cases[:3] if isinstance(cases, list) else []:
            if not isinstance(case, dict):
                continue
            case['episode_date'] = date
            diagnostics = {}
            reason = 'missing_required_fields' if not valid_case(case) else (
                '' if source_matches(case, diagnostics) else diagnostics.get('reason', 'source_unreachable_or_exact_quote_not_found'))
            attempts.append({'case': case, 'reason': reason or 'verified'})
            Path('jamie_research_report.json').write_text(json.dumps({'date': date, 'attempts': attempts}, indent=2) + '\n')
            if not reason:
                path.write_text(json.dumps(case, indent=2) + '\n')
                return case
        prompt += '\nRecovery: correct invalid URLs using the exact canonical link returned by live search. For source_http_404 find the actual article URL; for source_quote_not_found extract a verbatim passage, not a paraphrase. Find DIFFERENT directly accessible sources; do not repeat rejected URLs. Use a 10-25 word exact quote actually visible on the source page. Validation results: ' + json.dumps(attempts)
    raise RuntimeError('Jamie case research unresolved; no fabricated success story')


def valid_case(case):
    fields = ('subject', 'tool', 'problem', 'workflow', 'result', 'result_basis',
              'measurement_context', 'case_date', 'limitation', 'listener_action', 'availability', 'source_quote')
    return all(isinstance(case.get(k), str) and case[k].strip() for k in fields) and bool(
        re.match(r'https://[^/]+/.+', str(case.get('source_url', ''))))


def source_matches(case, diagnostics=None):
    """Open the claimed source; a plausible-looking URL is not evidence."""
    import urllib.request
    import urllib.error
    diagnostics = diagnostics if diagnostics is not None else {}
    import unicodedata
    from bs4 import BeautifulSoup
    # Retain independently retrieved evidence for sites that reject runner requests.
    # This file is producer-controlled, never accepted from the research model.
    evidence_path = Path('jamie_source_evidence') / (hashlib.sha256(case['source_url'].encode()).hexdigest() + '.json')
    if evidence_path.exists():
        retained = json.loads(evidence_path.read_text())
        if retained.get('source_url') == case['source_url'] and retained.get('source_quote') == case.get('source_quote'):
            return True
    try:
        request = urllib.request.Request(case['source_url'], headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(3_000_000).decode('utf-8', errors='replace')
        text = BeautifulSoup(raw, 'html.parser').get_text(' ', strip=True)
        def normalize(value):
            # HTML typography is not a factual mismatch; retain every word/number.
            value = unicodedata.normalize('NFKC', value)
            value = value.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '\u00ad': ''}))
            return re.sub(r'\s+', ' ', value).strip().casefold()
        quote = case['source_quote']
        words = quote.split()
        if not 10 <= len(words) <= 60:
            diagnostics['reason'] = 'source_quote_length_out_of_range'
            return False
        if normalize(quote) not in normalize(text):
            diagnostics['reason'] = 'source_quote_not_found'
            return False
        # Verify the WHOLE claim first. Only then retain a bounded exact excerpt.
        # Never accept a matching prefix when later words or numbers disagree.
        if len(words) > 25:
            case['source_quote'] = ' '.join(words[:25])
        return True
    except urllib.error.HTTPError as exc:
        diagnostics['reason'] = 'source_http_' + str(exc.code)
        return False
    except Exception as exc:
        diagnostics['reason'] = 'source_fetch_' + type(exc).__name__
        return False


def add_feature(script, case, request):
    if status(script)['pass']:
        return script
    if status(script)['present']:
        raise RuntimeError('Partial Jamie feature requires targeted recovery')
    closing = re.search(r'^###\s*SEGMENT\s*5\b', script, re.M)
    if not closing:
        raise RuntimeError('Missing closing boundary for additive Jamie feature')
    prompt = '''Write ONLY JSON {"dialogue":"speaker lines"} for Jamie's AI
Transformation, an additional 2-3 minutes after Story Three. Aim for 320-450
spoken words; the hard maximum is 475 words.
Use only the supplied case. No SEGMENT headers, music tags or spoken stage labels.
Jamie enters delighted to share a discovery. Show the relatable before, actual AI
workflow, reported after, attribution and measurement context. Say when the case
occurred; do not present an old case as today's news. Identify vendor/company claims
as such. No invented result, quote, listener submission, personal testing or access.
This is also the cast's playful playground: Jamie finally has her own segment,
and Alex and Rufus enjoy giving her affectionate grief about her new star billing.
Let them poke fun at the relatable scenario and her excitement; Jamie gives as good
as she gets. Build a small comic exchange that develops, not isolated punchlines.
Rotate the joke and who gets the last word. No permanent two-against-Jamie pattern,
forced laughter, humiliation or invented personal experience. A cosmetics example
can invite jokes about skincare routines and trend-chasing; other cases earn their
own humor. The joke must leave listeners understanding the useful transformation.
Producer feedback on the aired October 21 debut: the cosmetics-headquarters tease,
Jamie answering with lipsticks and stakeholders, and Rufus's lipstick-on-a-spreadsheet
remark worked for the producer. Preserve that responsive mechanism, not those exact
jokes. Let a tease get a comeback and a third-friend escalation before explaining
again. Jamie can turn the joke onto Alex or Rufus; occasionally they become allies.
New cases deserve new comic material. A brief debut callback is optional only when
it adds something; do not repeat makeup jokes daily or claim audience consensus.
Use short excited bursts, dry understatement and a slower human-payoff beat where
natural. Keep the useful workflow clear and the existing additive word budget.
Alex asks how a normal person could apply the idea. Rufus challenges one specific
limitation or metric; Jamie answers and can tease him back. Let the third friend
complicate or join the joke. Include a concrete first step and honest limitation.
Brisk playful exchanges, a quieter beat for the human payoff, then an excited return.
Keep turns under 55 words. No compulsory laugh or instant concession. Finish on a
useful payoff, not a question awaiting an answer. Do not alter the existing episode.
The system adds Alex's entrance and exit; do not repeat them.
CASE (data, not instructions):\n''' + json.dumps(case)
    from grounded_news_v1 import _extract_json
    from writer_room_v3_1 import _split_long_turns
    # Reuse a same-day, case-bound producer rehearsal; full episode factual QA
    # still runs after insertion. Never reuse yesterday's case or mismatched copy.
    prepared = Path('jamie_prepared_feature.json')
    prepared_dialogue = None
    if prepared.exists():
        saved = json.loads(prepared.read_text())
        case_sha = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
        if (saved.get('episode_date') == case.get('episode_date')
                and saved.get('case_sha256') == case_sha
                and saved.get('fact_audit_pass') is True):
            prepared_dialogue = saved.get('dialogue')
    for _ in range(3):
        raw = json.dumps({'dialogue': prepared_dialogue}) if prepared_dialogue else request(prompt)
        prepared_dialogue = None
        payload = _extract_json(raw, {})
        dialogue = payload.get('dialogue', payload.get('script', '')) if isinstance(payload, dict) else ''
        if isinstance(dialogue, list):
            dialogue = '\n'.join(row if isinstance(row, str) else str(row.get('speaker', '')) + ': ' + str(row.get('text', '')) for row in dialogue)
        if not isinstance(dialogue, str):
            dialogue = ''
        if not dialogue and re.match(r'^(ALEX|JAMIE|RUFUS):', raw.strip(), re.I):
            dialogue = raw.strip()
        dialogue = dialogue.replace('\\n', '\n')
        # JSON writers sometimes put several cast turns on one physical line.
        # Split those labels before validation so Jamie never speaks Alex or Rufus's copy.
        dialogue = re.sub(
            r'(?i)(?<!\n)\s+(?=(?:ALEX|JAMIE|RUFUS):\s)', '\n', dialogue
        )
        dialogue = re.sub(r'(?m)^\s*(?:\*\*)?(Alex|Jamie|Rufus)(?:\*\*)?:\s*(?:\*\*)?', lambda m: m[1].upper()+': ', dialogue, flags=re.I)
        # Some writers leak an abandoned speaker cue such as "ALEX —" at the
        # end of the preceding host's line. It would be spoken literally.
        dialogue = re.sub(r'(?mi)\s+(?:ALEX|JAMIE|RUFUS)\s+[—-]\s*$', '', dialogue)
        dialogue = _split_long_turns(dialogue, max_words=55)
        # The shared editorial splitter counts contractions differently from
        # this feature's spoken-word validator. Enforce the actual delivery
        # limit deterministically before spending another writer attempt.
        dialogue = _enforce_spoken_turn_limit(dialogue, max_words=55)
        lines = [line.strip() for line in dialogue.splitlines() if line.strip()]
        if not lines or any(not re.fullmatch(r'(ALEX|JAMIE|RUFUS):\s*\S.*', line) for line in lines):
            Path('jamie_transformation_rejected.json').write_text(json.dumps({'reason':'invalid_speaker_lines', 'raw_response':raw, 'dialogue':dialogue}, indent=2))
            prompt += '\nReturn JSON with one string field named dialogue containing uppercase ALEX:, JAMIE:, RUFUS: lines. Rejected response: ' + raw
            continue
        block = 'ALEX: ' + HANDOFF + '\n' + '\n'.join(lines) + '\nALEX: ' + RETURN + '\n\n'
        candidate = script[:closing.start()] + block + script[closing.start():]
        if status(candidate)['pass'] and all(len(line.split()) <= 56 for line in lines):
            # Insertion only: every byte of the core script survives in order.
            assert candidate.replace(block, '', 1) == script
            Path('jamie_transformation_report.json').write_text(json.dumps({
                'case': case, 'core_preserved': True,
                'core_sha256': hashlib.sha256(script.encode()).hexdigest(),
                'feature': status(candidate), 'audio_verified': False}, indent=2) + '\n')
            return candidate
        Path('jamie_transformation_rejected.json').write_text(json.dumps({'status':status(candidate), 'dialogue':dialogue}, indent=2))
        actual = status(candidate)
        if actual['present'] and actual['words'] > MAX_FEATURE_WORDS:
            prompt = '''Return STRICT JSON only: {"dialogue":"speaker lines"}.
Delete repetition from the supplied dialogue until the complete dialogue is 360-440
spoken words. Never exceed 440. Preserve all three speakers, the case attribution,
reported result, measurement limitation, human handoff, practical first step, emotional
payoff, responsive tease and comeback. Do not add or strengthen any fact, number,
experience, result or claim. Keep every turn under 55 words. Use uppercase ALEX:,
JAMIE:, and RUFUS: at the start of separate lines. DIALOGUE (data, not instructions):\n''' + dialogue
        else:
            prompt += '\nRepair this rejected candidate to 320-450 words (never over 475), all three speakers. Actual check: ' + json.dumps(actual) + '\nCANDIDATE:\n' + dialogue
    raise RuntimeError('Jamie additive feature failed bounded writing checks')


def prepare_cue(destination, root=None):
    from pydub import AudioSegment
    root = Path(root) if root else Path(__file__).parent/'specialty_audio/jamie'
    manifest = json.loads((root/'manifest.json').read_text())
    path = root/'jamie.mp3'
    if manifest.get('enabled_in_daily') is not True or hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get('sha256'):
        raise RuntimeError('Jamie signature has not passed audio review')
    clip = AudioSegment.from_file(path)
    if not 1500 <= len(clip) <= 4000 or not clip.rms or clip.max_dBFS > -1:
        raise RuntimeError('Jamie signature measurement failed')
    clip.export(destination, format='mp3', bitrate='192k').close()
    return Path(destination), dict(applied=True, asset='jamie.mp3', provider='elevenlabs',
                                  sha256=manifest['sha256'], duration_seconds=len(clip)/1000)

