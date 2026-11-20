"""Advisory producer evidence. Matching dialogue is not proof of listening quality."""
import hashlib
import re

FOCUS = {
    'opening': 'The opening establishes the real development and a reason to stay.',
    'cast_identity': 'The hosts express distinct perspectives rather than interchangeable summaries.',
    'responsive_exchange': 'A challenge or discovery develops through an answer and a response to it.',
    'scene_variety': 'The three stories differ in question, scene shape and emotional movement.',
    'comic_payoff': 'A specific tease or observation earns a response without explaining the joke.',
    'discovery': 'A sourced mechanism, example or useful possibility advances understanding.',
    'rufus_feature': 'The imagined dispatch or honest desk exchange has substance and a studio response.',
    'listener_value': 'Each story answers its own question with a practical consequence or development to watch.',
    'portable_exchanges': 'Two candidate exchanges stand alone with named subjects and retained qualifications.',
    'closing_payoff': 'The ending answers the opening promise and gives one natural follow invitation.',
}


def review_brief():
    return ('\nAlso return producer_evidence, an object keyed by the following ten areas. '
            'Each value has evidence_line_numbers (numbered input speaker lines), '
            'observation (specific assessment), and next_edit (concrete improvement or empty). '
            'Cite complete exchanges where relevant, not isolated praise. Missing evidence '
            'is allowed and must be reported. These are advisory observations, not new gates. '
            'Do not infer sound quality, publication, or audience impact from a script.\n'
            + '\n'.join(f'{key}: {value}' for key, value in FOCUS.items()))


def evidence_report(original, final, proposed):
    """Resolve input references and invalidate citations changed by accepted edits."""
    proposed = proposed if isinstance(proposed, dict) else {}
    lines = original.splitlines()
    final_lines = set(final.splitlines())
    areas = {}
    for key in FOCUS:
        row = proposed.get(key)
        row = row if isinstance(row, dict) else {}
        refs = row.get('evidence_line_numbers', [])
        refs = refs if isinstance(refs, list) else []
        cited = list(dict.fromkeys(lines[i-1] for i in refs
                                  if type(i) is int and 1 <= i <= len(lines)
                                  and re.match(r'^(ALEX|JAMIE|RUFUS):\s*\S', lines[i-1])))
        retained = [line for line in cited if line in final_lines]
        status = ('missing_evidence' if not cited else
                  'changed_by_repair_needs_review' if len(retained) != len(cited) else
                  'input_evidence_retained_needs_editorial_review')
        areas[key] = {'status': status, 'retained_lines': retained,
                      'observation': str(row.get('observation', ''))[:600],
                      'next_edit': str(row.get('next_edit', ''))[:600]}
    return {'basis': 'model observations on input script; citations checked against output',
            'blocking': False, 'listened': False, 'quality_score': None,
            'input_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'output_sha256': hashlib.sha256(final.encode()).hexdigest(), 'areas': areas}
