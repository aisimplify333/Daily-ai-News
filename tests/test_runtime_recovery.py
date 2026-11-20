import ast
from pathlib import Path
import unittest

class RuntimeRecoveryTests(unittest.TestCase):
    def test_word_band_is_advisory_and_does_not_trigger_padding_or_trimming(self):
        source = (Path(__file__).resolve().parents[1] / 'writer_room_v3_1.py').read_text()
        tree = ast.parse(source)
        gates = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'hard_gate_keys' for t in n.targets))
        self.assertNotIn('runtime_word_band', ast.literal_eval(gates))
        tests = [ast.unparse(n.test) for n in ast.walk(tree) if isinstance(n, ast.If)]
        self.assertNotIn('final_words < min_episode_words', tests)
        self.assertNotIn('final_words > max_episode_words', tests)
