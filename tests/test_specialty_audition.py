import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from specialty_audio import audition


def test_no_paid_retry_after_uncertain_request():
    report = {'takes': [{'name': 'test', 'status': 'attempted'}], 'reserved_credits': 500}
    with tempfile.TemporaryDirectory() as tmp, patch.object(audition, 'ROOT', Path(tmp)), \
         patch.object(audition.urllib.request, 'urlopen') as post:
        with pytest.raises(RuntimeError, match='incomplete'):
            audition.render('test', report, 'test', 'Hello.', {'voice_id':'sample'})
        post.assert_not_called()


def test_credit_cap_blocks_before_network():
    report = {'takes': [], 'reserved_credits': audition.CAP}
    with patch.object(audition, 'get_json') as get, patch.object(audition.urllib.request, 'urlopen') as post:
        with pytest.raises(RuntimeError, match='budget'):
            audition.render('test', report, 'test', 'Hello.', {'voice_id':'sample'})
        get.assert_not_called()
        post.assert_not_called()


def test_custom_voices_not_selected_for_auditions():
    catalog = [{'voice_id':str(i), 'name':str(i), 'category':'premade',
                'labels':{'gender':'male' if i < 3 else 'female', 'accent':'british'}} for i in range(5)]
    catalog.insert(0, {'voice_id':'private', 'name':'A', 'category':'cloned', 'labels':{'gender':'male','accent':'british'}})
    narrators, british = audition.select_voices(catalog)
    assert len(narrators) == 4 and len(british) == 3
    assert all(v['voice_id'] != 'private' for v in narrators+british)
