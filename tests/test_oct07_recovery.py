import json
import tempfile
import unittest
import os
import types
from unittest.mock import patch, Mock
from pathlib import Path
from performance_plan import build_plan, planned_mood
from editorial_selection import balanced_story_order, concentrated
from crew_review import review_final_scenes

class RecoveryTests(unittest.TestCase):
    def test_json_director_does_not_receive_spoken_dialogue_system_instruction(self):
        import writer_room_v3_1 as writer
        messages=Mock()
        messages.create.return_value=types.SimpleNamespace(content=[types.SimpleNamespace(text='{"directions":[]}')])
        provider=types.SimpleNamespace(Anthropic=lambda **kwargs:types.SimpleNamespace(messages=messages))
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY':'test-only'}), patch.dict('sys.modules', {'anthropic':provider}):
            writer._anthropic_text({}, 'Direct as JSON', 'test-model', json_output=True)
            system=messages.create.call_args.kwargs['system']
            self.assertIn('valid JSON', system)
            self.assertNotIn('only clean spoken dialogue', system)
            writer._anthropic_text({}, 'Write a scene', 'test-model')
            self.assertIn('only clean spoken dialogue', messages.create.call_args.kwargs['system'])

    def test_full_episode_batched_and_failed_batch_recovers(self):
        script = '\n'.join(f'JAMIE: Useful discovery number {i}.' for i in range(150))
        primary_calls, fallback_calls = [], []
        def response(prompt, record):
            target = json.loads(prompt.split('TARGET TURNS:\n')[-1])
            record.append(target)
            return json.dumps({'directions':[{'id':r['id'], 'mood':'curiosity'} for r in target]})
        def primary(prompt):
            result = response(prompt, primary_calls)
            return '{"directions":[' if len(primary_calls) == 2 else result
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'p.json')
            result = build_plan(script, primary, path, fallback_request=lambda p:response(p, fallback_calls))
            self.assertTrue(result['complete'])
            self.assertEqual(len(result['directions']), 150)
            self.assertEqual(result['requested_calls'], 8)
            self.assertEqual(len(fallback_calls), 1)
            self.assertLessEqual(max(map(len, primary_calls)), 24)
            self.assertEqual(planned_mood('Useful discovery number 35.', 'JAMIE', path), 'curiosity')

    def test_partial_batch_retries_only_missing_and_protects_valid_mood(self):
        calls = []
        def request(prompt):
            target = json.loads(prompt.split('TARGET TURNS:\n')[-1]);calls.append(target)
            return json.dumps({'directions':[{'id':target[0]['id'], 'mood':'warmth'}]})
        with tempfile.TemporaryDirectory() as folder:
            result = build_plan('JAMIE: Good discovery.\nALEX: Tell me more.',request,str(Path(folder)/'p.json'))
        self.assertTrue(result['complete'])
        self.assertEqual([r['id'] for r in calls[1]], [1])
        self.assertEqual(result['directions'][0]['mood'], 'warmth')

    def test_malformed_output_bounded_and_not_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            result=build_plan('JAMIE: A fact.',lambda p:'broken',str(Path(folder)/'p.json'))
        self.assertFalse(result['complete'])
        self.assertEqual(result['requested_calls'],2)
        self.assertEqual(result['directions'],[])

    def test_today_risk_slate_is_not_three_different_experiences(self):
        rows=[{'headline':h,'source_tier':3} for h in (
            "Wikimedia Foundation Confirms Unauthorized Rogue OpenAI Agent Activity",
            "IMF chief urges countries to regulate AI as part of a broader economic warning",
            "Temporal Acquires Cybersecurity Startup Oso to Bolster Agent Security",
            "New AI accessibility tool launches for deaf students")]
        self.assertTrue(concentrated(rows))
        chosen=balanced_story_order(rows)
        self.assertEqual(chosen[0]['headline'],rows[0]['headline'])
        self.assertIn(rows[3]['headline'],[r['headline'] for r in chosen[:3]])
        rows[3]['source_tier']=0
        self.assertTrue(concentrated(balanced_story_order(rows)))

    def test_numbered_edit_and_deletion_preserve_other_scenes(self):
        script='### SEGMENT 2\nALEX: Here is the useful result.\nJAMIE: We already said that.\n### SEGMENT 3\nRUFUS: A different fact.\n### SEGMENT 4\nJAMIE: Next.\n### SEGMENT 5\nALEX: Close.'
        response={'edits':[{'segment':2,'start_line':3,'end_line':3,'new':'','reason':'Remove redundant response'}]}
        result,report=review_final_scenes(script,[],{},lambda p:json.dumps(response),lambda s:s,lambda s:{'failed':[]})
        self.assertEqual(report['accepted_edits'],1)
        self.assertNotIn('We already said',result)
        self.assertIn('RUFUS: A different fact.',result)

if __name__=='__main__':unittest.main()
