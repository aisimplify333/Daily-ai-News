"""Build repeatable discovery copy from published assets; no paid calls or outreach."""
import html
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

SITE = 'https://aisimplify333.github.io/Daily-ai-News'


def chapter_lines(chapters):
    lines = []
    for row in chapters:
        seconds = max(0, int(float(row['startTime'])))
        label = re.sub(r'^\d+\.\s*', '', row['title'])
        if seconds == 0:
            label = 'Cold open and cast introduction'
        lines.append(f'{seconds//60:02d}:{seconds%60:02d} {label}')
    return lines


def package(root=Path('.')):
    root = Path(root)
    feed = root/'feed.xml'
    source = feed.read_text(encoding='utf-8')
    packages = []
    def update(match):
        block = match.group()
        # Items use channel-level namespace declarations. Find only local fields.
        enclosure = re.search(r'<enclosure\b[^>]*url=["\']([^"\']+)', block)
        date = re.search(r'podcast_(\d{4}-\d{2}-\d{2})\.mp3', enclosure[1]) if enclosure else None
        if not date:
            return block
        date = date[1]
        cp = root/'episode_audio'/f'podcast_{date}.chapters.json'
        if not cp.exists():
            return block
        chapters = chapter_lines(json.loads(cp.read_text())['chapters'])
        title_match = re.search(r'<title>(.*?)</title>', block, re.S)
        title = html.unescape(title_match[1]) if title_match else 'The AI Edge'
        dm = re.search(r'<description>(.*?)</description>', block, re.S)
        if not dm:
            return block
        raw = dm[1]
        desc = raw[9:-3] if raw.startswith('<![CDATA[') else html.unescape(raw)
        desc = re.sub(r'\n\nChapters:\n.*?(?=\n\n|$)', '', desc, flags=re.S)
        # Keep the sponsor last, and avoid repeating the title as the hook.
        if desc.startswith(title.rstrip('?') + '.'):
            desc = desc[len(title.rstrip('?') + '.'):].lstrip()
        sponsor = re.search(r'\n\n(?:This episode is brought|Today.s episode is brought)', desc)
        point = sponsor.start() if sponsor else len(desc)
        desc = desc[:point].rstrip() + '\n\nChapters:\n' + '\n'.join(chapters) + desc[point:]
        block = block[:dm.start(1)] + html.escape(desc, quote=False) + block[dm.end(1):]
        # Keep an existing content:encoded description in sync when present.
        block = re.sub(r'(<content:encoded>).*?(</content:encoded>)', lambda m:m[1]+html.escape(desc,quote=False)+m[2],block,flags=re.S)
        art = {}
        if not packages:
            try:
                from discovery_art import create_art
                art = create_art(title, date, root)
            except (ImportError, OSError) as exc:
                art = {'status': 'not_generated', 'reason': type(exc).__name__}
        art_file = root/'episode_art'/f'{date}-cover.png'
        if art_file.exists() and 'xmlns:itunes=' in source:
            tag = f'<itunes:image href="{SITE}/episode_art/{date}-cover.png" />'
            if re.search(r'<itunes:image\b[^>]*/>', block):
                block = re.sub(r'<itunes:image\b[^>]*/>', tag, block)
            else:
                block = block.replace('</item>', tag+'</item>')
        target = root/'distribution'/date
        target.mkdir(parents=True, exist_ok=True)
        question = re.search(r'Listener question:\s*([^\n]+)', desc)
        payload = {'date':date, 'title':title, 'description':desc, 'episode_url':f'{SITE}/episodes/{date}/',
            'artwork':art, 'chapters':chapters, 'community_prompt':question[1] if question else None,
            'share_copy':f'{title}\nAlex, Jamie and Rufus unpack what changed, who wins and what you do next.\n{SITE}/episodes/{date}/?utm_source=share&utm_medium=episode',
            'clip_file':f'episode_audio/clip_{date}.mp4' if (root/'episode_audio'/f'clip_{date}.mp4').exists() else None,
            'spotify_native_status':{'clip_upload':'unverified','pinned_question':'unverified','best_place_to_start':'unverified'},
            'analytics':{'starts':None,'completion_rate':None,'follows':None,'shares':None},
            'publication':'RSS metadata only; this file does not post messages or configure Spotify-native features'}
        (target/'package.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        sidecar=root/'episode_audio'/f'podcast_{date}.json'
        if sidecar.exists():
            metadata=json.loads(sidecar.read_text()); metadata['description']=desc
            sidecar.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
        packages.append(date)
        return block
    result = re.sub(r'<item\b[^>]*>.*?</item>',update,source,flags=re.S)
    ET.fromstring(result)  # Validate before touching the published feed.
    feed.write_text(result,encoding='utf-8')
    return packages


if __name__ == '__main__':
    print('Distribution packages:', ', '.join(package()))
