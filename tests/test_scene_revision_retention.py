from dialogue_editor import edit_story_scenes


def run(revised, allow=False, failures=None):
    original = '### SEGMENT 2\nALEX: ' + 'detail '*99 + '\n### SEGMENT 3\n'
    return original, edit_story_scenes(original, {'failed': [], 'distance': 0},
        lambda *_: revised, lambda s: s,
        lambda s: {'failed': failures or ['runtime_word_band'], 'distance': 1},
        lambda a: a['distance'], allow_runtime_repair=allow)


def test_tighter_scene_retained_only_with_downstream_runtime_repair():
    revision = 'ALEX: ' + 'detail '*89
    original, (script, _, report) = run(revision)
    assert script == original
    _, (script, _, report) = run(revision, allow=True)
    assert script != original and report['accepted']
    assert report['scenes'][0]['runtime_repair_pending']
    assert report['scenes'][0]['candidate'] == revision.strip()
    assert report['scenes'][0]['original'] in original


def test_structural_damage_and_excessive_cuts_still_rejected():
    for revision, failures in [('ALEX: too short', None), ('ALEX: '+'detail '*89, ['missing_sponsor'])]:
        original, (script, _, report) = run(revision, allow=True, failures=failures)
        assert script == original and not report['accepted']


def test_retry_receives_rejection_and_preserves_numbers():
    original = '### SEGMENT 2\nALEX: 8 ' + 'detail '*98 + '\n### SEGMENT 3\n'
    bad = 'ALEX: 9 ' + 'detail '*98
    good = 'ALEX: 8 ' + 'detail '*97 + 'indeed'
    seen = []
    def repair(segment, source, candidate, reason):
        seen.append((segment, source, candidate, reason))
        return good
    script, _, report = edit_story_scenes(original, {'failed': []},
        lambda *_: bad, lambda s:s, lambda s:{'failed': []}, lambda a:0,
        repair_scene=repair)
    assert good in script and report['requested_calls'] == 2
    assert seen[0][2:] == (bad.strip(), 'numeric_receipts_changed')
    assert len(report['scenes'][0]['attempts']) == 2
    assert report['scenes'][0]['attempts'][0]['accepted'] is False
    assert report['scenes'][0]['accepted'] is True


def test_failed_retry_keeps_original_and_stops():
    original = '### SEGMENT 2\nALEX: ' + 'detail '*99 + '\n### SEGMENT 3\n'
    script, _, report = edit_story_scenes(original, {'failed': []},
        lambda *_:'ALEX: short', lambda s:s, lambda s:{'failed': []}, lambda a:0,
        repair_scene=lambda *_:'ALEX: still short')
    assert script == original and report['requested_calls'] == 2
    assert not report['accepted']


def test_accepted_scene_never_requests_retry():
    original = '### SEGMENT 2\nALEX: ' + 'detail '*99 + '\n### SEGMENT 3\n'
    def forbidden(*args):
        raise AssertionError('successful scene must not retry')
    _, _, report = edit_story_scenes(original, {'failed': []},
        lambda *_:'ALEX: '+ 'detail '*99, lambda s:s,
        lambda s:{'failed': []}, lambda a:0, repair_scene=forbidden)
    assert report['accepted'] and report['requested_calls'] == 1
