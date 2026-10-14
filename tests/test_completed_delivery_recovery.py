import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from recover_completed_episode import restore

class CompletedDeliveryRecoveryTests(unittest.TestCase):
    def test_restores_exact_master_preserves_archive_and_refuses_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            source, root = Path(temp)/'source', Path(temp)/'root'
            source.mkdir(); root.mkdir()
            audio = b'ID3-completed-master'
            (source/'podcast_2026-10-13.mp3').write_bytes(audio)
            (source/'feed.xml').write_text('<rss><channel><item><enclosure url="https://example.com/podcast_2026-10-13.mp3"/></item></channel></rss>')
            (root/'feed.xml').write_text('<rss><channel><title>Keep metadata</title><item><title>Keep archive</title></item></channel></rss>')
            for name, field in [('final_acceptance_report.json','pass'),('grounded_fact_check.json','pass'),('production_delivery_report.json','passed')]:
                (source/name).write_text(json.dumps({field:True}))
            with self.assertRaisesRegex(ValueError, 'hash'):
                restore(source,'2026-10-13','wrong',root)
            digest=hashlib.sha256(audio).hexdigest()
            restore(source,'2026-10-13',digest,root)
            self.assertEqual((root/'episode_audio/podcast_2026-10-13.mp3').read_bytes(),audio)
            self.assertEqual(len(ET.parse(root/'feed.xml').findall('./channel/item')),2)
            self.assertIn('Keep archive',(root/'feed.xml').read_text())
            with self.assertRaisesRegex(ValueError,'already exists'):
                restore(source,'2026-10-13',digest,root)

    def test_generated_cache_does_not_break_sparse_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def git(*args,check=True):
                return subprocess.run(['git','-C',temp,*args],check=check,capture_output=True,text=True)
            git('init','-q');git('config','user.name','test');git('config','user.email','test@example.test')
            (root/'episode_audio').mkdir();(root/'.tts_cache').mkdir()
            (root/'episode_audio/old.mp3').write_text('old');(root/'main.py').write_text('old')
            (root/'.tts_cache/old.mp3').write_text('cache')
            git('add','.');git('commit','-qm','initial')
            git('sparse-checkout','set','--no-cone','/*','!/episode_audio/*.mp3','!/.tts_cache/','/episode_audio/today.mp3')
            (root/'.tts_cache').mkdir(exist_ok=True);(root/'.tts_cache/new.mp3').write_text('new cache')
            (root/'episode_audio').mkdir(exist_ok=True);(root/'episode_audio/today.mp3').write_text('master')
            (root/'episode_audio/show_trailer_candidate_today.mp3').write_text('candidate')
            result=git('add','--sparse','--','.',':(exclude).tts_cache',':(exclude)_voice_recovery',':(exclude)_run_artifacts',check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            staged=git('diff','--cached','--name-status').stdout
            self.assertIn('A\tepisode_audio/today.mp3',staged)
            self.assertIn('A\tepisode_audio/show_trailer_candidate_today.mp3',staged)
            self.assertNotIn('.tts_cache',staged)
            self.assertNotIn('old.mp3',staged)

if __name__ == '__main__':
    unittest.main()
