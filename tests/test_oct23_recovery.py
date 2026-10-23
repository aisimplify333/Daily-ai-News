import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from episode_freshness import canonical_url, repeated_story
from grounded_news_v1 import _normalize_story
from jamie_transformation import research


def test_ap_slug_variants_cannot_repeat_published_story():
    article = '13ecd6c459e39a3602f302bcc2412fe9'
    old = {'source_url': 'https://apnews.com/article/' + article}
    new = {'source_url': 'https://apnews.com/article/meta-earnings-muse-' + article}
    assert canonical_url(old['source_url']) == canonical_url(new['source_url'])
    assert repeated_story(new, [{'date': '2026-10-22', 'stories': [old]}]) == '2026-10-22'


def test_search_absence_is_not_a_story():
    now = dt.datetime.now(dt.timezone.utc)
    base = dict(headline='Apple AI update', publisher='Apple',
                published_at=now.isoformat(), original_publication_verified=True,
                source_url='https://www.apple.com/newsroom/archive/?month=10',
                summary='A long enough description of a concrete verified launch. ' * 3,
                facts=['One fact', 'Two facts'])
    assert _normalize_story(base, now) is None
    base['source_url'] = 'https://www.apple.com/newsroom/2026/10/real-release/'
    assert _normalize_story(base, now) is not None
    base['summary'] = 'This candidate is a negative finding rather than a product announcement. ' * 3
    assert _normalize_story(base, now) is None


def test_case_research_tries_alternative_before_abandoning(tmp_path):
    payload = {'cases': [{'subject': 'blocked'}, {'subject': 'accessible'}]}
    with patch('jamie_transformation.Path', side_effect=lambda p: tmp_path / p), \
         patch('jamie_transformation.valid_case', return_value=True), \
         patch('jamie_transformation.source_matches', side_effect=[False, True]):
        result = research('2026-10-23', lambda _: json.dumps(payload))
    assert result['subject'] == 'accessible'
    report = json.loads((tmp_path / 'jamie_research_report.json').read_text())
    assert len(report['attempts']) == 2
    assert report['attempts'][0]['reason'] == 'source_unreachable_or_exact_quote_not_found'


def test_case_research_feedback_preserves_failure_evidence(tmp_path):
    prompts = []
    def search(prompt):
        prompts.append(prompt)
        return json.dumps({'subject': 'incomplete'})
    with patch('jamie_transformation.Path', side_effect=lambda p: tmp_path / p):
        try:
            research('2026-10-23', search)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unverified case accepted')
    assert 'missing_required_fields' in prompts[1]
    assert (tmp_path / 'jamie_research_report.json').exists()
