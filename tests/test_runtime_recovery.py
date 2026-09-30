import ast
from pathlib import Path
import unittest

class RuntimeRecoveryTests(unittest.TestCase):
    def run_repair(self, growth):
        source = (Path(__file__).resolve().parents[1] / 'writer_room_v3_1.py').read_text()
        tree = ast.parse(source)
        block = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                     and ast.unparse(n.test) == 'final_words < min_episode_words')
        calls = []
        def expand(g, script, stories, date, board, add_words):
            calls.append(add_words)
            return script + growth
        ns = dict(final_words=2174, min_episode_words=3300, target_episode_words=3800,
                  script=2174, g={}, stories=[], date_str='2026-09-30', board={}, fuel={},
                  _safe_print=lambda *a: None, _expand_segment_four=expand,
                  _word_count=lambda x:x, stabilize=lambda x:x,
                  _split_long_turns=lambda x, **k:x, _repair_relative_dates=lambda x,d:x,
                  _assess=lambda script,*a: {'metrics':{'words':script}})
        exec(compile(ast.Module(body=[block], type_ignores=[]), '<repair>', 'exec'), ns)
        return ns['final_words'], calls

    def test_large_deficit_reaches_minimum_after_third_pass(self):
        words, calls = self.run_repair(400)
        self.assertGreaterEqual(words, 3300)
        self.assertEqual(len(calls), 3)

    def test_no_progress_stops_without_spending_all_attempts(self):
        words, calls = self.run_repair(0)
        self.assertEqual(words, 2174)
        self.assertEqual(len(calls), 1)

    def test_slow_progress_is_bounded(self):
        words, calls = self.run_repair(50)
        self.assertEqual(len(calls), 6)
        self.assertLess(words, 3300)
