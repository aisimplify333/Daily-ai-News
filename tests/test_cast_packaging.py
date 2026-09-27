import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch, Mock
import os
from discovery_art import create_art, monthly_cover
import grok_tts_v4 as grok
from production_review import write_review

class CastPackagingTests(unittest.TestCase):
    def test_rotation_reuses_exact_approved_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'assets').mkdir()
            (root/'assets/cover_rotation_manifest.json').write_text(json.dumps({
                'rotation_pattern': {'9':'cover_rufus.png','10':'cover_trio_master.png'}}))
            for name in ['cover_rufus.png','cover_trio_master.png']:
                (root/'assets'/name).write_bytes(b'approved image '+name.encode())
            for date,name in [('2026-09-27','cover_rufus.png'),('2026-10-01','cover_trio_master.png')]:
                result=create_art('Never overlay this title',date,root)
                self.assertEqual(result['source'],'assets/'+name)
                self.assertEqual(Path(result['cover']).read_bytes(),(root/'assets'/name).read_bytes())
                self.assertEqual(Path(result['thumbnail']).read_bytes(),Path(result['cover']).read_bytes())

    def test_dramatic_controls_reach_provider_without_changing_words(self):
        cases={'pushback':'emphasis','pressure':'build-intensity','interruption':'fast',
               'concern':'soft','concession':'decrease-intensity'}
        line='We still need evidence. The result is not independently verified.'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'XAI_API_KEY':'test','GROK_TTS_CACHE':'false','JAMIE_EMOTIONAL_DIRECTION':'true'}), patch.object(grok,'CACHE_DIR',Path(tmp)/'cache'), patch.object(grok.requests,'post',return_value=Mock(ok=True,content=b'ID3'+b'x'*2000)) as post:
            for mood,tag in cases.items():
                result=grok.render_jamie(line,mood,Path(tmp)/'take.mp3',primary_only=True)
                delivered=post.call_args.kwargs['json']['text']
                self.assertEqual(re.sub(r'</?[^>]+>','',delivered),line)
                self.assertIn(tag,result['expressions'])
                self.assertIn(f'<{tag}>',delivered)
        with patch.dict(os.environ,{'JAMIE_EMOTIONAL_DIRECTION':'false'}):
            for mood in list(cases)+['amused']:
                self.assertEqual(grok._expressive_text(line,mood),line)

    def test_producer_reports_missing_delivery_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'hybrid_tts_report.json').write_text(json.dumps({'calls':[
                {'speaker':'JAMIE','provider':'grok','mood':'pushback','expressions':[]},
                {'speaker':'JAMIE','provider':'grok','mood':'warmth','expressions':['soft']}]}))
            result=write_review([],{'rows':[]},root)
            self.assertEqual(result['jamie_performance']['undirected_expressive_calls'],1)
            self.assertEqual(result['jamie_performance']['grok_expression_counts'],{'soft':1})
            self.assertIsNone(result['entertainment_rating'])
