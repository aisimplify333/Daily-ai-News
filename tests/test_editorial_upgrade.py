import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from dialogue_editor import edit_story_scenes
from editorial_contract import feature_status, ensure_feature_fallback
from performance_plan import build_plan, planned_mood
from gemini_cast_tts import payload
import hybrid_tts_router_v3_1 as router

class EditorialUpgradeTests(unittest.TestCase):
    def test_bad_scene_does_not_discard_good_scene(self):
        script = ''.join(f'### SEGMENT {n}\nALEX: There are 12 trials and the result is uncertain.\nJAMIE: Which tasks did they test in the study?\n\n' for n in range(1,6))
        assessment = {'failed':[], 'metrics':{'words':120}}
        def request(n, body):
            if n == 3: return body.replace('12','99')
            return body.replace('Which tasks','What tasks')
        result, _, report = edit_story_scenes(script, assessment, request, lambda x:x,
            lambda x:assessment, lambda a:0)
        self.assertTrue(report['accepted'])
        self.assertEqual([r['accepted'] for r in report['scenes']], [True,False,True])
        self.assertNotIn('99',result)
        self.assertIn('What tasks',result)
        self.assertIn('Which tasks',result)

    def test_contextual_mood_reaches_router_without_changing_speech(self):
        line = 'That gives ordinary people a useful option for the first time.'
        with TemporaryDirectory() as d:
            old=os.getcwd();os.chdir(d)
            try:
                report=build_plan('JAMIE: '+line,lambda p:json.dumps({'directions':[{'id':0,'mood':'warmth','reason':'responds to useful progress'}]}))
                self.assertEqual(router.infer_mood(line,'JAMIE'),'warmth')
                self.assertEqual(report['directions'][0]['text'],line)
                self.assertEqual(planned_mood('ordinary people a useful option for the first time','JAMIE'),'warmth')
            finally: os.chdir(old)

    def test_bad_direction_never_becomes_spoken_text(self):
        with TemporaryDirectory() as d:
            path=str(Path(d)/'plan.json')
            report=build_plan('JAMIE: A fact.',lambda p:json.dumps({'directions':[{'id':0,'mood':'invent-news'},{'id':99,'mood':'amused'}]}),path)
            self.assertEqual(report['directions'],[])
            self.assertTrue(report['issues'])
            self.assertIsNone(planned_mood('A fact.','JAMIE',path))

    def test_sponsor_cannot_be_directed_as_a_joke(self):
        with TemporaryDirectory() as d:
            r=build_plan('JAMIE: The Ledger helps.',lambda p:'{"directions":[{"id":0,"mood":"amused"}]}',str(Path(d)/'p.json'))
            self.assertEqual(r['directions'][0]['mood'],'neutral')

    def test_missing_location_is_honest_desk_fallback(self):
        script='### SEGMENT 3\nRUFUS: '+('A sourced observation. '*25)+'\nJAMIE: '+('A relevant question. '*15)+'\n### SEGMENT 4\nALEX: Next story.'
        result=ensure_feature_fallback(script)
        status=feature_status(result)
        self.assertTrue(status['present'])
        self.assertEqual(status['mode'],'global_desk')
        self.assertNotIn('on location',result)
        self.assertEqual(result,ensure_feature_fallback(result))

    def test_distinct_rufus_instruction_is_not_spoken(self):
        part=payload('The facts are unchanged.','RUFUS','dry_wit','Iapetus','Understate the observation')['contents'][0]['parts'][0]
        self.assertEqual(part['text'],'The facts are unchanged.')
        self.assertIn('non-rhotic',part['speech_metadata']['style'])
        self.assertIn('Lighter',part['speech_metadata']['style'])
