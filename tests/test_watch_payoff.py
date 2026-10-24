from unittest.mock import patch
import pytest
import writer_room_v3_1 as writer


@pytest.mark.parametrize('ending', [
    "So the thing to actually watch isn't the launch.",
    "That's the thing to watch. Does the constitution stay in the lab notes?",
])
def test_expansion_precedes_existing_watch_payoff(ending):
    script = '### SEGMENT 2\nALEX: Here is the development.\nALEX: ' + ending + '\n### SEGMENT 3\nJAMIE: Next story.\n'
    addon = 'JAMIE: The permission settings still need an explicit owner.\nRUFUS: Someone must be accountable for reviewing those permissions.'
    with patch.object(writer, 'expansion_segment', return_value=2), patch.object(writer, '_anthropic_text', return_value=addon):
        result = writer._expand_segment_four({}, script, [{}, {}, {}], '2026-10-23', {}, 100)
    assert addon in result
    assert result.index(addon) < result.index(ending)
    assert result.count(ending) == 1
