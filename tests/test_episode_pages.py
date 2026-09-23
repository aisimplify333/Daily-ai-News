import tempfile
from pathlib import Path
import unittest
from episode_pages import build, SITE


class EpisodePagesTests(unittest.TestCase):
    def test_public_feed_drives_pages_with_escaped_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'episode_audio').mkdir()
            (root/'episode_audio/podcast_2026-09-22.txt').write_text('ALEX: <script>never execute</script>')
            (root/'feed.xml').write_text(f'<rss><channel><item><title>AI &amp; You</title><description>Useful facts.</description><enclosure url="{SITE}/episode_audio/podcast_2026-09-22.mp3"/></item></channel></rss>')
            self.assertEqual(len(build(root)),1)
            page=(root/'episodes/2026-09-22/index.html').read_text()
            self.assertIn('&lt;script&gt;',page)
            self.assertIn('PodcastEpisode',page)
            self.assertTrue((root/'sitemap.xml').exists())
