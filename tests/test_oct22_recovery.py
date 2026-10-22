from writer_room_v3_1 import _ensure_connection_elements
from editorial_contract import ensure_feature_fallback, feature_status


def test_closing_preserves_complete_question_and_is_idempotent():
    question = 'If your company deployed an AI agent that made a costly mistake, who carries accountability: the engineer, the manager who approved it, or the vendor who sold the platform?'
    script = '### SEGMENT 5\nALEX: Today\'s question: ' + question + '\nALEX: Today’s question for you: abandoned frag'
    board = {'listener_question': question[:139]}
    result = _ensure_connection_elements(script, [], board, '2026-10-22')
    assert question in result
    assert 'abandoned frag' not in result
    assert result.count('Today’s question for you:') == 1
    assert result == _ensure_connection_elements(result, [], board, '2026-10-22')


def test_generated_long_question_is_not_cut_mid_word():
    question = 'Which team should take responsibility when an automated assistant makes a mistake that affects a customer and the vendor and manager disagree about who authorized the action?'
    result = _ensure_connection_elements('### SEGMENT 5\nALEX: A useful takeaway.', [], {'listener_question': question}, '2026-10-22')
    assert question in result


def test_early_return_moves_after_existing_studio_response():
    script = ('### SEGMENT 3\nALEX: Rufus, take us to the global desk.\n'
              'RUFUS: Existing reporting.\nJAMIE: A setup question.\n'
              'ALEX: That\'s a real distinction. Rufus — take us on location.\n'
              'RUFUS: Picture the meeting.\nALEX: Back to the wider story.\n'
              'JAMIE: But does that solve the issue?\nRUFUS: That remains uncertain.\n'
              '### SEGMENT 4\nALEX: Next.')
    result = ensure_feature_fallback(script)
    assert feature_status(result)['present']
    assert result.index('Back to the wider story.') > result.index('That remains uncertain.')
    assert result.count('take us') == 1
    assert ensure_feature_fallback(result) == result


def test_marker_repair_does_not_invent_missing_dialogue():
    script = '### SEGMENT 3\nALEX: Rufus, take us on location.\nRUFUS: Imagine the room.\nALEX: Back to the wider story.\n### SEGMENT 4\nALEX: Next.'
    assert not feature_status(ensure_feature_fallback(script))['present']
