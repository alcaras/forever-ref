#!/usr/bin/env python3
"""Split the Mobalytics WoW Forever guide harvest into one Markdown file per guide.

The harvest (cache/mobalytics/guides.json) is made in the browser: the site answers plain Python with 403,
so the page list comes from mobalytics.gg/wow-forever/sitemap.xml and each page is fetched same-origin
from a mobalytics.gg tab, then posted to tools/recv.py (python tools/recv.py 8790 cache/mobalytics).
The text is third-party content for local reference only: it stays in cache/ and is never published.
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'cache', 'mobalytics')
data = json.load(open(os.path.join(DIR, 'guides.json'), encoding='utf-8'))
index = []
for g in data['guides']:
    parts = g['slug'].split('/')
    kind = parts[2] if parts[0] == 'profile' else parts[0]   # profile/<author>/<kind>/<slug> are community guides
    author = parts[1] if parts[0] == 'profile' else ''
    m = re.search(r'\bBy\s+(\S[^\n]*)', g.get('text', ''))
    by = author or (m.group(1).strip() if m else '')
    path = os.path.join(DIR, ('community-' if author else '') + kind, parts[-1] + '.md')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"<!-- {g['url']} (harvested {data['harvested'][:10]}) -->\n\n{g.get('text', '')}\n")
    index.append((kind, g['title'].strip(), by, os.path.relpath(path, DIR).replace('\\', '/'), g['url']))
index.sort()
with open(os.path.join(DIR, 'INDEX.md'), 'w', encoding='utf-8') as f:
    f.write(f"# Mobalytics WoW Forever guides ({len(index)}, harvested {data['harvested'][:10]})\n\nLocal reference copy; not for publishing.\n")
    last = None
    for kind, title, by, rel, url in index:
        if kind != last:
            f.write(f'\n## {kind}\n\n')
            last = kind
        f.write(f'- [{title}]({rel}){" — " + by if by else ""} · <{url}>\n')
print(len(index), 'guides ->', DIR)
