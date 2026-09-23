import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from distribution_package import package
from jamie_performance import emotional_intent, direct_delivery
from dialogue_editor import edit_dialogue

class PackageTests(unittest.TestCase):
    def test_chapters_are_idempotent_and_paid_enclosure_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'episode_audio').mkdir()
            (p/'feed.xml').write_text('<rss><channel><item><title>AI news?</title><guid>keep-me</guid><description>AI news. Useful hook.\n\nThis episode is brought to you by The Ledger.</description><enclosure url="https://example.com/podcast_2026-09-23.mp3" length="123" type="audio/mpeg"/></item></channel></rss>')
            (p/'episode_audio/podcast_2026-09-23.chapters.json').write_text(json.dumps({'chapters':[{'startTime':0,'title':'1. lead'},{'startTime':77.5,'title':'2. Story 1: News'}]}))
            package(p);first=(p/'feed.xml').read_text();package(p)
            self.assertEqual(first,(p/'feed.xml').read_text())
            item=ET.fromstring(first).find('channel/item')
            self.assertEqual(item.findtext('guid'),'keep-me')
            self.assertEqual(item.find('enclosure').get('length'),'123')
            desc=item.findtext('description');self.assertIn('01:17 Story 1: News',desc)
            self.assertLess(desc.index('Chapters:'),desc.index('This episode'))
            self.assertTrue(desc.startswith('Useful hook.'))

    def test_real_episode_reactions_are_directed_without_touching_quotes(self):
        samples=[("The thing that genuinely gets me about this launch is the distribution.",'curiosity'),("If this is real, it's genuinely extraordinary.",'delight'),('Thanks for spending the morning with us.','warmth')]
        for line,mood in samples:
            self.assertEqual(emotional_intent(line),mood)
            self.assertIn('<',direct_delivery(line,mood))
        self.assertIsNone(emotional_intent('The company calls its product extraordinary.'))

    def test_small_runtime_edit_can_reach_existing_repair(self):
        original='ALEX: 12 '+ 'word '*100
        candidate='ALEX: 12 '+ 'word '*96
        current={'failed':['runtime_word_band'],'metrics':{'words':102},'distance':50}
        revised={'failed':['runtime_word_band'],'metrics':{'words':98},'distance':54}
        result=edit_dialogue(original,current,lambda:candidate,lambda x:x,lambda x:revised,lambda x:x['distance'],allow_runtime_repair=True)
        self.assertTrue(result[2]['accepted'])
        self.assertIn('repair_pending',result[2]['reason'])
        bad=dict(revised,failed=['missing_music'])
        self.assertFalse(edit_dialogue(original,current,lambda:candidate,lambda x:x,lambda x:bad,lambda x:x['distance'],allow_runtime_repair=True)[2]['accepted'])
