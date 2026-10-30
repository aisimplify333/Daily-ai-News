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


def test_published_history_and_vendor_aliases(tmp_path, monkeypatch):
    from jamie_transformation import recent_features, repeated_vendor, HANDOFF, RETURN
    monkeypatch.chdir(tmp_path)
    archive = tmp_path / 'episode_audio'
    archive.mkdir()
    (archive / 'podcast_2026-10-28.txt').write_text(HANDOFF + '\nJAMIE: Salesforce helped this retailer.\n' + RETURN)
    (archive / 'podcast_2026-10-29.txt').write_text('No feature in this script')
    history = recent_features()
    assert len(history) == 1
    assert repeated_vendor({'tool': 'Agentforce'}, history)
    assert not repeated_vendor({'tool': 'NotebookLM'}, history)


def test_inventory_is_date_bounded_and_keeps_hypothetical_label(tmp_path, monkeypatch):
    from jamie_transformation import select_inventory
    monkeypatch.chdir(tmp_path)
    case = {'subject':'New idea','feature_mode':'hypothetical_capability','verified_on':'2026-10-30','review_by':'2026-11-06'}
    (tmp_path/'jamie_feature_inventory.json').write_text(json.dumps({'candidates':[case]}))
    with patch('jamie_transformation.valid_case', return_value=True), patch('jamie_transformation.source_matches', return_value=True):
        result = select_inventory('2026-10-30', [])
        assert result['feature_mode'] == 'hypothetical_capability'
        assert select_inventory('2026-11-07', []) is None
        assert select_inventory('2026-10-30', [{'dialogue':'We tried New idea'}]) is None


def test_exhausted_research_uses_verified_inventory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fallback = {'subject':'Verified capability','episode_date':'2026-10-30'}
    with patch('jamie_transformation.select_inventory', return_value=fallback):
        assert research('2026-10-30', lambda _: '{"unavailable":true}') == fallback
    assert json.loads((tmp_path/'jamie_research_report.json').read_text())['fallback'] == 'verified_editorial_inventory'


def test_duplicate_boundaries_and_empty_cues_do_not_trigger_paid_rewrite(tmp_path, monkeypatch):
    from jamie_transformation import add_feature, status, HANDOFF, RETURN
    monkeypatch.chdir(tmp_path)
    dialogue = HANDOFF + '\n' + '\n'.join(name + ': ' + 'useful ' * 26 for name in ['JAMIE','ALEX','RUFUS'] * 4) + '\nALEX: \n' + RETURN
    calls = []
    def request(prompt):
        calls.append(prompt)
        return json.dumps({'dialogue': dialogue})
    result = add_feature('### SEGMENT 5 — Close', {}, request)
    assert status(result)['pass']
    assert len(calls) == 1
    assert result.count(HANDOFF) == result.count(RETURN) == 1


def test_recovery_draft_requires_same_case_and_date(tmp_path, monkeypatch):
    import hashlib
    from jamie_transformation import add_feature, status
    monkeypatch.chdir(tmp_path)
    case = {'episode_date':'2026-10-30', 'subject':'verified capability'}
    dialogue = '\n'.join(name + ': ' + 'useful ' * 26 for name in ['JAMIE','ALEX','RUFUS'] * 4)
    (tmp_path/'jamie_recovery_feature.json').write_text(json.dumps({
        'episode_date':case['episode_date'],
        'case_sha256':hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
        'dialogue':dialogue}))
    def no_paid_call(_):
        raise AssertionError('writer called')
    assert status(add_feature('### SEGMENT 5 — Close', case, no_paid_call))['pass']
    import pytest
    with pytest.raises(AssertionError, match='writer called'):
        add_feature('### SEGMENT 5 — Close', dict(case, episode_date='2026-11-02'), no_paid_call)
