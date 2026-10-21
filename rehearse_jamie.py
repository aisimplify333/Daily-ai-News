"""Exercise live research and feature writing without generating a full episode."""
import datetime as dt
import json
from pathlib import Path
from openai import OpenAI
from grounded_news_v1 import _grounded_text, fact_check_script, audit_with_repairs
from jamie_transformation import research, add_feature, status


def main():
    date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    case = research(date, _grounded_text)
    client = OpenAI()
    def request(prompt):
        return client.responses.create(model='gpt-5.4-mini', input=prompt, max_output_tokens=5000).output_text
    core = '### SEGMENT 4 — Story Three\n### SEGMENT 5 — Payoff\n'
    script = add_feature(core, case, request)
    script, audits, count = audit_with_repairs(script,
        lambda candidate: fact_check_script(candidate, [{'jamie_transformation_case':case}], date),
        lambda candidate: candidate)
    report = {'date':date, 'feature':status(script), 'fact_audits':audits,
              'fact_repairs':count, 'pass':status(script)['pass'] and audits[-1].get('pass') is True,
              'basis':'sourced writing rehearsal; not episode audio'}
    Path('jamie_rehearsal.txt').write_text(script)
    Path('jamie_rehearsal.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:
        raise RuntimeError('Jamie rehearsal requires correction')


if __name__ == '__main__': main()
