from unittest.mock import patch
from urllib.error import HTTPError
import jamie_transformation as j

def test_long_quote_verified_before_excerpt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    quote = 'It used to take 16 to 24 hours for us to process a manual order. Now with Agentforce, we have reduced that time to less than an hour.'
    case = {'source_url':'https://example.org/case', 'source_quote':quote}
    with patch('urllib.request.urlopen') as opened:
        opened.return_value.__enter__.return_value.read.return_value = ('<p>'+quote+'</p>').encode()
        assert j.source_matches(case)
        assert len(case['source_quote'].split()) == 25
        case['source_quote'] = quote.replace('an hour', 'a second')
        details = {}
        assert not j.source_matches(case, details)
        assert details['reason'] == 'source_quote_not_found'

def test_http_error_is_actionable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    case = {'source_url':'https://example.org/missing', 'source_quote':'A documented customer report with enough words to validate its result.'}
    with patch('urllib.request.urlopen', side_effect=HTTPError(case['source_url'],404,'missing',{},None)):
        details = {}
        assert not j.source_matches(case, details)
        assert details['reason'] == 'source_http_404'
