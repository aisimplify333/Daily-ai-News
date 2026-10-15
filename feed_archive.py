"""Keep published RSS entries when sparse checkout omits their audio files."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse


def preserve_archive(previous, path='feed.xml', keep=60):
    tree=ET.parse(path);channel=tree.getroot().find('channel')
    old=ET.fromstring(previous).find('channel')
    if channel is None or old is None:
        raise ValueError('Feed channel missing')
    items={}
    for source in (old,channel):
        for item in source.findall('item'):
            enclosure=item.find('enclosure')
            match=re.search(r'/podcast_(\d{4}-\d{2}-\d{2})\.mp3$',urlparse(enclosure.get('url','')).path) if enclosure is not None else None
            if match:items[match[1]]=item
    for item in list(channel.findall('item')):channel.remove(item)
    for date in sorted(items,reverse=True)[:max(1,int(keep))]:channel.append(items[date])
    tree.write(Path(path),encoding='utf-8',xml_declaration=True)
