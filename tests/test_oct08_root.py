import datetime as dt
import json
import os
import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
import grounded_news_v1 as news
import writer_room_v3_1 as writer
from editorial_selection import concentrated, balanced_story_order, listener_frame
from claim_math import check_calculations
from final_acceptance import verify, repair_and_verify, CHECKS

HEADLINES = ['Manus AI Raises $500 Million After Blocked Meta Deal',
             'Norway Proposes Temporary Ban on AI Glasses in Public Spaces',
             'FCC considers loosening rules for political robocalls that include AI voices']
RATIO_LINE = 'RUFUS: The four-billion valuation is roughly four times revenue.'
REVENUE = 'ALEX: Manus had a hundred million dollars in annualized revenue.'
CALC = {'exact_line': RATIO_LINE, 'left_quote': 'four-billion valuation',
        'right_quote': 'a hundred million dollars', 'operation': 'ratio',
        'ratio_quote': 'four times', 'replacement_line': 'RUFUS: That valuation is roughly forty times revenue.'}

def payload(**kwargs):
    return dict(pass_=True, **kwargs)

class RootRepairs(unittest.TestCase):
    def test_actual_slate_is_risk_concentrated(self):
        rows = [dict(headline=h, source_tier=3) for h in HEADLINES]
        self.assertTrue(concentrated(rows))
        rows.append(dict(headline='Researchers use AI to restore speech for patients', source_tier=3))
        result = balanced_story_order(rows)
        self.assertEqual(result[0]['headline'], HEADLINES[0])
        self.assertIn(rows[-1]['headline'], [r['headline'] for r in result[:3]])
        self.assertFalse(concentrated(result))

    def test_central_question_counts_but_incidental_caveat_does_not(self):
        story = {'headline':'Acme launches drawing tool', 'limitations_or_qualifiers':['Privacy risk']}
        self.assertNotEqual(listener_frame(story), 'accountability_risk')
        story['editorial_case'] = {'distinct_question':'Does this increase surveillance?'}
        self.assertEqual(listener_frame(story), 'accountability_risk')

    def test_homepage_evidence_rejected(self):
        from test_grounded_recovery import story
        row = story(1, source_url='https://www.cnbc.com/')
        self.assertEqual(news._rejection_reason(row, dt.datetime.now(dt.timezone.utc)), 'invalid_source_url')
        self.assertIsNone(news._normalize_story(row, dt.datetime.now(dt.timezone.utc)))

    def test_risk_slate_requires_alternative_or_stops(self):
        from test_grounded_recovery import story
        rows = [story(i, headline=h) for i,h in enumerate(HEADLINES)]
        with tempfile.TemporaryDirectory() as tmp, patch('grounded_news_v1.Path', side_effect=lambda x:Path(tmp)/x):
            news.build_grounded_story_slate.cache_clear()
            with patch.object(news, '_grounded_text', return_value=json.dumps({'stories':rows})), patch.object(news, '_recovery_search', return_value='{}') as refill:
                with self.assertRaisesRegex(RuntimeError, 'variety unresolved'):
                    news.build_grounded_story_slate('2026-10-08', n=3)
                self.assertEqual(refill.call_count, 1)
            news.build_grounded_story_slate.cache_clear()

    def test_arithmetic_recomputed_not_advisory(self):
        errors, unresolved = check_calculations(RATIO_LINE+'\n'+REVENUE, [CALC])
        self.assertEqual(len(errors), 1)
        self.assertIn('= 40, not 4', errors[0]['reason'])
        self.assertFalse(unresolved)

    def test_correct_ratio_and_rounding_pass(self):
        line = RATIO_LINE.replace('four times', 'forty times')
        row = dict(CALC, exact_line=line, ratio_quote='forty times')
        self.assertEqual(check_calculations(line+'\n'+REVENUE, [row]), ([], []))

    def test_omitted_ratio_and_invented_operands_block(self):
        self.assertTrue(check_calculations(RATIO_LINE, [])[1])
        self.assertTrue(check_calculations(RATIO_LINE+'\n'+REVENUE, [dict(CALC, right_quote='$1 million')])[1])

    def test_funding_is_not_valuation(self):
        line = 'JAMIE: Raise more money than the acquisition was worth.'
        script = line+'\nALEX: Five hundred million dollars raised, two billion dollars acquisition.'
        row = dict(exact_line=line, left_quote='hundred million dollars', right_quote='two billion dollars',
                   operation='greater_than', replacement_line='JAMIE: Raise new money at a higher valuation.')
        self.assertEqual(len(check_calculations(script, [row])[0]), 1)

    def test_empty_or_skipped_audit_cannot_pass(self):
        with patch.object(news, '_grounded_text', return_value='{}'):
            with self.assertRaises(RuntimeError): news.fact_check_script('ALEX: Test.', [], '2026-10-08')
        with patch.dict(os.environ, {'ENABLE_GROUNDED_FACT_AUDIT':'false'}):
            with self.assertRaises(RuntimeError): news.fact_check_script('ALEX: Test.', [], '2026-10-08')

    def test_provider_pass_does_not_override_wrong_math(self):
        result = {'pass':True, 'critical_errors':[], 'warnings':['Derived arithmetic'], 'calculations':[CALC]}
        with patch.object(news, '_grounded_text', return_value=json.dumps(result)):
            audit = news.fact_check_script(RATIO_LINE+'\n'+REVENUE, [], '2026-10-08')
        self.assertFalse(audit['pass'])
        fixed, count = news.apply_fact_replacements(RATIO_LINE+'\n'+REVENUE, audit)
        self.assertEqual(count, 1)
        self.assertIn('forty times', fixed)

    def test_unrepairable_factual_error_does_not_disappear(self):
        result = {'pass':False, 'critical_errors':[{'claim_type':'factual_assertion', 'reason':'Wrong year',
                  'exact_line':'ALEX: Earlier this year.'}], 'calculations':[]}
        with patch.object(news, '_grounded_text', return_value=json.dumps(result)):
            audit = news.fact_check_script('ALEX: Earlier this year.', [], '2026-10-08')
        self.assertFalse(audit['pass'])
        self.assertTrue(audit['unresolved'])

    def test_duplicate_generic_follow_removed_and_counted(self):
        from test_production_contract import SCRIPT, STORIES, BOARD
        bad = writer._ensure_connection_elements(SCRIPT, STORIES, BOARD, '2026-10-08')+'\nALEX: I am Alex. Follow the show, and we will see you tomorrow.'
        self.assertGreater(writer._assess(bad, STORIES, BOARD, {})['metrics']['show_follow_cta_count'], 1)
        fixed = writer._ensure_connection_elements(bad, STORIES, BOARD, '2026-10-08')
        self.assertNotIn('Follow the show', fixed)
        self.assertEqual(writer._assess(fixed, STORIES, BOARD, {})['metrics']['show_follow_cta_count'], 1)
        self.assertEqual(fixed, writer._ensure_connection_elements(fixed, STORIES, BOARD, '2026-10-08'))

    def test_verifier_rejects_fabricated_evidence(self):
        response = {'checks':{k:{'pass':True,'evidence':['JAMIE: Imaginary evidence.']} for k in CHECKS}}
        result = verify('ALEX: Real line.', [], lambda _:json.dumps(response))
        self.assertFalse(result['pass'])

    def test_failed_editorial_repair_is_bounded_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd();os.chdir(tmp)
            try:
                request = Mock(return_value='{}')
                with self.assertRaisesRegex(RuntimeError, 'unresolved'):
                    repair_and_verify('ALEX: Real line.', [], {}, request, lambda x:x, lambda x:{'failed':[]})
                self.assertEqual(request.call_count, 3)
                self.assertTrue(Path('script_editorial_blocked.txt').exists())
                self.assertFalse(json.loads(Path('final_acceptance_report.json').read_text())['pass'])
            finally: os.chdir(old)

    def test_verified_clean_script_needs_no_repair(self):
        script = 'ALEX: Rufus, take us on location.\nRUFUS: Picture a scene.\nJAMIE: A challenge.\nRUFUS: A reply.'
        response = {'checks':{k:{'pass':True,'evidence':['JAMIE: A challenge.']} for k in CHECKS}}
        with tempfile.TemporaryDirectory() as tmp, patch('final_acceptance.feature_status', return_value={'present':True,'duration_in_word_band':True}):
            request = Mock(return_value=json.dumps(response))
            result, report = repair_and_verify(script, [], {}, request, lambda x:x, lambda x:{}, str(Path(tmp)/'report.json'))
            self.assertEqual(result,script)
            self.assertTrue(report['pass'])
            self.assertEqual(request.call_count,1)
