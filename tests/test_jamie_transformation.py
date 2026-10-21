import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jamie_transformation import add_feature, status, HANDOFF, RETURN, prepare_cue, valid_case


class JamieTests(unittest.TestCase):
    def test_additive_feature_preserves_every_core_line(self):
        core = '### SEGMENT 4 — Story Three\nJAMIE: Keep this story.\n### SEGMENT 5 — Payoff\nALEX: Keep the close.\n'
        dialogue = '\n'.join(name + ': ' + 'useful ' * 26 for name in ['JAMIE','ALEX','RUFUS'] * 4)
        with tempfile.TemporaryDirectory() as directory, patch('jamie_transformation.Path', side_effect=lambda p: Path(directory)/p):
            result = add_feature(core, {}, lambda _: json.dumps({'dialogue':dialogue}))
        self.assertTrue(status(result)['pass'])
        a, b = result.index('ALEX: '+HANDOFF), result.index('### SEGMENT 5')
        self.assertEqual(result[:a] + result[b:], core)
        self.assertEqual(add_feature(result, {}, lambda _: self.fail('duplicate generation')), result)

    def test_missing_partial_and_oversize_features_rejected(self):
        self.assertFalse(status('ALEX: '+HANDOFF)['pass'])
        self.assertFalse(status('ALEX: '+HANDOFF+'\nJAMIE: short\nALEX: '+RETURN)['pass'])
        with self.assertRaises(RuntimeError):
            add_feature('### SEGMENT 5 — Close', {}, lambda _: '{"dialogue":"JAMIE: Too short."}')
        self.assertFalse(valid_case({'subject':'invented'}))

    def test_cue_requires_approval_and_matching_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'manifest.json').write_text('{"enabled_in_daily":false}')
            with self.assertRaises(RuntimeError):
                prepare_cue(root/'out.mp3', root)


if __name__ == '__main__': unittest.main()

class JamieRecoveryTests(unittest.TestCase):
    def test_completed_feature_is_not_sped_up_to_fit(self):
        from post_render_recovery import recover_completed_render
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'episode_audio').mkdir()
            (root/'episode_audio/podcast_2026-10-21.mp3').write_bytes(b'x'*1200)
            (root/'script_2026-10-21.txt').write_text('ALEX: '+HANDOFF)
            with patch('post_render_recovery._duration_seconds', return_value=34*60), patch('post_render_recovery.subprocess.run') as render:
                result = recover_completed_render(root, '2026-10-21', 19, 33)
                self.assertEqual(result['disposition'], 'held_for_editorial_review')
                render.assert_not_called()
