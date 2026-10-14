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
