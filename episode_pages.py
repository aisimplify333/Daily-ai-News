"""Build indexable episode pages from published RSS, without model/TTS calls."""
from html import escape
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SITE = 'https://aisimplify333.github.io/Daily-ai-News'
SPOTIFY = 'https://open.spotify.com/show/5awh0CJZ0qm6l2d69FWD2n'


def build(root=Path('.')):
    root = Path(root)
    channel = ET.parse(root/'feed.xml').getroot().find('channel')
    links = []
    for item in channel.findall('item'):
        enclosure = item.find('enclosure')
        if enclosure is None:
            continue
        audio = enclosure.get('url', '')
        match = re.search(r'/podcast_(\d{4}-\d{2}-\d{2})\.mp3$', audio)
        if not match or not audio.startswith(SITE + '/'):
            continue
        date = match[1]
        title = item.findtext('title') or 'The AI Edge'
        description = item.findtext('description') or ''
        target = root/'episodes'/date
        target.mkdir(parents=True, exist_ok=True)
        canonical = f'{SITE}/episodes/{date}/'
        tx = root/'episode_audio'/f'podcast_{date}.txt'
        transcript = tx.read_text(encoding='utf-8') if tx.exists() else ''
        schema = json.dumps({'@context':'https://schema.org', '@type':'PodcastEpisode',
            'name':title, 'url':canonical, 'datePublished':date,
            'description':description.split('\n\n')[0], 'associatedMedia':{
                '@type':'AudioObject', 'contentUrl':audio, 'encodingFormat':'audio/mpeg'},
            'partOfSeries':{'@type':'PodcastSeries', 'name':'The AI Edge', 'url':SITE+'/listen/'}}, ensure_ascii=False).replace('<', '\\u003c')
        page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} | The AI Edge</title><link rel="canonical" href="{canonical}">
<meta name="description" content="{escape(description.split(chr(10))[0][:220], quote=True)}">
<meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/assets/cover_trio_master.png">
<script type="application/ld+json">{schema}</script>
<style>body{{max-width:850px;margin:40px auto;padding:24px;background:#101921;color:#f4f1e8;font:18px/1.65 system-ui}}a{{color:#b4ee86}}h1{{line-height:1.2}}audio{{width:100%}}.copy{{white-space:pre-wrap;overflow-wrap:anywhere}}details{{margin-top:32px}}nav{{display:flex;gap:24px;flex-wrap:wrap}}</style></head><body>
<nav><a href="{SITE}/listen/">The AI Edge</a><a href="../">All episodes</a><a href="{SPOTIFY}">Follow on Spotify</a></nav>
<main><p>{date} · AI news and analysis</p><h1>{escape(title)}</h1>
<audio controls preload="none" src="{escape(audio, quote=True)}"></audio>
<div class="copy">{escape(description)}</div>
<p>Our sponsor: <a href="https://theledgr.io">The Ledger</a></p>
<details><summary>Read transcript</summary><div class="copy">{escape(transcript) if transcript else 'Transcript not available for this archive entry.'}</div></details>
</main></body></html>'''
        (target/'index.html').write_text(page, encoding='utf-8')
        links.append((date,title,canonical))
    directory = root/'episodes';directory.mkdir(exist_ok=True)
    rows = ''.join(f'<li>{d}: <a href="{u}">{escape(t)}</a></li>' for d,t,u in links)
    (directory/'index.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>The AI Edge episode archive</title><body><a href="{SITE}/listen/">The AI Edge</a><h1>Episode archive</h1><ul>{rows}</ul></body></html>',encoding='utf-8')
    sitemap = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for url in [SITE+'/listen/',SITE+'/episodes/']+[u for _,_,u in links]:
        ET.SubElement(ET.SubElement(sitemap,'url'),'loc').text=url
    ET.ElementTree(sitemap).write(root/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    print(f'Built {len(links)} episode pages from published RSS; no paid calls.')
    return links


if __name__ == '__main__':
    build()
