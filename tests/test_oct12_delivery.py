import json
from unittest.mock import patch
import pytest
import grounded_news_v1 as news
from verify_publication import check, BASE


def test_malformed_fact_correction_recovers_and_requires_reaudit():
    line = 'RUFUS: The chip is commercially available today. Bless their little cotton socks.'
    bad = {'pass': False, 'critical_errors': [{'reason': 'Availability is planned, not current',
            'exact_line': line}], 'warnings': [], 'calculations': []}
    fixed = 'RUFUS: The chip deployment is planned for next year. Bless their little cotton socks.'
    good = {'pass': False, 'critical_errors': [{'line_number': 1, 'reason': 'Availability is planned, not current',
        'claim_type': 'factual_assertion', 'factual_claim': 'available today',
        'evidence_quote': 'deployment next year', 'source_url': 'https://example.com/chip',
        'replacement_line': fixed}], 'warnings': [], 'calculations': []}
    with patch.object(news, '_grounded_text', return_value=json.dumps(bad)), patch.object(
        news, '_recovery_search', return_value=json.dumps(good)) as recovery:
        result = news.fact_check_script(line, [], '2026-10-12')
    assert recovery.call_count == 1
    assert not result['pass']
    assert result['recovery_from']
    updated, count = news.apply_fact_replacements(line, result)
    assert count == 1 and updated == fixed


def test_empty_recovery_cannot_clear_a_factual_concern():
    bad = {'pass': False, 'critical_errors': [{'reason': 'Wrong date'}], 'calculations': []}
    with patch.object(news, '_grounded_text', return_value=json.dumps(bad)), patch.object(
        news, '_recovery_search', return_value=json.dumps({'pass': True, 'critical_errors': [], 'calculations': []})):
        result = news.fact_check_script('ALEX: Today.', [], '2026-10-12')
    assert not result['pass'] and result['unresolved']


def getter_for(date='2026-10-12', audio=b'ID3'+b'0'*200, duplicate=False):
    url = BASE + '/episode_audio/podcast_' + date + '.mp3'
    item = f'<item><title>A useful show</title><enclosure url="{url}"/></item>'
    feed = ('<rss><channel>'+item*(2 if duplicate else 1)+'</channel></rss>').encode()
    def getter(path, headers=None, limit=None):
        if path.endswith('feed.xml'): return 200, {}, feed
        if path.endswith('.mp3'): return 206, {}, audio
        return 200, {}, url.encode()
    return getter


def test_listener_delivery_requires_dated_feed_audio_and_page():
    assert check('2026-10-12', getter_for())['pass']
    with pytest.raises(ValueError): check('2026-10-12', getter_for('2026-10-09'))
    with pytest.raises(ValueError): check('2026-10-12', getter_for(audio=b'<html>'+b'0'*200))
    with pytest.raises(ValueError): check('2026-10-12', getter_for(duplicate=True))


def test_specialist_science_and_primary_research_sources_recognized():
    assert news._source_tier('Nature News', 'https://www.nature.com/articles/example') >= 2
    assert news._source_tier('MIT News', 'https://news.mit.edu/2026/example') == 3
    assert news._source_tier('Unknown', 'https://mit.edu.example.org/article') == 1


def test_official_government_and_vendor_sources_are_trusted():
    assert news._source_tier('GOV.UK', 'https://www.gov.uk/government/news/example') == 3
    assert news._source_tier('Moonshot AI', 'https://kimi.moonshot.cn/pro') == 3


def test_audio_review_covers_entire_master_and_rejects_unheard_audio():
    from review_rendered_episode import windows, validate
    spans = list(windows(1201000))
    assert spans[0][0] == 0 and spans[-1][1] == 1201000
    assert all(b[0] < a[1] for a, b in zip(spans, spans[1:]))
    with pytest.raises(ValueError): validate({'audio_evaluated': False}, 240)


def test_sparse_checkout_does_not_delete_historical_media(tmp_path):
    import subprocess
    from pathlib import Path
    repo = tmp_path/'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout
    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.test')
    for path in ['main.py', 'episode_audio/podcast_old.mp3', 'episode_audio/podcast_2026-10-12.mp3',
                 'episode_audio/old.json', '.tts_cache/old.mp3', 'assets/chime.mp3']:
        f = repo/path; f.parent.mkdir(exist_ok=True, parents=True); f.write_text('fixture')
    git('add', '.')
    git('commit', '-qm', 'fixture')
    git('sparse-checkout', 'set', '--no-cone', '/*', '!/episode_audio/*.mp3', '!/.tts_cache/',
        '/episode_audio/podcast_2026-10-12.mp3')
    assert not (repo/'episode_audio/podcast_old.mp3').exists()
    assert (repo/'episode_audio/podcast_2026-10-12.mp3').exists()
    assert (repo/'episode_audio/old.json').exists()
    assert (repo/'assets/chime.mp3').exists()
    (repo/'main.py').write_text('updated')
    git('add', '.')
    assert git('diff', '--cached', '--name-status').strip() == 'M\tmain.py'
