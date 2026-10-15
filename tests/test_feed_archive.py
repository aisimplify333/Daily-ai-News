import xml.etree.ElementTree as ET
from feed_archive import preserve_archive


def feed(items):
    return '<rss><channel><title>Show</title>'+''.join(f'<item><title>{title}</title><enclosure url="https://example.com/podcast_{date}.mp3"/></item>' for date,title in items)+'</channel></rss>'


def test_sparse_generation_keeps_archive_without_local_media(tmp_path):
    path=tmp_path/'feed.xml';path.write_text(feed([('2026-10-14','New')]))
    preserve_archive(feed([('2026-10-13','Archive'),('2026-10-14','Stale')]),path)
    assert [x.findtext('title') for x in ET.parse(path).findall('./channel/item')]==['New','Archive']
    preserve_archive(feed([('2026-10-12','Older')]),path,keep=2)
    assert len(ET.parse(path).findall('./channel/item'))==2
