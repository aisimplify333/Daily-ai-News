"""Regression coverage for bounded production recovery."""
from unittest.mock import Mock, patch
import pytest
from grounded_news_v1 import audit_with_repairs
from final_acceptance import repair_and_verify

def test_malformed_audit_does_not_consume_fact_repair_budget():
    audit = Mock(side_effect=[
        {'pass': False, 'unresolved': ['Invalid or ungrounded calculation record']},
        {'pass': False, 'critical_errors': [{'exact_line': 'ALEX: a', 'replacement_line': 'ALEX: b'}]},
        {'pass': False, 'critical_errors': [{'exact_line': 'ALEX: b', 'replacement_line': 'ALEX: c'}]},
        {'pass': True},
    ])
    script, audits, count = audit_with_repairs('ALEX: a', audit, lambda s: s)
    assert script == 'ALEX: c'
    assert count == 2 and len(audits) == 4 and audits[-1]['pass']
    assert audit.call_args.args == ('ALEX: c',)

def test_editorial_retry_receives_rejection_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    failed = {'pass': False, 'failures': ['scene lacks response']}
    request = Mock(return_value='{}')
    seen = []
    def repair(script, stories, board, ask, normalize, assess):
        ask('repair')
        seen.append(script)
        return script + ' next', {'reason': 'introduced numeric claim'}
    with patch('final_acceptance.verify', side_effect=[failed, failed, {'pass': True}]), patch('final_acceptance.review_final_scenes', side_effect=repair):
        script, report = repair_and_verify('ALEX: start', [], {}, request, lambda s:s, lambda s:{})
    assert len(report['repairs']) == 2 and report['pass']
    assert seen == ['ALEX: start', 'ALEX: start next']
    assert 'introduced numeric claim' in request.call_args.args[0]

def test_editorial_failure_still_blocks_after_two_repairs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    failed = {'pass': False, 'failures': ['unresolved']}
    with patch('final_acceptance.verify', return_value=failed), patch('final_acceptance.review_final_scenes', return_value=('ALEX: blocked', {})) as repair:
        with pytest.raises(RuntimeError):
            repair_and_verify('ALEX: start', [], {}, Mock(), lambda s:s, lambda s:{})
    assert repair.call_count == 2
