import unittest
from dialogue_editor import edit_dialogue


class DialogueEditorTests(unittest.TestCase):
    def run_edit(self, response, candidate=None):
        original = "ALEX: The source reports 12 trials. JAMIE: That is useful."
        current = {"failed": [], "soft_flags": [], "distance": 0}
        def request():
            if isinstance(response, Exception):
                raise response
            return response
        return original, edit_dialogue(original, current, request, lambda s: s,
            lambda s: candidate or current, lambda a: a["distance"])

    def test_rewrite_can_improve_wording_without_gaming_counters(self):
        draft = "ALEX: The source reports 12 trials. JAMIE: Which tasks?"
        _, (script, _, report) = self.run_edit(draft)
        self.assertEqual(script, draft)
        self.assertTrue(report["accepted"])
        self.assertFalse(report["listened"])

    def test_number_changes_and_provider_errors_keep_original(self):
        for response in ("ALEX: The source reports 13 trials.", "", RuntimeError("provider")):
            original, (script, _, report) = self.run_edit(response)
            self.assertEqual(script, original)
            self.assertFalse(report["accepted"])

    def test_structural_and_runtime_regressions_keep_original(self):
        for candidate in ({"failed": ["missing_music"], "distance": 0}, {"failed": [], "distance": 2}):
            original, (script, _, report) = self.run_edit("ALEX: 12 trials. JAMIE: Which tasks?", candidate)
            self.assertEqual(script, original)
            self.assertFalse(report["accepted"])
