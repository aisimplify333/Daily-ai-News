from editorial_contract import feature_status,ensure_feature_fallback
from specialty_audio.mixer import choose_bed


def test_wrong_host_cannot_pass_feature_contract_and_is_repaired():
    script='### SEGMENT 3\nRUFUS: Quite. Rufus, take us on location.\nRUFUS: Picture Wall Street.\nJAMIE: What changes?\nRUFUS: The access.\nALEX: Back to the wider story.\n### SEGMENT 4\n'
    assert not feature_status(script)['present']
    fixed=ensure_feature_fallback(script)
    assert 'ALEX: Rufus, take us on location.' in fixed
    assert feature_status(fixed)['present']
    assert ensure_feature_fallback(fixed)==fixed


def test_wall_street_atmosphere_requires_imagined_frame():
    assert choose_bed('Picture Wall Street the morning after a launch.')=='city'
    assert choose_bed('Wall Street reported a launch.') is None


def test_reassigning_navigation_preserves_preceding_reporting():
    s='### SEGMENT 3\nRUFUS: The source reports 12 trials. Rufus, take us on location.\nRUFUS: Picture an office.\nJAMIE: Which trials?\nRUFUS: The reported trials.\nALEX: Back to the wider story.\n### SEGMENT 4\n'
    fixed=ensure_feature_fallback(s)
    assert 'RUFUS: The source reports 12 trials.' in fixed
    assert 'ALEX: Rufus, take us on location.' in fixed
