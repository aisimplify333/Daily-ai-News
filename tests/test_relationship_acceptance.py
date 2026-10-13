import json
from unittest.mock import patch
from final_acceptance import verify, CHECKS


def reviewed(script, evidence):
    response = {'checks': {name: {'pass': True, 'evidence': evidence,
                                 'reason': 'Grounded in these replies.'} for name in CHECKS}}
    with patch('final_acceptance.feature_status', return_value={'present': True, 'duration_in_word_band': True}):
        return verify(script, [], lambda _: json.dumps(response))


def test_review_does_not_require_three_turn_joke_in_each_story():
    script = '### SEGMENT 2\nALEX: What am I missing?\nJAMIE: Let me explain.\n### SEGMENT 3\nRUFUS: The result is uncertain.\n### SEGMENT 4\nJAMIE: I see why you are excited.'
    assert reviewed(script, ['ALEX: What am I missing?', 'JAMIE: Let me explain.'])['pass']


def test_invented_evidence_still_cannot_pass():
    assert not reviewed('ALEX: What am I missing?', ['RUFUS: A line that never aired.'])['pass']


def test_alex_ordinary_question_is_curious_not_automatic_pressure():
    from hybrid_tts_router_v3_1 import infer_mood
    with patch('performance_plan.planned_mood', return_value=None):
        assert infer_mood('How does that work?', 'ALEX') == 'curiosity'
        assert infer_mood('Who gets blamed?', 'ALEX') == 'pressure'


def test_published_early_signoff_is_removed_before_canonical_close():
    import writer_room_v3_1 as writer
    from test_production_contract import SCRIPT as episode, STORIES, BOARD
    bad = episode + "\nALEX: For The AI Edge, I'm Alex. Thanks for listening."
    fixed = writer._ensure_connection_elements(bad, STORIES, BOARD, '2026-10-12')
    assert "For The AI Edge, I'm Alex. Thanks for listening." not in fixed
    assert fixed == writer._ensure_connection_elements(fixed, STORIES, BOARD, '2026-10-12')
