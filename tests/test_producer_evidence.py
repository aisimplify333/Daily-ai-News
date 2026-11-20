import json
import unittest

from crew_review import review_final_scenes
from producer_evidence import evidence_report


SCRIPT = '### SEGMENT 2 — Story\nALEX: What changes?\nJAMIE: The announcement describes a new option.\n'


class ProducerEvidenceTests(unittest.TestCase):
    def test_missing_evidence_never_becomes_success(self):
        report = evidence_report(SCRIPT, SCRIPT, None)
        self.assertEqual(len(report['areas']), 10)
        self.assertTrue(all(r['status'] == 'missing_evidence' for r in report['areas'].values()))
        self.assertFalse(report['blocking'])
        self.assertFalse(report['listened'])
        self.assertIsNone(report['quality_score'])

    def test_only_valid_speaker_references_survive(self):
        report = evidence_report(SCRIPT, SCRIPT, {'opening': {
            'evidence_line_numbers': [True, 0, 1, 2, 2, 99, '3']}})
        self.assertEqual(report['areas']['opening']['retained_lines'], ['ALEX: What changes?'])

    def test_edit_invalidates_whole_exchange_citation(self):
        final = SCRIPT.replace('What changes?', 'Who can use it?')
        report = evidence_report(SCRIPT, final, {'responsive_exchange': {
            'evidence_line_numbers': [2, 3]}})
        row = report['areas']['responsive_exchange']
        self.assertEqual(row['status'], 'changed_by_repair_needs_review')
        self.assertEqual(len(row['retained_lines']), 1)
        self.assertNotEqual(report['input_sha256'], report['output_sha256'])

    def test_review_integration_has_no_extra_request_and_survives_repair(self):
        calls = []
        def request(prompt):
            calls.append(prompt)
            return json.dumps({'producer_evidence': {'opening': {'evidence_line_numbers': [2]}},
                               'edits': [{'segment': 2, 'start_line': 2, 'end_line': 2,
                                          'new': 'ALEX: Who can use it?'}]})
        final, report = review_final_scenes(SCRIPT, [], {}, request, lambda x: x,
                                          lambda _: {'failed': []})
        self.assertEqual(len(calls), 1)
        self.assertIn('producer_evidence', calls[0])
        self.assertIn('Who can use it?', final)
        self.assertEqual(report['producer_evidence']['areas']['opening']['status'],
                         'changed_by_repair_needs_review')

    def test_unavailable_provider_retains_script_and_reports_unknown(self):
        final, report = review_final_scenes(SCRIPT, [], {}, lambda _: 'bad JSON',
                                          lambda x: x, lambda _: {'failed': []})
        self.assertEqual(final, SCRIPT)
        self.assertEqual(report['producer_evidence']['areas']['opening']['status'], 'missing_evidence')

    def test_malformed_optional_rows_are_advisory(self):
        report = evidence_report(SCRIPT, SCRIPT, {'opening': [], 'cast_identity': {
            'evidence_line_numbers': '2'}})
        self.assertEqual(report['areas']['opening']['status'], 'missing_evidence')
        self.assertEqual(report['areas']['cast_identity']['status'], 'missing_evidence')


if __name__ == '__main__':
    unittest.main()
