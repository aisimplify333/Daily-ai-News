import json
from unittest.mock import patch

from jamie_transformation import research, source_matches


def test_transient_search_error_uses_remaining_attempt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch('jamie_transformation.valid_case', return_value=True), patch('jamie_transformation.source_matches', return_value=True):
        calls = iter([TimeoutError('private request detail'), json.dumps({'subject': 'verified'})])
        def search(_):
            result = next(calls)
            if isinstance(result, Exception):
                raise result
            return result
        assert research('2026-10-23', search)['subject'] == 'verified'
    report = (tmp_path / 'jamie_research_report.json').read_text()
    assert 'research_provider_error' in report
    assert 'private request detail' not in report


def test_source_typography_normalization_does_not_change_numbers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    case = {'source_url': 'https://example.org/case', 'source_quote': "The team's new assistant reduced average handling time from twelve minutes to four minutes."}
    raw = '<p>The team’s new assistant reduced average handling time from twelve minutes to four minutes.</p>'.encode()
    with patch('urllib.request.urlopen') as opened:
        opened.return_value.__enter__.return_value.read.return_value = raw
        assert source_matches(case)
        case['source_quote'] = case['source_quote'].replace('four', 'two')
        assert not source_matches(case)
