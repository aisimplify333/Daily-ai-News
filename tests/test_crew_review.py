import json
import tempfile
import unittest
from pathlib import Path
from crew_review import review_final_scenes, spoken_leaks
from editorial_selection import balanced_story_order, concentrated
from performance_plan import build_plan, planned_mood


SCRIPT = '''### SEGMENT 1 — Welcome
ALEX: Welcome.
### SEGMENT 2 — Lead
ALEX: The scene plan says the tool supports 12 languages.
JAMIE: That opens up a useful possibility.
### SEGMENT 3 — Second
RUFUS: The price is 20 dollars.
JAMIE: The Ledger supports this show.
### SEGMENT 4 — Third
ALEX: What changes for students?
JAMIE: Access matters here.
### SEGMENT 5 — Close
ALEX: Goodbye.
'''


class CrewReviewTests(unittest.TestCase):
    def review(self, edits, assess=lambda _: {'failed': []}):
        return review_final_scenes(SCRIPT, [], {}, lambda _: json.dumps({'edits': edits}),
                                   lambda x: x, assess)

    def test_local_repair_survives_independent_bad_edit(self):
        old = SCRIPT.splitlines()[3]
        result, report = self.review([
            {'segment': 2, 'old': old, 'new': 'ALEX: The announcement says the tool supports 12 languages.'},
            {'segment': 3, 'old': 'RUFUS: The price is 20 dollars.', 'new': 'RUFUS: The price is 2 dollars.'}])
        self.assertNotIn('scene plan', result)
        self.assertIn('20 dollars', result)
        self.assertEqual(report['accepted_edits'], 1)
        self.assertFalse(report['listened'])

    def test_sponsor_partial_turn_and_cross_scene_are_protected(self):
        edits = [
            {'segment':3, 'old':'JAMIE: The Ledger supports this show.', 'new':'JAMIE: Buy something else.'},
            {'segment':2, 'old':'ALEX: The scene plan', 'new':'ALEX: Nothing'},
            {'segment':4, 'old':'RUFUS: The price is 20 dollars.', 'new':'RUFUS: It costs 20 dollars.'}]
        result, report = self.review(edits)
        self.assertEqual(result, SCRIPT)
        self.assertEqual(report['accepted_edits'], 0)

    def test_invalid_provider_output_preserves_script_and_reports_leaks(self):
        result, report = review_final_scenes(SCRIPT, [], {}, lambda _: 'not JSON', lambda x:x, lambda _: {})
        self.assertEqual(result, SCRIPT)
        self.assertEqual(len(report['remaining_production_language']), 1)
        self.assertEqual(report['requested_calls'], 1)

    def test_runtime_regression_is_rejected(self):
        result, report = self.review([{'segment':4, 'old':'JAMIE: Access matters here.',
            'new':'JAMIE: Yes.'}], lambda x: {'failed': ['runtime_word_band'] if 'JAMIE: Yes.' in x else []})
        self.assertEqual(result, SCRIPT)
        self.assertEqual(report['edits'][0]['reason'], 'new_structural_or_runtime_failure')

    def test_october_slate_and_mixed_security_are_same_listener_frame(self):
        rows = [{'headline': x, 'source_tier':3} for x in (
            'Trump names Jay Clayton to lead a new federal AI task force',
            'OpenAI and Anthropic welcome mandatory reporting of AI agent hacks',
            'AI insiders warn New York City leaders as local governments take up safety concerns',
            'AI accessibility tool launches for deaf students')]
        self.assertTrue(concentrated(rows))
        chosen = balanced_story_order(rows)
        self.assertEqual(chosen[0]['headline'], rows[0]['headline'])
        self.assertIn(rows[3]['headline'], [r['headline'] for r in chosen[:3]])
        rows[1]['headline'] = 'AI security breach exposes passwords'
        self.assertTrue(concentrated(rows))

    def test_daily_context_reaches_director_and_exact_turn_routing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'plan.json')
            captured = []
            context = {'date':'2026-10-07', 'scenes':[{'cast_direction':{'jamie':'Discovery earns delight'}}]}
            def request(prompt):
                captured.append(prompt)
                return json.dumps({'directions':[{'id':0,'mood':'delight','reason':'Useful discovery'},
                                                  {'id':1,'mood':'amused','reason':'Sponsor'}]})
            report = build_plan('JAMIE: This tool opens up a useful possibility.\nJAMIE: Subscribe to TheLEDGR.', request, path, context)
            self.assertIn('Discovery earns delight', captured[0])
            self.assertEqual(planned_mood('This tool opens up a useful possibility.', 'JAMIE', path), 'delight')
            self.assertEqual(report['directions'][1]['mood'], 'neutral')
            self.assertEqual(report['scene_context'], context)

    def test_production_language_checked_for_all_hosts(self):
        self.assertEqual(len(spoken_leaks('RUFUS: The scene plan says so.\nJAMIE: The source packet says so.')), 2)

    def test_spoken_notes_fail_final_writer_gate(self):
        import writer_room_v3_1 as writer
        from test_production_contract import SCRIPT as episode, STORIES, BOARD
        clean = writer._assess(episode, STORIES, BOARD, {})
        dirty = writer._assess(episode + '\nRUFUS: The scene plan says so.', STORIES, BOARD, {})
        self.assertNotIn('no_spoken_production_language', clean['failed'])
        self.assertIn('no_spoken_production_language', dirty['failed'])


if __name__ == '__main__':
    unittest.main()
